"""回填 shengyi imaging_study.sop_count = Σ dicom_series.file_count（Issue 28）。

背景
----
省医 lnrs_anon_imaging_study 全部 82,994 行 sop_count=0（build_shengyi_imaging_study_index.py
灌库时未数 SOP），而 dicom_series 层有真实 file_count（82,897 个 study 有 series 行、
合计 29,010,775 个文件）。issue-28 把页面 file_count 公式改为 Σ sop_count 后，
省医必须回填，否则总文件数对省医归零。

规则
----
UPDATE lnrs.lnrs_anon_imaging_study s
SET sop_count = agg.file_count
FROM (SELECT dicom_study_uid, SUM(file_count) AS file_count
      FROM lnrs.lnrs_anon_dicom_series GROUP BY 1) agg
WHERE s.center_code = 'shengyi'
  AND s.sop_count = 0
  AND s.dicom_study_uid = agg.dicom_study_uid
  AND agg.file_count > 0;

仅动 shengyi、仅动 sop_count=0 的行；series 层无行的 study（实测 97 个，
无 DICOM 归档的真实零文件目录）保持 0 —— 符合「真实零文件目录才允许
sop_count=0」。xinqiao / zhujiang 的 sop_count 已有真实值，不触碰。

用法
----
    ENVIRONMENT=test uv run python etl2/backfill_shengyi_sop_count.py --dry-run
    ENVIRONMENT=test uv run python etl2/backfill_shengyi_sop_count.py --apply
    ENVIRONMENT=test uv run python etl2/backfill_shengyi_sop_count.py --rollback --backup-table lnrs.lnrs_anon_imaging_study_bak_sop_<ts>
    ENVIRONMENT=dev  uv run python etl2/backfill_shengyi_sop_count.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import text  # noqa: E402

from app.core.database import async_db_session  # noqa: E402
from app.core.logger import log  # noqa: E402

CENTER_CODE = "shengyi"


def backup_table_name(ts: str) -> str:
    return f"lnrs.lnrs_anon_imaging_study_bak_sop_{ts}"


_UPDATE_SQL = text(
    "UPDATE lnrs.lnrs_anon_imaging_study s "
    "SET sop_count = agg.file_count "
    "FROM (SELECT dicom_study_uid, SUM(file_count) AS file_count "
    "      FROM lnrs.lnrs_anon_dicom_series GROUP BY 1) agg "
    "WHERE s.center_code = :c "
    "  AND s.sop_count = 0 "
    "  AND s.dicom_study_uid = agg.dicom_study_uid "
    "  AND agg.file_count > 0"
)


async def _baseline(session) -> tuple[int, int, int]:
    # series 层口径：shengyi study 的每个 dicom_study_uid 对应的 file_count 合计
    # （join 去重 uid；shengyi 实测有 841 个跨患者重复 UID，IN 子查询会漏计）
    row = (await session.execute(text(
        "SELECT COUNT(*), COUNT(*) FILTER (WHERE sop_count = 0), "
        " COALESCE((SELECT SUM(ds.file_count) FROM lnrs.lnrs_anon_dicom_series ds "
        "  JOIN (SELECT DISTINCT dicom_study_uid FROM lnrs.lnrs_anon_imaging_study "
        "        WHERE center_code = :c) u ON u.dicom_study_uid = ds.dicom_study_uid), 0) "
        "FROM lnrs.lnrs_anon_imaging_study WHERE center_code = :c"
    ), {"c": CENTER_CODE})).one()
    return int(row[0]), int(row[1]), int(row[2])


async def run_dry_run_async() -> int:
    """仅 SELECT 统计将被回填的行数。"""
    async with async_db_session() as session:
        total, zero, series_sum = await _baseline(session)
        will = (await session.execute(text(
            "SELECT COUNT(*) FROM lnrs.lnrs_anon_imaging_study s "
            "JOIN (SELECT dicom_study_uid, SUM(file_count) AS fc "
            "      FROM lnrs.lnrs_anon_dicom_series GROUP BY 1) agg "
            "  ON agg.dicom_study_uid = s.dicom_study_uid "
            "WHERE s.center_code = :c AND s.sop_count = 0 AND agg.fc > 0"
        ), {"c": CENTER_CODE})).scalar()
        print(f"\n[DRY-RUN] {CENTER_CODE}: study 总数 {total:,}，sop_count=0 共 {zero:,} 行，"
              f"其中可回填 {int(will):,} 行"
              f"（series 层 Σ file_count = {series_sum:,}，其余为真实零文件目录）\n")
        return int(will)


async def run_apply_async() -> int:
    """备份 → UPDATE → 断言。返回受影响行数。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_table = backup_table_name(ts)

    async with async_db_session() as session:
        total, zero, series_sum = await _baseline(session)
        print(f"\n[APPLY] shengyi sop_count=0 共 {zero:,} 行；备份表 {backup_table}")
        await session.execute(text(
            f"CREATE TABLE {backup_table} AS "
            "SELECT study_key, sop_count FROM lnrs.lnrs_anon_imaging_study "
            "WHERE center_code = :c AND sop_count = 0"
        ), {"c": CENTER_CODE})
        await session.commit()

        result = await session.execute(_UPDATE_SQL, {"c": CENTER_CODE})
        affected = result.rowcount
        await session.commit()
        log.info(f"[APPLY] 已回填 {affected:,} 行 sop_count")

        # 断言 1：sop_count=0 的行 = 无 series 行的 study（真实零文件）
        bad = (await session.execute(text(
            "SELECT COUNT(*) FROM lnrs.lnrs_anon_imaging_study s "
            "WHERE s.center_code = :c AND s.sop_count = 0 "
            "  AND EXISTS (SELECT 1 FROM lnrs.lnrs_anon_dicom_series ds "
            "              WHERE ds.dicom_study_uid = s.dicom_study_uid AND ds.file_count > 0)"
        ), {"c": CENTER_CODE})).scalar()
        if bad:
            raise RuntimeError(f"[APPLY] 断言失败：仍有 {bad:,} 个有文件的 study sop_count=0")

        # 断言 2（per-uid 一致性，issue-28）：每个 shengyi study 的 sop_count
        # == 其 dicom_study_uid 在 series 层的 file_count 合计（无 series 行 → 0）。
        # shengyi 有 841 个跨患者重复 UID（同 UID 多目录），朴素 Σ 相等会因
        # 同 UID 多行而误判，故按 study 行逐一比对。
        mismatch = (await session.execute(text(
            "SELECT COUNT(*) FROM lnrs.lnrs_anon_imaging_study s "
            "LEFT JOIN (SELECT dicom_study_uid, SUM(file_count) AS fc "
            "           FROM lnrs.lnrs_anon_dicom_series GROUP BY 1) agg "
            "  ON agg.dicom_study_uid = s.dicom_study_uid "
            "WHERE s.center_code = :c "
            "  AND s.sop_count <> COALESCE(agg.fc, 0)"
        ), {"c": CENTER_CODE})).scalar()
        if mismatch:
            raise RuntimeError(
                f"[APPLY] 断言失败：{int(mismatch):,} 个 study 的 sop_count ≠ 其 UID 的 series file_count 合计"
            )
        sop_sum = (await session.execute(text(
            "SELECT COALESCE(SUM(sop_count),0) FROM lnrs.lnrs_anon_imaging_study "
            "WHERE center_code = :c"
        ), {"c": CENTER_CODE})).scalar()

        print(f"\n[APPLY] 断言通过：per-uid 全一致；Σ sop_count = {int(sop_sum):,}（目录级合计，"
              f"含 841 个跨患者重复 UID 目录的重复计入）\n")

    print(f"[APPLY] 完成：affected={affected:,}，备份表 {backup_table}\n")
    return affected


async def run_rollback_async(backup_table: str) -> int:
    """按备份表还原 sop_count。"""
    print(f"\n[ROLLBACK] 按 {backup_table} 还原 sop_count …\n")
    async with async_db_session() as session:
        exists = (await session.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema='lnrs' AND table_name = :t"
        ), {"t": backup_table.split(".", 1)[1]})).scalar()
        if not exists:
            raise RuntimeError(f"备份表 {backup_table} 不存在")

        result = await session.execute(text(
            "UPDATE lnrs.lnrs_anon_imaging_study s "
            "SET sop_count = b.sop_count "
            f"FROM {backup_table} b WHERE s.study_key = b.study_key"
        ))
        affected = result.rowcount
        await session.commit()
        log.info(f"[ROLLBACK] 已还原 {affected:,} 行 → apply 前值")

    print(f"\n[ROLLBACK] 完成：affected={affected:,}\n")
    return affected


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="仅打印统计，不修改")
    g.add_argument("--apply", action="store_true", help="备份 + 回填 shengyi sop_count")
    g.add_argument("--rollback", metavar="BACKUP_TABLE",
                   help="按备份表还原（如 lnrs.lnrs_anon_imaging_study_bak_sop_<ts>）")
    return p.parse_args()


async def main() -> int:
    args = _parse_args()
    if args.dry_run:
        await run_dry_run_async()
    elif args.apply:
        await run_apply_async()
    elif args.rollback:
        await run_rollback_async(args.rollback)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
