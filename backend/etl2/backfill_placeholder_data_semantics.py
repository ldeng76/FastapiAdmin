"""按数据型语义统一 lnrs_anon_patient.is_placeholder（Issue 27 / ADR 0012）。

背景
----
ADR 0011 / migration 0018 的身份型规则（sex='0' 且人口学全 NULL ⇒ 占位）
导致三个中心互相矛盾：zhujiang / xinqiao 的影像 stub（名下有真实 DICOM 数据）
全 TRUE，shengyi 同结构 stub 全 FALSE。ADR 0012 决策改为**数据型**语义：

    名下无任何业务数据（12 张业务子表均无引用行）⇒ is_placeholder = TRUE；
    否则 FALSE。

2026-09-20 dev 实测目标分布（need_flip）：
    zhujiang  74,450  TRUE → FALSE
    xinqiao   49,664  TRUE → FALSE
    shengyi  169,820  FALSE 不变（全部有业务数据）
    其余中心按同规则计算

本脚本
------
- dry-run：仅 SELECT 统计各中心应翻转的行数，不改 DB
- apply：建备份表 → 单条 UPDATE（目标值 = 无业务数据）→ 分布断言
- rollback：按备份表把 is_placeholder 还原回 apply 前的值
- verify：断言全表 is_placeholder == (无业务数据)，输出分布

备份表：lnrs.lnrs_anon_patient_bak_ph_<ts>（patient_id, is_placeholder）
回退：rollback 后可 DROP 备份表。

执行环境约束
------------
沙箱演练用 ENVIRONMENT=test（沙箱库 lnrs_dev）；真库执行用 ENVIRONMENT=dev。
脚本不限定环境，由调用方保证。

用法
----
    ENVIRONMENT=test uv run python etl2/backfill_placeholder_data_semantics.py --dry-run
    ENVIRONMENT=test uv run python etl2/backfill_placeholder_data_semantics.py --apply
    ENVIRONMENT=test uv run python etl2/backfill_placeholder_data_semantics.py --rollback --backup-table lnrs.lnrs_anon_patient_bak_ph_<ts>
    ENVIRONMENT=dev  uv run python etl2/backfill_placeholder_data_semantics.py --apply
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

# 允许直接 `python backend/etl2/backfill_placeholder_data_semantics.py` 跑
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import text  # noqa: E402

from app.core.database import async_db_session  # noqa: E402
from app.core.logger import log  # noqa: E402

# 业务数据子表（ADR 0012 §2 候选 B）：患者在其中任一表有引用行 ⇒ 非占位。
# 新增业务表时必须同步本清单与 ADR 0012。
BUSINESS_DATA_TABLES = (
    "exam",
    "visit",
    "visit_detail",
    "surgery",
    "lab_result",
    "order",
    "diagnosis",
    "clinical_document",
    "medical_history",
    "vital_observation",
    "exam_file",
    "imaging_study",
)


def no_data_predicate() -> str:
    """「患者无任何业务数据」的 SQL 谓词（patient 表别名固定为 p）。"""
    branches = " UNION ALL ".join(
        f"SELECT 1 FROM lnrs.lnrs_anon_{t} k WHERE k.patient_id = p.patient_id"
        for t in BUSINESS_DATA_TABLES
    )
    return f"NOT EXISTS ({branches})"


def backup_table_name(ts: str) -> str:
    return f"lnrs.lnrs_anon_patient_bak_ph_{ts}"


async def _current_distribution(session) -> list:
    rows = (await session.execute(text(
        "SELECT center_code, is_placeholder, COUNT(*)::bigint "
        "FROM lnrs.lnrs_anon_patient GROUP BY 1, 2 ORDER BY 1, 2"
    ))).fetchall()
    return [(r[0], r[1], r[2]) for r in rows]


def _print_distribution(rows) -> None:
    for center, ph, cnt in rows:
        print(f"  {center:<20} is_placeholder={ph!s:<5} {cnt:>10,}")


async def run_dry_run_async() -> int:
    """仅 SELECT 统计各中心需翻转的行数。返回总翻转行数。"""
    async with async_db_session() as session:
        print("\n[DRY-RUN] 当前 is_placeholder 分布：")
        _print_distribution(await _current_distribution(session))

        rows = (await session.execute(text(
            "SELECT p.center_code, p.is_placeholder, COUNT(*)::bigint AS n "
            "FROM lnrs.lnrs_anon_patient p "
            f"WHERE p.is_placeholder <> ({no_data_predicate()}) "
            "GROUP BY 1, 2 ORDER BY 1, 2"
        ))).fetchall()

        total = 0
        print("\n[DRY-RUN] 按数据型语义需翻转的行（目标值 = 无业务数据）：")
        for center, cur, n in rows:
            print(f"  {center:<20} {cur!s:<5} → {not cur!s:<5} {n:>10,}")
            total += n
        if not rows:
            print("  （0 行 —— 全表已符合数据型语义）")
        print(f"\n  合计需翻转: {total:,}")
        return total


async def run_apply_async() -> int:
    """备份 → 单条 UPDATE（目标值 = 无业务数据）→ 分布断言。返回翻转行数。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_table = backup_table_name(ts)
    predicate = no_data_predicate()

    async with async_db_session() as session:
        # 1. 备份所有将翻转的行
        cnt = (await session.execute(text(
            "SELECT COUNT(*) FROM lnrs.lnrs_anon_patient p "
            f"WHERE p.is_placeholder <> ({predicate})"
        ))).scalar()
        print(f"\n[APPLY] 需翻转 {cnt:,} 行；备份表 {backup_table}")
        await session.execute(text(
            f"CREATE TABLE {backup_table} AS "
            "SELECT p.patient_id, p.is_placeholder "
            "FROM lnrs.lnrs_anon_patient p "
            f"WHERE p.is_placeholder <> ({predicate})"
        ))
        await session.commit()

        # 2. 单条 UPDATE：目标值 = 无业务数据
        result = await session.execute(text(
            "UPDATE lnrs.lnrs_anon_patient p SET is_placeholder = "
            f"({predicate}) WHERE p.is_placeholder <> ({predicate})"
        ))
        affected = result.rowcount
        await session.commit()
        log.info(f"[APPLY] 已翻转 {affected:,} 行 → 数据型语义")

        # 3. 分布断言：全表 is_placeholder == 无业务数据
        bad = (await session.execute(text(
            "SELECT COUNT(*) FROM lnrs.lnrs_anon_patient p "
            f"WHERE p.is_placeholder <> ({predicate})"
        ))).scalar()
        if bad:
            raise RuntimeError(f"[APPLY] 断言失败：仍有 {bad:,} 行不符合数据型语义")

        print("\n[APPLY] 断言通过，最终分布：")
        _print_distribution(await _current_distribution(session))

    print(f"\n[APPLY] 完成：affected={affected:,}，备份表 {backup_table}\n")
    return affected


async def run_rollback_async(backup_table: str) -> int:
    """按备份表还原 is_placeholder；其它列不被触碰。"""
    print(f"\n[ROLLBACK] 按 {backup_table} 还原 is_placeholder …\n")
    async with async_db_session() as session:
        exists = (await session.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema='lnrs' AND table_name = :t"
        ), {"t": backup_table.split(".", 1)[1]})).scalar()
        if not exists:
            raise RuntimeError(f"备份表 {backup_table} 不存在")

        result = await session.execute(text(
            "UPDATE lnrs.lnrs_anon_patient p "
            "SET is_placeholder = b.is_placeholder "
            f"FROM {backup_table} b WHERE p.patient_id = b.patient_id"
        ))
        affected = result.rowcount
        await session.commit()
        log.info(f"[ROLLBACK] 已还原 {affected:,} 行 → apply 前值")

    print(f"\n[ROLLBACK] 完成：affected={affected:,}\n")
    return affected


async def run_verify_async() -> int:
    """断言全表符合数据型语义；输出分布。返回不符合行数。"""
    async with async_db_session() as session:
        bad = (await session.execute(text(
            "SELECT COUNT(*) FROM lnrs.lnrs_anon_patient p "
            f"WHERE p.is_placeholder <> ({no_data_predicate()})"
        ))).scalar()
        print("\n[VERIFY] 当前分布：")
        _print_distribution(await _current_distribution(session))
        print(f"\n[VERIFY] 不符合数据型语义的行数: {bad:,} → "
              f"{'PASS' if bad == 0 else 'FAIL'}\n")
        return bad


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="仅打印统计，不修改")
    g.add_argument("--apply", action="store_true", help="备份 + 回填到数据型语义")
    g.add_argument("--rollback", metavar="BACKUP_TABLE",
                   help="按备份表还原（如 lnrs.lnrs_anon_patient_bak_ph_20260920_120000）")
    g.add_argument("--verify", action="store_true", help="断言全表符合数据型语义")
    return p.parse_args()


async def main() -> int:
    args = _parse_args()
    if args.dry_run:
        await run_dry_run_async()
    elif args.apply:
        await run_apply_async()
    elif args.rollback:
        await run_rollback_async(args.rollback)
    elif args.verify:
        return 1 if await run_verify_async() else 0
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
