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
    AnonExamModel,
    AnonPatientModel,
    AnonPhiAuditModel,
    AnonReportTextModel,
)
from .anonymize import (
    CLEAN_METHOD_REGEX_ONLY,
    birth_date_from,
    compute_anon_exam_id,
    compute_anon_id,
    hash_for_audit,
    normalize_sex,
    normalize_ethnicity,
    normalize_smoking_status,
    normalize_abo_blood_type,
    normalize_rh_blood_type,
    source_exam_hash,
    truncate_body,
)

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


# --------------------------------------------------------------------------- #
# patient 批量三态机
# --------------------------------------------------------------------------- #


async def _batch_upsert_patients(
    db: AsyncSession,
    *,
    center_code: str,
    patient_records: list[dict[str, Any]],
    batch_id: str,
) -> dict[str, str]:
    """批量处理病人，返回 {anon_id: patient_id} 映射。

    patient_records: [{"local_id", "anon_id", "sex", "birth_date", "ethnicity", "smoking_status", "abo_blood_type", "rh_blood_type"}]
    三态机（ADR-0006 Rev 2026-07-19 §1-4）：
    - 活行：UPDATE last_seen + sex/birth_date
    - 软删：复活（清空 deleted_*）
    - 新：nextval 发号 + INSERT
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
        update_columns = {
                "last_seen_batch_id": stmt.excluded.last_seen_batch_id,
                "sex": stmt.excluded.sex,
                "birth_date": stmt.excluded.birth_date,
                "ethnicity": stmt.excluded.ethnicity,
                "smoking_status": stmt.excluded.smoking_status,
                "abo_blood_type": stmt.excluded.abo_blood_type,
                "rh_blood_type": stmt.excluded.rh_blood_type,
                "deleted_at": None,
                "deleted_reason": None,
                "deleted_batch_id": None,
            }
        stmt = stmt.on_conflict_do_update(
            constraint="lnrs_anon_uq_patient_center",
            set_=update_columns,
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

    ON CONFLICT (center_code, source_exam_hash) DO UPDATE last_seen + 关键字段。
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
                "exam_type": stmt.excluded.exam_type,
                "patient_id": stmt.excluded.patient_id,
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
# 单表导入
# --------------------------------------------------------------------------- #


async def _import_patient_table(
    db: AsyncSession,
    *,
    center_code: str,
    parquet_path: Path,
    batch_id: str,
) -> int:
    """导入 patient.parquet → lnrs_anon_patient（批量）。返回入库（去重后）行数。"""
    cols, rows = await _read_parquet_async(parquet_path)
    if not rows:
        log.warning(f"ETL2: {center_code}/patient.parquet 无数据，跳过")
        return 0

    # 预计算所有 patient 记录 + phi_audit
    patient_records: list[dict[str, Any]] = []
    audit_records: list[dict[str, Any]] = []
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
        patient_records.append(
            {
                "local_id": str(local_pid),
                "anon_id": anon_id,
                "sex": normalize_sex(rd.get("gender")),
                "ethnicity": normalize_ethnicity(rd.get("ethnicity")),
                "smoking_status": normalize_smoking_status(rd.get("smoking_status")),
                "abo_blood_type": normalize_abo_blood_type(rd.get("abo_blood_type")),
                "rh_blood_type": normalize_rh_blood_type(rd.get("rh_blood_type")),
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
    imported = len({r["anon_id"] for r in patient_records})
    log.info(
        f"ETL2: {center_code}/patient 导入 {imported} 行（去重前 {len(patient_records)}）"
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
) -> int:
    """通用：把 nodule_imaging / pathology_specimen 批量落 exam + report_text。"""
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
    imported = 0

    for row in rows:
        rd = _row_to_dict(cols, row)
        local_pid = rd.get("patient_id")
        local_exam = rd.get(id_field)
        exam_date = rd.get("exam_date")

        if not local_pid or not local_exam:
            continue
        if not isinstance(exam_date, date):
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
            {"local_id": str(local_pid), "anon_id": anon_id, "sex": "U", "birth_date": None}
        )

        if anon_exam_id in seen_exam_anon:
            continue  # 同源重复 exam_id（zhujiang 12 dup），跳后续构造
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

        # 拼接正文
        parts: list[str] = []
        for f in body_fields:
            v = rd.get(f)
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
            if rd.get(f):
                audit_records.append(
                    {
                        "source_table": src_table,
                        "source_field": f,
                        "source_hash": hash_for_audit(rd.get(f)),
                        "strategy": "llm_replace",
                        "confidence": 0.0,
                    }
                )
        imported += 1

    # 1. 先 upsert 所有 exam 涉及的病人（确保 FK 存在）
    pid_map = await _batch_upsert_patients(
        db, center_code=center_code, patient_records=exam_patient_records, batch_id=batch_id
    )

    # 2. 回填 exam_rows 的 patient_id（去掉临时键）
    for er in exam_rows:
        er["patient_id"] = pid_map[er["_anon_id"]]
        del er["_anon_id"]

    # 3. 批量 upsert exam + report_text + phi_audit
    await _batch_upsert_exams(db, exam_rows=exam_rows)
    await _batch_upsert_report_text(db, report_rows=report_rows)
    await _write_phi_audit_batch(db, batch_id=batch_id, records=audit_records)

    log.info(f"ETL2: {center_code}/{src_table} 导入 {imported} 行 exam+report")
    return imported


# --------------------------------------------------------------------------- #
# 中心级主入口
# --------------------------------------------------------------------------- #

# 每中心的数据处理规则（visit_record 不在内：本轮跳过）
_CENTER_PARQUET_SPECS: dict[str, list[dict[str, Any]]] = {
    "shengyi": [
        {"src_table": "patient", "kind": "patient"},
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
            "body_fields": ["impression", "findings"],
        },
        {
            "src_table": "pathology_specimen",
            "kind": "exam_text",
            "exam_type": "Pathology",
            "id_field": "specimen_id",
            "body_fields": ["pathology_diagnosis"],
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

    顺序：先 patient，再 exam_text（依赖 patient）。
    visit_record 存在则显式跳过。
    """
    if not data_dir.exists():
        raise FileNotFoundError(f"中心数据目录不存在: {data_dir}")

    # 预热全部有限枚举映射，归一化只查内存缓存。
    from .enum_normalization import load_all_enum_mappings
    await load_all_enum_mappings(db)


    result: dict[str, int] = {}
    specs = _CENTER_PARQUET_SPECS.get(center_code)
    if not specs:
        log.warning(f"ETL2: 未知中心 {center_code}，无处理规则")
        return result

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
