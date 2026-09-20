"""以 PACS 导出 ct_mapped.parquet 校正 xinqiao dicom_series.series_count / byte_size。

背景
----
2026-09-20 发现 xinqiao 33,314 个 study 的 dicom_series.series_count 大面积低估
（19,238 个 study 记 1；扫描器对新桥 zip_folder / 布局 C 的 series 枚举不全），
/medicalFiles 页面【总文件个数】（CT 模态 = Σseries_count）随之低估；
byte_size 另有 128 行与 PACS 导出侧 total_size_bytes 不一致。

数据源：/data/wlx/DATABASE/extracted_tables/xinqiao/ct_mapped.parquet
（CT 报告+DICOM 合并导出，与 issue-13 灌库的 ct.parquet 为同一批数据：
  - exam 侧对账：ct.parquet 124,045 行的 sha256('xinqiao:'+exam_id) 与库内
    lnrs_anon_exam.source_exam_hash 124,045/124,045 全命中，0 多余；
    ct_mapped 有日期行 124,046 与 ct.parquet 按 (patient_id, exam_date) 全配、
    raw_text 全等；
  - study 侧对账：ct_mapped 41,298 行 exam_id=StudyInstanceUID，其中 33,314
    精确命中 lnrs_anon_imaging_study.dicom_study_uid（其余 7,984 = cxf_archives
    未入库，不属本脚本范围））。

差异方向：PACS 值 ≥ 磁盘扫描实测（部分 series/文件未落盘属正常），
以 PACS 导出为权威覆盖 series_count / byte_size 两列。

不做的事
----
- 不动 lnrs_anon_imaging_study / lnrs_anon_exam / lnrs_anon_patient
- 不动 zhujiang / shengyi（临时表只含 xinqiao study uid；dicom_study_uid 全局
  UNIQUE 且跨中心重叠实测 0，UPDATE join 天然隔离）
- 不动 ct_mapped 中 7,984 行 cxf（未入库）与 83,010 行 Accession 纯报告

用法
----
    ENVIRONMENT=h196_3 uv run python etl2/backfill_xinqiao_series_counts_from_pacs.py --dry-run
    ENVIRONMENT=h196_3 uv run python etl2/backfill_xinqiao_series_counts_from_pacs.py --apply

apply 步骤：备份表 → 临时映射表 → UPDATE join → 验收（剩余差异=0、
其他中心合计值不变）。幂等：重跑差异为 0、UPDATE 0 行。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

# 允许直接 `python backend/etl2/backfill_xinqiao_series_counts_from_pacs.py` 跑
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

import duckdb  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.database import async_db_session  # noqa: E402
from app.core.logger import log  # noqa: E402

CENTER_CODE = "xinqiao"
PACS_PARQUET = Path(
    "/data/wlx/DATABASE/extracted_tables/xinqiao/ct_mapped.parquet"
)
TMP_TABLE = "lnrs.lnrs_tmp_xq_series_counts"

# 映射表单批插入行数
_INSERT_BATCH = 5_000


# ---------- 纯函数（可测 seam） ----------


def plan_updates(
    pacs: dict[str, tuple[int, int]],
    db_rows: list[tuple[str, int | None, int | None]],
) -> tuple[list[tuple[str, int, int]], int]:
    """对比 PACS 计数值与库内现值，产出 UPDATE 计划。

    pacs: {dicom_study_uid: (file_count, total_size_bytes)}（仅 StudyUID 行）
    db_rows: [(uid, series_count, byte_size)]（库内 xinqiao 现值）

    返回 (updates, skipped_invalid)：
    - updates: [(uid, series_count, byte_size)]，fc 或 sz 与库内不同才收录；
    - 库内不存在的 uid（cxf 未入库）忽略；
    - pacs 值非法（fc<1、sz<0 或 None）跳过并计数。
    """
    updates: list[tuple[str, int, int]] = []
    skipped = 0
    for uid, fc, sz in db_rows:
        want = pacs.get(uid)
        if want is None:
            continue
        p_fc, p_sz = want
        if p_fc is None or p_fc < 1 or p_sz is None or p_sz < 0:
            skipped += 1
            continue
        cur_fc = fc if fc is not None else 0
        cur_sz = sz if sz is not None else 0
        if cur_fc != p_fc or cur_sz != p_sz:
            updates.append((uid, p_fc, p_sz))
    return updates, skipped


def load_pacs_counts(parquet_path: Path) -> dict[str, tuple[int, int]]:
    """读 ct_mapped 的 StudyUID 行 → {study_uid: (file_count, total_size_bytes)}。

    与引擎 _read_parquet_rows 同款 duckdb 直读；Accession 行（纯报告，无
    DICOM）不带计数值语义，按 exam_id 前缀排除。
    """
    con = duckdb.connect(database=":memory:")
    try:
        rows = con.execute(
            "SELECT exam_id, file_count, total_size_bytes FROM read_parquet(?) "
            "WHERE exam_id NOT LIKE 'Accession_%'",
            [parquet_path.as_posix()],
        ).fetchall()
    finally:
        con.close()
    return {r[0]: (r[1], r[2]) for r in rows}


# ---------- DB 路径 ----------


async def _fetch_db_rows() -> list[tuple[str, int | None, int | None]]:
    """库内 xinqiao 的 (uid, series_count, byte_size)（经 imaging_study 限定中心）。"""
    async with async_db_session() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT s.dicom_study_uid, s.series_count, s.byte_size "
                    "FROM lnrs.lnrs_anon_dicom_series s "
                    "JOIN lnrs.lnrs_anon_imaging_study i "
                    "  ON i.dicom_study_uid = s.dicom_study_uid "
                    "WHERE i.center_code = :c"
                ),
                {"c": CENTER_CODE},
            )
        ).all()
    return [(r[0], r[1], r[2]) for r in rows]


async def _other_centers_baseline() -> dict[str, object]:
    """zhujiang/shengyi 的 dicom_series 合计（apply 前后必须一致）。"""
    async with async_db_session() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT i.center_code, COUNT(*), COALESCE(SUM(s.series_count),0), "
                    "COALESCE(SUM(s.byte_size),0) "
                    "FROM lnrs.lnrs_anon_dicom_series s "
                    "JOIN lnrs.lnrs_anon_imaging_study i "
                    "  ON i.dicom_study_uid = s.dicom_study_uid "
                    "WHERE i.center_code IN ('zhujiang','shengyi') "
                    "GROUP BY i.center_code ORDER BY 1"
                )
            )
        ).all()


async def _count_remaining_diff() -> int:
    """独立连接统计 dicom_series 与临时映射表仍不一致的行数（只读已提交数据）。"""
    async with async_db_session() as session:
        return (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM lnrs.lnrs_anon_dicom_series s "
                    f"JOIN {TMP_TABLE} t ON s.dicom_study_uid = t.dicom_study_uid "
                    "WHERE (s.series_count, s.byte_size) "
                    "IS DISTINCT FROM (t.series_count, t.byte_size)"
                )
            )
        ).scalar()

async def run_dry_run() -> int:
    """仅统计，不修改 DB。返回待更新行数。"""
    pacs = load_pacs_counts(PACS_PARQUET)
    db_rows = await _fetch_db_rows()
    updates, skipped = plan_updates(pacs, db_rows)

    db_map = {r[0]: (r[1], r[2]) for r in db_rows}
    fc_changes = sum(1 for u in updates if db_map[u[0]][0] != u[1])
    sz_changes = sum(1 for u in updates if db_map[u[0]][1] != u[2])

    old_series_sum = sum(r[1] or 0 for r in db_rows)
    new_series_sum = sum(u[1] for u in updates) + sum(
        r[1] or 0 for r in db_rows if r[0] not in {x[0] for x in updates}
    )

    print("\n[DRY-RUN] xinqiao dicom_series 计数校正（PACS 权威值）：仅统计，不修改\n")
    print(f"  PACS parquet          = {PACS_PARQUET}")
    print(f"  PACS StudyUID 行      = {len(pacs):,}")
    print(f"  库内 xinqiao study    = {len(db_rows):,}")
    print(f"  待更新行              = {len(updates):,}（series_count 变化 {fc_changes:,} /"
          f" byte_size 变化 {sz_changes:,}）")
    if skipped:
        print(f"  ⚠️ PACS 非法值跳过     = {skipped:,}")
    print(f"  Σseries_count（页面【总文件个数】基数）: {old_series_sum:,} → {new_series_sum:,}")
    print()
    return len(updates)


async def run_apply() -> int:
    """备份 → 临时表 → UPDATE → 验收。返回 UPDATE 行数。"""
    pacs = load_pacs_counts(PACS_PARQUET)
    db_rows = await _fetch_db_rows()
    updates, skipped = plan_updates(pacs, db_rows)
    if skipped:
        log.warning(f"[APPLY] PACS 非法值跳过 {skipped} 行（不更新）")
    print(f"\n[APPLY] 校正 xinqiao dicom_series.series_count/byte_size：待更新 {len(updates):,} 行\n")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_tbl = f"lnrs.lnrs_anon_dicom_series_bak_{ts}"
    baseline = await _other_centers_baseline()

    async with async_db_session() as session:
        # 1) 备份（CTAS+SELECT；AS TABLE..WHERE 非合法 PG，同 issue-13 处理）
        await session.execute(
            text(
                f"CREATE TABLE {backup_tbl} AS "
                "SELECT s.* FROM lnrs.lnrs_anon_dicom_series s "
                "JOIN lnrs.lnrs_anon_imaging_study i "
                "  ON i.dicom_study_uid = s.dicom_study_uid "
                "WHERE i.center_code = :c"
            ),
            {"c": CENTER_CODE},
        )
        n_bak = (
            await session.execute(text(f"SELECT COUNT(*) FROM {backup_tbl}"))
        ).scalar()
        log.info(f"[BACKUP] {backup_tbl} +{n_bak:,} 行")

        # 2) 临时映射表
        await session.execute(text(f"DROP TABLE IF EXISTS {TMP_TABLE}"))
        await session.execute(
            text(
                f"CREATE TABLE {TMP_TABLE} ("
                "dicom_study_uid VARCHAR PRIMARY KEY, "
                "series_count INT NOT NULL, byte_size BIGINT NOT NULL)"
            )
        )
        for i in range(0, len(updates), _INSERT_BATCH):
            chunk = updates[i : i + _INSERT_BATCH]
            await session.execute(
                text(
                    f"INSERT INTO {TMP_TABLE} (dicom_study_uid, series_count, byte_size) "
                    "VALUES (:u, :fc, :sz)"
                ),
                [{"u": u, "fc": fc, "sz": sz} for u, fc, sz in chunk],
            )
        n_tmp = (
            await session.execute(text(f"SELECT COUNT(*) FROM {TMP_TABLE}"))
        ).scalar()
        if n_tmp != len(updates):
            raise RuntimeError(f"临时表行数 {n_tmp} != 计划 {len(updates)}，中止")
        await session.commit()
        log.info(f"[STAGE] {TMP_TABLE} +{n_tmp:,} 行")

        # 3) UPDATE join（dicom_study_uid 全局 UNIQUE；临时表只含 xinqiao uid）
        result = await session.execute(
            text(
                "UPDATE lnrs.lnrs_anon_dicom_series s "
                "SET series_count = t.series_count, byte_size = t.byte_size "
                f"FROM {TMP_TABLE} t "
                "WHERE s.dicom_study_uid = t.dicom_study_uid"
            )
        )
        affected = result.rowcount or 0
        # ⚠️ 必须显式 commit：漏掉会在会话关闭时被回滚（issue-13 同款缺陷），
        # 且同会话验收会看到未提交的脏值造成假阳性。
        await session.commit()
        log.info(f"[APPLY] 实际更新 {affected:,} 行")
        if affected != len(updates):
            raise RuntimeError(f"UPDATE 行数 {affected} != 计划 {len(updates)}，请核查")

        # 4) 验收：剩余差异 = 0（独立连接，只读已提交数据）
        remaining = (
            await _count_remaining_diff()
        )
        if remaining != 0:
            raise RuntimeError(f"验收失败：仍有 {remaining} 行与 PACS 值不一致")
        log.info("[VERIFY] 剩余差异 = 0")

    # 5) 其他中心零漂移
    after = await _other_centers_baseline()
    if after != baseline:
        raise RuntimeError(
            f"验收失败：zhujiang/shengyi 合计值漂移 {baseline} -> {after}"
        )
    log.info(f"[VERIFY] zhujiang/shengyi 零漂移: {after}")

    print(f"\n[APPLY] 完成：updated={affected:,} 剩余差异=0 backup={backup_tbl} tmp={TMP_TABLE}\n")
    return affected


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="以 PACS 导出校正 xinqiao dicom_series.series_count/byte_size"
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="仅统计，不修改")
    g.add_argument("--apply", action="store_true", help="备份后执行 UPDATE")
    return p.parse_args()


async def main() -> int:
    args = _parse_args()
    if args.dry_run:
        await run_dry_run()
        return 0
    await run_apply()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
