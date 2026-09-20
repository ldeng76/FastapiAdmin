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
from pathlib import Path

# 允许直接 `python backend/etl2/promote_stage_dicom_series.py` 跑
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from _script_guard import add_target_argument, gate  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.database import async_db_session  # noqa: E402
from app.core.logger import log  # noqa: E402
from app.plugin.module_medical.hospital.anon_pg_copy import copy_then_merge  # noqa: E402

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


async def stage_row_count(db, stage_table: str = STAGE_TABLE) -> int:
    """stage 中待 promote 的行数（dry-run 输出口径）。"""
    return int((await db.execute(text(f"SELECT COUNT(*) FROM {stage_table}"))).scalar() or 0)


async def promote(
    db,
    *,
    stage_table: str = STAGE_TABLE,
    prod_table: str = PROD_TABLE,
    constraint: str = PROD_CONSTRAINT,
) -> int:
    """把 stage 表全部行经 copy_then_merge 幂等 upsert 进生产表。返回处理行数。

    stage_table/prod_table/constraint 可注入 —— 供沙箱测试在 scratch 表上
    验证 promote 语义，不触碰生产表。
    """
    col_list = ", ".join(PROMOTE_COLUMNS)
    rows = (await db.execute(
        text(f"SELECT {col_list} FROM {stage_table}")
    )).mappings().all()
    if not rows:
        log.info("[PROMOTE] stage 表为空，nothing to do")
        return 0
    n = await copy_then_merge(
        db,
        target_table_name=prod_table,
        rows=[dict(r) for r in rows],
        constraint=constraint,
        update_set=dict.fromkeys(UPDATE_COLUMNS, 1),
        column_order=PROMOTE_COLUMNS,
    )
    await db.commit()
    log.info(f"[PROMOTE] {stage_table} → {prod_table} upsert {n} 行")
    return n


async def run_dry_run() -> int:
    """打印将要 promote 的行数，不写库。"""
    async with async_db_session() as db:
        n = await stage_row_count(db)
    print(f"[PROMOTE-DRY-RUN] {STAGE_TABLE} 待 promote 行数: {n}")
    print("[PROMOTE-DRY-RUN] 未写库。正式执行：--apply（写非沙箱库加 --target production）")
    return 0


async def run_apply() -> int:
    """实际 promote。"""
    async with async_db_session() as db:
        n = await stage_row_count(db)
        print(f"[PROMOTE] {STAGE_TABLE} 待 promote 行数: {n}")
        if not n:
            print("[PROMOTE] stage 表为空，nothing to do")
            return 0
        await promote(db)
    print(f"[PROMOTE] 完成：upsert {n} 行 → {PROD_TABLE}")
    return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="promote_stage_dicom_series",
        description="把 lnrs_stage_dicom_series 幂等 promote 到生产表（issue-20）",
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="仅打印待 promote 行数，不写库")
    g.add_argument("--apply", action="store_true", help="实际 promote（写非沙箱库需 --target）")
    add_target_argument(p)
    return p.parse_args()


async def main() -> int:
    args = _parse_args()
    # issue-21 闸：promote 是 stage→生产的唯一写入点，apply 写非沙箱库必须显式声明。
    gate(
        schema="lnrs",
        tables=[PROD_TABLE],
        declared=args.target,
        estimated_rows=None,
        action="read" if args.dry_run else "write",
    )
    if args.dry_run:
        return await run_dry_run()
    return await run_apply()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
