"""Issue 25: xinqiao exam 报告源补全 — Accession 纯报告 + 262 新检查（执行脚本）。

按 docs/etl2/prd/issue-25-xinqiao-exam-report-source-completion.md，把
ct_mapped.parquet（124,308 行，CT 报告+DICOM 合并版）中未入库的两类数据
增量灌入 lnrs_anon_exam / lnrs_anon_report_text / lnrs_anon_exam_detail：

1. 83,010 行 Accession_* 纯报告（raw_text / exam_date 100%，盘上无 DICOM）；
2. 262 行 StudyUID 键新检查（exam_date NULL → lnrs.uid_study_date(StudyUID)
   内嵌时间戳兜底；兜底失败的行与对应患者保持不入并在报告列明）。

决策门（开单时预置，均已确认）：
- 去重口径：按 (patient_id, exam_date, sha256(raw_text)) 三键幂等跳过与
  已灌 124,045 行内容全等的部分；另按 source_exam_hash 精确跳过同 exam_id
  （两口径并集，保证不产生重复 exam、不改既有行）。
- 双 ID 空间：新行 exam_no 直接用 ct_mapped 的 exam_id（Accession_* 或
  StudyUID），hash/anon_exam_id 由引擎派生，与旧键空间天然不相交。
- 262 行 exam_date NULL：uid_study_date 兜底，成功者灌入，失败者不入。

数据流
------
1. 备份：exam / report_text / exam_detail（xinqiao CT 范围）+ patient
   （xinqiao 全量）建 `lnrs_anon_<t>_bak_<ts>` CTAS 快照。
2. 分类（seam: decide_row，纯函数见 tests）：逐行判定
   ingest / skip_ingested（source_exam_hash 命中，最高优先级——幂等重跑口径）/
   skip_duplicate_content（(anon_pid, exam_date, body_md5) 三键命中）/
   drop_no_date（含兜底失败）。
3. staging：survivor 行按 0904 适配同款变换（中文标题切分 findings/impression、
   nodules 展开、占位 n0）写 data_xq_issue25/xinqiao/nodule_imaging.parquet
   （gitignore）；NULL 日期行 exam_date 取 uid_study_date 结果。
4. 灌库：直调引擎 _import_exam_text_table（不走 ETL2 CLI，避免连带 dicom_series
   重注册，issue-13 惯例）；_close_batch 显式 commit（issue-13 遗留缺陷教训）。
5. 验收：重复 exam 断言 + Accession 行 exam_date 非空率 + zhujiang/shengyi
   零漂移；产出 docs/etl2/verify_xinqiao_exam_source_completion.sql。

幂等：三键 + source_exam_hash 去重 → 重跑全 skip，0 新增。

环境: ENVIRONMENT=h196_3（本机即 h196_3，不要 ssh）。
用法:
    cd backend
    ENVIRONMENT=h196_3 uv run python etl2/_issue25_ingest_xinqiao_report_source.py --dry-run
    ENVIRONMENT=h196_3 uv run python etl2/_issue25_ingest_xinqiao_report_source.py --apply
    ENVIRONMENT=h196_3 uv run python etl2/_issue25_ingest_xinqiao_report_source.py --apply   # 幂等重跑
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from datetime import datetime
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_ETL2_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_BACKEND_ROOT))
sys.path.insert(0, str(_ETL2_DIR))

import duckdb  # noqa: E402
from _script_guard import (  # noqa: E402
    EXAM_TEXT_INGEST_TABLES,
    add_target_argument,
    count_parquet_rows,
    gate,
)
from sqlalchemy import text  # noqa: E402

from app.core.database import async_db_session  # noqa: E402
from app.core.logger import log  # noqa: E402
from app.plugin.module_medical.hospital.anonymize import (  # noqa: E402
    compute_anon_id,
    truncate_body,
)
from app.plugin.module_medical.hospital.anon_etl_engine import (  # noqa: E402
    _CENTER_PARQUET_SPECS as _ENGINE_SPECS,
)

CENTER = "xinqiao"

DEFAULT_SRC = Path("/data/wlx/DATABASE/extracted_tables/xinqiao/ct_mapped.parquet")
STAGING_ROOT = _BACKEND_ROOT.parent / "data_xq_issue25" / CENTER

# xinqiao spec：复用引擎 nodule_imaging 条目（剔除 'kind'），单源定义。
XQ_NODULE_SPEC: dict = {
    k: v
    for k, v in next(
        s for s in _ENGINE_SPECS["xinqiao"] if s["src_table"] == "nodule_imaging"
    ).items()
    if k != "kind"
}

# 与 etl1_adapt_xinqiao_ct.py 完全一致的中文标题切分正则（显式 's' flag）
FINDINGS_PAT = r"检查所见[\r\n]+(.*?)[\r\n]+检查结论"
IMPRESSION_PAT = r"检查结论[\r\n]+(.*?)$"


# ---------- seam: 行级决策（纯函数，见 tests） ----------

def recombined_body(findings: str | None, impression: str | None) -> str:
    """复刻引擎 _import_exam_text_table 的正文拼接（仅非空段 join + 截断）。"""
    parts = [p for p in (findings, impression) if p]
    return truncate_body("\n\n".join(parts))


def content_body_md5(findings: str | None, impression: str | None) -> str:
    """内容三键的第三键：拼接正文 md5（与 report_text.md5(body_clean) 可比）。"""
    return hashlib.md5(recombined_body(findings, impression).encode("utf-8")).hexdigest()


def decide_row(
    *,
    exam_hash_in_db: bool,
    content_key_in_db: bool,
    resolved_date: object | None,
) -> str:
    """行级增量判定。

    优先级：source_exam_hash 已入库（幂等重跑口径，无论日期）→ skip_ingested；
    无日期（且兜底失败）→ drop_no_date；
    (patient, date, body) 三键已入库 → skip_duplicate_content；
    否则 → ingest。
    """
    if exam_hash_in_db:
        return "skip_ingested"
    if resolved_date is None:
        return "drop_no_date"
    if content_key_in_db:
        return "skip_duplicate_content"
    return "ingest"


# ---------- 库内基线 ----------

async def load_db_baselines() -> tuple[set[str], set[tuple[str, str, str]]]:
    """(source_exam_hash 集合, (anon_pid, exam_date, body_md5) 三键集合)。

    范围：xinqiao CT 既有 124,045 行。body_md5 由 PG 侧 md5(body_clean) 计算，
    与 content_body_md5 同口径（均经引擎截断后再落库，可比）。
    """
    async with async_db_session() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT e.source_exam_hash, p.anon_id, e.exam_date::text, "
                    "coalesce(md5(rt.body_clean), '') "
                    "FROM lnrs.lnrs_anon_exam e "
                    "JOIN lnrs.lnrs_anon_patient p ON p.patient_id = e.patient_id "
                    "LEFT JOIN lnrs.lnrs_anon_report_text rt "
                    "ON rt.anon_exam_id = e.anon_exam_id "
                    "WHERE e.center_code = :c AND e.exam_type = 'CT'"
                ),
                {"c": CENTER},
            )
        ).fetchall()
    hashes: set[str] = set()
    keys: set[tuple[str, str, str]] = set()
    for h, pid, d, bmd5 in rows:
        hashes.add(h)
        if pid and d:
            keys.add((pid, d, bmd5))
    log.info(f"[BASELINE] source_exam_hash={len(hashes)} content_keys={len(keys)}")
    return hashes, keys


async def resolve_uid_dates(exam_ids: list[str]) -> dict[str, str]:
    """lnrs.uid_study_date(StudyUID) 批量兜底，返回 {exam_id: 'YYYY-MM-DD'}。"""
    if not exam_ids:
        return {}
    out: dict[str, str] = {}
    async with async_db_session() as s:
        await s.execute(text("CREATE TEMP TABLE _i25_uids(exam_id text PRIMARY KEY)"))
        for i in range(0, len(exam_ids), 5000):
            await s.execute(
                text("INSERT INTO _i25_uids VALUES (:e)"),
                [{"e": e} for e in exam_ids[i : i + 5000]],
            )
        rows = (
            await s.execute(
                text(
                    "SELECT u.exam_id, lnrs.uid_study_date(u.exam_id)::text "
                    "FROM _i25_uids u WHERE lnrs.uid_study_date(u.exam_id) IS NOT NULL"
                )
            )
        ).fetchall()
        await s.execute(text("DROP TABLE _i25_uids"))
    out = {e: d for e, d in rows}
    log.info(f"[UID-DATE] 兜底成功 {len(out)}/{len(exam_ids)}")
    return out


# ---------- 分类主流程 ----------

def classify(
    src: Path,
    known_hashes: set[str],
    known_keys: set[tuple[str, str, str]],
    uid_dates: dict[str, str],
) -> dict[str, list[str]]:
    """扫描 ct_mapped，逐行 decide_row；返回各决策的 exam_id 列表。"""
    con = duckdb.connect()
    cur = con.execute(
        f"""
        SELECT exam_id, patient_id, CAST(exam_date AS DATE) AS exam_date,
               coalesce(
                   nullif(trim(regexp_extract(raw_text, '{FINDINGS_PAT}', 1, 's')), ''), ''
               ) AS findings,
               coalesce(
                   nullif(trim(regexp_extract(raw_text, '{IMPRESSION_PAT}', 1, 's')), ''), ''
               ) AS impression
        FROM read_parquet('{src.as_posix()}')
        """
    )
    result: dict[str, list[str]] = {
        "ingest": [],
        "skip_ingested": [],
        "skip_duplicate_content": [],
        "drop_no_date": [],
    }
    while True:
        rows = cur.fetchmany(2000)
        if not rows:
            break
        for exam_id, pid, exam_date, findings, impression in rows:
            exam_hash = hashlib.sha256(
                f"{CENTER}:{exam_id}".encode("utf-8")
            ).hexdigest()
            resolved = exam_date.isoformat() if exam_date else uid_dates.get(exam_id)
            if exam_hash in known_hashes:
                decision = "skip_ingested"
            elif resolved is None:
                decision = "drop_no_date"
            else:
                content_key = (
                    compute_anon_id(CENTER, str(pid)),
                    resolved,
                    content_body_md5(findings, impression),
                )
                decision = decide_row(
                    exam_hash_in_db=False,
                    content_key_in_db=content_key in known_keys,
                    resolved_date=resolved,
                )
            result[decision].append(exam_id)
    con.close()
    return result


def write_staging(src: Path, ingest_ids: list[str], uid_dates: dict[str, str]) -> Path:
    """survivor 行 → staging nodule_imaging.parquet（0904 适配同款变换）。"""
    STAGING_ROOT.mkdir(parents=True, exist_ok=True)
    dst = STAGING_ROOT / "nodule_imaging.parquet"
    con = duckdb.connect()
    # ingest id 集与 uid 兜底日期都经临时 parquet 传入（83k 行 VALUES 列表不可靠）
    id_tbl = STAGING_ROOT / "_ingest_ids.parquet"
    uid_tbl = STAGING_ROOT / "_uid_dates.parquet"
    con.execute(
        "COPY (SELECT * FROM (VALUES " +
        ",".join(f"('{e}')" for e in ingest_ids) +
        ") t(exam_id)) TO '" + id_tbl.as_posix() + "' (FORMAT PARQUET)"
    )
    id_join = f"JOIN read_parquet('{id_tbl.as_posix()}') i USING (exam_id) "
    if uid_dates:
        con.execute(
            "COPY (SELECT * FROM (VALUES " +
            ",".join(f"('{k}', DATE '{v}')" for k, v in uid_dates.items()) +
            ") t(exam_id, uid_date)) TO '" + uid_tbl.as_posix() + "' (FORMAT PARQUET)"
        )
        uid_join = f"LEFT JOIN read_parquet('{uid_tbl.as_posix()}') u USING (exam_id) "
    else:
        uid_join = ""
    sql = f"""
        COPY (
            WITH src AS (
                SELECT
                    m.patient_id, m.exam_id, m.exam_name, m.contrast,
                    m.slice_thickness_mm, m.mediastinal_lymphadenopathy,
                    m.pleural_effusion, m.vs_prior, m.nodules, m.raw_text,
                    COALESCE(CAST(m.exam_date AS DATE), u.uid_date) AS exam_date
                FROM read_parquet('{src.as_posix()}') m
                {id_join}
                {uid_join}
            ),
            unnested AS (
                SELECT
                    s.*,
                    g.i AS ord,
                    list_extract(s.nodules, g.i) AS nodule,
                    (s.nodules IS NULL OR len(s.nodules) = 0) AS is_placeholder
                FROM src s,
                     generate_series(1, GREATEST(COALESCE(len(s.nodules), 0), 1)) g(i)
            )
            SELECT
                patient_id,
                exam_id,
                exam_date,
                CASE WHEN is_placeholder THEN 'n0' ELSE 'n' || ord::VARCHAR END
                    AS nodule_no,
                CASE WHEN is_placeholder THEN NULL ELSE nodule.nodule_location.lobe END
                    AS nodule_location,
                CASE WHEN is_placeholder THEN NULL ELSE nodule.long_diameter_mm END
                    AS long_diameter,
                CASE WHEN is_placeholder THEN NULL ELSE nodule.density_type END
                    AS density_type,
                CASE
                    WHEN is_placeholder THEN NULL
                    ELSE struct_pack(
                        exam_name := exam_name,
                        contrast := contrast,
                        slice_thickness_mm := slice_thickness_mm,
                        vs_prior := vs_prior,
                        mediastinal_lymphadenopathy := mediastinal_lymphadenopathy,
                        pleural_effusion := pleural_effusion,
                        report_date := exam_date,
                        source := 'xinqiao_ct_mapped.parquet'
                    )
                END AS exam_meta,
                CASE WHEN is_placeholder THEN NULL ELSE [nodule] END
                    AS nodule_morphology,
                coalesce(nullif(trim(regexp_extract(raw_text, '{FINDINGS_PAT}', 1, 's')), ''), '')
                    AS findings,
                coalesce(nullif(trim(regexp_extract(raw_text, '{IMPRESSION_PAT}', 1, 's')), ''), '')
                    AS impression,
                raw_text
            FROM unnested
        ) TO '{dst.as_posix()}' (FORMAT PARQUET, OVERWRITE_OR_IGNORE)
    """
    con.execute(sql)
    id_tbl.unlink(missing_ok=True)
    uid_tbl.unlink(missing_ok=True)
    con.close()
    return dst


# ---------- 备份 ----------

async def backup() -> dict[str, str]:
    """PRD：exam / report_text / exam_detail / patient 建 _bak_<ts> 快照。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    made: dict[str, str] = {}
    async with async_db_session() as s:
        specs = [
            ("lnrs_anon_exam", "WHERE center_code = 'xinqiao' AND exam_type = 'CT'"),
            (
                "lnrs_anon_report_text",
                "WHERE anon_exam_id IN (SELECT anon_exam_id FROM lnrs.lnrs_anon_exam "
                "WHERE center_code = 'xinqiao' AND exam_type = 'CT')",
            ),
            (
                "lnrs_anon_exam_detail",
                "WHERE anon_exam_id IN (SELECT anon_exam_id FROM lnrs.lnrs_anon_exam "
                "WHERE center_code = 'xinqiao' AND exam_type = 'CT')",
            ),
            ("lnrs_anon_patient", "WHERE center_code = 'xinqiao'"),
        ]
        for tbl, where in specs:
            bak = f"{tbl}_bak_{ts}"
            await s.execute(
                text(f"CREATE TABLE lnrs.{bak} AS SELECT * FROM lnrs.{tbl} {where}")
            )
            n = (
                await s.execute(text(f"SELECT COUNT(*) FROM lnrs.{bak}"))
            ).scalar()
            made[tbl] = bak
            log.info(f"[BACKUP] lnrs.{bak} <- {n} rows")
        await s.commit()
    return made


# ---------- 灌库 ----------

async def ingest(parquet_path: Path) -> dict:
    """直调引擎 _import_exam_text_table（stage_mode=False 直写主表）。"""
    from app.plugin.module_medical.hospital.anon_etl_engine import (
        _import_exam_text_table,
        _resolve_hospital_id,
    )
    from app.plugin.module_medical.hospital.anon_etl_service import (
        _close_batch,
        _create_batch,
    )
    async with async_db_session() as batch_sess:
        batch_id = await _create_batch(
            batch_sess, center_code=CENTER, data_dir=STAGING_ROOT.parent,
            source_kind="csv_report",
        )
        await batch_sess.commit()
    log.info(f"[ETL-2] batch_id={batch_id}")
    n = 0
    try:
        async with async_db_session() as sess:
            await _resolve_hospital_id(sess, CENTER)
            n = await _import_exam_text_table(
                sess, center_code=CENTER, parquet_path=parquet_path,
                batch_id=batch_id, **XQ_NODULE_SPEC,
            )
            # issue-13 教训：_close_batch 之外，灌库事务本身也要显式 commit
            await sess.commit()
    except Exception:
        async with async_db_session() as close_sess:
            await _close_batch(close_sess, batch_id=batch_id, status="failed", row_counts={})
            await close_sess.commit()
        raise
    async with async_db_session() as close_sess:
        await _close_batch(
            close_sess, batch_id=batch_id, status="success",
            row_counts={XQ_NODULE_SPEC["src_table"]: n},
        )
        await close_sess.commit()
    log.info(f"[ETL-2] nodule_imaging 导入 {n} 行 exam+report (batch={batch_id})")
    return {"batch_id": batch_id, "rows": n}


# ---------- 验收 ----------

async def verify_apply(ingested_before: int, patients_before: int) -> dict:
    """灌后断言 + 增量计数。"""
    async with async_db_session() as s:
        q = lambda sql: s.execute(text(sql))
        exam_after = (
            await q(
                "SELECT COUNT(*) FROM lnrs.lnrs_anon_exam "
                "WHERE center_code='xinqiao' AND exam_type='CT'"
            )
        ).scalar()
        pat_after = (
            await q(
                "SELECT COUNT(*) FROM lnrs.lnrs_anon_patient WHERE center_code='xinqiao'"
            )
        ).scalar()
        # 重复 exam 断言：(patient_id, exam_date, body md5) 口径不存在重复
        dup = (
            await q(
                "SELECT COUNT(*) FROM ("
                "  SELECT e.patient_id, e.exam_date, coalesce(md5(rt.body_clean),'') AS k,"
                "         COUNT(*) AS n"
                "  FROM lnrs.lnrs_anon_exam e"
                "  LEFT JOIN lnrs.lnrs_anon_report_text rt USING (anon_exam_id)"
                "  WHERE e.center_code='xinqiao' AND e.exam_type='CT'"
                "  GROUP BY 1,2,3 HAVING COUNT(*) > 1"
                ")"
            )
        ).scalar()
        # Accession 行 exam_date 非空率 100%：Accession exam_id 无法从 anon 域反推，
        # 以「最新 batch 新增行 exam_date 非空」断言（staging 构造已保证非空，
        # verify SQL V4 独立复核），见 verify_xinqiao_exam_source_completion.sql
        new_rows = (
            await q(
                "SELECT COUNT(*) FILTER (WHERE exam_date IS NULL), COUNT(*) "
                "FROM lnrs.lnrs_anon_exam "
                "WHERE center_code='xinqiao' AND exam_type='CT' "
                "AND created_batch_id = ("
                "  SELECT batch_id FROM lnrs.lnrs_anon_ingest_batch"
                "  WHERE center_code='xinqiao' ORDER BY started_at DESC LIMIT 1)"
            )
        ).fetchone()
        zj = (
            await q(
                "SELECT center_code, COUNT(*) FROM lnrs.lnrs_anon_exam "
                "WHERE center_code IN ('zhujiang','shengyi') GROUP BY 1"
            )
        ).fetchall()
        zj_rt = (
            await q(
                "SELECT e.center_code, COUNT(*) FROM lnrs.lnrs_anon_report_text rt "
                "JOIN lnrs.lnrs_anon_exam e USING (anon_exam_id) "
                "WHERE e.center_code IN ('zhujiang','shengyi') GROUP BY 1"
            )
        ).fetchall()
    out = {
        "exam_new": exam_after - ingested_before,
        "patient_new": pat_after - patients_before,
        "dup_content_keys": dup,
        "new_rows_null_date": new_rows[0],
        "new_rows_total": new_rows[1],
        "zj_sy_exam": {c: int(n) for c, n in zj},
        "zj_sy_rt": {c: int(n) for c, n in zj_rt},
        "exam_after": exam_after,
    }
    assert out["dup_content_keys"] == 0, f"重复 exam: {out['dup_content_keys']}"
    assert out["new_rows_null_date"] == 0, "新增行存在 NULL exam_date"
    log.info(f"[VERIFY] {out}")
    return out


# ---------- 主流程 ----------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Issue 25: xinqiao 报告源补全（Accession + 262 新检查）")
    p.add_argument("--dry-run", action="store_true", help="只分类对账，不写库不写 staging")
    p.add_argument("--apply", action="store_true", help="写 staging + 灌库")
    p.add_argument("--src", type=Path, default=DEFAULT_SRC)
    p.add_argument("--skip-backup", action="store_true",
                   help="跳过备份（中断重跑时备份快照已存在）")
    add_target_argument(p)
    return p.parse_args()


async def preflight(src: Path) -> None:
    assert src.exists(), f"源文件缺失: {src}"


async def main() -> int:
    args = _parse_args()
    gate(
        schema="lnrs",
        tables=list(EXAM_TEXT_INGEST_TABLES),
        declared=args.target,
        estimated_rows=None,
        action="write" if args.apply else "read",
    )
    await preflight(args.src)

    known_hashes, known_keys = await load_db_baselines()
    uid_dates = await resolve_uid_dates_for_candidates(args.src, known_hashes, known_keys)
    decisions = classify(args.src, known_hashes, known_keys, uid_dates)
    for k, v in decisions.items():
        log.info(f"[CLASSIFY] {k}: {len(v)}")

    ingested_before = await count_center_exams()
    patients_before = await count_center_patients()

    if args.dry_run or not args.apply:
        log.info(
            "[DRY-RUN] exam 增量=%d（Accession 新 exam + 新检查），跳过 ingested=%d / "
            "重复内容=%d，兜底失败不入=%d；新患者（引擎占位，apply 后实测）≈ 未计",
            len(decisions["ingest"]),
            len(decisions["skip_ingested"]),
            len(decisions["skip_duplicate_content"]),
            len(decisions["drop_no_date"]),
        )
        return 0

    if not decisions["ingest"]:
        out = await verify_apply(ingested_before, patients_before)
        log.info(f"[DONE] 幂等重跑：0 新增（全部行已被三键/hash 跳过），verify={out}")
        return 0

    backup_tbls = {} if args.skip_backup else await backup()
    staging = write_staging(args.src, decisions["ingest"], uid_dates)
    n_stage = count_parquet_rows(staging)
    log.info(f"[STAGING] {staging} rows={n_stage}")
    assert n_stage is not None and n_stage >= len(decisions["ingest"]), "staging 行数异常"
    res = await ingest(staging)
    out = await verify_apply(ingested_before, patients_before)
    log.info(f"[DONE] batch={res['batch_id']} backup={backup_tbls} verify={out}")
    return 0


async def resolve_uid_dates_for_candidates(
    src: Path, known_hashes: set[str], known_keys: set[tuple[str, str, str]]
) -> dict[str, str]:
    """只对「无日期且 hash 未命中」的行做 uid 兜底查询（缩小范围）。"""
    con = duckdb.connect()
    ids = [
        r[0]
        for r in con.execute(
            f"""
            SELECT DISTINCT exam_id FROM read_parquet('{src.as_posix()}')
            WHERE exam_date IS NULL
            """
        ).fetchall()
        if hashlib.sha256(f"{CENTER}:{r[0]}".encode("utf-8")).hexdigest() not in known_hashes
    ]
    con.close()
    return await resolve_uid_dates(ids)


async def count_center_exams() -> int:
    async with async_db_session() as s:
        return (
            await s.execute(
                text(
                    "SELECT COUNT(*) FROM lnrs.lnrs_anon_exam "
                    "WHERE center_code='xinqiao' AND exam_type='CT'"
                )
            )
        ).scalar()


async def count_center_patients() -> int:
    async with async_db_session() as s:
        return (
            await s.execute(
                text(
                    "SELECT COUNT(*) FROM lnrs.lnrs_anon_patient "
                    "WHERE center_code='xinqiao'"
                )
            )
        ).scalar()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
