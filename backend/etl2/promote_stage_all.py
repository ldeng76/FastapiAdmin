"""4 表 stage 统一 promote 命令（issue-23）。

按 FK 依赖序（patient → exam → imaging_study → dicom_series）把各 stage
表幂等 promote 到生产表，复用 issue-22 的校验闸/审计/回滚：

    # 全部 4 张按序 promote
    python backend/etl2/promote_stage_all.py --apply [--target production]
    # 只 promote 指定表（仍受 FK 顺序闸约束）
    python backend/etl2/promote_stage_all.py --apply --table exam
    # 校验 + 审计，不写生产
    python backend/etl2/promote_stage_all.py --dry-run
    # 按批次回滚（需指明目标表族）
    python backend/etl2/promote_stage_all.py --rollback <batch_id> --table exam

FK 顺序闸：promote 某表前，更早的表若还有未 promote 的新键 → 报错拒绝
（不静默跳过，AC）。空 stage 的表在 promote-all 中按「无行可上」跳过
（各表独立灌库，空属正常）；显式 --table 单表时空集仍报校验异常（与
issue-22 口径一致——单表调用是明确意图，空集是意外）。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from _script_guard import add_target_argument, gate  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.database import async_db_session  # noqa: E402
from etl2.promote_guardrails import (  # noqa: E402
    AUDIT_TABLE,
    PromoteRefused,
    audit_by_batch,
    rollback_batch,
)
from stage_promote import (  # noqa: E402
    REGISTRY_BY_NAME,
    STAGE_REGISTRY,
    promote_stage_all,
    promote_stage_table,
)

#: 校验闸拒绝 promote 时的退出码（区别于 issue-21 闸的 2）
REFUSED_EXIT_CODE = 3


async def _stage_count(stage_table: str) -> int:
    async with async_db_session() as db:
        return int((await db.execute(
            text(f"SELECT COUNT(*) FROM {stage_table}")
        )).scalar() or 0)


async def run(mode: str, only: str | None) -> int:
    try:
        async with async_db_session() as db:
            if only:
                spec = REGISTRY_BY_NAME[only]
                n, bid = await promote_stage_table(db, spec, mode=mode)
                print(f"[PROMOTE] {spec.stage_table} → {spec.prod_table}"
                      f" upsert {n} batch={bid}")
            else:
                # promote-all：空 stage 表按「无行可上」跳过（各表独立灌库）
                results = []
                for spec in STAGE_REGISTRY:
                    if await _stage_count(spec.stage_table) == 0:
                        print(f"[PROMOTE] {spec.stage_table} 为空，跳过")
                        continue
                    results.append(spec.name)
                if not results:
                    print("[PROMOTE] 所有 stage 表均为空，nothing to do")
                    return 0
                for name, n, bid in await promote_stage_all(db, names=results, mode=mode):
                    spec = REGISTRY_BY_NAME[name]
                    print(f"[PROMOTE] {spec.stage_table} → {spec.prod_table}"
                          f" upsert {n} batch={bid}")
                    if mode == "apply":
                        print(f"[PROMOTE] 回滚命令：promote_stage_all.py"
                              f" --rollback {bid} --table {name}")
    except PromoteRefused as e:
        for v in e.violations:
            print(f"[PROMOTE-REFUSED] {v}", file=sys.stderr)
        print("[PROMOTE-REFUSED] 校验闸拒绝，生产库零变化", file=sys.stderr)
        return REFUSED_EXIT_CODE
    return 0


async def run_rollback(batch_id: str, table: str) -> int:
    spec = REGISTRY_BY_NAME.get(table)
    if spec is None:
        print(f"[ROLLBACK-REFUSED] 未知表名: {table}", file=sys.stderr)
        return REFUSED_EXIT_CODE
    async with async_db_session() as db:
        try:
            r = await rollback_batch(
                db, batch_id=batch_id, prod_table=spec.prod_table,
                key_column=spec.key_column, promote_columns=spec.promote_columns)
        except PromoteRefused as e:
            for v in e.violations:
                print(f"[ROLLBACK-REFUSED] {v}", file=sys.stderr)
            return REFUSED_EXIT_CODE
        await db.commit()
    print(f"[ROLLBACK] 完成 batch={batch_id} {spec.prod_table}:"
          f" 删除 {r['deleted']} 行, 还原 {r['restored']} 行")
    return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="promote_stage_all",
        description="4 表 stage 按 FK 序幂等 promote（issue-23）",
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="校验+审计，不写生产表")
    g.add_argument("--apply", action="store_true", help="实际 promote（写非沙箱库需 --target）")
    g.add_argument("--rollback", metavar="BATCH_ID", help="按批次回滚一次 promote")
    p.add_argument("--table", choices=[s.name for s in STAGE_REGISTRY],
                   help="只 promote/回滚指定表（默认全部按序）")
    add_target_argument(p)
    return p.parse_args()


async def main() -> int:
    args = _parse_args()
    gate(
        schema="lnrs",
        tables=[s.prod_table for s in STAGE_REGISTRY] + [
            AUDIT_TABLE, "lnrs.lnrs_promote_audit_row"],
        declared=args.target,
        estimated_rows=None,
        action="read" if args.dry_run else "write",
    )
    if args.dry_run:
        return await run("dry_run", args.table)
    if args.rollback:
        return await run_rollback(args.rollback, args.table or "dicom_series")
    return await run("apply", args.table)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
