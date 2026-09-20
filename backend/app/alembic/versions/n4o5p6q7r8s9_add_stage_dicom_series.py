"""新增 lnrs.lnrs_stage_dicom_series — 「先暂存再上」第一片（issue-20）

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2026-09-20

背景 (Issue 20: docs/etl2/prd/issue-20-dicom-series-stage-and-promote.md，
源自 docs/etl2/findings/incident-20260920-test-cascade-delete.md §10)：

ad-hoc 执行脚本直写生产库、没有任何闸。本迁移建立同库 stage 表，
让 `backfill_dicom_series_count.py` 先写 stage，再由 promote 命令
（复用 anon_pg_copy.copy_then_merge）幂等上到生产表。

选型（已决）：同库 stage 表，不是独立 stage 数据库 —— 代码里 470 处
硬编码 `lnrs.` 前缀会绕过 search_path，且 B 方案（同库）是 A 方案
（跨库 FDW）的严格子集，promote SQL 只差源引用。

结构：
- `LIKE lnrs.lnrs_anon_dicom_series INCLUDING DEFAULTS`：列与默认值与
  生产表一致（含 series_id 的 sequence 默认）。
- 显式补 `UNIQUE (dicom_study_uid)` 约束（LIKE 不复制约束）：promote
  的幂等键，约束名与生产表同形 `lnrs_stage_dicom_series_dicom_study_uid_key`，
  供 `ON CONFLICT ON CONSTRAINT` 使用。
- 不复制 FK / CHECK（LIKE 也不复制）：stage 行不参与级联删除，
  `TRUNCATE lnrs.lnrs_stage_dicom_series` 对生产零影响 —— 这是事故
  复盘要求的可逆性。
"""
from collections.abc import Sequence

from alembic import op

revision: str = "n4o5p6q7r8s9"
down_revision: str | None = "m3n4o5p6q7r8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STAGE_DDL = [
    """
    CREATE TABLE IF NOT EXISTS lnrs.lnrs_stage_dicom_series (
      LIKE lnrs.lnrs_anon_dicom_series INCLUDING DEFAULTS
    )
    """,
    """
    ALTER TABLE lnrs.lnrs_stage_dicom_series
      ADD CONSTRAINT lnrs_stage_dicom_series_dicom_study_uid_key
      UNIQUE (dicom_study_uid)
    """,
    """
    COMMENT ON TABLE lnrs.lnrs_stage_dicom_series IS
      'dicom_series 暂存表 (issue-20): ad-hoc 脚本先写这里, promote 命令
       经 anon_pg_copy.copy_then_merge 幂等 upsert 到生产表
       lnrs.lnrs_anon_dicom_series; 无 FK/CHECK, TRUNCATE 不影响生产。
       2026-09-20 (issue-20, 源自 incident-20260920 复盘 §10)'
    """,
]


def upgrade() -> None:
    for ddl in _STAGE_DDL:
        op.execute(ddl)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lnrs.lnrs_stage_dicom_series;")
