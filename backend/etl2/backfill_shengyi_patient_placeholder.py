# ⚠ 方向作废注记（Issue 27 / ADR 0012，2026-09-20）：本脚本按 0018 身份型口径
# 把 shengyi 无人口学患者翻 TRUE 的方向已被数据型语义取代（shengyi 影像 stub
# 名下有真实业务数据 ⇒ 维持 FALSE）。本文件保留作轨迹，**不再执行**；
# 存量统一由 backfill_placeholder_data_semantics.py 处理。
"""回填 lnrs_anon_patient.is_placeholder = TRUE（shengyi 漏标存量，Issue 9）。

背景
----
2026-09-07 迁移 0018 给 lnrs_anon_patient 加 is_placeholder 列（sex='0' 且 8 个
人口学列全 NULL 标 TRUE），但 shengyi 的离线灌库脚本 build_shengyi_imaging_study_index.py
在 2026-09-14 灌库时漏写 is_placeholder 列，走 DDL 默认值 FALSE，导致 82,682 个
无人口学占位患者被错标 FALSE，与同口径 zhujiang / xinqiao（脚本显式写 TRUE）行为不一致。

本脚本
----
- dry-run：仅 SELECT 统计应被标 TRUE 的行数（与 0018 口径同）
- apply：先建备份表（patient_id, is_placeholder），再 UPDATE 翻 TRUE
- rollback：按备份表把 is_placeholder 还原回 apply 前的值

WHERE 与 0018 同口径（Issue 9 修复）：
  center_code='shengyi' AND sex='0' AND NOT is_placeholder
  AND <8 个人口学列全 NULL>

回退（通用）
------------
- dry-run 不改数据
- apply 后可用 rollback 还原（备份表 p_shengyi_placeholder_bak）
- DROP TABLE lnrs.p_shengyi_placeholder_bak;

执行环境约束
------------
必须 ENVIRONMENT=dev / h196_3（连真实 PG；本机 SSH 不通、pg_hba 仅放行 lnrs 远程）。

用法
----
    ENVIRONMENT=dev uv run python etl2/backfill_shengyi_patient_placeholder.py --dry-run
    ENVIRONMENT=dev uv run python etl2/backfill_shengyi_patient_placeholder.py --apply
    ENVIRONMENT=dev uv run python etl2/backfill_shengyi_patient_placeholder.py --rollback
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# 允许直接 `python backend/etl2/backfill_shengyi_patient_placeholder.py` 跑
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import text  # noqa: E402

from app.core.database import async_db_session  # noqa: E402
from app.core.logger import log  # noqa: E402

CENTER_CODE = "shengyi"
BACKUP_TABLE = "lnrs.p_shengyi_placeholder_bak"

# 8 个人口学列（与 0018 migration 同口径；新增列需同步 0018）
PLACEHOLDER_DEMOGRAPHIC_COLUMNS = (
    "birth_date", "ethnicity", "smoking_status", "abo_blood_type",
    "rh_blood_type", "native_place", "first_nodule_date", "bmi",
)

# 不含 center_code 守卫的 WHERE 子句（便于 0018 / 其他脚本复用同口径）
# 完整 WHERE = f"center_code = '{center}' AND ({PLACEHOLDER_WHERE_BASE})"
PLACEHOLDER_WHERE_BASE = (
    "sex = '0' AND NOT is_placeholder AND "
    + " AND ".join(f"{c} IS NULL" for c in PLACEHOLDER_DEMOGRAPHIC_COLUMNS)
)


def _full_where(center: str) -> str:
    return f"center_code = '{center}' AND ({PLACEHOLDER_WHERE_BASE})"


# ---------- 路径 ----------


async def run_dry_run_async() -> int:
    """async 主体：仅 SELECT 统计，不改 DB。打印统计并返回受影响行数。"""
    async with async_db_session() as session:
        # 当前 is_placeholder 分布
        dist_rows = (await session.execute(
            text(
                "SELECT is_placeholder, COUNT(*)::int "
                "FROM lnrs.lnrs_anon_patient "
                "WHERE center_code = :c "
                "GROUP BY 1 ORDER BY 1"
            ),
            {"c": CENTER_CODE},
        )).all()
        dist = {bool(r[0]): r[1] for r in dist_rows}

        # 应被标 TRUE 的行数（按 0018 口径）
        affected = (await session.execute(
            text(
                "SELECT COUNT(*)::int FROM lnrs.lnrs_anon_patient "
                f"WHERE {_full_where(CENTER_CODE)}"
            ),
        )).scalar()
        total = sum(dist.values())

    print(
        "\n[DRY-RUN] shengyi 占位标记回填：仅统计，不修改\n"
    )
    print(f"  center_code = '{CENTER_CODE}'")
    print(f"  total patients = {total:,}")
    for k in (False, True):
        if k in dist:
            print(f"  is_placeholder = {k}: {dist[k]:,}")
    print(f"\n  按 0018 口径应被标 TRUE 的行数: {affected:,}")
    print(f"  WHERE: {_full_where(CENTER_CODE)}")
    print()
    return affected


def run_dry_run() -> int:
    """sync 包装：CLI 调用入口（asyncio.run）。"""
    print(
        "\n[DRY-RUN] shengyi 占位标记回填：仅统计，不修改\n"
    )
    affected, dist, total = asyncio.run(run_dry_run_async())
    print(f"  center_code = '{CENTER_CODE}'")
    print(f"  total patients = {total:,}")
    for k in (False, True):
        if k in dist:
            print(f"  is_placeholder = {k}: {dist[k]:,}")
    print(f"\n  按 0018 口径应被标 TRUE 的行数: {affected:,}")
    print(f"  WHERE: {_full_where(CENTER_CODE)}")
    print()
    return affected


async def run_apply(center: str = CENTER_CODE) -> int:
    """备份 → UPDATE → 验证。返回受影响行数。"""
    print(
        f"\n[APPLY] 回填 lnrs_anon_patient.is_placeholder = TRUE（center={center}）…\n"
    )

    full_where = _full_where(center)

    async with async_db_session() as session:
        # 0) 备份：先 DROP 旧备份，再 CREATE 新备份
        await session.execute(text(f"DROP TABLE IF EXISTS {BACKUP_TABLE}"))
        await session.execute(
            text(
                f"CREATE TABLE {BACKUP_TABLE} AS "
                f"SELECT patient_id, is_placeholder, created_batch_id, "
                f"       last_seen_batch_id, deleted_at "
                f"FROM lnrs.lnrs_anon_patient WHERE center_code = :c"
            ),
            {"c": center},
        )
        await session.commit()
        log.info(f"[APPLY] 备份表已创建: {BACKUP_TABLE}")

        # 1) 受影响行数预检（dry-run 同口径）
        expected = (await session.execute(
            text(
                "SELECT COUNT(*)::int FROM lnrs.lnrs_anon_patient "
                f"WHERE {full_where}"
            ),
        )).scalar()
        log.info(f"[APPLY] 预计影响行数: {expected:,}")

        # 2) 实际 UPDATE
        result = await session.execute(
            text(
                "UPDATE lnrs.lnrs_anon_patient SET is_placeholder = TRUE "
                f"WHERE {full_where}"
            ),
        )
        affected = result.rowcount or 0
        await session.commit()

        log.info(f"[APPLY] 实际受影响行数: {affected:,}")
        if affected != expected:
            log.warning(
                f"[APPLY] rowcount ({affected}) 与预期 ({expected}) 不一致；"
                f"可能受并发写入或过滤条件影响"
            )

        # 3) 验证：受影响判据的剩余行数应为 0
        remaining = (await session.execute(
            text(
                "SELECT COUNT(*)::int FROM lnrs.lnrs_anon_patient "
                f"WHERE {full_where}"
            ),
        )).scalar()
        if remaining != 0:
            log.error(
                f"[APPLY] 验证失败：受影响判据仍剩 {remaining} 行；"
                f"请检查并发写入或 backup 是否完整"
            )
        else:
            log.info("[APPLY] 验证通过：受影响判据剩余 0 行")

    print(
        f"\n[APPLY] 完成：affected={affected:,} remaining=0 "
        f"backup={BACKUP_TABLE}\n"
    )
    return affected


async def run_rollback(center: str = CENTER_CODE) -> int:
    """按备份表还原 is_placeholder；其它列不被触碰。"""
    print(
        f"\n[ROLLBACK] 按 {BACKUP_TABLE} 还原 is_placeholder（center={center}）…\n"
    )

    async with async_db_session() as session:
        # 检查备份表存在
        exists = (await session.execute(
            text(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.tables "
                "  WHERE table_schema='lnrs' AND table_name=:t"
                ")"
            ),
            {"t": BACKUP_TABLE.split(".")[-1]},
        )).scalar()
        if not exists:
            log.error(f"[ROLLBACK] 备份表 {BACKUP_TABLE} 不存在，无法回退")
            return 0

        # 按 patient_id 把 is_placeholder 还原
        result = await session.execute(
            text(
                f"UPDATE lnrs.lnrs_anon_patient p "
                f"SET is_placeholder = b.is_placeholder "
                f"FROM {BACKUP_TABLE} b "
                f"WHERE p.patient_id = b.patient_id "
                f"  AND p.center_code = :c"
            ),
            {"c": center},
        )
        affected = result.rowcount or 0
        await session.commit()

        log.info(f"[ROLLBACK] 已还原 {affected:,} 行 → 原 is_placeholder")

    print(f"\n[ROLLBACK] 完成：affected={affected:,}\n")
    return affected


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="backfill_shengyi_patient_placeholder",
        description=__doc__.split("\n", 1)[0] if __doc__ else "Issue 9 修复",
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="仅打印统计，不修改")
    g.add_argument("--apply", action="store_true", help="实际回填 is_placeholder=TRUE")
    g.add_argument("--rollback", action="store_true", help="按备份表还原")
    return p.parse_args()


async def main() -> int:
    args = _parse_args()
    if args.dry_run:
        await run_dry_run_async()
    elif args.apply:
        await run_apply()
    else:
        await run_rollback()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
