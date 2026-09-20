"""promote lnrs_stage_dicom_series → lnrs_anon_dicom_series（issue-20「先暂存再上」）。

「先暂存再上」第一片的最后一环：`backfill_dicom_series_count.py`（issue-20 起）
把回填结果写进同库 stage 表 `lnrs.lnrs_stage_dicom_series`，本命令再把它
幂等 upsert 到生产表 `lnrs.lnrs_anon_dicom_series`。

机制复用 issue-19 抽出的 `anon_pg_copy.copy_then_merge`（COPY+temp table →
ON CONFLICT ON CONSTRAINT DO UPDATE）—— 不另写第二套 upsert。

用法：
    # 只看将要 promote 的行数，不写库
    python backend/etl2/promote_stage_dicom_series.py --dry-run
    # 实际 promote（写非沙箱库必须 --target production 显式声明，issue-21 闸）
    python backend/etl2/promote_stage_dicom_series.py --apply [--target production]

幂等性：
- ON CONFLICT 走生产表 UNIQUE (dicom_study_uid) 约束
  `lnrs_anon_dicom_series_dicom_study_uid_key`，重放同一批 stage 行
  行数与关键字段值不变。
- series_id（PK）不参与 promote：column_order 排除主键，新行由生产表
  sequence 现场分配 —— stage 清空重跑后再 promote 也不会撞主键。

护栏（issue-22，promote_guardrails）：
- 前置校验闸：promote 前校验 stage 不变量（非空 / 行数 / NOT NULL+CHECK /
  外键完整性），不过则拒绝、生产库零变化、退出码 3；
- 审计：每次 promote（含 dry-run）写 lnrs_promote_audit（+ 行级明细，
  update 行存 promote 前像）；
- 回滚：`--rollback <batch_id>` 按批次撤销（删 insert 行 + 还原 update 行）。

安全：
- 本命令是唯一的 stage→生产写入点，自带 issue-21 闸（--apply 写非沙箱库
  必须 --target 显式声明；沙箱 lnrs_dev 免声明）。
- stage 表可随时 TRUNCATE，不影响生产（stage 无 FK/CHECK，见迁移
  n4o5p6q7r8s9）。
 """
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

# 允许直接 `python backend/etl2/promote_stage_dicom_series.py` 跑
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from _script_guard import add_target_argument, gate  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.database import async_db_session  # noqa: E402
from app.core.logger import log  # noqa: E402
from app.plugin.module_medical.hospital.anon_pg_copy import copy_then_merge  # noqa: E402
from stage_promote import StageTableSpec, promote_stage_table  # noqa: E402
from etl2.promote_guardrails import (  # noqa: E402
    AUDIT_TABLE,
    PromoteRefused,
    audit_by_batch,
    record_audit,
    record_batch_detail,
    finalize_audit,
    rollback_batch,
    validate_stage,
)

#: 校验闸拒绝 promote 时的退出码（区别于 issue-21 闸的 2）
REFUSED_EXIT_CODE = 3

STAGE_TABLE = "lnrs.lnrs_stage_dicom_series"
PROD_TABLE = "lnrs.lnrs_anon_dicom_series"

#: 生产表 upsert 幂等键约束（UNIQUE (dicom_study_uid)，实测存在）
PROD_CONSTRAINT = "lnrs_anon_dicom_series_dicom_study_uid_key"

#: promote 涉及的列 —— 排除 series_id（PK）：新行由生产表 sequence 分配，
#: 避免 stage 重跑后 series_id 变化撞主键、破坏幂等。
PROMOTE_COLUMNS = [
    "anon_exam_id",
    "dicom_study_uid",
    "file_count",
    "byte_size",
    "series_count",
    "created_batch_id",
    "created_at",
    "updated_at",
]

#: DO UPDATE SET 的字段（EXCLUDED 引用）；created_at/created_batch_id 保留首次值
UPDATE_COLUMNS = [
    "anon_exam_id",
    "file_count",
    "byte_size",
    "series_count",
    "updated_at",
]


async def _stage_rows(db, stage_table: str) -> tuple[int, list[dict]]:
    """stage 待 promote 行数与行内容（单次读取，行数校验同源）。"""
    rows = (await db.execute(
        text(f"SELECT {', '.join(PROMOTE_COLUMNS)} FROM {stage_table}")
    )).mappings().all()
    n = int((await db.execute(
        text(f"SELECT COUNT(*) FROM {stage_table}")
    )).scalar() or 0)
    return n, [dict(r) for r in rows]

async def promote(
    db,
    *,
    stage_table: str = STAGE_TABLE,
    prod_table: str = PROD_TABLE,
    constraint: str = PROD_CONSTRAINT,
    key_column: str = "dicom_study_uid",
    mode: str = "apply",
) -> tuple[int, str]:
    """带护栏的 promote（issue-22），委托 stage_promote.promote_stage_table。

    返回 (upsert 行数, batch_id)。校验不过抛 PromoteRefused，生产零变化。
    stage_table/prod_table/constraint 可注入 —— 供沙箱测试在 scratch 表上
    验证语义，不触碰生产表。issue-23 起本体在 stage_promote.promote_stage_table，
    此处只做 dicom_series 的参数绑定（不检查其它表顺序，保持单表语义）。
    """
    spec = StageTableSpec(
        name="dicom_series", stage_table=stage_table, prod_table=prod_table,
        constraint=constraint, key_column=key_column,
        promote_columns=PROMOTE_COLUMNS, update_columns=UPDATE_COLUMNS,
    )
    return await promote_stage_table(db, spec, mode=mode, check_order=False)

async def run_dry_run() -> int:
    """校验 + 审计（mode=dry_run），不写生产。"""
    async with async_db_session() as db:
        n = int((await db.execute(text(f"SELECT COUNT(*) FROM {STAGE_TABLE}"))).scalar() or 0)
        print(f"[PROMOTE-DRY-RUN] {STAGE_TABLE} 待 promote 行数: {n}")
        try:
            _, batch_id = await promote(db, mode="dry_run")
            print(f"[PROMOTE-DRY-RUN] 校验通过 batch={batch_id}，未写生产表")
        except PromoteRefused as e:
            for v in e.violations:
                print(f"[PROMOTE-DRY-RUN] 违规: {v}")
            print("[PROMOTE-DRY-RUN] 校验不通过，--apply 将被拒绝")
    print("[PROMOTE-DRY-RUN] 正式执行：--apply（写非沙箱库加 --target production）")
    return 0


async def run_apply() -> int:
    """实际 promote；校验闸拒绝 → 退出码 3，生产零变化。"""
    async with async_db_session() as db:
        n = int((await db.execute(text(f"SELECT COUNT(*) FROM {STAGE_TABLE}"))).scalar() or 0)
        print(f"[PROMOTE] {STAGE_TABLE} 待 promote 行数: {n}")
        try:
            upserted, batch_id = await promote(db)
        except PromoteRefused as e:
            for v in e.violations:
                print(f"[PROMOTE-REFUSED] {v}", file=sys.stderr)
            print(f"[PROMOTE-REFUSED] 校验闸拒绝 promote，生产库零变化", file=sys.stderr)
            return REFUSED_EXIT_CODE
    print(f"[PROMOTE] 完成：upsert {upserted} 行 → {PROD_TABLE} batch={batch_id}")
    print(f"[PROMOTE] 回滚命令：--rollback {batch_id}")
    return 0


async def run_rollback(batch_id: str) -> int:
    """按批次回滚一次 promote。"""
    async with async_db_session() as db:
        audits = await audit_by_batch(db, batch_id)
        if not audits:
            print(f"[ROLLBACK] 未找到 batch={batch_id} 的审计记录", file=sys.stderr)
            return REFUSED_EXIT_CODE
        for a in audits:
            print(f"[ROLLBACK] 审计: {a['target_table']} mode={a['mode']}"
                  f" upsert={a['upsert_rows']} validation={a['validation']}"
                  f" rolled_back_at={a['rolled_back_at']}")
        try:
            r = await rollback_batch(
                db, batch_id=batch_id, prod_table=PROD_TABLE,
                key_column="dicom_study_uid", promote_columns=PROMOTE_COLUMNS)
        except PromoteRefused as e:
            for v in e.violations:
                print(f"[ROLLBACK-REFUSED] {v}", file=sys.stderr)
            return REFUSED_EXIT_CODE
        await db.commit()
    print(f"[ROLLBACK] 完成 batch={batch_id}: 删除 {r['deleted']} 行,"
          f" 还原 {r['restored']} 行")
    return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="promote_stage_dicom_series",
        description="把 lnrs_stage_dicom_series 带护栏 promote 到生产表（issue-20/22）",
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="校验+审计，不写生产表")
    g.add_argument("--apply", action="store_true", help="实际 promote（写非沙箱库需 --target）")
    g.add_argument("--rollback", metavar="BATCH_ID", help="按批次回滚一次 promote")
    add_target_argument(p)
    return p.parse_args()


async def main() -> int:
    args = _parse_args()
    # issue-21 闸：本命令是 stage→生产的唯一写入点，写非沙箱库必须显式声明。
    gate(
        schema="lnrs",
        tables=[PROD_TABLE, AUDIT_TABLE, "lnrs.lnrs_promote_audit_row"],
        declared=args.target,
        estimated_rows=None,
        action="read" if args.dry_run else "write",
    )
    if args.dry_run:
        return await run_dry_run()
    if args.rollback:
        return await run_rollback(args.rollback)
    return await run_apply()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
