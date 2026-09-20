"""Issue 13: xinqiao exam 灌库 + 回填 imaging_study / dicom_series.anon_exam_id（执行脚本）。

按 docs/etl2/prd/issue-13-xinqiao-exam-ingest.md，复用 issue-6
(_issue6_ingest_zhujiang_ct_exam.py) 的「备份 → 灌库 → dry-run → apply → 验收」
路径，扩展 `--center xinqiao`。调研与数据实测见
docs/etl2/verify_result/xinqiao-exam-source-20260920.md。

数据流
------
1. 备份：lnrs_anon_imaging_study xinqiao 全表快照 lnrs_anon_imaging_study_bak_<ts>
   （PRD 验收 9）+ dicom_series.anon_exam_id 现值到 lnrs_tmp_issue13_series_before
   （回退用）+ exam 分布日志。
2. 适配：ct.parquet（新桥 extracted_tables 导出）→ staging nodule_imaging.parquet
   （复用 0904 批次适配脚本 etl1_adapt_xinqiao_ct.py，中文标题切分，幂等）。
3. 灌库：直调引擎 _import_exam_text_table 写 lnrs_anon_exam（exam_type='CT'，
   124,045 行）+ report_text + exam_detail + phi_audit；患者 upsert 复用既有
   33,109 行、新增 ~16,351 占位（sex='0'）。不走 ETL2 CLI（CLI 会连带触发
   xinqiao spec 的 dicom_series kind 重注册，违背「不动既有 dicom_series」）。
   与 issue-6 的差异：本脚本用 _close_batch 正常关闭 batch（issue-6 遗留的
   两个 zhujiang running batch 即此缺陷）。
4. 回填 tier-1：复用 backfill_imaging_study_exam_id 模块（--center xinqiao）：
   (patient_id, |exam_date - study_date| 最近, 平局 anon_exam_id 最小)；
   study_date = COALESCE(path_study_date(image_path), uid_study_date(dicom_study_uid))
   —— xinqiao image_path 无日期，由 StudyInstanceUID 内嵌时间戳兜底
   （0027-uid-study-date.sql；实测 99.93% 与 exam_date 同日）。
   实测 matchable = 31,098（dry-run，灌库后）。
5. 回填残留（xinqiao 特有）：无日期 study（2,012 个，患者有 CT exam）按
   pick_residual_exam 确定性兜底（唯一候选 / ct_dicom_map 文件数精确匹配 /
   anon_exam_id 平局），见 docs/etl2/verify_result/xinqiao-exam-source-20260920.md §4。
6. dicom_series.anon_exam_id：从 imaging_study 同步（study:series = 1:1，
   守卫 WHERE ds.anon_exam_id IS NULL；issue-6 明确不动 dicom_series，
   本 issue 的端到端目标就是它非全 NULL）。
7. 验收：PRD 断言 1-3（断言 3 按调研文档 §5 的可执行口径）+ 外键完整 +
   抽样 + 跨中心零漂移 + 全列 checksum（除 anon_exam_id）。

幂等
----
- 灌库按 (center_code, source_exam_hash) upsert → 重跑无重复行。
- 回填 / 残留 / series 全部带 WHERE anon_exam_id IS NULL 守卫 → 重跑 0 更新。
- 重跑建议：--skip-adapt --skip-ingest（staging 与灌库已完成）。

环境: ENVIRONMENT=h196_3（本机即 h196_3，不要 ssh）。
用法:
    cd backend
    ENVIRONMENT=h196_3 uv run python etl2/_issue13_ingest_xinqiao_ct_exam.py --dry-run
    ENVIRONMENT=h196_3 uv run python etl2/_issue13_ingest_xinqiao_ct_exam.py
    # 幂等重跑（staging/灌库已完成）:
    ENVIRONMENT=h196_3 uv run python etl2/_issue13_ingest_xinqiao_ct_exam.py --skip-adapt --skip-ingest
"""

import argparse
import asyncio
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_ETL2_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_BACKEND_ROOT))
sys.path.insert(0, str(_ETL2_DIR))

import duckdb  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.database import async_db_session  # noqa: E402
from app.core.logger import log  # noqa: E402
from app.plugin.module_medical.hospital.anon_etl_engine import (  # noqa: E402
    _CENTER_PARQUET_SPECS as _ENGINE_SPECS,
)

CENTER = "xinqiao"
DEFAULT_SRC_CT = "/data/wlx/DATABASE/extracted_tables/xinqiao/ct.parquet"
DEFAULT_SRC_MAP = "/data/wlx/DATABASE/extracted_tables/xinqiao/ct_dicom_map.parquet"
DEFAULT_STAGING = _BACKEND_ROOT.parent / "data_xq0913" / CENTER

# xinqiao spec：直接复用引擎 _CENTER_PARQUET_SPECS["xinqiao"] 的 nodule_imaging
# 条目（剔除 'kind'，直调 _import_exam_text_table 不需要）——单源定义，避免双拷贝漂移。
XQ_NODULE_SPEC: dict = {
    k: v
    for k, v in next(
        s for s in _ENGINE_SPECS["xinqiao"] if s["src_table"] == "nodule_imaging"
    ).items()
    if k != "kind"
}


# ---------- seam: 无日期残留 study 的确定性选择（纯函数，见 tests） ----------


def pick_residual_exam(
    study_file_count: int,
    candidates: list[dict],
) -> tuple[str, str] | None:
    """无日期残留 study 的 exam 选择。

    参数:
      study_file_count: 该 study 的 dicom_series.file_count（扫描实测在盘文件数）。
      candidates: 同患者全部 CT exam，每项
        {"anon_exam_id": str, "map_file_sum": int | None}
        —— map_file_sum = ct_dicom_map 中该 exam 的在盘文件数之和（未覆盖为 None）。

    规则（优先级从高到低，全部确定性可复现）:
      1. 无候选 → None（患者无 CT exam，study 保持 NULL —— 断言 3 不受影响）
      2. 唯一候选 → ('single')
      3. 恰有一个候选 map_file_sum == study_file_count → ('filecount')
         —— 一个 study 一次检查，exam 的在盘文件集合 == study 实测文件数
      4. 其余 → anon_exam_id 字典序最小 → ('tiebreak')（与 issue-1 平局规则一致）

    返回 (anon_exam_id, rule) 或 None。
    """
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]["anon_exam_id"], "single"
    matches = [
        c for c in candidates
        if c["map_file_sum"] is not None and c["map_file_sum"] == study_file_count
    ]
    if len(matches) == 1:
        return matches[0]["anon_exam_id"], "filecount"
    return min(c["anon_exam_id"] for c in candidates), "tiebreak"


async def backup_imaging_study(center: str) -> str:
    """PRD 验收 9：lnrs_anon_imaging_study_bak_<ts> 快照（PRD 原文 AS TABLE … WHERE 非合法 PG，按意图改 CTAS+SELECT）。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tbl = f"lnrs.lnrs_anon_imaging_study_bak_{ts}"
    async with async_db_session() as s:
        await s.execute(text(f"CREATE TABLE {tbl} AS SELECT * FROM lnrs.lnrs_anon_imaging_study WHERE center_code = :c"), {"c": center})
        n = (await s.execute(text(f"SELECT count(*) FROM {tbl}"))).scalar()
        await s.commit()
    log.info(f"[BACKUP] {tbl} +{n} 行")
    return tbl


async def backup_series_exam_state(center: str) -> None:
    """dicom_series.anon_exam_id 现值 → lnrs_tmp_issue13_series_before（回退用）。"""
    async with async_db_session() as s:
        await s.execute(text("""
            CREATE TABLE IF NOT EXISTS lnrs.lnrs_tmp_issue13_series_before (
                dicom_study_uid text PRIMARY KEY,
                anon_exam_id    text
            )
        """))
        await s.execute(text("""
            DELETE FROM lnrs.lnrs_tmp_issue13_series_before
            USING lnrs.lnrs_anon_dicom_series ds
            JOIN lnrs.lnrs_anon_imaging_study s USING (dicom_study_uid)
            WHERE lnrs.lnrs_tmp_issue13_series_before.dicom_study_uid = ds.dicom_study_uid
              AND s.center_code = :c
        """), {"c": center})
        n = (await s.execute(text("""
            INSERT INTO lnrs.lnrs_tmp_issue13_series_before (dicom_study_uid, anon_exam_id)
            SELECT ds.dicom_study_uid, ds.anon_exam_id
            FROM lnrs.lnrs_anon_dicom_series ds
            JOIN lnrs.lnrs_anon_imaging_study s USING (dicom_study_uid)
            WHERE s.center_code = :c
        """), {"c": center})).rowcount
        await s.commit()
    log.info(f"[BACKUP] lnrs_tmp_issue13_series_before +{n} 行")


async def log_exam_distribution(center: str, stage: str) -> None:
    async with async_db_session() as s:
        r = await s.execute(text("""
            SELECT exam_type, COUNT(*) AS n
            FROM lnrs.lnrs_anon_exam WHERE center_code = :c
            GROUP BY 1 ORDER BY 1
        """), {"c": center})
        log.info(f"[EXAM-DIST {stage}] {center}: {[dict(x._mapping) for x in r]}")


# ---------- 跨中心零漂移 + 全列 checksum（验收「不动既有数据」） ----------


def xq_checksum_sql() -> tuple[str, str]:
    """xinqiao 全列 checksum（除 anon_exam_id）SQL：(imaging_study, dicom_series)。

    snapshot 与零漂移校验共用（两查询语义必须一致）。
    """
    study_sql = """
        SELECT md5(string_agg(md5(r::text), ',' ORDER BY study_key))
        FROM (
            SELECT study_key, (row_to_json(x)::jsonb - 'anon_exam_id') AS r
            FROM (SELECT * FROM lnrs.lnrs_anon_imaging_study WHERE center_code = :c) x
        ) t
    """
    series_sql = """
        SELECT md5(string_agg(md5(r::text), ',' ORDER BY uid))
        FROM (
            SELECT x.dicom_study_uid AS uid,
                   (row_to_json(x)::jsonb - 'anon_exam_id') AS r
            FROM (
                SELECT ds.* FROM lnrs.lnrs_anon_dicom_series ds
                JOIN lnrs.lnrs_anon_imaging_study s USING (dicom_study_uid)
                WHERE s.center_code = :c
            ) x
        ) t
    """
    return study_sql, series_sql


async def snapshot_other_centers() -> dict:
    """记录 xinqiao 之外各中心的行数与 xinqiao 全列 checksum（除 anon_exam_id）。"""
    async with async_db_session() as s:
        other = {}
        r = await s.execute(text("""
            SELECT 'study', center_code,
                   COUNT(*), COUNT(*) FILTER (WHERE anon_exam_id IS NOT NULL)
            FROM lnrs.lnrs_anon_imaging_study
            WHERE center_code <> :c GROUP BY center_code
        """), {"c": CENTER})
        for row in r:
            other[f"study:{row.center_code}"] = (row[2], row[3])
        r = await s.execute(text("""
            SELECT 'series', s.center_code,
                   COUNT(*), COUNT(*) FILTER (WHERE ds.anon_exam_id IS NOT NULL)
            FROM lnrs.lnrs_anon_dicom_series ds
            JOIN lnrs.lnrs_anon_imaging_study s USING (dicom_study_uid)
            WHERE s.center_code <> :c GROUP BY s.center_code
        """), {"c": CENTER})
        for row in r:
            other[f"series:{row.center_code}"] = (row[2], row[3])
        r = await s.execute(text("""
            SELECT center_code, COUNT(*) FROM lnrs.lnrs_anon_exam
            GROUP BY center_code ORDER BY center_code
        """))
        other["exam:all"] = {row.center_code: row[1] for row in r}
        # xinqiao 全列 checksum（除 anon_exam_id）：回滚判定用
        study_sql, series_sql = xq_checksum_sql()
        other["xinqiao_study_checksum"] = (
            await s.execute(text(study_sql), {"c": CENTER})
        ).scalar()
        other["xinqiao_series_checksum"] = (
            await s.execute(text(series_sql), {"c": CENTER})
        ).scalar()
    log.info(f"[SNAPSHOT] {other['xinqiao_study_checksum'][:16]}… / {other['xinqiao_series_checksum'][:16]}…")
    return other


async def verify_no_drift(pre: dict, center: str, expected_new_exams: int) -> None:
    async with async_db_session() as s:
        for key in [k for k in pre if k.startswith(("study:", "series:"))]:
            total, with_exam = pre[key]
            if key.startswith("study:"):
                cc = key.split(":", 1)[1]
                r = (await s.execute(text("""
                    SELECT COUNT(*), COUNT(*) FILTER (WHERE anon_exam_id IS NOT NULL)
                    FROM lnrs.lnrs_anon_imaging_study WHERE center_code = :cc
                """), {"cc": cc})).one()
                assert (r[0], r[1]) == (total, with_exam), f"零漂移违例 {key}: {(total, with_exam)} → {(r[0], r[1])}"
            elif key.startswith("series:"):
                cc = key.split(":", 1)[1]
                r = (await s.execute(text("""
                    SELECT COUNT(*), COUNT(*) FILTER (WHERE ds.anon_exam_id IS NOT NULL)
                    FROM lnrs.lnrs_anon_dicom_series ds
                    JOIN lnrs.lnrs_anon_imaging_study s USING (dicom_study_uid)
                    WHERE s.center_code = :cc
                """), {"cc": cc})).one()
                assert (r[0], r[1]) == (total, with_exam), f"零漂移违例 {key}: {(total, with_exam)} → {(r[0], r[1])}"
        exams = (await s.execute(text("""
            SELECT center_code, COUNT(*) FROM lnrs.lnrs_anon_exam
            GROUP BY center_code ORDER BY center_code
        """))).all()
        now = {row.center_code: row[1] for row in exams}
        for cc, n in pre["exam:all"].items():
            expect = n + (expected_new_exams if cc == center else 0)
            assert now.get(cc, 0) == expect, f"exam 计数漂移 {cc}: {n} → {now.get(cc, 0)} (期望 {expect})"
        study_sql, series_sql = xq_checksum_sql()
        study_sum = (await s.execute(text(study_sql), {"c": center})).scalar()
        series_sum = (await s.execute(text(series_sql), {"c": center})).scalar()
        assert study_sum == pre["xinqiao_study_checksum"], "xinqiao imaging_study 非 anon_exam_id 列发生变化"
        assert series_sum == pre["xinqiao_series_checksum"], "xinqiao dicom_series 非 anon_exam_id 列发生变化"
    log.info("[VERIFY] 跨中心零漂移 + xinqiao 非 anon_exam_id 列 checksum 通过")


# ---------- 适配 + 灌库 ----------


def adapt_ct_parquet(src: Path, out_dir: Path) -> Path:
    """ct.parquet → staging nodule_imaging.parquet（0904 适配脚本，幂等）。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    adapter = _ETL2_DIR / "etl1_adapt_xinqiao_ct.py"
    log.info(f"[ADAPT] {src} → {out_dir / 'nodule_imaging.parquet'}")
    subprocess.run(
        [sys.executable, str(adapter), "--src", str(src), "--out-dir", str(out_dir)],
        check=True,
    )
    pq = out_dir / "nodule_imaging.parquet"
    assert pq.exists(), f"适配产物缺失: {pq}"
    return pq


async def ingest_ct_exam(center: str, parquet_path: Path, data_dir: Path) -> dict:
    """直调引擎灌库（issue-6 同款）；与 issue-6 的差异：正常关闭 batch。"""
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
            batch_sess, center_code=center, data_dir=data_dir,
            source_kind="csv_report",
        )
        await batch_sess.commit()
    log.info(f"[ETL-2] batch_id={batch_id}")

    n = 0
    try:
        async with async_db_session() as sess:
            await _resolve_hospital_id(sess, center)
            n = await _import_exam_text_table(
                sess, center_code=center, parquet_path=parquet_path,
                batch_id=batch_id, **XQ_NODULE_SPEC,
            )
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
    log.info(f"[ETL-2] {XQ_NODULE_SPEC['src_table']} 导入 {n} 行 exam+report (batch={batch_id})")
    return {"batch_id": batch_id, "rows": n}


# ---------- 回填 tier-1（复用 backfill 模块） ----------


async def run_tier1(center: str) -> int:
    """dry-run 报告 + apply；返回 matchable（实测 31,098）。"""
    from backfill_imaging_study_exam_id import run_apply, run_dry_run
    rows = await run_dry_run(center)
    row = next((r for r in rows if r.center_code == center), None)
    matchable = int(row.matchable) if row else 0
    log.info(f"[TIER-1] dry-run matchable={matchable} no_study_date={row.no_study_date if row else 0}")
    await run_apply(center)
    return matchable


# ---------- 回填残留（xinqiao 特有：无日期 study） ----------


def _load_map_file_sums(map_path: Path) -> dict[tuple[str, str], int]:
    """ct_dicom_map → {(raw_pid, raw_exam_id): 在盘文件数之和}。"""
    con = duckdb.connect()
    try:
        rows = con.execute(
            """
            SELECT patient_id, exam_id, sum(len(filenames)) AS n
            FROM read_parquet(?)
            GROUP BY 1, 2
            """,
            [map_path.as_posix()],
        ).fetchall()
    finally:
        con.close()
    return {(p, e): int(n) for p, e, n in rows}


def _load_pid_exam_index(src_ct: Path, center: str) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """ct.parquet → (pid→patient anon_id, patient anon_id→{anon_exam_id: raw_exam_id})。"""
    from app.plugin.module_medical.hospital.anonymize import (
        compute_anon_exam_id,
        compute_anon_id,
    )
    con = duckdb.connect()
    try:
        rows = con.execute(
            "SELECT DISTINCT patient_id, exam_id FROM read_parquet(?)",
            [src_ct.as_posix()],
        ).fetchall()
    finally:
        con.close()
    pid2anon: dict[str, str] = {}
    pid2exams: dict[str, dict[str, str]] = {}
    for pid, exam_id in rows:
        anon = compute_anon_id(center, pid)
        pid2anon[pid] = anon
        pid2exams.setdefault(anon, {})[compute_anon_exam_id(center, exam_id)] = exam_id
    return pid2anon, pid2exams


async def run_residual(center: str, src_ct: Path, map_path: Path) -> dict:
    """无日期残留 study 兜底回填。返回 {rule: 行数}。"""
    from collections import Counter

    async with async_db_session() as s:
        residual = (await s.execute(text("""
            SELECT s.study_key, p.anon_id AS patient_anon_id, ds.file_count
            FROM lnrs.lnrs_anon_imaging_study s
            JOIN lnrs.lnrs_anon_patient p ON p.patient_id = s.patient_id
            JOIN lnrs.lnrs_anon_dicom_series ds USING (dicom_study_uid)
            WHERE s.center_code = :c AND s.anon_exam_id IS NULL
              AND EXISTS (
                SELECT 1 FROM lnrs.lnrs_anon_exam e
                WHERE e.patient_id = s.patient_id AND e.exam_type = 'CT'
              )
        """), {"c": center})).all()
        db_exams = (await s.execute(text("""
            SELECT p.anon_id AS patient_anon_id, e.anon_exam_id
            FROM lnrs.lnrs_anon_exam e
            JOIN lnrs.lnrs_anon_patient p ON p.patient_id = e.patient_id
            WHERE e.center_code = :c AND e.exam_type = 'CT'
        """), {"c": center})).all()
    log.info(f"[RESIDUAL] 无日期残留 study（患者有 CT exam）: {len(residual)}")
    if not residual:
        return {}

    file_sums = _load_map_file_sums(map_path)
    pid2anon, pid2exams = _load_pid_exam_index(src_ct, center)
    anon2pid = {v: k for k, v in pid2anon.items()}
    patient_exams: dict[str, set[str]] = {}
    for anon, eid in db_exams:
        patient_exams.setdefault(anon, set()).add(eid)

    rules: Counter = Counter()
    updates: list[tuple[int, str, str]] = []
    for row in residual:
        study_key, patient_anon, file_count = row[0], row[1], row[2]
        pid = anon2pid.get(patient_anon)
        exam_ids = sorted(patient_exams.get(patient_anon, set()))
        if not exam_ids:
            continue  # 理论上不存在（EXISTS 守卫）
        raw_ids = pid2exams.get(patient_anon, {})
        candidates = [
            {"anon_exam_id": eid, "map_file_sum": file_sums.get((pid, raw_ids.get(eid, ""))) if pid else None}
            for eid in exam_ids
        ]
        picked = pick_residual_exam(int(file_count), candidates)
        if not picked:
            continue
        updates.append((study_key, picked[0], picked[1]))
        rules[picked[1]] += 1

    log.info(f"[RESIDUAL] 选择分布: {dict(rules)}（合计 {len(updates)}）")
    async with async_db_session() as s:
        BATCH = 500
        for i in range(0, len(updates), BATCH):
            n = 0
            for study_key, eid, _rule in updates[i : i + BATCH]:
                r = await s.execute(
                    text(
                        "UPDATE lnrs.lnrs_anon_imaging_study SET anon_exam_id = :e "
                        "WHERE study_key = :k AND anon_exam_id IS NULL"
                    ),
                    {"e": eid, "k": study_key},
                )
                n += r.rowcount
            await s.commit()
            log.info(f"[RESIDUAL] 进度 {min(i + BATCH, len(updates))}/{len(updates)} updated={n}")
    return dict(rules)


# ---------- dicom_series 回填 ----------


async def backfill_dicom_series(center: str) -> int:
    async with async_db_session() as s:
        n = (await s.execute(text("""
            UPDATE lnrs.lnrs_anon_dicom_series ds
            SET anon_exam_id = s.anon_exam_id
            FROM lnrs.lnrs_anon_imaging_study s
            WHERE ds.dicom_study_uid = s.dicom_study_uid
              AND s.center_code = :c
              AND s.anon_exam_id IS NOT NULL
              AND ds.anon_exam_id IS NULL
        """), {"c": center})).rowcount
        await s.commit()
    log.info(f"[SERIES] dicom_series.anon_exam_id 回填 {n} 行")
    return int(n or 0)


# ---------- 验收 ----------


async def verify(center: str) -> dict:
    """PRD 断言 1-3 + 外键完整 + 抽样。"""
    out: dict = {}
    async with async_db_session() as s:
        # 断言 1：dicom_series 非 NULL > 0
        a1 = (await s.execute(text("""
            SELECT COUNT(*)
            FROM lnrs.lnrs_anon_dicom_series ds
            JOIN lnrs.lnrs_anon_imaging_study s USING (dicom_study_uid)
            WHERE s.center_code = :c AND ds.anon_exam_id IS NOT NULL
        """), {"c": center})).scalar()
        out["series_with_exam"] = a1
        assert a1 > 0, "断言 1 失败：dicom_series.anon_exam_id 仍全 NULL"

        # 断言 2：dicom_series 外键完整 = 0
        a2 = (await s.execute(text("""
            SELECT COUNT(*) FROM lnrs.lnrs_anon_dicom_series ds
            WHERE ds.anon_exam_id IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM lnrs.lnrs_anon_exam e
                WHERE e.anon_exam_id = ds.anon_exam_id
              )
        """))).scalar()
        out["series_fk_violate"] = a2
        assert a2 == 0, f"断言 2 失败：外键违例 {a2}"

        # 断言 3（调研文档 §5 可执行口径）：无漏匹配 = 0
        a3 = (await s.execute(text("""
            SELECT COUNT(*) FROM lnrs.lnrs_anon_imaging_study s
            WHERE s.center_code = :c AND s.anon_exam_id IS NULL
              AND EXISTS (
                SELECT 1 FROM lnrs.lnrs_anon_exam e
                WHERE e.patient_id = s.patient_id AND e.exam_type = 'CT'
              )
        """), {"c": center})).scalar()
        out["study_unmatched_with_exam"] = a3
        assert a3 == 0, f"断言 3 失败：未漏匹配 {a3}"

        # study 覆盖率
        cov = (await s.execute(text("""
            SELECT COUNT(*), COUNT(*) FILTER (WHERE anon_exam_id IS NOT NULL)
            FROM lnrs.lnrs_anon_imaging_study WHERE center_code = :c
        """), {"c": center})).one()
        out["study_total"], out["study_with_exam"] = cov[0], cov[1]

        # 抽样 3 条：patient 一致 + 距离
        r = await s.execute(text("""
            WITH samples AS (
                SELECT study_key FROM lnrs.lnrs_anon_imaging_study
                WHERE center_code = :c AND anon_exam_id IS NOT NULL
                ORDER BY random() LIMIT 3
            )
            SELECT s.study_key, e.patient_id = s.patient_id AS same_patient,
                   e.exam_date,
                   COALESCE(lnrs.path_study_date(s.image_path),
                            lnrs.uid_study_date(s.dicom_study_uid)) AS study_date
            FROM lnrs.lnrs_anon_imaging_study s
            JOIN samples USING (study_key)
            JOIN lnrs.lnrs_anon_exam e ON e.anon_exam_id = s.anon_exam_id
            ORDER BY s.study_key
        """), {"c": center})
        for row in r:
            d = dict(row._mapping)
            assert d["same_patient"], f"抽样患者不一致: {d}"
            log.info(f"[VERIFY 抽样] {d}")
    log.info(f"[VERIFY] 断言 1={a1} 2={a2} 3={a3} 覆盖率={out['study_with_exam']}/{out['study_total']}")
    return out


# ---------- 主流程 ----------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Issue 13: xinqiao exam 灌库 + anon_exam_id 回填")
    p.add_argument("--center", default=CENTER, choices=[CENTER],
                   help="中心码（本脚本源文件与残留兜底为 xinqiao 专用；通用回填逻辑在 backfill_imaging_study_exam_id）")
    p.add_argument("--src-ct", default=DEFAULT_SRC_CT, help="ct.parquet 路径")
    p.add_argument("--src-map", default=DEFAULT_SRC_MAP, help="ct_dicom_map.parquet 路径")
    p.add_argument("--staging", default=str(DEFAULT_STAGING), help="适配产物目录")
    p.add_argument("--skip-backup", action="store_true", help="跳过备份（不推荐）")
    p.add_argument("--skip-adapt", action="store_true", help="跳过适配（staging 已存在时）")
    p.add_argument("--skip-ingest", action="store_true", help="跳过灌库（已灌库时）")
    p.add_argument("--dry-run", action="store_true",
                   help="只报告（源文件/覆盖统计/残留预估），不写库")
    return p.parse_args()


async def preflight(center: str, src_ct: Path, src_map: Path) -> None:
    assert src_ct.exists(), f"源文件缺失: {src_ct}"
    assert src_map.exists(), f"源文件缺失: {src_map}"
    async with async_db_session() as s:
        n_studies = (await s.execute(text("""
            SELECT COUNT(*) FROM lnrs.lnrs_anon_imaging_study WHERE center_code = :c
        """), {"c": center})).scalar()
        n_exam = (await s.execute(text("""
            SELECT COUNT(*) FROM lnrs.lnrs_anon_exam WHERE center_code = :c AND exam_type = 'CT'
        """), {"c": center})).scalar()
        n_uid_date = (await s.execute(text("""
            SELECT COUNT(*) FROM lnrs.lnrs_anon_imaging_study
            WHERE center_code = :c AND lnrs.uid_study_date(dicom_study_uid) IS NOT NULL
        """), {"c": center})).scalar()
    log.info(f"[PREFLIGHT] {center}: studies={n_studies} CT_exam(库内)={n_exam} uid_date 覆盖={n_uid_date}")


async def main() -> int:
    args = _parse_args()
    center = args.center
    src_ct = Path(args.src_ct)
    src_map = Path(args.src_map)
    staging = Path(args.staging)

    await preflight(center, src_ct, src_map)
    if args.dry_run:
        # dry-run：只读报告（tier-1 覆盖统计 + 残留预估），不写库
        from backfill_imaging_study_exam_id import coverage_report_sql, run_dry_run
        await run_dry_run(center)
        async with async_db_session() as s:
            r = await s.execute(text(coverage_report_sql(center)))
            row = r.mappings().first()
            log.info(f"[DRY-RUN] 覆盖统计: {dict(row) if row else None}")
            n_residual = (await s.execute(text("""
                SELECT COUNT(*) FROM lnrs.lnrs_anon_imaging_study s
                WHERE s.center_code = :c AND s.anon_exam_id IS NULL
                  AND COALESCE(lnrs.path_study_date(s.image_path),
                               lnrs.uid_study_date(s.dicom_study_uid)) IS NULL
                  AND EXISTS (
                    SELECT 1 FROM lnrs.lnrs_anon_exam e
                    WHERE e.patient_id = s.patient_id AND e.exam_type = 'CT'
                  )
            """), {"c": center})).scalar()
        log.info(f"[DRY-RUN] 无日期残留（将走文件数/单 exam/平局兜底）: {n_residual}")
        log.info("[DRY-RUN] 未写库。正式执行：去掉 --dry-run")
        return 0

    await log_exam_distribution(center, "BEFORE")
    pre = await snapshot_other_centers()
    if not args.skip_backup:
        tbl = await backup_imaging_study(center)
        await backup_series_exam_state(center)
        log.info(f"[BACKUP] imaging_study 备份表: {tbl}")

    if not args.skip_ingest:
        if not args.skip_adapt:
            adapt_ct_parquet(src_ct, staging)
        pq = staging / "nodule_imaging.parquet"
        assert pq.exists(), f"staging 缺失: {pq}"
        await ingest_ct_exam(center, pq, staging)
        await log_exam_distribution(center, "AFTER")

    # 本次 exam 净增（首跑 = 124,045；重跑 upsert 不增行 = 0）
    async with async_db_session() as s:
        post_exam = (await s.execute(text("""
            SELECT COUNT(*) FROM lnrs.lnrs_anon_exam
            WHERE center_code = :c AND exam_type = 'CT'
        """), {"c": center})).scalar()
    expected_new_exams = int(post_exam) - int(pre["exam:all"].get(center, 0))

    matchable = await run_tier1(center)
    rules = await run_residual(center, src_ct, src_map)
    series_n = await backfill_dicom_series(center)
    out = await verify(center)
    await verify_no_drift(pre, center, expected_new_exams)

    log.info("=" * 60)
    log.info(f"[DONE] tier-1 matchable={matchable} residual={rules} series={series_n}")
    log.info(f"[DONE] study 覆盖率 {out['study_with_exam']}/{out['study_total']} "
             f"series 非 NULL {out['series_with_exam']}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
