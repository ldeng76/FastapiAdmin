"""ETL-2 脱敏落库引擎 — Parquet → lnrs_anon_* (PostgreSQL)。

设计要点：
- DuckDB 读 parquet（独立连接，避免与查询 API 的锁竞争）
- **批量**写入：patient 先预计算 anon_id → 单次查现存 → 批量发号 + 批量 INSERT/UPDATE
  exam/report_text 用 pg_insert().values(batch).on_conflict_do_update() 批量幂等
- patient 三态机：活→复用 / 软删→复活 / 新→发号（ADR-0006 Rev 2026-07-19）
- 自由文本原样入 body_clean（本轮不清洗，clean_method='regex_only', review_status='pending'）
- 每个脱敏字段批量写 phi_audit 满足合规回放

来源 → 落点（已与用户确认的边界）：
- {center}/patient.parquet            → lnrs_anon_patient（每行 1 病人）
- {center}/nodule_imaging.parquet     → lnrs_anon_exam(CT) + lnrs_anon_report_text
- {center}/pathology_specimen.parquet → lnrs_anon_exam(Pathology) + lnrs_anon_report_text
- {center}/genetic_test.parquet      → lnrs_anon_exam(Genetic) + lnrs_anon_exam_detail
- {center}/ihc_result.parquet        → lnrs_anon_exam(IHC) + lnrs_anon_exam_detail
- {center}/surgery_record.parquet    → lnrs_anon_visit + lnrs_anon_surgery
- {center}/visit_record.parquet       → 跳过（visit 桥本轮未启用）

事务模型：调用方控制 begin/commit；本引擎只 execute 不 commit。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

import duckdb
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import log

from .anon_model import (
    AnonClinicalDocumentModel,
    AnonDiagnosisModel,
    AnonExamDetailModel,
    AnonExamModel,
    AnonLabResultModel,
    AnonMedicalHistoryModel,
    AnonOrderModel,
    AnonPatientModel,
    AnonPhiAuditModel,
    AnonReportTextModel,
    AnonSurgeryModel,
    AnonVitalObservationModel,
    AnonVisitDetailModel,
    AnonVisitModel,
)
from .anonymize import (
    CLEAN_METHOD_REGEX_ONLY,
    birth_date_from,
    compute_anon_exam_id,
    compute_anon_id,
    compute_anon_visit_id,
    hash_for_audit,
    source_diagnosis_hash,
    source_document_hash,
    source_exam_hash,
    source_history_hash,
    source_lab_hash,
    source_observation_hash,
    source_order_hash,
    source_surgery_hash,
    source_visit_hash,
    truncate_body,
)
from .enum_normalization import (
    normalize_abo_blood_type_with_status,
    normalize_ethnicity_with_status,
    normalize_rh_blood_type_with_status,
    normalize_sex_with_status,
    normalize_smoking_status_with_status,
)

# 未匹配字典字段的 dict_type 名（用于 _flush_unmatched 反查 dict_type_id）
_ENUM_DICT_TYPE_BY_FIELD = {
    "sex": "med_sex",
    "ethnicity": "med_ethnicity",
    "smoking_status": "med_smoking_status",
    "abo_blood_type": "med_blood_type_abo",
    "rh_blood_type": "med_blood_type_rh",
}

# 来源表名校验：仅允许字母/数字/下划线（防 path traversal）
_SRC_TABLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# 批量大小
BATCH_SIZE = 1000

# Sub-transaction 阈值：每累计此行数后 commit 一次，缩短长事务暴露时间（减少
# ConnectionDoesNotExistError / WAL 撑爆风险）。可通过环境变量
# LNRS_ETL_SUB_TX_ROWS 调小（A/B 测试用）。0 = 禁用 sub-tx，单事务直到结束。
SUB_TX_ROWS = int(os.environ.get("LNRS_ETL_SUB_TX_ROWS", "1000000"))

# COPY 触发阈值：当一次 upsert 行数 ≥ 此值时改走 COPY+temp-table 路径
# （asyncpg copy_records_to_table 比 executemany 快 10-50×）。
# 0 = 禁用 COPY 路径，全部走 executemany。环境变量 LNRS_ETL_COPY_THRESHOLD 覆盖。
COPY_THRESHOLD = int(os.environ.get("LNRS_ETL_COPY_THRESHOLD", "50000"))

# 临时表名后缀（每次调用拼接 uuid 避免同 session 内冲突）
_COPY_TMP_SUFFIX = "_etl_copy"


# --------------------------------------------------------------------------- #
# Parquet 读取
# --------------------------------------------------------------------------- #


def _read_parquet_rows(parquet_path: Path) -> tuple[list[str], list[tuple]]:
    """用独立 DuckDB 连接读 parquet，返回 (列名, 行)。"""
    con = duckdb.connect(database=":memory:")
    try:
        cur = con.execute("SELECT * FROM read_parquet(?)", [parquet_path.as_posix()])
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        return cols, rows
    finally:
        con.close()


async def _read_parquet_async(parquet_path: Path) -> tuple[list[str], list[tuple]]:
    """异步包装：阻塞 duckdb 读放到线程池。"""
    return await asyncio.to_thread(_read_parquet_rows, parquet_path)


def _row_to_dict(cols: list[str], row: tuple) -> dict[str, Any]:
    return {col: val for col, val in zip(cols, row)}

# asyncpg 单次查询参数上限 32767；10M-row 级表（如检验/护理）的 visit 预读
# 若一次 IN 全表 anon_visit_id 会爆栈，故统一改分块查询
_IN_CHUNK_SIZE = 10_000


async def _in_lookup_chunked(
    db: AsyncSession,
    build: Callable[[list[str]], Any],
    ids: list[str],
) -> list:
    """对 `WHERE col IN (...)` 查询按 _IN_CHUNK_SIZE 分块执行并合并结果。

    build(chunk) 返回该次 SELECT 的 Statement；返回拼接后的 Row 列表。
    """
    results: list = []
    for i in range(0, len(ids), _IN_CHUNK_SIZE):
        chunk = ids[i : i + _IN_CHUNK_SIZE]
        results.extend((await db.execute(build(chunk))).fetchall())
    return results
async def _copy_then_merge(
    db: AsyncSession,
    *,
    target_table_name: str,
    rows: list[dict[str, Any]],
    constraint: str,
    update_set: dict[str, Any],
    column_order: list[str],
) -> int:
    """用 COPY+temp table 路径批量 upsert 行到目标表（省医扩展性能优化）。

    工作流（单事务内）：
      1. CREATE TEMP TABLE tmp_<uuid> ON COMMIT DROP
      2. asyncpg copy_records_to_table → 流式灌入 tmp
      3. INSERT INTO target SELECT ... FROM tmp ON CONFLICT ON CONSTRAINT DO UPDATE
      4. （事务结束自动 DROP，ON COMMIT DROP）

    性能：COPY 比 executemany(BATCH_SIZE=1000) 快 10-50×（省医 nursing 13.8M 行
    实测 95 min → 预估 ~5-15 min）。

    参数：
      target_table_name: 目标表名（SQLAlchemy Table.name，schema 已包含）
      rows: 待 upsert 行（dict，key 在 column_order 中）
      constraint: ON CONFLICT UNIQUE 约束名
      update_set: DO UPDATE SET 字段名列表（用 EXCLUDED 自动引用）
      column_order: 行转 tuple 列顺序（必须与目标表 INSERT 列一致）
    """
    if not rows:
        return 0
    raw = await (await db.connection()).get_raw_connection()
    inner = raw.driver_connection  # type: ignore[attr-defined]

    tmp_name = f"tmp_anon_{uuid.uuid4().hex[:12]}"
    try:
        # 用 LIKE target INCLUDING DEFAULTS 克隆结构（保留 DEFAULT 与 NOT NULL）
        # ON COMMIT DROP 在 asyncpg+SQLAlchemy 组合下偶尔失败，
        # 改用 finally 显式 DROP（保证清理；崩溃时 PG 自动收 session-level temp）
        await inner.execute(
            f"CREATE TEMP TABLE {tmp_name} (LIKE {target_table_name} INCLUDING DEFAULTS)"
        )
        records = [tuple(r.get(c) for c in column_order) for r in rows]
        await inner.copy_records_to_table(tmp_name, records=records, columns=column_order)
        set_clause = ", ".join(f'"{k}" = EXCLUDED."{k}"' for k in update_set.keys())
        col_list = ", ".join(f'"{c}"' for c in column_order)
        sql = (
            f'INSERT INTO {target_table_name} ({col_list}) '
            f'SELECT {col_list} FROM {tmp_name} '
            f'ON CONFLICT ON CONSTRAINT {constraint} DO UPDATE SET {set_clause}'
        )
        await db.execute(text(sql))
        return len(rows)
    finally:
        try:
            await inner.execute(f"DROP TABLE IF EXISTS {tmp_name}")
        except Exception:
            pass

async def _maybe_commit(
    db: AsyncSession,
    *,
    rows_done: int,
    label: str,
) -> None:
    """Sub-tx commit 阈值检查：在累计写入行数跨过 SUB_TX_ROWS 整数倍时 commit 一次。

    用法：循环内每写完 BATCH_SIZE 后调用：
      await _maybe_commit(db, rows_done=i + len(batch), label='lab_result')

    行为：
      - rows_done > 0 且 rows_done % SUB_TX_ROWS == 0：commit 一次
      - SUB_TX_ROWS <= 0：禁用 sub-tx，回退原单事务行为
    """
    if SUB_TX_ROWS <= 0:
        return
    if rows_done > 0 and rows_done % SUB_TX_ROWS == 0:
        await db.commit()
        log.info(f"ETL2: {label} sub-tx commit @ {rows_done:,} 行")


def _get_nested(rd: dict[str, Any], path: str) -> Any:
    """按点号路径取嵌套值（如 'exam_detail.findings'）。

    支持省医 imaging_report 等表的正文/详情列在 struct 子字段的情况：
    body_fields=["exam_detail.findings"] 时取 rd['exam_detail']['findings']。
    无点号时退化为普通 rd.get(path)。
    """
    if "." not in path:
        return rd.get(path)
    cur: Any = rd
    for seg in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(seg)
        else:
            return None
        if cur is None:
            return None
    return cur


async def _maybe_commit(
    db: AsyncSession,
    *,
    rows_done: int,
    label: str,
) -> None:
    """Sub-tx commit 阈值检查：在累计写入行数跨过 SUB_TX_ROWS 整数倍时 commit 一次。

    用法：循环内每写完 BATCH_SIZE 后调用：
      await _maybe_commit(db, rows_done=i + len(batch), label='lab_result')

    行为：
      - rows_done > 0 且 rows_done % SUB_TX_ROWS == 0：commit 一次
      - SUB_TX_ROWS <= 0：禁用 sub-tx，回退原单事务行为
    """
    if SUB_TX_ROWS <= 0:
        return
    if rows_done > 0 and rows_done % SUB_TX_ROWS == 0:
        await db.commit()
        log.info(f"ETL2: {label} sub-tx commit @ {rows_done:,} 行")



def _clean_str(val: Any) -> str | None:
    """清洗字符串列：None/空串 → None，其余 strip。供 patient 稳定属性提取用。"""
    if val is None:
        return None
    s = str(val).strip()
    return s or None


def _extract_bmi(demographics: Any) -> float | None:
    """从 demographics struct 提取 bmi。"""
    if isinstance(demographics, dict):
        bmi = demographics.get("bmi")
        if bmi is not None:
            try:
                return float(bmi)
            except (TypeError, ValueError):
                return None
    return None


def _extract_patient_meta(rd: dict[str, Any]) -> dict[str, Any] | None:
    """构造 patient_meta JSONB：medical_history（病史终身属性）兜底。

    珠江 patient.parquet 的 medical_history 含家族史/既往肿瘤/合并症/发现途径/吸烟包年，
    这些是患者终身属性，原样整体序列化进 patient_meta。
    返回 None 表示无病史数据（JSONB 列存 NULL）。
    """
    mh = rd.get("medical_history")
    if isinstance(mh, dict) and mh:
        return mh
    return None


def _build_detail_json(rd: dict[str, Any], detail_fields: list[str]) -> dict[str, Any]:
    """从行字典提取指定字段构造 exam_detail.detail_json。

    detail_fields 是 parquet 里的 struct/scalar 列名（如 driver_mutations、staging）。
    缺失或 None 的字段不放入结果，保持 JSONB 紧凑。
    """
    detail: dict[str, Any] = {}
    for f in detail_fields:
        v = rd.get(f)
        if v is not None:
            detail[f] = v
    # date/datetime 转 ISO 字符串，使 JSONB 可序列化（省医 detail struct 含日期字段）
    return _json_safe(detail)


# 从 nodule_no 等字段解析数字序号：'n1'→1, 'n2'→2, '3'→3, None/无数字→1
_ORDINAL_DIGIT_RE = re.compile(r"(\d+)")


def _parse_ordinal(val: Any) -> int:
    """从 ordinal_field 值解析 detail_ordinal。

    - 'n1' / 'N2' / '结节3' → 提取数字部分
    - 纯数字 '3' / 3 → 直接转 int
    - None / 空值 / 无数字 → 1（默认单实例）
    """
    if val is None:
        return 1
    s = str(val).strip()
    if not s:
        return 1
    m = _ORDINAL_DIGIT_RE.search(s)
    return int(m.group(1)) if m else 1


# 省医数据用 1900-01-01 作为时间占位哨兵（lab.collection_time / order.order_stop_time）
# 导入时需视为 NULL
_SENTINEL_DATES = {date(1900, 1, 1)}


def _clean_date(raw: Any) -> date | None:
    """清洗日期列：解析 + 剔除省医 1900-01-01 占位哨兵。

    复用 birth_date_from 的多格式解析能力，额外把 1900-01-01 当 NULL 处理。
    """
    if raw is None:
        return None
    d = birth_date_from(raw)
    if d is None:
        return None
    return None if d in _SENTINEL_DATES else d


def _json_safe(obj: Any) -> Any:
    """递归把 dict/list 中的 date/datetime 转 ISO 字符串，使其可 JSON 序列化入 JSONB。

    parquet 读出的 struct 含 date 类型（如 admission_time），直接塞 JSONB 会抛
    "date is not JSON serializable"。本函数在构造 *_detail_json 时统一过一遍。
    """
    from datetime import date as _date, datetime as _dt
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, _dt):
        return obj.isoformat()
    if isinstance(obj, _date):
        return obj.isoformat()
    return obj


# --------------------------------------------------------------------------- #
# patient 批量三态机
# --------------------------------------------------------------------------- #


async def _batch_upsert_patients(
    db: AsyncSession,
    *,
    center_code: str,
    patient_records: list[dict[str, Any]],
    batch_id: str,
    is_placeholder: bool = False,
) -> dict[str, str]:
    """批量处理病人，返回 {anon_id: patient_id} 映射。

    patient_records: [{"local_id", "anon_id", "sex", "birth_date", "ethnicity", "smoking_status", "abo_blood_type", "rh_blood_type"}]
    三态机（ADR-0006 Rev 2026-07-19 §1-4）：
    - 活行：UPDATE last_seen + sex/birth_date
    - 软删：复活（清空 deleted_*）
    - 新：nextval 发号 + INSERT

    is_placeholder: True 表示这是 exam/surgery 导入时为确保 FK 存在而创建的占位
    记录（字段值未知，sex='0'/birth_date=None）。此时 ON CONFLICT 只刷新
    last_seen_batch_id + 复活软删，**不覆盖**已有 patient 的人口学/稳定属性字段
    （避免占位值冲掉 patient.parquet 先写入的真实数据）。
    """
    if not patient_records:
        return {}

    # 去重 by anon_id（zhujiang 有脏数据 20 个重复 patient_id；保留最后一条）
    by_anon: dict[str, dict[str, Any]] = {}
    for r in patient_records:
        by_anon[r["anon_id"]] = r  # 同 anon_id 后者覆盖前者
    unique = list(by_anon.values())
    anon_ids = [r["anon_id"] for r in unique]

    # 1. 分块查询现存 anon_id（asyncpg 单语句参数上限 32767，按 5000 一批）
    existing_map: dict[str, str] = {}  # anon_id → patient_id（含活行与软删行）
    for i in range(0, len(anon_ids), 5000):
        chunk = anon_ids[i : i + 5000]
        stmt = select(
            AnonPatientModel.anon_id,
            AnonPatientModel.patient_id,
        ).where(
            AnonPatientModel.center_code == center_code,
            AnonPatientModel.anon_id.in_(chunk),
        )
        for row in (await db.execute(stmt)).fetchall():
            existing_map[row.anon_id] = row.patient_id

    # 2. 分类：已存在的复用其 patient_id；新病人待发号
    result: dict[str, str] = {}
    to_insert: list[dict[str, Any]] = []
    for r in unique:
        anon_id = r["anon_id"]
        if anon_id in existing_map:
            result[anon_id] = existing_map[anon_id]
        else:
            to_insert.append(r)

    # 3. 为新病人批量发号（一次性 generate_series + nextval）
    n_new = len(to_insert)
    if n_new:
        # 一次性取 n_new 个序号：SELECT nextval FROM generate_series(1, n)
        seq_rows = (
            await db.execute(
                text("SELECT nextval('lnrs.lnrs_anon_patient_seq') FROM generate_series(1, :n)"),
                {"n": n_new},
            )
        ).fetchall()
        seqs = [r[0] for r in seq_rows]
        for r, seq in zip(to_insert, seqs):
            result[r["anon_id"]] = f"PT_{seq:08d}"

    # 4. 构造 upsert 行：每条 patient 记录都生成一行（新病人带新 patient_id，
    #    已存在的带其原 patient_id），统一用 ON CONFLICT DO UPDATE 处理。
    #    冲突键：(center_code, anon_id)（DDL UNIQUE 约束 lnrs_anon_uq_patient_center）
    #    - 新行：INSERT
    #    - 活行：UPDATE last_seen + 人口学
    #    - 软删行：UPDATE 清空 deleted_* + last_seen + 人口学（复活）
    #    created_batch_id 不在 SET 里，活行/软删行保留原值。
    upsert_rows = []
    for r in unique:
        upsert_rows.append(
            {
                "patient_id": result[r["anon_id"]],
                "anon_id": r["anon_id"],
                "center_code": center_code,
                "birth_date": r["birth_date"],
                "sex": r["sex"],
                "ethnicity": r.get("ethnicity"),
                "smoking_status": r.get("smoking_status"),
                "abo_blood_type": r.get("abo_blood_type"),
                "rh_blood_type": r.get("rh_blood_type"),
                # 医疗宽表直入扩展：患者非枚举稳定属性
                "native_place": r.get("native_place"),
                "first_nodule_date": r.get("first_nodule_date"),
                "bmi": r.get("bmi"),
                "patient_meta": r.get("patient_meta"),
                "created_batch_id": batch_id,
                "last_seen_batch_id": batch_id,
                "deleted_at": None,
                "deleted_reason": None,
                "deleted_batch_id": None,
            }
        )

    # 批量 ON CONFLICT upsert（每批 BATCH_SIZE 行）
    for i in range(0, len(upsert_rows), BATCH_SIZE):
        batch = upsert_rows[i : i + BATCH_SIZE]
        stmt = pg_insert(AnonPatientModel.__table__).values(batch)
        if is_placeholder:
            # 占位记录：只刷新 last_seen + 复活软删行，不覆盖人口学/稳定属性
            stmt = stmt.on_conflict_do_update(
                constraint="lnrs_anon_uq_patient_center",
                set_={
                    "last_seen_batch_id": stmt.excluded.last_seen_batch_id,
                    "deleted_at": None,
                    "deleted_reason": None,
                    "deleted_batch_id": None,
                },
            )
        else:
            # 完整记录（patient.parquet）：刷新 last_seen + 全部人口学/稳定属性；复活软删
            stmt = stmt.on_conflict_do_update(
                constraint="lnrs_anon_uq_patient_center",
                set_={
                    "last_seen_batch_id": stmt.excluded.last_seen_batch_id,
                    "sex": stmt.excluded.sex,
                    "birth_date": stmt.excluded.birth_date,
                    "ethnicity": stmt.excluded.ethnicity,
                    "smoking_status": stmt.excluded.smoking_status,
                    "abo_blood_type": stmt.excluded.abo_blood_type,
                    "rh_blood_type": stmt.excluded.rh_blood_type,
                    "native_place": stmt.excluded.native_place,
                    "first_nodule_date": stmt.excluded.first_nodule_date,
                    "bmi": stmt.excluded.bmi,
                    "patient_meta": stmt.excluded.patient_meta,
                    "deleted_at": None,
                    "deleted_reason": None,
                    "deleted_batch_id": None,
                },
            )
        await db.execute(stmt)
        await _maybe_commit(db, rows_done=i + len(batch), label=f"patient:{center_code}")

    if n_new:
        log.info(
            f"ETL2: 病人 upsert center={center_code} 新增 {n_new} "
            f"(seq {seqs[0]}..{seqs[-1]}) 复用 {len(unique) - n_new}"
        )
    else:
        log.info(
            f"ETL2: 病人 upsert center={center_code} 全部 {len(unique)} 复用（幂等重跑）"
        )

    return result


# --------------------------------------------------------------------------- #
# exam + report_text 批量 upsert
# --------------------------------------------------------------------------- #


async def _batch_upsert_exams(
    db: AsyncSession,
    *,
    exam_rows: list[dict[str, Any]],
) -> None:
    """批量 upsert exam 行（每行含所有 anon_exam 列）。

    ON CONFLICT (center_code, source_exam_hash) DO UPDATE last_seen + exam_date。
    Rev 2026-07-24: 不再覆盖 exam_type（修 IHC 覆盖 Pathology bug）——
    exam_type 在首次入库后保持不变，后续相同 source_exam_hash 的不同
    exam_type（如 IHC 复用 Pathology 的 specimen_id）只刷新时间戳，不
    覆盖类型。patient_id 同理保留首值（占位与真实行一致）。
    """
    if not exam_rows:
        return
    for i in range(0, len(exam_rows), BATCH_SIZE):
        batch = exam_rows[i : i + BATCH_SIZE]
        stmt = pg_insert(AnonExamModel.__table__).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="lnrs_anon_uq_exam_source",
            set_={
                "last_seen_batch_id": stmt.excluded.last_seen_batch_id,
                "exam_date": stmt.excluded.exam_date,
            },
        )
        await db.execute(stmt)
        await _maybe_commit(db, rows_done=i + len(batch), label="exam")


async def _batch_upsert_report_text(
    db: AsyncSession,
    *,
    report_rows: list[dict[str, Any]],
) -> None:
    """批量 upsert report_text 行。

    PK=anon_exam_id，ON CONFLICT DO UPDATE body_clean。
    """
    if not report_rows:
        return
    for i in range(0, len(report_rows), BATCH_SIZE):
        batch = report_rows[i : i + BATCH_SIZE]
        stmt = pg_insert(AnonReportTextModel.__table__).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=[AnonReportTextModel.anon_exam_id],
            set_={
                "body_clean": stmt.excluded.body_clean,
                "clean_method": stmt.excluded.clean_method,
                "review_status": "pending",
            },
        )
        await db.execute(stmt)
        await _maybe_commit(db, rows_done=i + len(batch), label="report_text")


async def _batch_upsert_exam_detail(
    db: AsyncSession,
    *,
    detail_rows: list[dict[str, Any]],
) -> None:
    """批量 upsert exam_detail 行（JSONB 深结构，1:N）。

    Rev 2026-07-24: PK 改为 (anon_exam_id, detail_type, detail_ordinal)，
    ON CONFLICT DO UPDATE detail_json + created_batch_id（保留首值的
    detail_type/ordinal 不变，仅刷新 JSONB 内容）。
    """
    if not detail_rows:
        return
    for i in range(0, len(detail_rows), BATCH_SIZE):
        batch = detail_rows[i : i + BATCH_SIZE]
        stmt = pg_insert(AnonExamDetailModel.__table__).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="lnrs_anon_pk_exam_detail",
            set_={
                "detail_json": stmt.excluded.detail_json,
                "created_batch_id": stmt.excluded.created_batch_id,
            },
        )
        await db.execute(stmt)
        await _maybe_commit(db, rows_done=i + len(batch), label="exam_detail")

async def _batch_upsert_visits(
    db: AsyncSession,
    *,
    center_code: str,
    visit_records: list[dict[str, Any]],
    batch_id: str,
) -> dict[str, str]:
    """批量 upsert visit 行，返回 {anon_visit_id: 原 visit_id} 映射。

    visit_records: [{"visit_id", "anon_visit_id", "patient_id", "source_visit_hash"}]
    冲突键：(center_code, source_visit_hash)（DDL UNIQUE lnrs_anon_uq_visit_source）
    visit 无软删除机制，比 patient 简单：存在则刷新 last_seen，不存在则 INSERT。
    """
    if not visit_records:
        return {}

    # 去重 by source_visit_hash（同源多次出现，保留最后一条）
    by_hash: dict[str, dict[str, Any]] = {}
    for r in visit_records:
        by_hash[r["source_visit_hash"]] = r
    unique = list(by_hash.values())

    result: dict[str, str] = {}  # {anon_visit_id: 原 visit_id}
    upsert_rows: list[dict[str, Any]] = []
    for r in unique:
        anon_visit_id = r["anon_visit_id"]  # 确定性 HMAC，复用或新建都用同一个
        result[anon_visit_id] = r["visit_id"]
        upsert_rows.append(
            {
                "anon_visit_id": anon_visit_id,
                "patient_id": r["patient_id"],
                "center_code": center_code,
                "visit_ordinal": r["visit_id"],
                "source_visit_hash": r["source_visit_hash"],
                "created_batch_id": batch_id,
                "last_seen_batch_id": batch_id,
            }
        )

    for i in range(0, len(upsert_rows), BATCH_SIZE):
        batch = upsert_rows[i : i + BATCH_SIZE]
        stmt = pg_insert(AnonVisitModel.__table__).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="lnrs_anon_uq_visit_source",
            set_={
                "last_seen_batch_id": stmt.excluded.last_seen_batch_id,
                "patient_id": stmt.excluded.patient_id,
            },
        )
        await db.execute(stmt)
        await _maybe_commit(db, rows_done=i + len(batch), label=f"visit:{center_code}")

    log.info(f"ETL2: visit upsert center={center_code} 共 {len(unique)} 条")
    return result


async def _batch_upsert_surgeries(
    db: AsyncSession,
    *,
    surgery_rows: list[dict[str, Any]],
) -> None:
    """批量 upsert surgery 行。

    冲突键：(anon_visit_id, source_surgery_hash)（DDL UNIQUE lnrs_anon_uq_surgery）。
    """
    if not surgery_rows:
        return
    for i in range(0, len(surgery_rows), BATCH_SIZE):
        batch = surgery_rows[i : i + BATCH_SIZE]
        stmt = pg_insert(AnonSurgeryModel.__table__).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="lnrs_anon_uq_surgery",
            set_={
                "surgery_date": stmt.excluded.surgery_date,
                "procedure_name": stmt.excluded.procedure_name,
                "resection_scope": stmt.excluded.resection_scope,
                "surgical_approach": stmt.excluded.surgical_approach,
                "procedure_detail": stmt.excluded.procedure_detail,
            },
        )
        await db.execute(stmt)
        await _maybe_commit(db, rows_done=i + len(batch), label="surgery")


async def _batch_upsert_visit_details(
    db: AsyncSession,
    *,
    visit_detail_rows: list[dict[str, Any]],
) -> None:
    """批量 upsert visit_detail 行（省医扩展）。

    冲突键：(anon_visit_id)（DDL UNIQUE lnrs_anon_uq_visit_detail，visit 1:1）。
    """
    if not visit_detail_rows:
        return
    for i in range(0, len(visit_detail_rows), BATCH_SIZE):
        batch = visit_detail_rows[i : i + BATCH_SIZE]
        stmt = pg_insert(AnonVisitDetailModel.__table__).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="lnrs_anon_uq_visit_detail",
            set_={
                "visit_category": stmt.excluded.visit_category,
                "admission_time": stmt.excluded.admission_time,
                "discharge_date": stmt.excluded.discharge_date,
                "admission_dept": stmt.excluded.admission_dept,
                "discharge_dept": stmt.excluded.discharge_dept,
                "length_of_stay": stmt.excluded.length_of_stay,
                "payment_method": stmt.excluded.payment_method,
                "visit_age": stmt.excluded.visit_age,
                "visit_detail_json": stmt.excluded.visit_detail_json,
            },
        )
        await db.execute(stmt)
        await _maybe_commit(db, rows_done=i + len(batch), label="visit_detail")


async def _batch_upsert_lab_results(
    db: AsyncSession,
    *,
    lab_rows: list[dict[str, Any]],
) -> None:
    """批量 upsert lab_result 行（省医扩展）。

    冲突键：(anon_visit_id, source_lab_hash)（DDL UNIQUE lnrs_anon_uq_lab_result）。
    anon_visit_id 可空：NULL 不参与 UNIQUE 冲突，visit 缺失的行各自独立插入。

    行数 ≥ COPY_THRESHOLD 时改走 COPY+temp 表路径（asyncpg copy_records_to_table，
    速度比 executemany 1000 行一批快 10-50×；省医 11M lab_result 预期 25-45 min → 5-10 min）。
    """
    if COPY_THRESHOLD and len(lab_rows) >= COPY_THRESHOLD:
        # COPY 路径：排除 lab_result_id（bigserial DEFAULT）和 created_at（CURRENT_TIMESTAMP），
        # 让 PG 自动生成；同时 source_lab_hash 必填无 None。
        # asyncpg copy_records_to_table 不自动序列化 JSON/Decimal，
        # 需要预先 json.dumps(JSONB 列) 和 str(Decimal)。
        import json as _json
        from decimal import Decimal as _Dec
        for r in lab_rows:
            v = r.get("lab_detail_json")
            if isinstance(v, (dict, list)):
                r["lab_detail_json"] = _json.dumps(v, ensure_ascii=False)
            v = r.get("item_result_value")
            if isinstance(v, _Dec):
                r["item_result_value"] = str(v)
        cols = [
            "anon_visit_id", "patient_id", "center_code",
            "report_id", "test_name", "item_name", "item_result",
            "item_result_value", "item_unit", "collection_time",
            "lab_detail_json", "source_lab_hash", "created_batch_id",
        ]
        await _copy_then_merge(
            db,
            target_table_name="lnrs.lnrs_anon_lab_result",
            rows=lab_rows,
            constraint="lnrs_anon_uq_lab_result",
            update_set={
                "test_name": 1, "item_name": 1, "item_result": 1,
                "item_result_value": 1, "item_unit": 1,
                "collection_time": 1, "lab_detail_json": 1,
            },
            column_order=cols,
        )
        log.info(f"ETL2: lab_result COPY path {len(lab_rows):,} 行")
        return
        batch = lab_rows[i : i + BATCH_SIZE]
        stmt = pg_insert(AnonLabResultModel.__table__).values(batch)
        # NULL anon_visit_id 的行无冲突键，用 (anon_visit_id, source_lab_hash) 仅命中非空 visit 行
        stmt = stmt.on_conflict_do_update(
            constraint="lnrs_anon_uq_lab_result",
            set_={
                "test_name": stmt.excluded.test_name,
                "item_name": stmt.excluded.item_name,
                "item_result": stmt.excluded.item_result,
                "item_result_value": stmt.excluded.item_result_value,
                "item_unit": stmt.excluded.item_unit,
                "collection_time": stmt.excluded.collection_time,
                "lab_detail_json": stmt.excluded.lab_detail_json,
            },
        )
        await db.execute(stmt)
        await _maybe_commit(db, rows_done=i + len(batch), label="lab_result")


async def _batch_upsert_orders(
    db: AsyncSession,
    *,
    order_rows: list[dict[str, Any]],
) -> None:
    """批量 upsert order 行（省医扩展，drug + non_drug 合并）。

    冲突键：source_order_hash（DDL UNIQUE lnrs_anon_uq_order，单列）。
    anon_visit_id 可空：NULL 不参与 UNIQUE 冲突。
    """
    if not order_rows:
        return
    for i in range(0, len(order_rows), BATCH_SIZE):
        batch = order_rows[i : i + BATCH_SIZE]
        stmt = pg_insert(AnonOrderModel.__table__).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="lnrs_anon_uq_order",
            set_={
                "order_time": stmt.excluded.order_time,
                "order_source": stmt.excluded.order_source,
                "order_detail_json": stmt.excluded.order_detail_json,
            },
        )
        await db.execute(stmt)
        await _maybe_commit(db, rows_done=i + len(batch), label="order")

async def _write_phi_audit_batch(
    db: AsyncSession,
    *,
    batch_id: str,
    records: list[dict[str, Any]],
) -> None:
    """批量写 phi_audit。"""
    if not records:
        return
    rows = [
        {
            "batch_id": batch_id,
            "source_table": r["source_table"],
            "source_field": r["source_field"],
            "source_hash": r["source_hash"],
            "strategy": r["strategy"],
            "confidence": r.get("confidence", 1.0),
        }
        for r in records
    ]
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        await db.execute(AnonPhiAuditModel.__table__.insert().values(batch))
        await _maybe_commit(db, rows_done=i + len(batch), label="phi_audit")


# --------------------------------------------------------------------------- #
# hospital 解析 + 未匹配标签落库
# --------------------------------------------------------------------------- #


async def _resolve_hospital_id(db: AsyncSession, center_code: str) -> int:
    """从 med_hospital.code 反查 hospital_id，找不到抛错（不退化）。

    ETL 启动前必须确保 center_code 已在 med_hospital 注册（见 0008 SQL 种子）。
    找不到时抛 RuntimeError 而非返回 PLATFORM_TENANT_ID=1，避免误把数据挂到
    平台租户名下污染其它中心的映射缓存。
    """
    # 延迟导入避免循环依赖
    from app.plugin.module_medical.hospital.model import HospitalModel
    # 触发 HospitalModel 的 relationship 依赖类注册到 metadata：
    #   - tenant         → TenantModel
    #   - mapping_rules  → MappingRuleModel（同文件，已随 HospitalModel 注册）
    #   - dict_mappings  → DictMappingModel
    from app.api.v1.module_system.tenant.model import TenantModel  # noqa: F401
    from app.plugin.module_medical.dict_mapping.model import DictMappingModel  # noqa: F401

    stmt = select(HospitalModel.id).where(HospitalModel.code == center_code)
    result = (await db.execute(stmt)).scalar_one_or_none()
    if result is None:
        raise RuntimeError(
            f"ETL2: center_code={center_code!r} 未在 med_hospital 注册，"
            f"请先执行 0008-zhujiang-dict-seed.sql 或通过 Hospital API 创建"
        )
    return result


async def _flush_unmatched(
    db: AsyncSession,
    *,
    hospital_id: int,
    unmatched: list[dict[str, Any]],
) -> None:
    """把 ETL 攒下来的未匹配标签 UPSERT 进 med_dict_unmatched。

    绕开 DictUnmatchedCRUD 的 auth 依赖：直接用表级 pg_insert + 裸列，
    ON CONFLICT (hospital_id, dict_type_id, raw_label) DO UPDATE 累加 occurrence_count。

    unmatched 每条形如 {"field": "sex", "raw_label": "xxx", "raw_value": "..."}
    field ∈ {sex/ethnicity/smoking_status/abo_blood_type/rh_blood_type}，映射到 dict_type_id。
    """
    if not unmatched:
        return

    # 批量查 dict_type_id（5 个枚举类型，一次性取齐）
    from app.api.v1.module_system.dict.model import DictTypeModel
    from app.plugin.module_medical.dict_mapping.model import DictUnmatchedModel

    dict_type_names = list({
        _ENUM_DICT_TYPE_BY_FIELD[r["field"]]
        for r in unmatched if r.get("field") in _ENUM_DICT_TYPE_BY_FIELD
    })
    if not dict_type_names:
        return

    dt_rows = (
        await db.execute(
            select(DictTypeModel.dict_type, DictTypeModel.id).where(
                DictTypeModel.dict_type.in_(dict_type_names)
            )
        )
    ).all()
    type_id_map = {row.dict_type: row.id for row in dt_rows}

    # 聚合：同一 (field, raw_label) 出现多次只写一行，occurrence_count 累加
    agg: dict[tuple[str, str], dict[str, Any]] = {}
    for r in unmatched:
        field = r.get("field")
        if field not in _ENUM_DICT_TYPE_BY_FIELD:
            continue
        dt_name = _ENUM_DICT_TYPE_BY_FIELD[field]
        dt_id = type_id_map.get(dt_name)
        if dt_id is None:
            continue
        key = (dt_id, str(r.get("raw_label", "")).strip())
        if not key[1]:
            continue
        if key not in agg:
            agg[key] = {
                "hospital_id": hospital_id,
                "dict_type_id": dt_id,
                "raw_label": key[1],
                "raw_value": r.get("raw_value"),
                "_count": 0,
            }
        agg[key]["_count"] += 1

    if not agg:
        return

    # 构造 UPSERT 行（裸列，不依赖 auth.user）
    from datetime import datetime
    now = datetime.now()
    rows = []
    for rec in agg.values():
        cnt = rec.pop("_count")
        rec.update(
            {
                "tenant_id": 1,  # PLATFORM_TENANT_ID
                "occurrence_count": cnt,
                "last_seen_at": now,
                # 命中已有行时清掉 resolution（重新进入待处理队列）
                "status": "0",
            }
        )
        rows.append(rec)

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        stmt = pg_insert(DictUnmatchedModel.__table__).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_med_dict_unmatched",
            set_={
                "occurrence_count": DictUnmatchedModel.__table__.c.occurrence_count
                + stmt.excluded.occurrence_count,
                "last_seen_at": stmt.excluded.last_seen_at,
                "status": "0",
            },
        )
        await db.execute(stmt)

    log.info(
        f"ETL2: unmatched 落库 hospital_id={hospital_id} 共 {len(rows)} 条标签"
    )


# --------------------------------------------------------------------------- #
# 单表导入
# --------------------------------------------------------------------------- #


async def _import_patient_table(
    db: AsyncSession,
    *,
    center_code: str,
    parquet_path: Path,
    batch_id: str,
    hospital_id: int,
) -> int:
    """导入 patient.parquet → lnrs_anon_patient（批量）。返回入库（去重后）行数。

    用 _with_status 版本归一化枚举字段，未命中 raw_label 攒进 unmatched 列表，
    导入完成后一次性 _flush_unmatched 落 med_dict_unmatched 表。
    """
    cols, rows = await _read_parquet_async(parquet_path)
    if not rows:
        log.warning(f"ETL2: {center_code}/patient.parquet 无数据，跳过")
        return 0

    # 预计算所有 patient 记录 + phi_audit
    patient_records: list[dict[str, Any]] = []
    audit_records: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    for row in rows:
        rd = _row_to_dict(cols, row)
        local_pid = rd.get("patient_id")
        if not local_pid:
            continue
        try:
            anon_id = compute_anon_id(center_code, str(local_pid))
        except ValueError as e:
            log.warning(f"ETL2: 跳过非法 patient_id={local_pid!r}: {e}")
            continue

        # 5 个枚举字段：结构化归一化（带 hit 信号）
        sex_v, sex_hit = normalize_sex_with_status(rd.get("gender"))
        eth_v, eth_hit = normalize_ethnicity_with_status(rd.get("ethnicity"))
        smk_v, smk_hit = normalize_smoking_status_with_status(rd.get("smoking_status"))
        abo_v, abo_hit = normalize_abo_blood_type_with_status(rd.get("abo_blood_type"))
        rh_v, rh_hit = normalize_rh_blood_type_with_status(rd.get("rh_blood_type"))
        if not sex_hit and rd.get("gender") is not None:
            unmatched.append({"field": "sex", "raw_label": str(rd.get("gender")), "raw_value": str(rd.get("gender"))})
        if not eth_hit and rd.get("ethnicity") is not None:
            unmatched.append({"field": "ethnicity", "raw_label": str(rd.get("ethnicity")), "raw_value": str(rd.get("ethnicity"))})
        if not smk_hit and rd.get("smoking_status") is not None:
            unmatched.append({"field": "smoking_status", "raw_label": str(rd.get("smoking_status")), "raw_value": str(rd.get("smoking_status"))})
        if not abo_hit and rd.get("abo_blood_type") is not None:
            unmatched.append({"field": "abo_blood_type", "raw_label": str(rd.get("abo_blood_type")), "raw_value": str(rd.get("abo_blood_type"))})
        if not rh_hit and rd.get("rh_blood_type") is not None:
            unmatched.append({"field": "rh_blood_type", "raw_label": str(rd.get("rh_blood_type")), "raw_value": str(rd.get("rh_blood_type"))})

        patient_records.append(
            {
                "local_id": str(local_pid),
                "anon_id": anon_id,
                "sex": sex_v,
                "ethnicity": eth_v,
                "smoking_status": smk_v,
                "abo_blood_type": abo_v,
                "rh_blood_type": rh_v,
                # 医疗宽表直入扩展：非枚举稳定属性 + 病史 JSONB
                "native_place": _clean_str(rd.get("native_place")),
                "first_nodule_date": birth_date_from(rd.get("first_nodule_date")),
                "bmi": _extract_bmi(rd.get("demographics")),
                "patient_meta": _extract_patient_meta(rd),
                "birth_date": birth_date_from(rd.get("birth_date")),
            }
        )
        # PHI 审计：patient_id HMAC + birth_date partial_keep
        audit_records.append(
            {
                "source_table": "patient",
                "source_field": "patient_id",
                "source_hash": hash_for_audit(local_pid),
                "strategy": "hmac",
                "confidence": 1.0,
            }
        )
        if rd.get("birth_date") is not None:
            audit_records.append(
                {
                    "source_table": "patient",
                    "source_field": "birth_date",
                    "source_hash": hash_for_audit(rd.get("birth_date")),
                    "strategy": "partial_keep",
                    "confidence": 1.0,
                }
            )

    await _batch_upsert_patients(
        db, center_code=center_code, patient_records=patient_records, batch_id=batch_id
    )
    await _write_phi_audit_batch(db, batch_id=batch_id, records=audit_records)
    await _flush_unmatched(db, hospital_id=hospital_id, unmatched=unmatched)
    imported = len({r["anon_id"] for r in patient_records})
    log.info(
        f"ETL2: {center_code}/patient 导入 {imported} 行（去重前 {len(patient_records)}），"
        f"未匹配标签 {len(unmatched)} 条"
    )
    return imported


# hos301/shengyi 扩展（Rev 2026-09-01/09-02）：exam_type 行级动态归一化
_EXAM_TYPE_DICT_VALUES = (
    "CT", "Pathology", "Genetic", "IHC", "PETCT", "Radiology",
    "Ultrasound", "MR", "ECG", "Other",
)


def _normalize_exam_type(
    field_name: str, row: dict[str, Any], cache: dict[str, str]
) -> str:
    """从行数据归一化 exam_type 值（hos301 examType / 省医 检查类型名称）。

    规则优先级：
    1. 去空白/全角后与 med_exam_type 字典值精确匹配（命中直接返回）
    2. med_dict_mapping raw_label → dict_value（预加载 cache）
    3. 兜底 Other（记 warning）
    """
    raw = str(row.get(field_name) or "").strip()
    if not raw:
        return "Other"
    # 全角 → 半角 C/T + 去空白（301 examClass/examType 原始数据用全角）
    normalized = raw.replace("Ｃ", "C").replace("Ｔ", "T").replace("　", " ").replace(" ", "")
    if normalized in _EXAM_TYPE_DICT_VALUES:
        return normalized
    mapped = cache.get(normalized.lower())
    if mapped:
        return mapped
    log.warning(f"ETL2: 未识别 exam_type: {raw!r}，兜底 Other")
    return "Other"


async def _import_exam_text_table(
    db: AsyncSession,
    *,
    center_code: str,
    parquet_path: Path,
    src_table: str,
    exam_type: str,
    exam_type_field: str | None = None,
    hospital_id: int | None = None,
    id_field: str,
    body_fields: list[str],
    batch_id: str,
    detail_type: str | None = None,
    detail_fields: list[str] | None = None,
    date_field: str = "exam_date",
    ordinal_field: str | None = None,
    date_lookup_field: str | None = None,
) -> int:
    """通用：把 nodule_imaging / pathology_specimen 批量落 exam + report_text。

    ordinal_field（Rev 2026-07-24）：标识"同 exam 多实例展开"的列名
    （如 nodule_imaging 的 nodule_no）。设置后，每行 parquet 都生成
    一条 exam_detail（1:N），detail_ordinal 从 ordinal_field 值解析。
    不设置时沿用旧行为：同 anon_exam_id 只生成一条 detail（detail_ordinal=1）。

    date_lookup_field（省医扩展）：date_field="" 时的反查来源。
    - 未设：反查同 id_field 已入库 exam 的日期（ihc 复用 pathology specimen_id 日期）。
    - "visit_id"：按 visit_id 反查 lnrs_anon_visit_detail.admission_time
      （省医 pathology 所有日期列空，反查 visit 兜底）。
    exam_type_field（hos301/省医扩展）：行数据中动态决定 exam_type 的列名
    （如 examType / exam_type）。设置后优先取该列值，经 _normalize_exam_type
    归一化（全角→半角 / 字典值精确匹配 / 字典映射）；空值或未识别时兜底 Other。
    hospital_id：exam_type_field 生效时限定预加载 med_dict_mapping 的医院范围。
    """
    cols, rows = await _read_parquet_async(parquet_path)
    if not rows:
        log.warning(f"ETL2: {center_code}/{src_table}.parquet 无数据，跳过")
        return 0

    # exam_type_field（hos301/省医）：预加载 exam_type 字典映射，供行级归一化
    exam_type_cache: dict[str, str] = {}
    if exam_type_field:
        from .enum_normalization import load_exam_type_mapping
        exam_type_cache = await load_exam_type_mapping(db, hospital_id)

    # 第一遍：构造 exam 行，同时收集 exam 中出现的 patient（可能 patient.parquet 里没有）
    exam_patient_records: list[dict[str, Any]] = []
    exam_rows: list[dict[str, Any]] = []
    report_rows: list[dict[str, Any]] = []
    audit_records: list[dict[str, Any]] = []
    seen_exam_anon: set[str] = set()  # 同源重复 exam_id 去重（zhujiang path 12 个重复）
    detail_rows: list[dict[str, Any]] = []
    seen_detail_keys: set[tuple[str, str, int]] = set()  # (anon_exam_id, detail_type, ordinal) 去重
    # date_field="" 时预加载反查表：exam_date_lookup（同 id_field exam 日期）
    # 或 visit_date_lookup（date_lookup_field="visit_id" 时按 visit_id 反查 visit_detail 日期）
    exam_date_lookup: dict[str, date] = {}
    visit_date_lookup: dict[str, date] = {}
    if not date_field:
        if date_lookup_field == "visit_id":
            # 省医 pathology：按 visit_id 反查 visit_detail.admission_time
            visit_ids = [
                str(v) for v in (
                    _row_to_dict(cols, row).get(date_lookup_field) for row in rows
                ) if v
            ]
            if visit_ids:
                anon_visit_ids = {
                    compute_anon_visit_id(center_code, v): v for v in set(visit_ids)
                }
                visit_results = await _in_lookup_chunked(
                    db,
                    lambda c: select(
                        AnonVisitDetailModel.anon_visit_id,
                        AnonVisitDetailModel.admission_time,
                    ).where(AnonVisitDetailModel.anon_visit_id.in_(c)),
                    list(anon_visit_ids.keys()),
                )
                for r in visit_results:
                    if r[1]:
                        visit_date_lookup[anon_visit_ids[r[0]]] = r[1]
        else:
            # ihc 等无日期列的表：预加载同 id_field 已入库 exam 的日期，供反查
            anon_exam_ids_for_lookup = [
                compute_anon_exam_id(center_code, str(_row_to_dict(cols, row).get(id_field)))
                for row in rows
                if _row_to_dict(cols, row).get(id_field)
            ]
            if anon_exam_ids_for_lookup:
                lookup_results = await _in_lookup_chunked(
                    db,
                    lambda c: select(AnonExamModel.anon_exam_id, AnonExamModel.exam_date).where(
                        AnonExamModel.anon_exam_id.in_(c)
                    ),
                    anon_exam_ids_for_lookup,
                )
                for row in lookup_results:
                    exam_date_lookup[row[0]] = row[1]
    imported = 0

    for row in rows:
        rd = _row_to_dict(cols, row)
        local_pid = rd.get("patient_id")
        local_exam = rd.get(id_field)
        # 取检查日期：优先 date_field 指定列，无 date_field 时反查
        if date_field:
            exam_date = birth_date_from(rd.get(date_field))
        elif date_lookup_field == "visit_id":
            # 省医 pathology：按本行 visit_id 反查 visit admission_time
            vid = rd.get(date_lookup_field)
            exam_date = visit_date_lookup.get(str(vid)) if vid else None
        else:
            try:
                aeid = compute_anon_exam_id(center_code, str(local_exam)) if local_exam else None
                exam_date = exam_date_lookup.get(aeid) if aeid else None
            except ValueError:
                exam_date = None

        if not local_pid or not local_exam:
            continue
        if exam_date is None:
            log.warning(
                f"ETL2: 跳过无 exam_date 的 exam: center={center_code} "
                f"{id_field}={local_exam!r}"
            )
            continue

        try:
            anon_id = compute_anon_id(center_code, str(local_pid))
            anon_exam_id = compute_anon_exam_id(center_code, str(local_exam))
        except ValueError as e:
            log.warning(
                f"ETL2: 跳过非法 ID center={center_code} pid={local_pid!r} "
                f"{id_field}={local_exam!r}: {e}"
            )
            continue

        # exam 中出现的病人也要确保存在（exam.patient_id FK）；
        # sex/birth_date 此处未知，置默认 U/None（若 patient.parquet 已入库则会被活行 UPDATE 覆盖）
        exam_patient_records.append(
            {"local_id": str(local_pid), "anon_id": anon_id, "sex": "0", "birth_date": None}
        )

        # 可选：构造 exam_detail JSONB 深结构
        # Rev 2026-07-24: 支持 ordinal_field 1:N 展开（如 nodule_imaging 多结节）
        # - 有 ordinal_field：每行 parquet 生成一条 detail（detail_ordinal 从字段解析），
        #   必须在 seen_exam_anon 去重之前执行（多结节共享 anon_exam_id 但各成一行 detail）
        # - 无 ordinal_field：同 anon_exam_id 只生成一条 detail（保持旧行为，受 seen_exam_anon 去重保护）
        if detail_type and detail_fields:
            ordinal = _parse_ordinal(rd.get(ordinal_field)) if ordinal_field else 1
            dedup_key = (anon_exam_id, detail_type, ordinal)
            if ordinal_field or dedup_key not in seen_detail_keys:
                seen_detail_keys.add(dedup_key)
                detail_json = _build_detail_json(rd, detail_fields)
                detail_rows.append(
                    {
                        "anon_exam_id": anon_exam_id,
                        "detail_type": detail_type,
                        "detail_ordinal": ordinal,
                        "detail_json": detail_json,
                        "created_batch_id": batch_id,
                    }
                )

        if anon_exam_id in seen_exam_anon:
            continue  # 同源重复 exam_id（zhujiang path 12 dup），跳后续 exam/report 构造
        seen_exam_anon.add(anon_exam_id)

        src_hash = source_exam_hash(center_code, str(local_exam))
        exam_rows.append(
            {
                "anon_exam_id": anon_exam_id,
                "patient_id": None,  # 占位，patient upsert 后回填
                "_anon_id": anon_id,  # 临时键，回填用
                "center_code": center_code,
                "exam_type": _normalize_exam_type(exam_type_field, rd, exam_type_cache) if exam_type_field else exam_type,
                "exam_date": exam_date,
                "source_exam_hash": src_hash,
                "created_batch_id": batch_id,
                "last_seen_batch_id": batch_id,
            }
        )

        # 拼接正文（支持点号路径访问嵌套 struct，如 exam_detail.findings）
        parts: list[str] = []
        for f in body_fields:
            v = _get_nested(rd, f)
            if v:
                parts.append(str(v))
        body = truncate_body("\n\n".join(parts))
        # 正文非空才写 report 行：report_text PK=anon_exam_id 跨 exam_type 唯一，
        # 空正文 upsert 会覆盖已有非空正文（IHC 与 Pathology 共享 specimen id，
        # 0825 批次 6,698 条病理正文会被空 IHC body 冲掉）
        if body:
            report_rows.append(
                {
                    "anon_exam_id": anon_exam_id,
                    "body_clean": body,
                    "pii_replaced_count": 0,
                    "clean_method": CLEAN_METHOD_REGEX_ONLY,
                    "llm_model": None,
                    "review_status": "pending",
                    "created_batch_id": batch_id,
                }
            )

        # PHI 审计：exam/specimen id HMAC + 正文 llm_replace(confidence=0 占位)
        audit_records.append(
            {
                "source_table": src_table,
                "source_field": id_field,
                "source_hash": hash_for_audit(local_exam),
                "strategy": "hmac",
                "confidence": 1.0,
            }
        )
        for f in body_fields:
            v = _get_nested(rd, f)
            if v:
                audit_records.append(
                    {
                        "source_table": src_table,
                        "source_field": f,
                        "source_hash": hash_for_audit(v),
                        "strategy": "llm_replace",
                        "confidence": 0.0,
                    }
                )
        imported += 1

    # 1. 先 upsert 所有 exam 涉及的病人（确保 FK 存在）
    pid_map = await _batch_upsert_patients(
        db, center_code=center_code, patient_records=exam_patient_records,
        batch_id=batch_id, is_placeholder=True,
    )

    # 2. 回填 exam_rows 的 patient_id（去掉临时键）
    for er in exam_rows:
        er["patient_id"] = pid_map[er["_anon_id"]]
        del er["_anon_id"]

    # 3. 批量 upsert exam + report_text + phi_audit
    await _batch_upsert_exams(db, exam_rows=exam_rows)
    await _batch_upsert_report_text(db, report_rows=report_rows)
    if detail_rows:
        await _batch_upsert_exam_detail(db, detail_rows=detail_rows)
    await _write_phi_audit_batch(db, batch_id=batch_id, records=audit_records)

    log.info(f"ETL2: {center_code}/{src_table} 导入 {imported} 行 exam+report")
    return imported


async def _import_surgery_table(
    db: AsyncSession,
    *,
    center_code: str,
    parquet_path: Path,
    src_table: str,
    batch_id: str,
) -> int:
    """导入 surgery_record.parquet → lnrs_anon_visit + lnrs_anon_surgery。

    visit 桥从 visit_id 反推生成；手术记录挂在 visit 下。
    返回入库（去重后）行数。
    """
    cols, rows = await _read_parquet_async(parquet_path)
    if not rows:
        log.warning(f"ETL2: {center_code}/{src_table}.parquet 无数据，跳过")
        return 0

    # 第一遍：构造 visit + surgery 行，同时收集涉及的 patient（确保 FK 存在）
    visit_patient_records: list[dict[str, Any]] = []
    visit_records: list[dict[str, Any]] = []
    surgery_rows: list[dict[str, Any]] = []
    audit_records: list[dict[str, Any]] = []
    seen_surgery_hash: set[str] = set()  # 同源重复手术去重
    imported = 0

    for row in rows:
        rd = _row_to_dict(cols, row)
        local_pid = rd.get("patient_id")
        visit_id = rd.get("visit_id")
        procedure_name = rd.get("procedure_name")

        if not local_pid or not visit_id or not procedure_name:
            continue

        try:
            anon_id = compute_anon_id(center_code, str(local_pid))
            anon_visit_id = compute_anon_visit_id(center_code, str(visit_id))
        except ValueError as e:
            log.warning(
                f"ETL2: 跳过非法 ID center={center_code} pid={local_pid!r} "
                f"visit={visit_id!r}: {e}"
            )
            continue

        # visit 涉及的病人也要确保存在（visit.patient_id FK）
        visit_patient_records.append(
            {"local_id": str(local_pid), "anon_id": anon_id, "sex": "0", "birth_date": None}
        )

        # visit 记录（带 _anon_id 临时键，patient upsert 后回填 patient_id；
        #            _batch_upsert_visits 内部再按 source_visit_hash 去重）
        visit_records.append(
            {
                "visit_id": str(visit_id),
                "anon_visit_id": anon_visit_id,
                "source_visit_hash": source_visit_hash(center_code, str(visit_id)),
                "_anon_id": anon_id,  # 临时键，回填 patient_id 用
            }
        )

        # 手术记录去重
        surg_hash = source_surgery_hash(center_code, str(visit_id), str(procedure_name))
        if surg_hash in seen_surgery_hash:
            continue
        seen_surgery_hash.add(surg_hash)

        surgery_date = birth_date_from(rd.get("surgery_date"))
        surgery_rows.append(
            {
                "anon_visit_id": anon_visit_id,
                "patient_id": None,  # 占位，patient upsert 后回填
                "_anon_id": anon_id,  # 临时键，回填用
                "center_code": center_code,
                "surgery_date": surgery_date,
                "procedure_name": str(procedure_name)[:200],
                "resection_scope": _clean_str(rd.get("resection_scope")),
                "surgical_approach": _clean_str(rd.get("surgical_approach")),
                "procedure_detail": rd.get("procedure_detail") if isinstance(
                    rd.get("procedure_detail"), dict
                ) else None,
                "source_surgery_hash": surg_hash,
                "created_batch_id": batch_id,
            }
        )

        # PHI 审计：visit_id HMAC
        audit_records.append(
            {
                "source_table": src_table,
                "source_field": "visit_id",
                "source_hash": hash_for_audit(visit_id),
                "strategy": "hmac",
                "confidence": 1.0,
            }
        )
        imported += 1

    # 1. 先 upsert 所有 visit 涉及的病人（确保 FK 存在）
    #    占位模式：不覆盖已有 patient 的人口学（避免冲掉 patient.parquet 写入的真实值）
    pid_map = await _batch_upsert_patients(
        db, center_code=center_code, patient_records=visit_patient_records,
        batch_id=batch_id, is_placeholder=True,
    )

    # 2. 回填 visit_records 与 surgery_rows 的 patient_id（去掉临时键 _anon_id）
    for vr in visit_records:
        vr["patient_id"] = pid_map[vr["_anon_id"]]
        del vr["_anon_id"]
    for sr in surgery_rows:
        sr["patient_id"] = pid_map[sr["_anon_id"]]
        del sr["_anon_id"]

    # 3. 批量 upsert visit + surgery + phi_audit
    await _batch_upsert_visits(
        db, center_code=center_code, visit_records=visit_records, batch_id=batch_id
    )
    await _batch_upsert_surgeries(db, surgery_rows=surgery_rows)
    await _write_phi_audit_batch(db, batch_id=batch_id, records=audit_records)

    log.info(f"ETL2: {center_code}/{src_table} 导入 {imported} 行 surgery")
    return imported


# --------------------------------------------------------------------------- #
# 省医扩展导入函数：visit_detail / lab / order
# 珠江无需这些表，函数独立于 zhujiang 链路，不影响既有逻辑。
# --------------------------------------------------------------------------- #


async def _import_visit_detail_table(
    db: AsyncSession,
    *,
    center_code: str,
    parquet_path: Path,
    src_table: str,
    id_field: str,
    date_field: str,
    batch_id: str,
) -> int:
    """导入 visit_record.parquet → lnrs_anon_visit(桥) + lnrs_anon_visit_detail(富信息)。

    省医特有：visit_record 含病案首页/病史/诊断数组/临床文档等富信息。
    本函数**自建 visit 桥**（照抄 surgery 三步范式），不依赖 surgery 反推——
    因为 visit_record 的 visit 集合 ⊋ surgery 涉及的 visit，且 visit_record 历史上
    被引擎显式跳过（ADR-0006 visit 桥未启用）。visit_detail 与 visit 桥 1:1。

    visit_detail_json 忠实保留原始嵌套结构（inpatient_front_page/medical_history/
    diagnoses[]/clinical_documents[]），不做语义对齐。
    """
    cols, rows = await _read_parquet_async(parquet_path)
    if not rows:
        log.warning(f"ETL2: {center_code}/{src_table}.parquet 无数据，跳过")
        return 0

    visit_patient_records: list[dict[str, Any]] = []
    visit_records: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []
    seen_visit_hash: set[str] = set()  # 同源 visit 去重
    imported = 0

    for row in rows:
        rd = _row_to_dict(cols, row)
        local_pid = rd.get("patient_id")
        visit_id = rd.get(id_field) or rd.get("visit_id")

        if not local_pid or not visit_id:
            continue

        try:
            anon_id = compute_anon_id(center_code, str(local_pid))
            anon_visit_id = compute_anon_visit_id(center_code, str(visit_id))
        except ValueError as e:
            log.warning(
                f"ETL2: 跳过非法 ID center={center_code} pid={local_pid!r} "
                f"visit={visit_id!r}: {e}"
            )
            continue

        src_v_hash = source_visit_hash(center_code, str(visit_id))
        if src_v_hash in seen_visit_hash:
            continue
        seen_visit_hash.add(src_v_hash)

        visit_patient_records.append(
            {"local_id": str(local_pid), "anon_id": anon_id, "sex": "0", "birth_date": None}
        )
        visit_records.append(
            {
                "visit_id": str(visit_id),
                "anon_visit_id": anon_visit_id,
                "source_visit_hash": src_v_hash,
                "_anon_id": anon_id,
            }
        )

        # 富信息列：提取标量，剩余整体序列化进 visit_detail_json
        visit_detail_json: dict[str, Any] = {}
        # 不放入提取列的键集合，剩余全进 JSONB
        extracted_keys = {"patient_id", id_field, "visit_id"}
        for k, v in rd.items():
            if k not in extracted_keys and v is not None:
                visit_detail_json[k] = v
        # date/datetime 转 ISO 字符串，使 JSONB 可序列化
        visit_detail_json = _json_safe(visit_detail_json)

        detail_rows.append(
            {
                "anon_visit_id": anon_visit_id,
                "patient_id": None,  # 占位，回填
                "_anon_id": anon_id,
                "center_code": center_code,
                "visit_category": _clean_str(rd.get("visit_category")),
                "admission_time": _clean_date(rd.get(date_field) or rd.get("admission_time")),
                "discharge_date": _clean_date(rd.get("discharge_date")),
                "admission_dept": _clean_str(rd.get("admission_dept")),
                "discharge_dept": _clean_str(rd.get("discharge_dept")),
                "length_of_stay": int(rd["length_of_stay"])
                if rd.get("length_of_stay") is not None
                else None,
                "payment_method": _clean_str(rd.get("payment_method")),
                "visit_age": float(rd["visit_age"])
                if rd.get("visit_age") is not None
                else None,
                "visit_detail_json": visit_detail_json,
                "source_visit_hash": src_v_hash,
                "created_batch_id": batch_id,
            }
        )
        imported += 1

    # 1. 占位 patient（确保 FK）
    pid_map = await _batch_upsert_patients(
        db, center_code=center_code, patient_records=visit_patient_records,
        batch_id=batch_id, is_placeholder=True,
    )
    # 2. 回填 patient_id + 建 visit 桥
    for vr in visit_records:
        vr["patient_id"] = pid_map[vr["_anon_id"]]
        del vr["_anon_id"]
    for dr in detail_rows:
        dr["patient_id"] = pid_map[dr["_anon_id"]]
        del dr["_anon_id"]
    await _batch_upsert_visits(
        db, center_code=center_code, visit_records=visit_records, batch_id=batch_id
    )
    # 3. 写 visit_detail
    await _batch_upsert_visit_details(db, visit_detail_rows=detail_rows)

    log.info(f"ETL2: {center_code}/{src_table} 导入 {imported} 行 visit_detail")
    return imported


async def _import_lab_table(
    db: AsyncSession,
    *,
    center_code: str,
    parquet_path: Path,
    src_table: str,
    id_field: str,
    batch_id: str,
) -> int:
    """导入 lab_result.parquet → lnrs_anon_lab_result（省医扩展）。

    挂在 visit 下（anon_visit_id 可空，visit_id 缺失时退化为只挂 patient）。
    守卫顺序：先无条件收集 patient 占位，再按 visit_id 决定是否建桥——
    避免照抄 surgery 三连守卫导致 visit_id 为空时连 patient 占位也建不了。
    """
    cols, rows = await _read_parquet_async(parquet_path)
    if not rows:
        log.warning(f"ETL2: {center_code}/{src_table}.parquet 无数据，跳过")
        return 0

    # 预读已入库 visit 桥：visit_id → anon_visit_id（本批及历史）
    visit_id_set = set()
    for row in rows:
        rd = _row_to_dict(cols, row)
        vid = rd.get("visit_id")
        if vid:
            visit_id_set.add(str(vid))
    visit_lookup: dict[str, str] = {}
    if visit_id_set:
        anon_visit_ids = {
            compute_anon_visit_id(center_code, v): v for v in visit_id_set
        }
        existing = await _in_lookup_chunked(
            db,
            lambda c: select(AnonVisitModel.anon_visit_id).where(
                AnonVisitModel.anon_visit_id.in_(c)
            ),
            list(anon_visit_ids.keys()),
        )
        for (aevid,) in existing:
            visit_lookup[anon_visit_ids[aevid]] = aevid

    patient_records: list[dict[str, Any]] = []
    lab_rows: list[dict[str, Any]] = []
    seen_lab_hash: set[tuple] = set()  # (anon_visit_id, source_lab_hash) 去重
    imported = 0

    for row in rows:
        rd = _row_to_dict(cols, row)
        local_pid = rd.get("patient_id")
        report_id = rd.get(id_field) or rd.get("report_id")
        item_name = rd.get("item_name")

        if not local_pid or not report_id:
            continue

        try:
            anon_id = compute_anon_id(center_code, str(local_pid))
        except ValueError as e:
            log.warning(f"ETL2: 跳过非法 pid center={center_code} pid={local_pid!r}: {e}")
            continue

        # 无条件收集 patient（即使无 visit_id 也要建 patient 占位）
        patient_records.append(
            {"local_id": str(local_pid), "anon_id": anon_id, "sex": "0", "birth_date": None}
        )

        vid = rd.get("visit_id")
        anon_visit_id = visit_lookup.get(str(vid)) if vid else None

        src_hash = source_lab_hash(
            center_code, str(report_id), str(item_name) if item_name else ""
        )
        dedup_key = (anon_visit_id, src_hash)
        if dedup_key in seen_lab_hash:
            continue
        seen_lab_hash.add(dedup_key)

        # 数值结果：非数值时保留 None
        # 数值结果：非数值 / 越界时保留 None（NUMERIC(18,4) 上限 ~1e14；
        # 实际检验值极少 >1e9，遇到日期格式"202503130006"被误读为 2e11 之类
        # 直接丢弃，避免 asyncpg NumericValueOutOfRangeError 中断整批）
        num_val = None
        raw_val = rd.get("item_result_value")
        if raw_val is not None:
            try:
                candidate = float(raw_val)
                if -1e8 < candidate < 1e8:
                    num_val = candidate
            except (TypeError, ValueError):
                num_val = None

        # lab_detail_json：剩余结构（test_detail 等）忠实保留
        extracted_keys = {"patient_id", id_field, "report_id", "visit_id", "test_name",
                          "item_name", "item_result", "item_result_value", "item_unit",
                          "collection_time"}
        lab_detail_json: dict[str, Any] = {}
        for k, v in rd.items():
            if k not in extracted_keys and v is not None:
                lab_detail_json[k] = v
        # date/datetime 转 ISO 字符串，使 JSONB 可序列化
        lab_detail_json = _json_safe(lab_detail_json) or None

        lab_rows.append(
            {
                "anon_visit_id": anon_visit_id,
                "patient_id": None,  # 占位，回填
                "_anon_id": anon_id,
                "center_code": center_code,
                "report_id": _clean_str(str(report_id)),
                "test_name": (_clean_str(rd.get("test_name")) or "")[:200],
                "item_name": _clean_str(item_name),
                "item_result": _clean_str(rd.get("item_result")),
                "item_result_value": num_val,
                "item_unit": _clean_str(rd.get("item_unit")),
                "collection_time": _clean_date(rd.get("collection_time")),
                "lab_detail_json": lab_detail_json or None,
                "source_lab_hash": src_hash,
                "created_batch_id": batch_id,
            }
        )
        imported += 1

    pid_map = await _batch_upsert_patients(
        db, center_code=center_code, patient_records=patient_records,
        batch_id=batch_id, is_placeholder=True,
    )
    for lr in lab_rows:
        lr["patient_id"] = pid_map[lr["_anon_id"]]
        del lr["_anon_id"]
    await _batch_upsert_lab_results(db, lab_rows=lab_rows)

    log.info(f"ETL2: {center_code}/{src_table} 导入 {imported} 行 lab_result")
    return imported


async def _import_order_table(
    db: AsyncSession,
    *,
    center_code: str,
    parquet_path: Path,
    src_table: str,
    order_type: str,
    order_name_field: str,
    order_hash_extra: bool = False,
    batch_id: str,
) -> int:
    """导入 drug_order / no_drug_order.parquet → lnrs_anon_order（省医扩展）。

    drug + non_drug 合并一表，order_type 区分。
    挂在 visit 下（anon_visit_id 可空，visit_id 缺失时退化为只挂 patient）。
    守卫顺序：先收集 patient，再按 visit_id 决定是否建桥（同 lab）。
    order_name_field 参数化：drug_order 用 drug_generic_name，no_drug_order 用 order_name。
    order_hash_extra（省医全量批次，2026-09-02）：source_order_hash 追加
    patient_id + order_detail 规范 JSON 两段。旧哈希 (center,time,name,type)
    不含患者/明细：省医 24M 住院医嘱中 53% 的行会跨患者同药同时刻碰撞，
    且 staging 按就诊展开产生整行重复。False 时哈希与旧版逐字节一致
    （其他中心存量数据不受影响）。
    """
    cols, rows = await _read_parquet_async(parquet_path)
    if not rows:
        log.warning(f"ETL2: {center_code}/{src_table}.parquet 无数据，跳过")
        return 0

    # 预读 visit 桥
    visit_id_set = set()
    for row in rows:
        rd = _row_to_dict(cols, row)
        vid = rd.get("visit_id")
        if vid:
            visit_id_set.add(str(vid))
    visit_lookup: dict[str, str] = {}
    if visit_id_set:
        anon_visit_ids = {
            compute_anon_visit_id(center_code, v): v for v in visit_id_set
        }
        visit_results = await _in_lookup_chunked(
            db,
            lambda c: select(AnonVisitModel.anon_visit_id).where(
                AnonVisitModel.anon_visit_id.in_(c)
            ),
            list(anon_visit_ids.keys()),
        )
        for (aevid,) in visit_results:
            visit_lookup[anon_visit_ids[aevid]] = aevid
    patient_records: list[dict[str, Any]] = []
    order_rows: list[dict[str, Any]] = []
    seen_order_hash: set[tuple] = set()
    imported = 0

    for row in rows:
        rd = _row_to_dict(cols, row)
        local_pid = rd.get("patient_id")
        order_name = rd.get(order_name_field)

        if not local_pid or not order_name:
            continue

        try:
            anon_id = compute_anon_id(center_code, str(local_pid))
        except ValueError as e:
            log.warning(f"ETL2: 跳过非法 pid center={center_code} pid={local_pid!r}: {e}")
            continue

        patient_records.append(
            {"local_id": str(local_pid), "anon_id": anon_id, "sex": "0", "birth_date": None}
        )

        vid = rd.get("visit_id")
        anon_visit_id = visit_lookup.get(str(vid)) if vid else None

        order_time = rd.get("order_time") or rd.get("order_start_time")
        order_time_str = str(order_time) if order_time else ""

        # order_detail struct 忠实保留（order_hash_extra 时同时作哈希 detail_key）
        order_detail = rd.get("order_detail")
        order_detail_json = (
            _json_safe(order_detail) if isinstance(order_detail, dict) else None
        )
        detail_key = ""
        if order_hash_extra and isinstance(order_detail, dict):
            detail_key = json.dumps(
                order_detail, ensure_ascii=False, sort_keys=True, default=str
            )
        src_hash = source_order_hash(
            center_code,
            order_time_str,
            str(order_name),
            order_type,
            patient_id=str(local_pid) if order_hash_extra else "",
            detail_key=detail_key,
        )
        # order_hash_extra 开启时哈希已全局唯一标识一条医嘱 → 直接按哈希去重
        # （吸收 staging 按就诊展开的整行重复，规避 UNIQUE(source_order_hash) 冲突）；
        # 关闭时保持旧行为（同 visit 同哈希合并）。
        dedup_key = src_hash if order_hash_extra else (anon_visit_id, src_hash)
        if dedup_key in seen_order_hash:
            continue
        seen_order_hash.add(dedup_key)

        order_rows.append(
            {
                "anon_visit_id": anon_visit_id,
                "patient_id": None,
                "_anon_id": anon_id,
                "center_code": center_code,
                "order_type": order_type,
                "order_name": str(order_name)[:200],
                "order_time": _clean_date(order_time),
                "order_source": _clean_str(rd.get("order_source")),
                "order_detail_json": order_detail_json,
                "source_order_hash": src_hash,
                "created_batch_id": batch_id,
            }
        )
        imported += 1

    pid_map = await _batch_upsert_patients(
        db, center_code=center_code, patient_records=patient_records,
        batch_id=batch_id, is_placeholder=True,
    )
    for od in order_rows:
        od["patient_id"] = pid_map[od["_anon_id"]]
        del od["_anon_id"]
    await _batch_upsert_orders(db, order_rows=order_rows)

    log.info(f"ETL2: {center_code}/{src_table} 导入 {imported} 行 order({order_type})")
    return imported


# --------------------------------------------------------------------------- #
# 省医全量批次扩展（2026-09-02，DDL 见 0014-shengyi-anon-extend-2026-09.sql）：
# diagnosis / clinical_document / medical_history / vital_observation
# --------------------------------------------------------------------------- #


def _md5_text(text: str) -> str:
    """字符串 MD5 hex（无唯一编号的文本字段参与 source hash 用）。"""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


_OBS_TIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d",
)


def _parse_obs_datetime(value: Any) -> datetime | None:
    """VARCHAR 观察时间 → datetime；解析失败返回 None（obs_time 可空）。"""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    for fmt in _OBS_TIME_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


async def _import_diagnosis_table(
    db: AsyncSession,
    *,
    center_code: str,
    parquet_path: Path,
    src_table: str,
    source_label: str,
    batch_id: str,
    detail_fields: list[str] | None = None,
) -> int:
    """导入 就诊.诊断 / 住院病案首页.诊断 → lnrs_anon_diagnosis（0014 新表）。

    staging 列（适配层产出）：
      patient_id, diagnosis_code, diagnosis_name, diagnosis_date,
      is_primary, diagnosis_category, [detail struct 列（detail_fields 指定）]
    幂等键 source_diag_hash 含 source_label（区分两个来源文件）。
    守卫：patient_id 非空 且 (diagnosis_name 或 diagnosis_code) 非空。
    """
    cols, rows = await _read_parquet_async(parquet_path)
    if not rows:
        log.warning(f"ETL2: {center_code}/{src_table}.parquet 无数据，跳过")
        return 0

    patient_records: list[dict[str, Any]] = []
    seen_local_pid: set[str] = set()
    diag_rows: list[dict[str, Any]] = []
    seen_hash: set[str] = set()
    imported = 0

    for row in rows:
        rd = _row_to_dict(cols, row)
        local_pid = rd.get("patient_id")
        name = _clean_str(rd.get("diagnosis_name"))
        code = _clean_str(rd.get("diagnosis_code"))
        if not local_pid or not (name or code):
            continue
        try:
            anon_id = compute_anon_id(center_code, str(local_pid))
        except ValueError as e:
            log.warning(f"ETL2: 跳过非法 pid center={center_code} pid={local_pid!r}: {e}")
            continue
        if str(local_pid) not in seen_local_pid:
            seen_local_pid.add(str(local_pid))
            patient_records.append(
                {"local_id": str(local_pid), "anon_id": anon_id, "sex": "0", "birth_date": None}
            )

        date_v = _clean_date(rd.get("diagnosis_date"))
        category = _clean_str(rd.get("diagnosis_category"))
        is_primary = _clean_str(rd.get("is_primary"))
        detail_json = _build_detail_json(rd, detail_fields) if detail_fields else None
        src_hash = source_diagnosis_hash(
            center_code, source_label, str(local_pid),
            code or "", name or "",
            date_v.isoformat() if date_v else "",
            category or "", is_primary or "",
        )
        if src_hash in seen_hash:
            continue
        seen_hash.add(src_hash)
        diag_rows.append(
            {
                "patient_id": None,
                "_anon_id": anon_id,
                "center_code": center_code,
                "source": source_label,
                "diagnosis_code": code,
                "diagnosis_name": name,
                "diagnosis_date": date_v,
                "is_primary": is_primary,
                "diagnosis_category": category,
                "diagnosis_detail_json": detail_json,
                "source_diag_hash": src_hash,
                "created_batch_id": batch_id,
            }
        )
        imported += 1

    pid_map = await _batch_upsert_patients(
        db, center_code=center_code, patient_records=patient_records,
        batch_id=batch_id, is_placeholder=True,
    )
    for dr in diag_rows:
        dr["patient_id"] = pid_map[dr["_anon_id"]]
        del dr["_anon_id"]
    for i in range(0, len(diag_rows), BATCH_SIZE):
        batch = diag_rows[i : i + BATCH_SIZE]
        stmt = pg_insert(AnonDiagnosisModel.__table__).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="lnrs_anon_uq_diagnosis",
            set_={
                "diagnosis_code": stmt.excluded.diagnosis_code,
                "diagnosis_name": stmt.excluded.diagnosis_name,
                "diagnosis_date": stmt.excluded.diagnosis_date,
                "is_primary": stmt.excluded.is_primary,
                "diagnosis_category": stmt.excluded.diagnosis_category,
                "diagnosis_detail_json": stmt.excluded.diagnosis_detail_json,
                "created_batch_id": stmt.excluded.created_batch_id,
            },
        )
        await db.execute(stmt)

    log.info(f"ETL2: {center_code}/{src_table} 导入 {imported} 行 diagnosis({source_label})")
    return imported


async def _import_document_table(
    db: AsyncSession,
    *,
    center_code: str,
    parquet_path: Path,
    src_table: str,
    batch_id: str,
) -> int:
    """导入 病程记录文档 → lnrs_anon_clinical_document（0014 新表）。

    staging 列：patient_id, doc_type, doc_date, doc_content
    幂等键 source_doc_hash 用 md5(doc_content) 参与（避免超长文本直接进 SHA256）。
    空内容行（2.48M）随全量一并入库（md5('') 天然合并整行重复）。
    守卫：patient_id 非空。
    """
    cols, rows = await _read_parquet_async(parquet_path)
    if not rows:
        log.warning(f"ETL2: {center_code}/{src_table}.parquet 无数据，跳过")
        return 0

    patient_records: list[dict[str, Any]] = []
    seen_local_pid: set[str] = set()
    doc_rows: list[dict[str, Any]] = []
    seen_hash: set[str] = set()
    imported = 0

    for row in rows:
        rd = _row_to_dict(cols, row)
        local_pid = rd.get("patient_id")
        if not local_pid:
            continue
        try:
            anon_id = compute_anon_id(center_code, str(local_pid))
        except ValueError as e:
            log.warning(f"ETL2: 跳过非法 pid center={center_code} pid={local_pid!r}: {e}")
            continue
        if str(local_pid) not in seen_local_pid:
            seen_local_pid.add(str(local_pid))
            patient_records.append(
                {"local_id": str(local_pid), "anon_id": anon_id, "sex": "0", "birth_date": None}
            )

        doc_type = _clean_str(rd.get("doc_type"))
        date_v = _clean_date(rd.get("doc_date"))
        content = rd.get("doc_content")
        content_s = str(content) if content is not None else ""
        src_hash = source_document_hash(
            center_code, str(local_pid), doc_type or "",
            date_v.isoformat() if date_v else "",
            _md5_text(content_s),
        )
        if src_hash in seen_hash:
            continue
        seen_hash.add(src_hash)
        doc_rows.append(
            {
                "patient_id": None,
                "_anon_id": anon_id,
                "center_code": center_code,
                "doc_type": doc_type,
                "doc_date": date_v,
                "doc_content": content_s or None,
                "source_doc_hash": src_hash,
                "created_batch_id": batch_id,
            }
        )
        imported += 1

    pid_map = await _batch_upsert_patients(
        db, center_code=center_code, patient_records=patient_records,
        batch_id=batch_id, is_placeholder=True,
    )
    for dr in doc_rows:
        dr["patient_id"] = pid_map[dr["_anon_id"]]
        del dr["_anon_id"]
    for i in range(0, len(doc_rows), BATCH_SIZE):
        batch = doc_rows[i : i + BATCH_SIZE]
        stmt = pg_insert(AnonClinicalDocumentModel.__table__).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="lnrs_anon_uq_clinical_doc",
            set_={
                "doc_type": stmt.excluded.doc_type,
                "doc_date": stmt.excluded.doc_date,
                "doc_content": stmt.excluded.doc_content,
                "created_batch_id": stmt.excluded.created_batch_id,
            },
        )
        await db.execute(stmt)

    log.info(f"ETL2: {center_code}/{src_table} 导入 {imported} 行 clinical_document")
    return imported


async def _import_history_table(
    db: AsyncSession,
    *,
    center_code: str,
    parquet_path: Path,
    src_table: str,
    batch_id: str,
) -> int:
    """导入 就诊.病史 → lnrs_anon_medical_history（0014 新表）。

    staging 列：patient_id, chief_complaint, present_illness, past_history,
      personal_history, marriage_history, family_history, record_date, data_source
    幂等键 source_hist_hash 用 md5(六段文本 \\x1f 拼接) 参与。
    守卫：patient_id 非空 且 六段文本至少一段非空。
    """
    cols, rows = await _read_parquet_async(parquet_path)
    if not rows:
        log.warning(f"ETL2: {center_code}/{src_table}.parquet 无数据，跳过")
        return 0

    _FIELD_COLS = (
        "chief_complaint", "present_illness", "past_history",
        "personal_history", "marriage_history", "family_history",
    )
    patient_records: list[dict[str, Any]] = []
    seen_local_pid: set[str] = set()
    hist_rows: list[dict[str, Any]] = []
    seen_hash: set[str] = set()
    imported = 0

    for row in rows:
        rd = _row_to_dict(cols, row)
        local_pid = rd.get("patient_id")
        if not local_pid:
            continue
        fields = {c: _clean_str(rd.get(c)) or "" for c in _FIELD_COLS}
        if not any(fields.values()):
            continue
        try:
            anon_id = compute_anon_id(center_code, str(local_pid))
        except ValueError as e:
            log.warning(f"ETL2: 跳过非法 pid center={center_code} pid={local_pid!r}: {e}")
            continue
        if str(local_pid) not in seen_local_pid:
            seen_local_pid.add(str(local_pid))
            patient_records.append(
                {"local_id": str(local_pid), "anon_id": anon_id, "sex": "0", "birth_date": None}
            )

        date_v = _clean_date(rd.get("record_date"))
        data_source = _clean_str(rd.get("data_source"))
        fields_md5 = _md5_text("\x1f".join(fields[c] for c in _FIELD_COLS))
        src_hash = source_history_hash(
            center_code, str(local_pid), data_source or "",
            date_v.isoformat() if date_v else "", fields_md5,
        )
        if src_hash in seen_hash:
            continue
        seen_hash.add(src_hash)
        hist_rows.append(
            {
                "patient_id": None,
                "_anon_id": anon_id,
                "center_code": center_code,
                "chief_complaint": fields["chief_complaint"] or None,
                "present_illness": fields["present_illness"] or None,
                "past_history": fields["past_history"] or None,
                "personal_history": fields["personal_history"] or None,
                "marriage_history": fields["marriage_history"] or None,
                "family_history": fields["family_history"] or None,
                "record_date": date_v,
                "data_source": data_source,
                "source_hist_hash": src_hash,
                "created_batch_id": batch_id,
            }
        )
        imported += 1

    pid_map = await _batch_upsert_patients(
        db, center_code=center_code, patient_records=patient_records,
        batch_id=batch_id, is_placeholder=True,
    )
    for hr in hist_rows:
        hr["patient_id"] = pid_map[hr["_anon_id"]]
        del hr["_anon_id"]
    for i in range(0, len(hist_rows), BATCH_SIZE):
        batch = hist_rows[i : i + BATCH_SIZE]
        stmt = pg_insert(AnonMedicalHistoryModel.__table__).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="lnrs_anon_uq_medical_history",
            set_={
                "chief_complaint": stmt.excluded.chief_complaint,
                "present_illness": stmt.excluded.present_illness,
                "past_history": stmt.excluded.past_history,
                "personal_history": stmt.excluded.personal_history,
                "marriage_history": stmt.excluded.marriage_history,
                "family_history": stmt.excluded.family_history,
                "record_date": stmt.excluded.record_date,
                "data_source": stmt.excluded.data_source,
                "created_batch_id": stmt.excluded.created_batch_id,
            },
        )
        await db.execute(stmt)

    log.info(f"ETL2: {center_code}/{src_table} 导入 {imported} 行 medical_history")
    return imported


async def _import_observation_table(
    db: AsyncSession,
    *,
    center_code: str,
    parquet_path: Path,
    src_table: str,
    obs_type: str,
    batch_id: str,
    detail_fields: list[str] | None = None,
) -> int:
    """导入 护理测量/ICU护理/麻醉子项 观察 → lnrs_anon_vital_observation（0014 新表）。

    staging 列（适配层产出）：
      patient_id, visit_id（可空：ICU/麻醉源文件无就诊编号）,
      item_name, item_result, item_result_value（数值字符串）, item_unit,
      obs_time（VARCHAR）, [detail struct 列（detail_fields 指定）]
    obs_type 由 spec 指定（nursing / icu / anesthesia），与 DDL 注释一致。
    幂等键 source_obs_hash 的 time 段用解析后的 ISO（格式漂移不影响幂等）。
    守卫：patient_id 非空 且 item_name 非空。
    """
    cols, rows = await _read_parquet_async(parquet_path)
    if not rows:
        log.warning(f"ETL2: {center_code}/{src_table}.parquet 无数据，跳过")
        return 0

    # 预读 visit 桥（visit_id 全空时跳过，如 icu/anesthesia）
    visit_id_set: set[str] = set()
    for row in rows:
        rd = _row_to_dict(cols, row)
        vid = rd.get("visit_id")
        if vid:
            visit_id_set.add(str(vid))
    visit_lookup: dict[str, str] = {}
    if visit_id_set:
        anon_visit_ids = {
            compute_anon_visit_id(center_code, v): v for v in visit_id_set
        }
        existing = await _in_lookup_chunked(
            db,
            lambda c: select(AnonVisitModel.anon_visit_id).where(
                AnonVisitModel.anon_visit_id.in_(c)
            ),
            list(anon_visit_ids.keys()),
        )
        for (aevid,) in existing:
            visit_lookup[anon_visit_ids[aevid]] = aevid

    patient_records: list[dict[str, Any]] = []
    seen_local_pid: set[str] = set()
    obs_rows: list[dict[str, Any]] = []
    seen_hash: set[str] = set()
    imported = 0

    for row in rows:
        rd = _row_to_dict(cols, row)
        local_pid = rd.get("patient_id")
        item_name = _clean_str(rd.get("item_name"))
        if not local_pid or not item_name:
            continue
        try:
            anon_id = compute_anon_id(center_code, str(local_pid))
        except ValueError as e:
            log.warning(f"ETL2: 跳过非法 pid center={center_code} pid={local_pid!r}: {e}")
            continue
        if str(local_pid) not in seen_local_pid:
            seen_local_pid.add(str(local_pid))
            patient_records.append(
                {"local_id": str(local_pid), "anon_id": anon_id, "sex": "0", "birth_date": None}
            )

        vid = rd.get("visit_id")
        anon_visit_id = visit_lookup.get(str(vid)) if vid else None
        result = _clean_str(rd.get("item_result")) or ""
        value_s = _clean_str(rd.get("item_result_value")) or ""
        unit = _clean_str(rd.get("item_unit")) or ""
        time_v = _parse_obs_datetime(rd.get("obs_time"))
        value_num: Decimal | None = None
        if value_s:
            try:
                value_num = Decimal(value_s)
            except InvalidOperation:
                value_num = None
        detail_json = _build_detail_json(rd, detail_fields) if detail_fields else None
        src_hash = source_observation_hash(
            center_code, obs_type, str(local_pid),
            str(vid) if vid else "", item_name,
            result, value_s, unit,
            time_v.isoformat() if time_v else "",
        )
        if src_hash in seen_hash:
            continue
        seen_hash.add(src_hash)
        obs_rows.append(
            {
                "anon_visit_id": anon_visit_id,
                "patient_id": None,
                "_anon_id": anon_id,
                "center_code": center_code,
                "obs_type": obs_type,
                "item_name": item_name[:255],
                "item_result": (result[:255] or None),
                "item_result_value": value_num,
                "item_unit": (unit[:64] or None),
                "obs_time": time_v,
                "obs_detail_json": detail_json,
                "source_obs_hash": src_hash,
                "created_batch_id": batch_id,
            }
        )
        imported += 1

    pid_map = await _batch_upsert_patients(
        db, center_code=center_code, patient_records=patient_records,
        batch_id=batch_id, is_placeholder=True,
    )
    for orow in obs_rows:
        orow["patient_id"] = pid_map[orow["_anon_id"]]
        del orow["_anon_id"]
    for i in range(0, len(obs_rows), BATCH_SIZE):
        batch = obs_rows[i : i + BATCH_SIZE]
        stmt = pg_insert(AnonVitalObservationModel.__table__).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="lnrs_anon_uq_vital_observation",
            set_={
                "item_name": stmt.excluded.item_name,
                "item_result": stmt.excluded.item_result,
                "item_result_value": stmt.excluded.item_result_value,
                "item_unit": stmt.excluded.item_unit,
                "obs_time": stmt.excluded.obs_time,
                "obs_detail_json": stmt.excluded.obs_detail_json,
                "created_batch_id": stmt.excluded.created_batch_id,
            },
        )
        await db.execute(stmt)

    log.info(f"ETL2: {center_code}/{src_table} 导入 {imported} 行 vital_observation({obs_type})")
    return imported


# --------------------------------------------------------------------------- #
# 中心级主入口
# --------------------------------------------------------------------------- #

# 每中心的数据处理规则。
#
# 多中心扩展（ADR-0009）：新医院接入只需在下方添加一项，配置项含义：
#   - src_table:    parquet 文件名（不含 .parquet 后缀）
#   - kind:         patient / exam_text / surgery / visit_detail / lab / order /
#                   diagnosis / document / history / observation
#   - exam_type:    exam_text 的检查类型（CT/Pathology/Genetic/IHC/PETCT/Radiology/
#                   Ultrasound，必须是 med_exam_type 字典中的 dict_value）
#   - id_field:     exam_text 的主键列名（parquet 中的 exam_id/specimen_id/test_id/report_id）
#   - body_fields:  拼接进 report_text.body_clean 的正文列（无则 []）
#   - detail_type:  exam_detail.detail_type（如 pathology/genetic/ihc/nodule_imaging）
#   - detail_fields:落进 exam_detail.detail_json 的结构化列名（无则不写 detail）
#   - date_field:   exam_date 来源列；空串 "" 表示反查日期：
#                     * date_lookup_field 未设 → 反查同 id_field 的已入库 exam 日期
#                       （如 ihc 无日期列，复用 pathology 的 specimen_id 日期）
#                     * date_lookup_field="visit_id" → 按 visit_id 反查 visit_detail 的
#                       admission_time（省医 pathology 所有日期列空，反查 visit 兜底）
#   - ordinal_field:标识"同 exam 多实例展开"的列名（如 nodule_imaging 的 nodule_no）。
#                   设置后每行 parquet 生成一条 exam_detail（1:N），detail_ordinal
#                   从该字段值解析数字（'n1'→1, 'n2'→2）。不设置则同 anon_exam_id
#                   只生成一条 detail（detail_ordinal=1）。
#   - order_type / order_name_field: kind=order 时必填，区分 drug/non_drug 及名称列
#   - order_hash_extra: kind=order，source_order_hash 追加 patient+order_detail（省医全量）
#   - source_label:   kind=diagnosis 时必填，区分来源（diagnosis / inpatient_front_page）
#   - obs_type:       kind=observation 时必填（nursing / icu / anesthesia）
#   - visit_detail / lab / order / diagnosis / document / history / observation
#     为省医(shengyi)扩展，珠江(zhujiang)/新桥(xinqiao)不用
#
# 前置条件：center_code 必须先在 med_hospital 注册（见 0008/0009 种子 SQL），
# 且该 hospital_id 下 med_dict_mapping 已灌入对应 raw_label → dict_value 映射规则。
_CENTER_PARQUET_SPECS: dict[str, list[dict[str, Any]]] = {
    "shengyi": [
        # 1. patient 先导（后续表依赖 patient FK）
        {"src_table": "patient", "kind": "patient"},
        # 2. visit_detail 建立 visit 桥 + 富信息（pathology 依赖它反查日期）
        {
            "src_table": "visit_record", "kind": "visit_detail",
            "id_field": "visit_id", "date_field": "admission_time",
        },
        # 3. 病理：检查日期 54.5% 空 / 报告日期 100% 空 → 适配层
        #    coalesce(检查日期, 报告日期, visit 入院时间) 回填 100%
        {
            "src_table": "pahology_specimen", "kind": "exam_text",
            "exam_type": "Pathology", "id_field": "specimen_id",
            "body_fields": ["pathology_diagnosis"],
            "detail_type": "pathology",
            "detail_fields": [
                "specimen_name", "exam_type", "exam_detail",
                "pathology_diagnosis",
            ],
            "date_field": "exam_date",
        },
        # 4. 影像：检查类型名称为自由文本，适配层按关键词规则归一化进 exam_type 列
        #    （CT/PETCT/MR/Radiology/Ultrasound/Other），引擎行级精确匹配字典值
        {
            "src_table": "imaging_report", "kind": "exam_text",
            "exam_type": "Radiology", "exam_type_field": "exam_type",
            "id_field": "report_id",
            "body_fields": ["exam_detail.findings", "exam_detail.impression"],
            "detail_type": "imaging_report",
            "detail_fields": ["exam_type", "exam_body_part", "exam_item", "exam_detail"],
            "date_field": "exam_date",
        },
        # 5. 超声：适配层按报告号聚合检查子项（1.56M 子项 → 181k 报告）
        {
            "src_table": "ultrasound_report", "kind": "exam_text",
            "exam_type": "Ultrasound", "id_field": "report_id",
            "body_fields": ["ultrasound_finding"],
            "detail_type": "ultrasound",
            "detail_fields": ["exam_name", "body_part", "exam_detail"],
            "date_field": "exam_date",
        },
        # 6. 心电图：适配层按报告号聚合检查子项（1.74M 子项 → 149k 报告）；
        #    ECG 为 0015 新增字典值
        {
            "src_table": "ecg_report", "kind": "exam_text",
            "exam_type": "ECG", "id_field": "report_id",
            "body_fields": ["ecg_diagnosis"],
            "detail_type": "ecg",
            "detail_fields": ["sub_items"],
            "date_field": "exam_date",
        },
        # 7. 基因检测：仅 SNV/CNV 两个有效检测单号文件（其余 4 文件 226 行全空单号，
        #    适配层跳过）；无日期列 → date_lookup_field 反查 visit 入院时间
        {
            "src_table": "genetic_report", "kind": "exam_text",
            "exam_type": "Genetic", "id_field": "report_id",
            "body_fields": [],
            "detail_type": "genetic",
            "detail_fields": ["test_name", "variants"],
            "date_field": "", "date_lookup_field": "visit_id",
        },
        # 8. 手术：适配层合并 手术信息（无就诊编号，(患者,手术日期) join 回填 visit_id）
        #    + 住院病案首页.手术（自带就诊编号）；守卫要求 patient+visit+名称三非空
        {"src_table": "surgery_record", "kind": "surgery"},
        # 9-12. 检验：44M 行拆 4 片防单文件内存峰值超限（每片 ~11M）
        {"src_table": "lab_result_p1", "kind": "lab", "id_field": "report_id"},
        {"src_table": "lab_result_p2", "kind": "lab", "id_field": "report_id"},
        {"src_table": "lab_result_p3", "kind": "lab", "id_field": "report_id"},
        {"src_table": "lab_result_p4", "kind": "lab", "id_field": "report_id"},
        # 13-16. 医嘱：patient+order_detail 进哈希（吸收跨患者碰撞 + 按就诊展开重复）
        {
            "src_table": "drug_order", "kind": "order",
            "order_type": "drug", "order_name_field": "order_name",
            "order_hash_extra": True,
        },
        {
            "src_table": "no_drug_order", "kind": "order",
            "order_type": "non_drug", "order_name_field": "order_name",
            "order_hash_extra": True,
        },
        # 17. 门诊药物处方：就诊编号 100% 空 → 只挂 patient；处方编号 100% 唯一
        {
            "src_table": "outp_order", "kind": "order",
            "order_type": "drug", "order_name_field": "order_name",
            "order_hash_extra": True,
        },
        # 18. 麻醉用药记录（术中用药 → order detail）
        {
            "src_table": "anesthesia_order", "kind": "order",
            "order_type": "drug", "order_name_field": "order_name",
            "order_hash_extra": True,
        },
        # 19-20. 诊断（两来源，source_label 区分；病案首页上下文落 detail）
        {
            "src_table": "diagnosis", "kind": "diagnosis",
            "source_label": "diagnosis",
        },
        {
            "src_table": "diagnosis_inpatient", "kind": "diagnosis",
            "source_label": "inpatient_front_page",
            "detail_fields": ["detail"],
        },
        # 21. 病程记录文档：5.16M（2.48M 空内容随全量入库）
        {"src_table": "clinical_document", "kind": "document"},
        # 22. 就诊病史：1.4M
        {"src_table": "medical_history", "kind": "history"},
        # 23-25. 观察测量（护理/ICU/麻醉子项，obs_type 区分；
        #       护理报告级就诊编号 100% 非空挂 visit，ICU/麻醉无就诊编号）
        {
            "src_table": "nursing_observation", "kind": "observation",
            "obs_type": "nursing", "detail_fields": ["detail"],
        },
        {
            "src_table": "icu_observation", "kind": "observation",
            "obs_type": "icu", "detail_fields": ["detail"],
        },
        {
            "src_table": "anesthesia_observation", "kind": "observation",
            "obs_type": "anesthesia", "detail_fields": ["detail"],
        },
    ],
    "xinqiao": [
        # 2026-09-04 extracted_tables 批次（ct/pathology/genetics 3 表，无 patient 表，
        # 患者由 exam 占位路径发号）：staging 与珠江 0825 同构，
        # 适配脚本 backend/etl2/etl1_adapt_xinqiao_{ct,pathology,genetics}.py
        {"src_table": "patient", "kind": "patient"},
        {
            "src_table": "nodule_imaging",
            "kind": "exam_text",
            "exam_type": "CT",
            "id_field": "exam_id",
            # 源 raw_text 为中文标题（检查所见/检查结论），适配层已切分为
            # findings/impression（珠江 DESCRIPTION/IMPRESSION 正则对 124k 行 0 命中）
            "body_fields": ["findings", "impression"],
            "detail_type": "nodule_imaging",
            "detail_fields": [
                "nodule_no", "nodule_location", "long_diameter", "density_type",
                "exam_meta", "nodule_morphology",
                "raw_text",
            ],
            "ordinal_field": "nodule_no",
        },
        {
            "src_table": "pathology_specimen",
            "kind": "exam_text",
            "exam_type": "Pathology",
            # 源文件无 exam_id：适配层按 (patient_id, exam_date, 送检部位)
            # 合成确定性 specimen_id（跨行同组 exam 合并，同珠江 0825 病理模式）
            "id_field": "specimen_id",
            "body_fields": ["histology_class"],
            "detail_type": "pathology",
            "detail_fields": [
                # 送检部位（组织病理/冰冻切片）珠江源文件没有，新桥专有列
                "submit_site", "frozen", "multi_nodules",
                "specimen_type", "sampling_site",
                "specimens",
                "raw_text",
            ],
        },
        {
            "src_table": "genetic_test",
            "kind": "exam_text",
            "exam_type": "Genetic",
            # 源文件无 exam_id：适配层按 (patient_id, exam_date,
            # sample_source, test_method) 合成确定性 test_id（四元组行级唯一）
            "id_field": "test_id",
            "body_fields": [],
            "detail_type": "genetic",
            "detail_fields": [
                "test_meta", "variant_result",
                "driver_mutations", "immune_markers",
            ],
            "date_field": "test_date",
        },
    ],
    "zhujiang": [
        {"src_table": "patient", "kind": "patient"},
        {
            "src_table": "nodule_imaging",
            "kind": "exam_text",
            "exam_type": "CT",
            "id_field": "exam_id",
            # 0719 全量文件是文本报告 schema（findings/impression 列，无结节结构列）；
            # 0723 sample 宽表则相反（无正文列，结节结构落 detail）。body_fields 同时
            # 覆盖两者：全量文件正文进 report_text，sample 缺列时 parts 为空、body=""。
            "body_fields": ["findings", "impression"],
            # detail_fields：sample 宽表结构列 + 全量文件 raw_text（原始报告全文，
            # 2026-08-25 补：与 findings/impression 提取正文并存，留档未加工原文）。
            # Rev 2026-07-24: ordinal_field=nodule_no 实现 1:N 展开
            #   同一 CT exam 下的 n1/n2/n3/n4 多结节各生成一行 detail
            #   标量字段（nodule_no/nodule_location/long_diameter/density_type）
            #   原来丢失，现在随 detail_json 一起落库
            "detail_type": "nodule_imaging",
            "detail_fields": [
                "nodule_no", "nodule_location", "long_diameter", "density_type",
                "exam_meta", "nodule_morphology",
                "nodule_quantitative", "follow_up_comparison",
                "raw_text",
            ],
            "ordinal_field": "nodule_no",
        },
        # 0901 批次 imaging_report（2026-09-02 重建：原 spec 随引擎文件外部覆盖丢失，
        # 字段按 09-01 staging 设计复原：适配层将 检查类型名称 关键词归一化进 exam_type，
        # 正文 findings/impression，raw_text 原文留档，lung_rads 结构化肺结节评估）
        {
            "src_table": "imaging_report",
            "kind": "exam_text",
            "exam_type": "Radiology",
            "exam_type_field": "exam_type",
            "id_field": "exam_id",
            "body_fields": ["findings", "impression"],
            "detail_type": "imaging_report",
            "detail_fields": ["exam_type", "exam_body_part", "exam_item", "lung_rads", "raw_text"],
            "date_field": "exam_date",
        },
        {
            "src_table": "pathology_specimen",
            "kind": "exam_text",
            "exam_type": "Pathology",
            "id_field": "specimen_id",
            "body_fields": ["histology_class"],
            # 诊断文本由宽表 histology_class 提供；深层病理结构落 exam_detail JSONB
            "detail_type": "pathology",
            "detail_fields": [
                "specimen_meta", "adenocarcinoma_subtypes", "tumor_measurement",
                "high_risk_factors", "staging",
                # Rev 2026-07-24: 补 specimen_type（肺叶/穿刺/淋巴结）+ sampling_site（解剖部位），
                # 这两个标量列非空率分别 15/39、29/39，是病理核心结构化字段，原遗漏未落库
                "specimen_type", "sampling_site",
                # Rev 2026-08-25 (0825 批次): 全量病理文件为 exam 级 + specimens[] 数组，
                # 完整标本数组原样落库（同 ct0820 nodule_morphology 模式）
                "specimens",
                # 2026-08-25: 原始报告全文落库（findings/impression 之外的未加工原文）
                "raw_text",
            ],
        },
        # 医疗宽表直入扩展：基因检测 / 免疫组化 / 手术记录
        {
            "src_table": "genetic_test",
            "kind": "exam_text",
            "exam_type": "Genetic",
            "id_field": "test_id",
            "body_fields": [],
            "detail_type": "genetic",
            "detail_fields": [
                "test_meta", "variant_result",
                "driver_mutations", "immune_markers",
            ],
            "date_field": "test_date",
        },
        {
            "src_table": "ihc_result",
            "kind": "exam_text",
            "exam_type": "IHC",
            "id_field": "specimen_id",
            "body_fields": [],
            "detail_type": "ihc",
            "detail_fields": [
                "ki67_pct", "pdl1_tps_pct", "pdl1_clone", "pdl1_cps",
                "alk_ihc", "ttf1", "napsina", "p40", "p53",
                # 2026-08-25: 原始报告全文落库（重复 exam 取结构化字段非空数最高行的 raw_text）
                "raw_text",
            ],
            "date_field": "exam_date",  # 0825 全量文件自带日期列（反查方案会丢弃 25 条无病理匹配行）
        },
        # 住院记录（0825 批次）：通用 visit_detail，chief_complaint/present_illness/
        # diagnoses[]/raw_text 原样进 visit_detail_json
        {
            "src_table": "inpatient", "kind": "visit_detail",
            "id_field": "inpatient_id", "date_field": "inpatient_date",
        },
        {
            "src_table": "surgery_record",
            "kind": "surgery",
        },
    ],
    # 301（nested parquet 批次，2026-09-01）：见 .claude/skills/nested-parquet-301-import
    # 与适配脚本 backend/etl1_adapt_hos301_exam.py；exam_type 由行内 examType 列
    # 经 med_dict_mapping（0013 种子）归一化（CT/Pathology/Ultrasound/其他→Other）
    "hos301": [
        # patient 无 parquet（数据目录缺文件跳过；患者由 visit/exam 占位路径入库）
        {"src_table": "patient", "kind": "patient"},
        {
            "src_table": "visit_record", "kind": "visit_detail",
            "id_field": "visit_id", "date_field": "admission_time",
        },
        {
            "src_table": "exam", "kind": "exam_text",
            "exam_type": "Other", "exam_type_field": "examType",
            "id_field": "exam_id",
            "body_fields": ["impression", "description", "recommendation"],
            "detail_type": "exam",
            "detail_fields": [
                "examClass", "examPara", "examSubClass", "examItem",
                "performedBy", "reqDept", "examDateTime", "reqDateTime",
            ],
            "date_field": "examDateTime",
        },
        {"src_table": "lab_result", "kind": "lab", "id_field": "test_id"},

        {
            "src_table": "order", "kind": "order",
            "order_type": "non_drug", "order_name_field": "task_name",
            # 301 staging 同 (time, name, type) 多达 22 次重复（一次开多条同医嘱），
            # source_order_hash 默认 4 元组 (center,time,name,type) 会全部合并为 1 行
            # 丢失数据。Rev 2026-09-02 起追加 patient_id 段，让哈希区分同患者不同行。
            "order_hash_extra": True,
        },
    ],
}


async def import_center(
    db: AsyncSession,
    *,
    center_code: str,
    data_dir: Path,
    batch_id: str,
    on_progress: Callable[[str, int], Any] | None = None,
) -> dict[str, int]:
    """导入单中心全部 parquet → lnrs_anon_*，返回 {src_table: rows}。

    顺序：先 patient，再 exam_text/visit_detail（依赖 patient）。
    visit_record：若该中心配置了 kind=visit_detail 的 spec 则正常处理（省医），
    否则显式跳过（珠江，ADR-0006 visit 桥未启用）。
    """

    # 大数据量 commit 加速：当前事务内关闭同步落盘。
    # SET LOCAL 作用域限定到当前事务，事务结束（commit/rollback）自动复原，
    # 不会污染同一连接上的查询 API 调用。
    # 代价：DB crash 时本事务已 ACK 但未刷盘的最后 WAL 段会丢失 → ETL 重跑幂等即可吸收。
    # 环境变量 LNRS_ETL_FSYNC=1 强制恢复同步落盘（用于对比 commit 耗时或复现 on 行为）。
    import os
    fsync_off = os.environ.get("LNRS_ETL_FSYNC", "0") != "1"
    if fsync_off:
        try:
            await db.execute(text("SET LOCAL synchronous_commit = off"))
            log.info(
                f"ETL2: {center_code} 事务内 synchronous_commit=off "
                f"（commit 不等 fsync；崩溃丢失风险由重跑幂等吸收）"
            )
        except Exception as e:
            # PG 版本不支持或权限不足 → 回退到 on（保持原行为，不阻断导入）
            log.warning(f"ETL2: {center_code} 关闭 synchronous_commit 失败，回退默认: {e}")

    if not data_dir.exists():
        raise FileNotFoundError(f"中心数据目录不存在: {data_dir}")

    # 解析 hospital_id（找不到抛错，不退化）；预热全部枚举映射（限定到本 hospital）
    hospital_id = await _resolve_hospital_id(db, center_code)
    from .enum_normalization import load_all_enum_mappings
    await load_all_enum_mappings(db, hospital_id=hospital_id)


    result: dict[str, int] = {}
    specs = _CENTER_PARQUET_SPECS.get(center_code)
    if not specs:
        log.warning(f"ETL2: 未知中心 {center_code}，无处理规则")
        return result

    # 是否有中心主动处理 visit_record（省医扩展）。若无，则对 visit_record 显式跳过。
    visit_detail_enabled = any(
        s.get("src_table") == "visit_record" and s.get("kind") == "visit_detail"
        for s in specs
    )
    if not visit_detail_enabled:
        visit_pq = data_dir / "visit_record.parquet"
        if visit_pq.exists():
            log.info(
                f"ETL2: {center_code}/visit_record.parquet 存在（{visit_pq.stat().st_size} 字节）"
                f"，本轮跳过——ADR-0006 visit 桥未启用"
            )

    for spec in specs:
        src_table = spec["src_table"]
        if not _SRC_TABLE_RE.match(src_table):
            raise ValueError(f"非法源表名: {src_table!r}")
        parquet_path = (data_dir / f"{src_table}.parquet").resolve()
        if not parquet_path.exists():
            log.warning(f"ETL2: {center_code}/{src_table}.parquet 不存在，跳过")
            continue

        try:
            if spec["kind"] == "patient":
                n = await _import_patient_table(
                    db,
                    center_code=center_code,
                    parquet_path=parquet_path,
                    batch_id=batch_id,
                    hospital_id=hospital_id,
                )
            elif spec["kind"] == "exam_text":
                n = await _import_exam_text_table(
                    db,
                    center_code=center_code,
                    parquet_path=parquet_path,
                    src_table=src_table,
                    exam_type=spec["exam_type"],
                    exam_type_field=spec.get("exam_type_field"),
                    hospital_id=hospital_id,
                    id_field=spec["id_field"],
                    body_fields=spec["body_fields"],
                    batch_id=batch_id,
                    detail_type=spec.get("detail_type"),
                    detail_fields=spec.get("detail_fields"),
                    date_field=spec.get("date_field", "exam_date"),
                    ordinal_field=spec.get("ordinal_field"),
                    date_lookup_field=spec.get("date_lookup_field"),
                )
            elif spec["kind"] == "surgery":
                n = await _import_surgery_table(
                    db,
                    center_code=center_code,
                    parquet_path=parquet_path,
                    src_table=src_table,
                    batch_id=batch_id,
                )
            elif spec["kind"] == "visit_detail":
                n = await _import_visit_detail_table(
                    db,
                    center_code=center_code,
                    parquet_path=parquet_path,
                    src_table=src_table,
                    id_field=spec.get("id_field", "visit_id"),
                    date_field=spec.get("date_field", "admission_time"),
                    batch_id=batch_id,
                )
            elif spec["kind"] == "lab":
                n = await _import_lab_table(
                    db,
                    center_code=center_code,
                    parquet_path=parquet_path,
                    src_table=src_table,
                    id_field=spec.get("id_field", "report_id"),
                    batch_id=batch_id,
                )
            elif spec["kind"] == "order":
                n = await _import_order_table(
                    db,
                    center_code=center_code,
                    parquet_path=parquet_path,
                    src_table=src_table,
                    order_type=spec["order_type"],
                    order_name_field=spec["order_name_field"],
                    order_hash_extra=spec.get("order_hash_extra", False),
                    batch_id=batch_id,
                )
            elif spec["kind"] == "diagnosis":
                n = await _import_diagnosis_table(
                    db,
                    center_code=center_code,
                    parquet_path=parquet_path,
                    src_table=src_table,
                    source_label=spec["source_label"],
                    batch_id=batch_id,
                    detail_fields=spec.get("detail_fields"),
                )
            elif spec["kind"] == "document":
                n = await _import_document_table(
                    db,
                    center_code=center_code,
                    parquet_path=parquet_path,
                    src_table=src_table,
                    batch_id=batch_id,
                )
            elif spec["kind"] == "history":
                n = await _import_history_table(
                    db,
                    center_code=center_code,
                    parquet_path=parquet_path,
                    src_table=src_table,
                    batch_id=batch_id,
                )
            elif spec["kind"] == "observation":
                n = await _import_observation_table(
                    db,
                    center_code=center_code,
                    parquet_path=parquet_path,
                    src_table=src_table,
                    obs_type=spec["obs_type"],
                    batch_id=batch_id,
                    detail_fields=spec.get("detail_fields"),
                )
            else:
                log.error(f"ETL2: 未知 spec.kind={spec['kind']}")
                continue
            result[src_table] = n
            if on_progress:
                if asyncio.iscoroutinefunction(on_progress):
                    await on_progress(src_table, n)
                else:
                    on_progress(src_table, n)
        except Exception as e:
            log.error(f"ETL2: 导入 {center_code}/{src_table} 失败: {e!s}")
            result[src_table] = 0
            raise

    return result
