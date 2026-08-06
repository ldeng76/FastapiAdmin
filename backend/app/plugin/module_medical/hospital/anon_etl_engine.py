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
import re
from datetime import date
from pathlib import Path
from typing import Any, Callable

import duckdb
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import log

from .anon_model import (
    AnonExamDetailModel,
    AnonExamModel,
    AnonLabResultModel,
    AnonOrderModel,
    AnonPatientModel,
    AnonPhiAuditModel,
    AnonReportTextModel,
    AnonSurgeryModel,
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
    source_exam_hash,
    source_lab_hash,
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


async def _batch_upsert_lab_results(
    db: AsyncSession,
    *,
    lab_rows: list[dict[str, Any]],
) -> None:
    """批量 upsert lab_result 行（省医扩展）。

    冲突键：(anon_visit_id, source_lab_hash)（DDL UNIQUE lnrs_anon_uq_lab_result）。
    anon_visit_id 可空：NULL 不参与 UNIQUE 冲突，visit 缺失的行各自独立插入。
    """
    if not lab_rows:
        return
    for i in range(0, len(lab_rows), BATCH_SIZE):
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


async def _batch_upsert_orders(
    db: AsyncSession,
    *,
    order_rows: list[dict[str, Any]],
) -> None:
    """批量 upsert order 行（省医扩展，drug + non_drug 合并）。

    冲突键：(anon_visit_id, source_order_hash)（DDL UNIQUE lnrs_anon_uq_order）。
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


async def _import_exam_text_table(
    db: AsyncSession,
    *,
    center_code: str,
    parquet_path: Path,
    src_table: str,
    exam_type: str,
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
    """
    cols, rows = await _read_parquet_async(parquet_path)
    if not rows:
        log.warning(f"ETL2: {center_code}/{src_table}.parquet 无数据，跳过")
        return 0

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
                stmt = select(
                    AnonVisitDetailModel.anon_visit_id,
                    AnonVisitDetailModel.admission_time,
                ).where(AnonVisitDetailModel.anon_visit_id.in_(list(anon_visit_ids.keys())))
                for r in (await db.execute(stmt)).fetchall():
                    if r.admission_time:
                        visit_date_lookup[anon_visit_ids[r.anon_visit_id]] = r.admission_time
        else:
            # ihc 等无日期列的表：预加载同 id_field 已入库 exam 的日期，供反查
            anon_exam_ids_for_lookup = [
                compute_anon_exam_id(center_code, str(_row_to_dict(cols, row).get(id_field)))
                for row in rows
                if _row_to_dict(cols, row).get(id_field)
            ]
            if anon_exam_ids_for_lookup:
                stmt = select(AnonExamModel.anon_exam_id, AnonExamModel.exam_date).where(
                    AnonExamModel.anon_exam_id.in_(anon_exam_ids_for_lookup)
                )
                for row in (await db.execute(stmt)).fetchall():
                    exam_date_lookup[row.anon_exam_id] = row.exam_date
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
                "exam_type": exam_type,
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
        stmt = select(AnonVisitModel.anon_visit_id).where(
            AnonVisitModel.anon_visit_id.in_(list(anon_visit_ids.keys()))
        )
        for (aevid,) in (await db.execute(stmt)).fetchall():
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
        num_val = None
        raw_val = rd.get("item_result_value")
        if raw_val is not None:
            try:
                num_val = float(raw_val)
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
                "test_name": _clean_str(rd.get("test_name")),
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
    batch_id: str,
) -> int:
    """导入 drug_order / no_drug_order.parquet → lnrs_anon_order（省医扩展）。

    drug + non_drug 合并一表，order_type 区分。
    挂在 visit 下（anon_visit_id 可空，visit_id 缺失时退化为只挂 patient）。
    守卫顺序：先收集 patient，再按 visit_id 决定是否建桥（同 lab）。
    order_name_field 参数化：drug_order 用 drug_generic_name，no_drug_order 用 order_name。
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
        stmt = select(AnonVisitModel.anon_visit_id).where(
            AnonVisitModel.anon_visit_id.in_(list(anon_visit_ids.keys()))
        )
        for (aevid,) in (await db.execute(stmt)).fetchall():
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

        src_hash = source_order_hash(
            center_code, order_time_str, str(order_name), order_type
        )
        dedup_key = (anon_visit_id, src_hash)
        if dedup_key in seen_order_hash:
            continue
        seen_order_hash.add(dedup_key)

        # order_detail struct 忠实保留
        order_detail = rd.get("order_detail")
        order_detail_json = (
            _json_safe(order_detail) if isinstance(order_detail, dict) else None
        )

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
# 中心级主入口
# --------------------------------------------------------------------------- #

# 每中心的数据处理规则。
#
# 多中心扩展（ADR-0009）：新医院接入只需在下方添加一项，配置项含义：
#   - src_table:    parquet 文件名（不含 .parquet 后缀）
#   - kind:         patient / exam_text / surgery / visit_detail / lab / order
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
#   - visit_detail / lab / order 为省医(shengyi)扩展，珠江(zhujiang)不用
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
        # 3. 病理：所有日期列空，date_field="" + date_lookup_field 反查 visit admission_time
        {
            "src_table": "pahology_specimen", "kind": "exam_text",
            "exam_type": "Pathology", "id_field": "specimen_id",
            "body_fields": ["pathology_diagnosis"],
            "detail_type": "pathology",
            "detail_fields": [
                "specimen_name", "exam_type", "exam_detail",
                "pathology_diagnosis", "tumor_total_size_mm",
            ],
            "date_field": "", "date_lookup_field": "visit_id",
        },
        # 4. 影像报告：自带 exam_date（文本报告，非结节结构化表）
        {
            "src_table": "imaging_report", "kind": "exam_text",
            "exam_type": "Radiology", "id_field": "report_id",
            "body_fields": ["exam_detail.findings", "exam_detail.impression"],
            "detail_type": "imaging_report",
            "detail_fields": ["exam_type", "exam_body_part", "exam_item", "exam_detail"],
            "date_field": "exam_date",
        },
        # 5. 超声：自带 exam_date
        {
            "src_table": "ultrasound_report", "kind": "exam_text",
            "exam_type": "Ultrasound", "id_field": "report_id",
            "body_fields": ["ultrasound_finding"],
            "detail_type": "ultrasound",
            "detail_fields": ["exam_name", "body_part", "exam_detail"],
            "date_field": "exam_date",
        },
        # 6. 手术（3/5 空脏数据会被守卫跳过，visit_id 缺失的行静默丢弃）
        {"src_table": "surgery_record", "kind": "surgery"},
        # 7. 检验（visit_id 全非空，100% join visit 桥）
        {"src_table": "lab_result", "kind": "lab", "id_field": "report_id"},
        # 8-9. 医嘱（drug + non_drug 合并，visit_id 缺失时退化为只挂 patient）
        {
            "src_table": "drug_order", "kind": "order",
            "order_type": "drug", "order_name_field": "drug_generic_name",
        },
        {
            "src_table": "no_drug_order", "kind": "order",
            "order_type": "non_drug", "order_name_field": "order_name",
        },
    ],
    "xinqiao": [
        {"src_table": "patient", "kind": "patient"},
        {
            "src_table": "nodule_imaging",
            "kind": "exam_text",
            "exam_type": "CT",
            "id_field": "exam_id",
            "body_fields": ["impression", "findings"],
        },
        {
            "src_table": "pathology_specimen",
            "kind": "exam_text",
            "exam_type": "Pathology",
            "id_field": "specimen_id",
            "body_fields": ["pathology_diagnosis", "gross_findings", "microscopic_findings"],
        },
    ],
    "zhujiang": [
        {"src_table": "patient", "kind": "patient"},
        {
            "src_table": "nodule_imaging",
            "kind": "exam_text",
            "exam_type": "CT",
            "id_field": "exam_id",
            "body_fields": [],
            # 宽表未提供正文列，结构化字段落 exam_detail JSONB
            # Rev 2026-07-24: ordinal_field=nodule_no 实现 1:N 展开
            #   同一 CT exam 下的 n1/n2/n3/n4 多结节各生成一行 detail
            #   标量字段（nodule_no/nodule_location/long_diameter/density_type）
            #   原来丢失，现在随 detail_json 一起落库
            "detail_type": "nodule_imaging",
            "detail_fields": [
                "nodule_no", "nodule_location", "long_diameter", "density_type",
                "exam_meta", "nodule_morphology",
                "nodule_quantitative", "follow_up_comparison",
            ],
            "ordinal_field": "nodule_no",
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
            ],
            "date_field": "",  # ihc 无日期列，反查同 specimen_id 的 pathology exam 日期
        },
        {
            "src_table": "surgery_record",
            "kind": "surgery",
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
                    batch_id=batch_id,
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
