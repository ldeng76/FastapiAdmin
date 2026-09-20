"""lnrs_anon_patient 增加 is_placeholder 占位标记列

Revision ID: h8c9d0e1f2a3
Revises: g7b8c9d0e1f2
Create Date: 2026-09-07

背景：患者列表 ~59% 显示「未知的性别」。根因是 ETL2 导入 exam/visit/surgery
表时为无档案患者自动发号的占位记录（sex 恒为 '0'、无人口学），占位患者：
- zhujiang 79,577（0719 CT 批次 66,597 + 0825 批次 12,980）
- xinqiao 49,563（无 patient 表，全部占位）
- hos301 8,350（无 patient parquet，全部占位）
合计 137,490 / 231,352（59.4%）。

本迁移：
1. 加列 is_placeholder BOOLEAN NOT NULL DEFAULT FALSE；
2. 回填：无任何人口学字段的 sex='0' 行标记为占位（dry-run 命中 137,490，
   唯一排除项为 shengyi PT_00282376——真实档案、有 birth_date、源数据性别
   缺失，保持 FALSE）。

注意：patient_meta 存在 jsonb 字面量 'null'（0825 批次写入痕迹），
回填条件需同时覆盖 SQL NULL / jsonb 'null' / '{}' 三种空态。

⚠ 归档注记（ADR 0012，2026-09-20）：第 2 步身份型回填规则已被数据型语义
取代（名下无业务数据才为占位）。本迁移保留（历史环境已应用），downgrade
仅删列；存量修正见 backend/etl2/backfill_placeholder_data_semantics.py。
禁止在任何新环境复用本迁移的回填 UPDATE 口径打标。
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "h8c9d0e1f2a3"
down_revision: str | None = "g7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. 加列（server_default 兜底引擎之外的手工 INSERT）
    op.add_column(
        "lnrs_anon_patient",
        sa.Column(
            "is_placeholder",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="占位患者标记：exam/visit/surgery 导入自动发号、无人口学",
        ),
        schema="lnrs",
    )

    # 2. 回填：sex='0' 且所有人口学字段均为空 → 占位
    op.execute(
        """
        UPDATE lnrs.lnrs_anon_patient
        SET is_placeholder = TRUE
        WHERE sex = '0'
          AND birth_date IS NULL
          AND ethnicity IS NULL
          AND smoking_status IS NULL
          AND abo_blood_type IS NULL
          AND rh_blood_type IS NULL
          AND native_place IS NULL
          AND first_nodule_date IS NULL
          AND bmi IS NULL
          AND (
                patient_meta IS NULL
                OR patient_meta = 'null'::jsonb
                OR patient_meta = '{}'::jsonb
          )
        """
    )


def downgrade() -> None:
    op.drop_column("lnrs_anon_patient", "is_placeholder", schema="lnrs")
