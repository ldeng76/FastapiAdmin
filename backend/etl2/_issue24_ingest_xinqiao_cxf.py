"""Issue 24: cxf_archives 7,984 study 入库 — ct_mapped 解锁外部映射阻塞。

背景
----
``/data/wlx/DATABASE/03_disk/xinqiao/3_cxf_archives/`` 的 7,984 个 study 因 DICOM
header 全去身份（PatientID 全空）被 issue-18 阻塞。``ct_mapped.parquet``（CT 报告
+DICOM 合并导出，2026-09-20 就位）中 ``exam_id = StudyInstanceUID`` 的行直接携带
院内 ``patient_id`` + ``path[]`` 全量 .dcm 文件路径 + ``file_count``（= series 数）
+ ``total_size_bytes``，入库无需遍历 1,016 GB 磁盘。

PRD: docs/etl2/prd/issue-24-xinqiao-cxf-ingest-via-ct-mapped.md

端到端行为
----------
7,984 个 cxf study 全链路落库：patient（占位）/ imaging_study / dicom_series /
exam / report_text / phi_audit / ingest_batch，``anon_exam_id`` 关联到位。

exam 侧口径（2026-09-21 实测，见 recon_cxf.json / recon_cxf_exam.json）：
- cxf StudyUID 的 ``sha256('xinqiao:'+StudyUID)`` 与库内 exam **0 命中**（ct.parquet
  的 exam_id 不是 StudyUID），但 7,924 个有日期行与已灌 exam（issue-13 灌 ct.parquet
  批次）按 ``(patient, exam_date)`` 精确同日——exam 内容已在库，**只关联不新建**
  （issue-25 决策门「不得产生重复 exam」同样约束本单）；
- 同日多 exam（实测 5 行）按 ``min(anon_exam_id)`` 平局（issue-13 残留兜底同款）；
- 60 个无日期行库内无任何 exam：``lnrs.uid_study_date`` 兜底（实测 56 行），
  仍无日期的读 DICOM header StudyDate 兜底（≤60 次单文件读），据此**新建** exam
  （exam_no = StudyUID，hash 键空间与既有 124,045 行天然不相交，实测 0 命中），
  raw_text 全空 → 不写 report_text（其报告内容本就不存在）。

写入路径（issue-23 护栏）
------------------------
- 4 张业务表写 ``lnrs_stage_*`` → ``promote_stage_all.py``（或 ``--promote``）
  按 FK 序上生产，带 issue-22 校验闸 / 审计 / 按批次回滚；
- ingest_batch（确定性 batch_id，幂等重跑 0 新增）/ phi_audit 按惯例直写
  （不在 4 表 promote 链路内，见 anon_etl_engine._import_exam_text_table 注释）。

用法
----
    ENVIRONMENT=h196_3 uv run python etl2/_issue24_ingest_xinqiao_cxf.py --dry-run
    ENVIRONMENT=h196_3 uv run python etl2/_issue24_ingest_xinqiao_cxf.py --apply --target production
    ENVIRONMENT=h196_3 uv run python etl2/_issue24_ingest_xinqiao_cxf.py --promote --target production
    ENVIRONMENT=h196_3 uv run python etl2/_issue24_ingest_xinqiao_cxf.py --audit-only

幂等性：apply 全程按「库内现状」先算计划（plan-first），已入库的 study/series/
patient/exam/phi 全部跳过；重跑 0 新增 0 更新（AC）。promote 幂等可重放。
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import hashlib
import json
import sys
import uuid
from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

import duckdb  # noqa: E402
from _script_guard import add_target_argument, count_parquet_rows, gate  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.database import async_db_session  # noqa: E402
from app.core.logger import log  # noqa: E402
from app.plugin.module_medical.hospital.anonymize import (  # noqa: E402
    compute_anon_exam_id,
    compute_anon_id,
    key_fingerprint,
    secret_version,
    source_exam_hash,
)

CENTER = "xinqiao"
SOURCE = "xinqiao_3_cxf"
CT_MAPPED = Path("/data/wlx/DATABASE/extracted_tables/xinqiao/ct_mapped.parquet")
LISTS_DIR = Path("/data/wlx/DATABASE/03_disk/xinqiao/3_cxf_archives/lists")

#: 确定性 batch_id：同一批数据重跑不产生新 batch 行（AC「幂等重跑 0 新增」）
BATCH_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, "issue24:xinqiao:3_cxf_archives:ct_mapped"))
#: ingest_batch UNIQUE(center, secret_version, key_fingerprint, schema_hash, started_at)
#: 的 schema_hash 按 source 派生（plan-xinqiao P1-8 处置）
SCHEMA_HASH = hashlib.sha256(
    f"xinqiao_cxf_ct_mapped_issue24:{SOURCE}".encode()
).hexdigest()

PHI_SOURCE_TABLE = "lnrs_anon_imaging_study"
PHI_SOURCE_FIELD = "patient_id"
PHI_STRATEGY = "hmac"

#: ct_mapped 临时映射表（无 PHI：patient 只落 anon 键），verify SQL 与 33,110
#: 复核项共用；dry-run / apply / audit 都会重建
TMP_MAP = "lnrs.lnrs_tmp_issue24_cxf_map"

#: stage 4 表（幂等键约束名统一在 ensure_stage_tables 的 constraints 字典）
_STAGE_TABLES = (
    "lnrs.lnrs_stage_patient",
    "lnrs.lnrs_stage_exam",
    "lnrs.lnrs_stage_imaging_study",
    "lnrs.lnrs_stage_dicom_series",
)


# --------------------------------------------------------------------------- #
# 纯函数 seam（tests/anon_etl/test_issue24_xinqiao_cxf_ingest.py）
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CxfRow:
    """ct_mapped 的一行 cxf study。"""

    study_uid: str
    pid: str
    exam_date: date | None            # ct_mapped.exam_date 的 date 部分
    n_files: int                      # len(path[])——instance（文件）数
    total_size_bytes: int
    series_count: int                 # ct_mapped.file_count——series 个数（PACS 权威）
    study_root: str                   # …/3_cxf_archives/folders/NNN/<StudyUID>
    fallback_date: date | None = None  # 无日期行的兜底日期（uid → header StudyDate）


def validate_rows(rows: Sequence[CxfRow]) -> tuple[list[CxfRow], list[str]]:
    """行级守卫（v2 filter_valid 同思路）。返回 (合法行, 非法 uid 列表)。"""
    good: list[CxfRow] = []
    bad: list[str] = []
    for r in rows:
        if r.n_files < 1:
            bad.append(r.study_uid)
        elif r.total_size_bytes < 0:
            bad.append(r.study_uid)
        elif r.series_count < 1:
            bad.append(r.study_uid)
        elif not r.study_root.endswith(r.study_uid):
            bad.append(r.study_uid)  # path[1] 上两级必须是 StudyUID 目录
        elif not r.pid:
            bad.append(r.study_uid)
        else:
            good.append(r)
    return good, bad


@dataclass
class IngestPlan:
    """一次 apply 的完整写入计划（全部为 stage/直写行 dict）。"""

    patients: list[dict]
    exams: list[dict]
    studies: list[dict]
    series: list[dict]
    phi_hashes: list[str]
    stats: dict


def build_plan(
    rows: Sequence[CxfRow],
    *,
    batch_id: str,
    pt_of_pid: Mapping[str, str],
    new_pids: Collection[str],
    exam_by_pt_date: Mapping[tuple[str, date], Sequence[str]],
    exam_by_hash: Mapping[str, str],
    existing_cxf_study_uids: Collection[str],
    existing_series_uids: Collection[str],
    existing_study_links: Mapping[str, str | None],
    phi_existing_hashes: Collection[str],
) -> IngestPlan:
    """按库内现状产出写入计划（plan-first，幂等的关键）。

    - study/series：只对库内缺的行出计划（崩在 promote 中途可自愈——imaging 上过
      series 没上时，重跑只补 series）；
    - exam 关联：有日期行 ``(patient, exam_date)`` 精确匹配（同日多 exam 取
      min(anon_exam_id)）；无日期行三级兜底 hash → (patient, fallback_date) → 新建；
    - patient：只对 new_pids 出占位行（sex='0'，is_placeholder=TRUE）；
    - phi：按全部行的患者（不只新建 study）去重生成，幂等重跑 0 新增。
    """
    stats: Counter[str] = Counter(dict.fromkeys(("rows_total", "rows_deduped", "rows_invalid", "patients_new", "studies_new", "studies_existing", "series_new", "series_existing", "exams_linked_by_date", "exams_linked_by_hash", "exams_linked_by_fallback_date", "exams_created", "exams_unlinked", "ambiguous_links", "dated_no_exam", "phi_new", "phi_existing"), 0))
    stats["rows_total"] = len(rows)

    by_uid: dict[str, CxfRow] = {}
    for r in rows:
        by_uid.setdefault(r.study_uid, r)
    stats["rows_deduped"] = len(rows) - len(by_uid)

    for pid in new_pids:
        if pid not in pt_of_pid:
            raise ValueError(f"new pid {pid!r} 未预分配 patient_id")

    patients = [
        {
            "patient_id": pt_of_pid[pid],
            "anon_id": compute_anon_id(CENTER, pid),
            "center_code": CENTER,
            "sex": "0",
            "is_placeholder": True,
            "created_batch_id": batch_id,
            "last_seen_batch_id": batch_id,
        }
        for pid in sorted(new_pids)
    ]
    stats["patients_new"] = len(patients)

    exams: list[dict] = []
    studies: list[dict] = []
    series: list[dict] = []
    phi_seen: set[str] = set(phi_existing_hashes)
    stats["phi_existing"] = len(phi_seen)
    phi_hashes: list[str] = []

    for uid in sorted(by_uid):
        r = by_uid[uid]
        pt = pt_of_pid[r.pid]
        ph = hashlib.sha256(pt.encode("utf-8")).hexdigest()
        if ph not in phi_seen:
            phi_seen.add(ph)
            phi_hashes.append(ph)

        study_exists = uid in existing_cxf_study_uids
        series_exists = uid in existing_series_uids
        if study_exists:
            # 已入库：exam 关联已在生产（崩在 promote 中途时 series 可能缺行，
            # 其 anon_exam_id 取既有 study 的链接值，保证 series 与 study 一致）
            stats["studies_existing"] += 1
            eid = existing_study_links.get(uid)
        else:
            eid = _resolve_exam(r, pt, exam_by_pt_date, exam_by_hash, exams, stats)
            studies.append(
                {
                    "patient_id": pt,
                    "center_code": CENTER,
                    "dicom_study_uid": uid,
                    "modality": "CT",
                    "image_path": r.study_root,
                    "sop_count": r.n_files,
                    "source": SOURCE,
                    "created_batch_id": batch_id,
                    "anon_exam_id": eid,
                }
            )
        if not series_exists:
            series.append(
                {
                    "anon_exam_id": eid,
                    "dicom_study_uid": uid,
                    "file_count": r.n_files,
                    "byte_size": r.total_size_bytes,
                    "series_count": r.series_count,
                    "created_batch_id": batch_id,
                }
            )
            stats["series_new"] += 1
        else:
            stats["series_existing"] += 1
    stats["studies_new"] = len(studies)
    stats["phi_new"] = len(phi_hashes)
    return IngestPlan(patients, exams, studies, series, phi_hashes, dict(stats))


def _resolve_exam(
    r: CxfRow,
    pt: str,
    exam_by_pt_date: Mapping[tuple[str, date], Sequence[str]],
    exam_by_hash: Mapping[str, str],
    exams_out: list[dict],
    stats: Counter,
) -> str | None:
    """一行 study 的 exam 关联 / 新建决策（口径见模块 docstring）。"""
    if r.exam_date is not None:
        cands = sorted(exam_by_pt_date.get((pt, r.exam_date), []))
        if cands:
            if len(cands) > 1:
                stats["ambiguous_links"] += 1
            stats["exams_linked_by_date"] += 1
            return cands[0]
        stats["dated_no_exam"] += 1
        return None
    if r.fallback_date is not None:
        hit = exam_by_hash.get(source_exam_hash(CENTER, r.study_uid))
        if hit:
            stats["exams_linked_by_hash"] += 1
            return hit
        cands = sorted(exam_by_pt_date.get((pt, r.fallback_date), []))
        if cands:
            if len(cands) > 1:
                stats["ambiguous_links"] += 1
            stats["exams_linked_by_fallback_date"] += 1
            return cands[0]
        eid = compute_anon_exam_id(CENTER, r.study_uid)
        exams_out.append(
            {
                "anon_exam_id": eid,
                "patient_id": pt,
                "center_code": CENTER,
                "exam_type": "CT",
                "exam_date": r.fallback_date,
                "source_exam_hash": source_exam_hash(CENTER, r.study_uid),
                "created_batch_id": BATCH_ID,
                "last_seen_batch_id": BATCH_ID,
            }
        )
        stats["exams_created"] += 1
        return eid
    stats["exams_unlinked"] += 1
    return None


# --------------------------------------------------------------------------- #
# 源数据加载（duckdb）+ 兜底日期
# --------------------------------------------------------------------------- #


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    return date.fromisoformat(s.strip()[:10])


def load_cxf_rows(parquet: Path = CT_MAPPED, *, cross_check_lists: bool = True) -> list[CxfRow]:
    """ct_mapped → cxf 行列表；与 lists/batch_*.txt 交叉核对 study 枚举。"""
    con = duckdb.connect()
    try:
        raw = con.execute(
            """
            SELECT exam_id, patient_id, exam_date, file_count,
                   total_size_bytes, len(path) AS n_files, path[1] AS p1
            FROM read_parquet(?)
            WHERE list_contains(list_transform(path, x -> x LIKE '%/3_cxf_archives/%'), true)
            ORDER BY exam_id
            """,
            [parquet.as_posix()],
        ).fetchall()
    finally:
        con.close()
    rows = [
        CxfRow(
            study_uid=uid,
            pid=pid,
            exam_date=_parse_date(d),
            n_files=int(n),
            total_size_bytes=int(sz),
            series_count=int(fc),
            study_root="/".join(p1.split("/")[:-2]),
        )
        for uid, pid, d, fc, sz, n, p1 in raw
    ]
    if cross_check_lists:
        listed: set[str] = set()
        for f in sorted(LISTS_DIR.glob("batch_*.txt")):
            listed |= {
                ln.strip()
                for ln in f.read_text(encoding="utf-8-sig").splitlines() if ln.strip()
            }
        from_disk = {r.study_uid for r in rows}
        if listed != from_disk:
            raise SystemExit(
                f"[LOAD] lists/batch_*.txt 与 ct_mapped cxf StudyUID 不一致："
                f"仅 lists 有 {len(listed - from_disk)}，仅 ct_mapped 有 "
                f"{len(from_disk - listed)}"
            )
    return rows


def load_all_studyuid_rows(parquet: Path = CT_MAPPED) -> list[dict]:
    """全部 exam_id=StudyUID 行（含已入库 33,314），供 33,110 复核项与全等断言。"""
    con = duckdb.connect()
    try:
        raw = con.execute(
            """
            SELECT exam_id, patient_id, exam_date, file_count,
                   total_size_bytes, len(path), path[1]
            FROM read_parquet(?)
            WHERE exam_id NOT LIKE 'Accession%'
            """,
            [parquet.as_posix()],
        ).fetchall()
    finally:
        con.close()
    return [
        {
            "study_uid": uid,
            "patient_anon": compute_anon_id(CENTER, pid),
            "exam_date": _parse_date(d),
            "n_files": int(n),
            "total_size_bytes": int(sz),
            "series_count": int(fc),
            "is_cxf": "3_cxf_archives" in p1,
        }
        for uid, pid, d, fc, sz, n, p1 in raw
    ]


def header_study_date(first_dcm: str) -> date | None:
    """读单个 .dcm 的 StudyDate（≤60 次单文件读，非全量遍历）。"""
    try:
        import pydicom

        ds = pydicom.dcmread(first_dcm, stop_before_pixels=True, specific_tags=["StudyDate"])
        raw = str(ds.get("StudyDate") or "")
        return datetime.datetime.strptime(raw, "%Y%m%d").date() if len(raw) == 8 else None
    except Exception as e:  # noqa: BLE001 —— 单文件失败只影响该行，报告列明
        log.warning(f"[FALLBACK] header 读取失败 {first_dcm}: {e}")
        return None


async def _uid_date_rows(s, uids: list[str]) -> list[tuple[str, date | None]]:
    rows = await s.execute(
        text("SELECT u, lnrs.uid_study_date(u) FROM unnest(CAST(:u AS text[])) AS t(u)"),
        {"u": uids},
    )
    return [(r[0], r[1]) for r in rows.all()]


# --------------------------------------------------------------------------- #
# DB 路径
# --------------------------------------------------------------------------- #


async def ensure_stage_tables(s) -> None:
    """镜像迁移 p6q7r8s9t0u1 / n4o5p6q7r8s9 / o5p6q7r8s9t0 的 DDL（幂等）。

    本库 stage 表与 promote 审计表 promote 后会被手工清理，故脚本自带建表。
    asyncpg 事务内一旦报错即整体 abort，故不靠 DuplicateObject 异常吞掉：
    CREATE 用 IF NOT EXISTS，ADD CONSTRAINT 先查 pg_constraint 再执行。
    """
    ddl: list[str] = [
        # issue-22 审计表（promote 护栏依赖，迁移 o5p6q7r8s9t0）
        """
        CREATE TABLE IF NOT EXISTS lnrs.lnrs_promote_audit (
          audit_id     bigserial PRIMARY KEY,
          batch_id     uuid        NOT NULL,
          target_table text        NOT NULL,
          mode         text        NOT NULL CHECK (mode IN ('dry_run', 'apply')),
          stage_rows   integer     NOT NULL,
          upsert_rows  integer     NOT NULL DEFAULT 0,
          validation   text        NOT NULL CHECK (validation IN ('passed', 'rejected')),
          violations   jsonb       NOT NULL DEFAULT '[]'::jsonb,
          actor        text        NOT NULL,
          created_at   timestamptz NOT NULL DEFAULT now(),
          rolled_back_at timestamptz
        )
        """,
        "CREATE INDEX IF NOT EXISTS lnrs_promote_audit_batch_id_idx"
        " ON lnrs.lnrs_promote_audit (batch_id)",
        """
        CREATE TABLE IF NOT EXISTS lnrs.lnrs_promote_audit_row (
          id           bigserial PRIMARY KEY,
          audit_id     bigint  NOT NULL REFERENCES lnrs.lnrs_promote_audit(audit_id),
          business_key text    NOT NULL,
          action       text    NOT NULL CHECK (action IN ('insert', 'update')),
          preimage     jsonb
        )
        """,
        "CREATE INDEX IF NOT EXISTS lnrs_promote_audit_row_audit_idx"
        " ON lnrs.lnrs_promote_audit_row (audit_id)",
        # issue-23 stage 4 表（迁移 p6q7r8s9t0u1 / n4o5p6q7r8s9）
        "CREATE TABLE IF NOT EXISTS lnrs.lnrs_stage_patient"
        " (LIKE lnrs.lnrs_anon_patient INCLUDING DEFAULTS)",
        "CREATE TABLE IF NOT EXISTS lnrs.lnrs_stage_exam"
        " (LIKE lnrs.lnrs_anon_exam INCLUDING DEFAULTS)",
        "CREATE TABLE IF NOT EXISTS lnrs.lnrs_stage_imaging_study"
        " (LIKE lnrs.lnrs_anon_imaging_study INCLUDING DEFAULTS)",
        "CREATE TABLE IF NOT EXISTS lnrs.lnrs_stage_dicom_series"
        " (LIKE lnrs.lnrs_anon_dicom_series INCLUDING DEFAULTS)",
    ]
    # 幂等键约束（promote ON CONFLICT / 写入 ON CONFLICT 依赖）
    constraints = {
        "lnrs_stage_patient": (
            "lnrs_stage_patient_uq_center", "UNIQUE (center_code, anon_id)"),
        "lnrs_stage_exam": (
            "lnrs_stage_exam_uq_source", "UNIQUE (center_code, source_exam_hash)"),
        "lnrs_stage_imaging_study": (
            "lnrs_stage_imaging_study_uq",
            "UNIQUE (patient_id, dicom_study_uid, source)"),
        "lnrs_stage_dicom_series": (
            "lnrs_stage_dicom_series_study_uid_uq", "UNIQUE (dicom_study_uid)"),
    }
    for table, (conname, defn) in constraints.items():
        exists = (await s.execute(text("""
            SELECT 1 FROM pg_constraint c
            JOIN pg_class cl ON cl.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = cl.relnamespace
            WHERE n.nspname = 'lnrs' AND cl.relname = :t AND c.conname = :cn
        """), {"t": table, "cn": conname})).scalar()
        if not exists:
            ddl.append(
                f"ALTER TABLE lnrs.{table} ADD CONSTRAINT {conname} {defn}")
    for stmt in ddl:
        await s.execute(text(stmt))
    await s.commit()


async def assert_stage_clean(s, cxf_uids: list[str]) -> None:
    """apply 前置：stage 只允许「本单的行」（已 promote 或待 promote）。

    promote 不清 stage（幂等重放是特性），故已上生产的本单行正常存在；
    仅当出现**非本单归属**的行（他人工单未 promote 的数据）时拒绝，
    防止 --promote 时被连带 promote。
    """
    foreign = 0
    foreign += int((await s.execute(text("""
        SELECT COUNT(*) FROM lnrs.lnrs_stage_patient sp
        WHERE sp.created_batch_id <> :b
          AND NOT EXISTS (SELECT 1 FROM lnrs.lnrs_anon_patient p
                          WHERE p.center_code = sp.center_code
                            AND p.anon_id = sp.anon_id)
    """), {"b": BATCH_ID})).scalar() or 0)
    foreign += int((await s.execute(text("""
        SELECT COUNT(*) FROM lnrs.lnrs_stage_exam se
        WHERE se.created_batch_id <> :b
          AND NOT EXISTS (SELECT 1 FROM lnrs.lnrs_anon_exam e
                          WHERE e.anon_exam_id = se.anon_exam_id)
    """), {"b": BATCH_ID})).scalar() or 0)
    foreign += int((await s.execute(text("""
        SELECT COUNT(*) FROM lnrs.lnrs_stage_imaging_study si
        WHERE si.source <> :src
    """), {"src": SOURCE})).scalar() or 0)
    foreign += int((await s.execute(text("""
        SELECT COUNT(*) FROM lnrs.lnrs_stage_dicom_series ds
        WHERE NOT (ds.dicom_study_uid = ANY(CAST(:u AS text[])))
    """), {"u": cxf_uids})).scalar() or 0)
    if foreign:
        raise SystemExit(
            f"[STAGE] stage 表含 {foreign} 行非本单数据（他人工单未 promote？）。"
            "先让对应工单 promote 或协调后重试。"
        )


async def build_map_table(s, all_rows: list[dict]) -> None:
    """全量 StudyUID 行 → lnrs_tmp_issue24_cxf_map（无 PHI，重跑刷新）。"""
    await s.execute(text(f"DROP TABLE IF EXISTS {TMP_MAP}"))
    await s.execute(text(f"""
        CREATE TABLE {TMP_MAP} (
          study_uid varchar(64) PRIMARY KEY,
          patient_anon varchar(32) NOT NULL,
          exam_date date,
          n_files integer NOT NULL,
          total_bytes bigint NOT NULL,
          series_cnt integer NOT NULL,
          is_cxf boolean NOT NULL
        )
    """))
    vals = [
        {
            "u": r["study_uid"],
            "a": r["patient_anon"],
            "d": r["exam_date"],
            "n": r["n_files"],
            "b": r["total_size_bytes"],
            "c": r["series_count"],
            "x": r["is_cxf"],
        }
        for r in all_rows
    ]
    for i in range(0, len(vals), 4000):
        await s.execute(
            text(f"""
                INSERT INTO {TMP_MAP} (study_uid, patient_anon, exam_date,
                                       n_files, total_bytes, series_cnt, is_cxf)
                VALUES (:u, :a, :d, :n, :b, :c, :x)
                ON CONFLICT (study_uid) DO UPDATE
                  SET patient_anon = EXCLUDED.patient_anon,
                      exam_date = EXCLUDED.exam_date,
                      n_files = EXCLUDED.n_files,
                      total_bytes = EXCLUDED.total_bytes,
                      series_cnt = EXCLUDED.series_cnt,
                      is_cxf = EXCLUDED.is_cxf
            """),
            vals[i : i + 4000],
        )
    await s.commit()
    log.info(f"[MAP] {TMP_MAP} = {len(vals)} 行（StudyUID 键全量）")


def first_dcm_paths(uids: list[str]) -> dict[str, str]:
    """无日期 study 的首个 .dcm 路径（供 header StudyDate 兜底；单文件读）。"""
    if not uids:
        return {}
    con = duckdb.connect()
    try:
        rows = con.execute(
            """
            SELECT exam_id, path[1] FROM read_parquet(?)
            WHERE list_contains(list_transform(path, x -> x LIKE '%/3_cxf_archives/%'), true)
              AND exam_id IN (SELECT unnest(CAST(? AS text[])))
            """,
            [CT_MAPPED.as_posix(), uids],
        ).fetchall()
    finally:
        con.close()
    return dict(rows)


async def collect_lookups(
    s, rows: list[CxfRow], *, allocate: bool = True
) -> tuple[dict, dict]:
    """库内现状查询 → (lookups, existing)。

    allocate=False（dry-run）：缺失患者用 PT_DRYRUN_* 虚拟号占位，不消耗序列。
    """
    pids = sorted({r.pid for r in rows})
    anons = [compute_anon_id(CENTER, p) for p in pids]
    anon2pid_raw: dict[str, str] = {}
    deleted_hits: list[str] = []
    for i in range(0, len(anons), 4000):
        for anon, pt, deld in (await s.execute(text("""
            SELECT anon_id, patient_id, deleted_at FROM lnrs.lnrs_anon_patient
            WHERE center_code = :c AND anon_id = ANY(:a)
        """), {"c": CENTER, "a": anons[i : i + 4000]})).all():
            anon2pid_raw[anon] = pt
            if deld is not None:
                deleted_hits.append(pt)
    if deleted_hits:
        raise SystemExit(
            f"[PATIENT] {len(deleted_hits)} 个 cxf 患者命中软删行 {deleted_hits[:3]}…；"
            "本单不擅自复活，请先人工处置"
        )
    pt_of_pid = {
        p: anon2pid_raw[compute_anon_id(CENTER, p)] for p in pids
        if compute_anon_id(CENTER, p) in anon2pid_raw
    }
    new_pids = [p for p in pids if compute_anon_id(CENTER, p) not in anon2pid_raw]

    if new_pids:
        if allocate:
            # 占位发号（v2 同款：advisory lock + sequence，事务内原子）
            await s.execute(text(
                "SELECT pg_advisory_xact_lock(hashtext('xinqiao_patient_seq'))"))
            for p in new_pids:
                pt_of_pid[p] = (await s.execute(text(
                    "SELECT 'PT_' || LPAD(nextval('lnrs.lnrs_anon_patient_seq')"
                    "::text, 8, '0')"
                ))).scalar()
            log.info(f"[PATIENT] 预分配 {len(new_pids)} 个占位 patient："
                     f"{[pt_of_pid[p] for p in new_pids[:5]]}…")
        else:
            for i, p in enumerate(new_pids):
                pt_of_pid[p] = f"PT_DRYRUN_{i:03d}"
            log.info(f"[PATIENT] [dry-run] 缺失患者 {len(new_pids)} 个（虚拟号）")

    pts = sorted(set(pt_of_pid.values()))
    exam_by_pt_date: dict[tuple[str, date], list[str]] = {}
    for i in range(0, len(pts), 2000):
        for pt, d, eid in (await s.execute(text("""
            SELECT e.patient_id, e.exam_date, e.anon_exam_id
            FROM lnrs.lnrs_anon_exam e
            WHERE e.center_code = :c AND e.exam_type = 'CT'
              AND e.patient_id = ANY(:p)
        """), {"c": CENTER, "p": pts[i : i + 2000]})).all():
            exam_by_pt_date.setdefault((pt, d), []).append(eid)

    nodate = [r for r in rows if r.exam_date is None]
    exam_by_hash: dict[str, str] = {}
    if nodate:
        hs = [source_exam_hash(CENTER, r.study_uid) for r in nodate]
        for i in range(0, len(hs), 1000):
            for h, eid in (await s.execute(text("""
                SELECT source_exam_hash, anon_exam_id FROM lnrs.lnrs_anon_exam
                WHERE center_code = :c AND source_exam_hash = ANY(:h)
            """), {"c": CENTER, "h": hs[i : i + 1000]})).all():
                exam_by_hash[h] = eid

    look = {
        "pt_of_pid": pt_of_pid,
        "new_pids": set(new_pids),
        "exam_by_pt_date": exam_by_pt_date,
        "exam_by_hash": exam_by_hash,
    }
    return look, await _existing_uids(s, [r.study_uid for r in rows])


async def _existing_uids(s, uids: list[str]) -> dict:
    """库内既有 cxf study uid / series uid / 本 batch phi。"""
    existing_study: set[str] = set()
    for i in range(0, len(uids), 4000):
        existing_study |= {
            r[0] for r in (await s.execute(text("""
                SELECT dicom_study_uid FROM lnrs.lnrs_anon_imaging_study
                WHERE center_code = :c AND source = :src AND dicom_study_uid = ANY(:u)
            """), {"c": CENTER, "src": SOURCE, "u": uids[i : i + 4000]})).all()
        }
    existing_series: set[str] = set()
    for i in range(0, len(uids), 4000):
        existing_series |= {
            r[0] for r in (await s.execute(text("""
                SELECT dicom_study_uid FROM lnrs.lnrs_anon_dicom_series
                WHERE dicom_study_uid = ANY(:u)
            """), {"u": uids[i : i + 4000]})).all()
        }
    phi_exist: list[str] = [
        r[0] for r in (await s.execute(text("""
            SELECT source_hash FROM lnrs.lnrs_anon_phi_audit
            WHERE batch_id = :b AND source_table = :t AND source_field = :f
        """), {"b": BATCH_ID, "t": PHI_SOURCE_TABLE, "f": PHI_SOURCE_FIELD})).all()
    ]
    existing_links: dict[str, str | None] = {}
    for i in range(0, len(uids), 4000):
        for r in (await s.execute(text("""
            SELECT dicom_study_uid, anon_exam_id FROM lnrs.lnrs_anon_imaging_study
            WHERE center_code = :c AND source = :src AND dicom_study_uid = ANY(:u)
        """), {"c": CENTER, "src": SOURCE, "u": uids[i : i + 4000]})).all():
            existing_links[r[0]] = r[1]
    return {
        "existing_cxf_study_uids": existing_study,
        "existing_series_uids": existing_series,
        "existing_study_links": existing_links,
        "phi_existing_hashes": set(phi_exist),
    }


async def write_stage(s, plan: IngestPlan) -> None:
    """stage 4 表写入（单事务，ON CONFLICT DO NOTHING 幂等）。"""
    if plan.patients:
        await s.execute(text("""
            INSERT INTO lnrs.lnrs_stage_patient
              (patient_id, anon_id, center_code, sex, is_placeholder,
               created_batch_id, last_seen_batch_id)
            VALUES (:patient_id, :anon_id, :center_code, :sex, :is_placeholder,
                    :created_batch_id, :last_seen_batch_id)
            ON CONFLICT ON CONSTRAINT lnrs_stage_patient_uq_center DO NOTHING
        """), plan.patients)
    if plan.exams:
        await s.execute(text("""
            INSERT INTO lnrs.lnrs_stage_exam
              (anon_exam_id, patient_id, center_code, exam_type, exam_date,
               source_exam_hash, created_batch_id, last_seen_batch_id)
            VALUES (:anon_exam_id, :patient_id, :center_code, :exam_type, :exam_date,
                    :source_exam_hash, :created_batch_id, :last_seen_batch_id)
            ON CONFLICT ON CONSTRAINT lnrs_stage_exam_uq_source DO NOTHING
        """), plan.exams)
    if plan.studies:
        for i in range(0, len(plan.studies), 2000):
            await s.execute(text("""
                INSERT INTO lnrs.lnrs_stage_imaging_study
                  (patient_id, center_code, dicom_study_uid, modality, image_path,
                   sop_count, source, created_batch_id, anon_exam_id)
                VALUES (:patient_id, :center_code, :dicom_study_uid, :modality,
                        :image_path, :sop_count, :source, :created_batch_id, :anon_exam_id)
                ON CONFLICT ON CONSTRAINT lnrs_stage_imaging_study_uq DO NOTHING
            """), plan.studies[i : i + 2000])
    if plan.series:
        for i in range(0, len(plan.series), 2000):
            await s.execute(text("""
                INSERT INTO lnrs.lnrs_stage_dicom_series
                  (anon_exam_id, dicom_study_uid, file_count, byte_size,
                   series_count, created_batch_id)
                VALUES (:anon_exam_id, :dicom_study_uid, :file_count, :byte_size,
                        :series_count, :created_batch_id)
                ON CONFLICT (dicom_study_uid) DO NOTHING
            """), plan.series[i : i + 2000])
    await s.commit()


async def write_phi(s, plan: IngestPlan) -> int:
    """phi_audit 直写（不在 4 表 promote 链路，引擎同惯例）。"""
    if not plan.phi_hashes:
        return 0
    rows = [
        {"b": BATCH_ID, "t": PHI_SOURCE_TABLE, "f": PHI_SOURCE_FIELD, "h": h, "s": PHI_STRATEGY}
        for h in plan.phi_hashes
    ]
    for i in range(0, len(rows), 4000):
        await s.execute(text("""
            INSERT INTO lnrs.lnrs_anon_phi_audit
              (batch_id, source_table, source_field, source_hash, strategy)
            VALUES (:b, :t, :f, :h, :s)
        """), rows[i : i + 4000])
    await s.commit()
    return len(rows)


async def upsert_batch_row(s, status: str, row_counts: dict) -> None:
    """确定性 batch 行（ON CONFLICT DO NOTHING + 关闭 UPDATE，显式 commit）。"""
    await s.execute(text("""
        INSERT INTO lnrs.lnrs_anon_ingest_batch
          (batch_id, center_code, source_kind, source_locator, secret_version,
           key_fingerprint, schema_hash, row_counts, status)
        VALUES (:b, :c, 'dicom_dir', :loc, :sv, :kf, :sh, CAST(:rc AS jsonb), :st)
        ON CONFLICT (batch_id) DO NOTHING
    """), {
        "b": BATCH_ID, "c": CENTER,
        "loc": f"{CT_MAPPED}#{SOURCE}",
        "sv": secret_version(), "kf": key_fingerprint(), "sh": SCHEMA_HASH,
        "rc": "{}", "st": "running",
    })
    await s.execute(text("""
        UPDATE lnrs.lnrs_anon_ingest_batch
        SET status = :st, finished_at = CURRENT_TIMESTAMP, row_counts = CAST(:rc AS jsonb)
        WHERE batch_id = :b
    """), {"b": BATCH_ID, "st": status, "rc": json.dumps(row_counts)})
    await s.commit()


async def backup_tables() -> str:
    """AC：执行前建 _bak_<ts> 全量快照（patient/exam/imaging_study/dicom_series）。"""
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    async with async_db_session() as s:
        for t in ("lnrs_anon_patient", "lnrs_anon_exam",
                  "lnrs_anon_imaging_study", "lnrs_anon_dicom_series"):
            bak = f"lnrs.{t}_bak_{ts}"
            exists = (await s.execute(text(
                "SELECT to_regclass(:r)"), {"r": bak})).scalar()
            if exists:
                log.info(f"[BACKUP] {bak} 已存在，复用")
            else:
                await s.execute(text(f"CREATE TABLE {bak} AS SELECT * FROM lnrs.{t}"))
                n = (await s.execute(text(f"SELECT COUNT(*) FROM {bak}"))).scalar()
                log.info(f"[BACKUP] {bak} = {n} 行")
        await s.commit()
    return ts


async def snapshot_baselines(s) -> dict:
    """zhujiang/shengyi 零漂移基线 + xinqiao 5-sub 现状。"""
    rows = (await s.execute(text("""
        SELECT center_code, source, COUNT(*) AS n
        FROM lnrs.lnrs_anon_imaging_study GROUP BY 1, 2
    """))).all()
    exam = (await s.execute(text("""
        SELECT center_code, exam_type, COUNT(*) AS n
        FROM lnrs.lnrs_anon_exam WHERE center_code IN ('zhujiang', 'shengyi')
        GROUP BY 1, 2
    """))).all()
    pat = (await s.execute(text("""
        SELECT center_code, COUNT(*) AS n FROM lnrs.lnrs_anon_patient
        WHERE center_code IN ('zhujiang', 'shengyi') GROUP BY 1
    """))).all()
    return {
        "imaging": {f"{r[0]}:{r[1]}": int(r[2]) for r in rows
                    if r[0] in ("zhujiang", "shengyi")},
        "exam": {f"{r[0]}:{r[1]}": int(r[2]) for r in exam},
        "patient": {f"{r[0]}": int(r[1]) for r in pat},
    }


# --------------------------------------------------------------------------- #
# 验证 / 复核
# --------------------------------------------------------------------------- #


async def verify_apply(expected_total: int, pre: dict | None = None) -> dict:
    """promote 后的生产端验收（AC SQL 断言的脚本内版本）。"""
    out: dict = {}
    async with async_db_session() as s:
        row = (await s.execute(text("""
            SELECT COUNT(*) AS n, COUNT(*) FILTER (WHERE anon_exam_id IS NOT NULL) AS linked
            FROM lnrs.lnrs_anon_imaging_study
            WHERE center_code = :c AND source = :src
        """), {"c": CENTER, "src": SOURCE})).mappings().first()
        out["studies"] = dict(row)
        assert row["n"] == expected_total, f"cxf study 行数 {row['n']} != {expected_total}"
        assert row["linked"] == expected_total, (
            f"anon_exam_id 非空率 {row['linked']}/{row['n']} != 100%"
        )

        # series 全等（map 表 join）
        row = (await s.execute(text(f"""
            SELECT COUNT(*) AS n,
                   COUNT(*) FILTER (WHERE ds.file_count = m.n_files
                                     AND ds.byte_size = m.total_bytes
                                     AND ds.series_count = m.series_cnt) AS equal
            FROM lnrs.lnrs_anon_dicom_series ds
            JOIN {TMP_MAP} m ON m.study_uid = ds.dicom_study_uid AND m.is_cxf
        """))).mappings().first()
        out["series_equal"] = dict(row)
        assert row["n"] == expected_total and row["equal"] == expected_total, (
            f"dicom_series 与 ct_mapped 全等 {row['equal']}/{row['n']}"
        )

        # FK：cxf 引用的 exam 全部存在；series.anon_exam_id 与 study 一致
        row = (await s.execute(text("""
            SELECT
              (SELECT COUNT(*) FROM lnrs.lnrs_anon_imaging_study s
               WHERE s.center_code = :c AND s.source = :src AND s.anon_exam_id IS NOT NULL
                 AND NOT EXISTS (SELECT 1 FROM lnrs.lnrs_anon_exam e
                                 WHERE e.anon_exam_id = s.anon_exam_id)) AS study_fk_bad,
              (SELECT COUNT(*) FROM lnrs.lnrs_anon_dicom_series ds
               JOIN lnrs.lnrs_anon_imaging_study st USING (dicom_study_uid)
               WHERE st.center_code = :c AND st.source = :src
                 AND ds.anon_exam_id IS DISTINCT FROM st.anon_exam_id) AS series_link_bad
        """), {"c": CENTER, "src": SOURCE})).mappings().first()
        out["fk"] = dict(row)
        assert row["study_fk_bad"] == 0 and row["series_link_bad"] == 0

        # UID 交集 = 0（cxf 与既有 source）
        n = (await s.execute(text("""
            SELECT COUNT(*) FROM lnrs.lnrs_anon_imaging_study a
            WHERE a.center_code = :c AND a.source = :src
              AND EXISTS (SELECT 1 FROM lnrs.lnrs_anon_imaging_study b
                          WHERE b.dicom_study_uid = a.dicom_study_uid
                            AND b.source <> :src)
        """), {"c": CENTER, "src": SOURCE})).scalar()
        out["uid_overlap"] = int(n)
        assert n == 0

        if pre is not None:
            post = await snapshot_baselines(s)
            drift: dict[str, tuple] = {}
            for key in ("imaging", "exam", "patient"):
                for k in sorted(set(pre[key]) | set(post[key])):
                    if pre[key].get(k) != post[key].get(k):
                        drift[f"{key}:{k}"] = (pre[key].get(k), post[key].get(k))
            out["zj_sy_drift"] = drift
            assert not drift, f"zhujiang/shengyi 零漂移被破坏: {drift}"
    log.info(f"[VERIFY] {out}")
    return out


async def audit_exam_links() -> dict:
    """AC 复核项：ct_mapped StudyUID 三方复核 issue-13 已回填的 anon_exam_id。

    对既有 5-sub study（source <> cxf）逐行比较：
    - 链接 exam 的患者 anon == ct_mapped 行患者 anon；
    - 链接 exam 的 exam_date == ct_mapped 行 exam_date。
    只读不改；差异写 CSV（anon 键，非 PHI）。
    """
    async with async_db_session() as s:
        n_linked = (await s.execute(text(f"""
            SELECT COUNT(*) FROM lnrs.lnrs_anon_imaging_study s
            WHERE s.center_code = :c AND s.source <> :src AND s.anon_exam_id IS NOT NULL
              AND EXISTS (SELECT 1 FROM {TMP_MAP} m WHERE m.study_uid = s.dicom_study_uid)
        """), {"c": CENTER, "src": SOURCE})).scalar()
        rows = (await s.execute(text(f"""
            SELECT s.study_key, s.dicom_study_uid, s.source, p.anon_id AS linked_pt,
                   e.exam_date AS linked_date, s.anon_exam_id,
                   m.patient_anon AS map_pt, m.exam_date AS map_date,
                   (SELECT COUNT(*) FROM lnrs.lnrs_anon_exam e2
                    JOIN lnrs.lnrs_anon_patient p2 ON p2.patient_id = e2.patient_id
                    WHERE e2.center_code = :c AND e2.exam_type = 'CT'
                      AND p2.anon_id = m.patient_anon AND e2.exam_date = m.exam_date) AS map_cands
            FROM lnrs.lnrs_anon_imaging_study s
            JOIN lnrs.lnrs_anon_patient p ON p.patient_id = s.patient_id
            LEFT JOIN lnrs.lnrs_anon_exam e ON e.anon_exam_id = s.anon_exam_id
            JOIN {TMP_MAP} m ON m.study_uid = s.dicom_study_uid
            WHERE s.center_code = :c AND s.source <> :src AND s.anon_exam_id IS NOT NULL
              AND (p.anon_id IS DISTINCT FROM m.patient_anon
                   OR e.exam_date IS DISTINCT FROM m.exam_date)
        """), {"c": CENTER, "src": SOURCE})).all()
        n_null = (await s.execute(text(f"""
            SELECT COUNT(*) FROM lnrs.lnrs_anon_imaging_study s
            WHERE s.center_code = :c AND s.source <> :src AND s.anon_exam_id IS NULL
              AND EXISTS (SELECT 1 FROM {TMP_MAP} m WHERE m.study_uid = s.dicom_study_uid)
        """), {"c": CENTER, "src": SOURCE})).scalar()
    out = {
        "linked_total": int(n_linked),
        "mismatch_total": len(rows),
        "null_linked": int(n_null),
    }
    if rows:
        csv_path = Path("/home/dzy/wk/lnrs/docs/etl2/verify_result/"
                        "xinqiao-cxf-exam-link-audit-20260921.csv")
        lines = ["study_key,dicom_study_uid,source,linked_patient,linked_exam_date,"
                 "anon_exam_id,map_patient,map_exam_date,map_candidates"]
        for r in rows:
            lines.append(",".join(str(x) for x in r))
        csv_path.write_text("\n".join(lines) + "\n")
        out["csv"] = str(csv_path)
        log.warning(f"[AUDIT] 链接复核差异 {len(rows)} 行 → {csv_path}（不擅自改，开评注）")
    log.info(f"[AUDIT] linked={n_linked} mismatch={len(rows)} null_linked={n_null}")
    return out


# --------------------------------------------------------------------------- #
# 报告 / 主流程
# --------------------------------------------------------------------------- #


def print_reconciliation(rows: list[CxfRow], plan: IngestPlan) -> None:
    st = plan.stats
    log.info("=" * 64)
    log.info(f"[对账] ct_mapped cxf 行数                 : {len(rows)}")
    log.info(f"[对账] study 将写入 / 已在库              : "
             f"{st.get('studies_new', 0)} / {st.get('studies_existing', 0)}")
    log.info(f"[对账] series 将写入 / 已在库             : "
             f"{st.get('series_new', 0)} / {st.get('series_existing', 0)}")
    log.info(f"[对账] exam 关联-既有(同日精确)           : {st.get('exams_linked_by_date', 0)}")
    log.info(f"[对账] exam 关联-既有(hash)               : {st.get('exams_linked_by_hash', 0)}")
    log.info(f"[对账] exam 关联-既有(兜底日期)           : "
             f"{st.get('exams_linked_by_fallback_date', 0)}")
    log.info(f"[对账] exam 新建                          : {st.get('exams_created', 0)}")
    log.info(f"[对账] exam 无法关联（无任何日期，保持 NULL）: {st.get('exams_unlinked', 0)}")
    log.info(f"[对账] 同日多 exam 平局(min anon_exam_id) : {st.get('ambiguous_links', 0)}")
    log.info(f"[对账] patient 新增(占位)                 : {st.get('patients_new', 0)}")
    log.info(f"[对账] phi_audit 新增 / 已在              : "
             f"{st.get('phi_new', 0)} / {st.get('phi_existing', 0)}")
    log.info(f"[对账] ingest_batch                       : {BATCH_ID}（确定性 id）")
    log.info(f"[对账] 非法行 / 重复行                    : "
             f"{st.get('rows_invalid', 0)} / {st.get('rows_deduped', 0)}")
    log.info("=" * 64)


async def do_dry_run() -> int:
    rows = load_cxf_rows()
    good, bad = validate_rows(rows)
    async with async_db_session() as s:
        await build_map_table(s, load_all_studyuid_rows())
        first_paths = first_dcm_paths(
            [r.study_uid for r in good if r.exam_date is None])
        good = await _resolve_fallback(s, good, first_paths)
        look, exist = await collect_lookups(s, good, allocate=False)
        plan = build_plan(good, batch_id=BATCH_ID, **look, **exist)
        plan.stats["rows_invalid"] = len(bad)
    print_reconciliation(good, plan)
    await audit_exam_links()
    log.info("[DRY-RUN] 未写库。正式执行：--apply --target production")
    return 0


async def _resolve_fallback(s, good, first_paths):
    """resolve_fallback_dates 的 async 适配（保持纯函数可测性）。"""
    nodate = [r for r in good if r.exam_date is None]
    if not nodate:
        return good
    uid_dates = dict(await _uid_date_rows(s, [r.study_uid for r in nodate]))
    out, n_hdr, n_fail = [], 0, 0
    for r in good:
        if r.exam_date is not None:
            out.append(r)
            continue
        d = uid_dates.get(r.study_uid)
        if d is None:
            d = header_study_date(first_paths[r.study_uid])
            n_hdr += d is not None
            n_fail += d is None
        else:
            n_hdr += 0
        out.append(replace(r, fallback_date=d))
    log.info(f"[FALLBACK] 无日期 {len(nodate)} 行：uid={len(nodate) - n_hdr - n_fail} "
             f"header={n_hdr} 仍无={n_fail}")
    return out


async def do_apply(declared: str | None, skip_backup: bool) -> int:
    rows = load_cxf_rows()
    good, bad = validate_rows(rows)
    if bad:
        raise SystemExit(f"[VALIDATE] {len(bad)} 行非法（首例 {bad[0]}），先处置再 apply")
    gate(schema="lnrs",
         tables=list(_STAGE_TABLES)
                + ["lnrs.lnrs_anon_phi_audit", "lnrs.lnrs_anon_ingest_batch",
                   "lnrs.lnrs_anon_*_bak_* (backup)"],
         declared=declared,
         estimated_rows=count_parquet_rows(CT_MAPPED),
         action="write")

    async with async_db_session() as s:
        log.info(f"[BASELINE] {await snapshot_baselines(s)}")
        await build_map_table(s, load_all_studyuid_rows())
        good = await _resolve_fallback(
            s, good, first_dcm_paths(
                [r.study_uid for r in good if r.exam_date is None]))
        await ensure_stage_tables(s)
        await assert_stage_clean(s, [r.study_uid for r in good])
        look, exist = await collect_lookups(s, good)
        plan = build_plan(good, batch_id=BATCH_ID, **look, **exist)
        plan.stats["rows_invalid"] = len(bad)
        print_reconciliation(good, plan)
        if not skip_backup:
            await backup_tables()
        await write_stage(s, plan)
        n_phi = await write_phi(s, plan)
        row_counts = {
            "imaging_study": plan.stats["studies_new"],
            "dicom_series": plan.stats["series_new"],
            "exam": plan.stats["exams_created"],
            "patient": plan.stats["patients_new"],
            "phi_audit": n_phi,
        }
        await upsert_batch_row(s, "success", row_counts)
        log.info(f"[APPLY] stage 写入完成 row_counts={row_counts}")

    log.info("[APPLY] 下一步：--promote --target production（4 表按 FK 序上生产），"
             "随后 --verify 验收")
    return 0


async def do_promote(declared: str | None) -> int:
    gate(schema="lnrs",
         tables=["lnrs.lnrs_anon_patient", "lnrs.lnrs_anon_exam",
                 "lnrs.lnrs_anon_imaging_study", "lnrs.lnrs_anon_dicom_series",
                 "lnrs.lnrs_promote_audit", "lnrs.lnrs_promote_audit_row"],
         declared=declared, estimated_rows=None, action="write")
    from stage_promote import STAGE_REGISTRY, promote_stage_all

    async with async_db_session() as db:
        await ensure_stage_tables(db)  # 审计表可能被清理，promote 护栏依赖
        for spec in STAGE_REGISTRY:
            n = int((await db.execute(text(
                f"SELECT COUNT(*) FROM {spec.stage_table}"))).scalar() or 0)
            log.info(f"[PROMOTE] {spec.stage_table} = {n} 行待上")
        results = await promote_stage_all(db)
    for name, n, bid in results:
        log.info(f"[PROMOTE] {name}: upsert {n}（batch={bid}）")
        log.info(f"[PROMOTE] 回滚命令：promote_stage_all.py --rollback {bid} --table {name}")
    return 0


async def do_verify() -> int:
    rows = load_cxf_rows()
    async with async_db_session() as s:
        n_map = (await s.execute(text(
            f"SELECT COUNT(*) FROM {TMP_MAP} WHERE is_cxf"))).scalar()
    if int(n_map) == 0:
        async with async_db_session() as s:
            await build_map_table(s, load_all_studyuid_rows())
    await verify_apply(len(rows))
    await audit_exam_links()
    log.info("[VERIFY] 全部断言通过")
    return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Issue 24: cxf_archives 7,984 study 入库")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="只读对账报告，不写库")
    mode.add_argument("--apply", action="store_true",
                      help="备份 + stage 写入 + phi/batch（生产 4 表由 --promote 上）")
    mode.add_argument("--promote", action="store_true",
                      help="stage 4 表按 FK 序 promote 上生产（issue-22/23 护栏）")
    mode.add_argument("--verify", action="store_true",
                      help="promote 后验收断言 + 33,110 复核（只读）")
    mode.add_argument("--audit-only", action="store_true",
                      help="只跑 33,110 anon_exam_id 复核（只读）")
    p.add_argument("--skip-backup", action="store_true", help="跳过备份（不推荐）")
    add_target_argument(p)
    return p.parse_args()


async def main() -> int:
    args = _parse_args()
    if args.dry_run:
        gate(schema="lnrs", tables=[], declared=args.target,
             estimated_rows=count_parquet_rows(CT_MAPPED), action="read")
        return await do_dry_run()
    if args.apply:
        return await do_apply(args.target, args.skip_backup)
    if args.promote:
        return await do_promote(args.target)
    if args.verify:
        gate(schema="lnrs", tables=[], declared=args.target, action="read")
        return await do_verify()
    gate(schema="lnrs", tables=[], declared=args.target, action="read")
    await audit_exam_links()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
