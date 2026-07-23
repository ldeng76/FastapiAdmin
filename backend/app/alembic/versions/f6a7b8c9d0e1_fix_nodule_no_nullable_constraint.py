"""fix nodule_no nullable constraint (sentinel value)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-23

med_nodule_imaging.nodule_no 原为 nullable=True，导致 UNIQUE(tenant_id, exam_id, nodule_no)
在 nodule_no 为 NULL 时失效（PostgreSQL NULL ≠ NULL）。
改为 nullable=False + default='UNKNOWN'，并回填历史 NULL 行为 'UNKNOWN'。
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. 回填历史 NULL 行为哨兵值 'UNKNOWN'
    op.execute(
        "UPDATE med_nodule_imaging SET nodule_no = 'UNKNOWN' WHERE nodule_no IS NULL"
    )

    # 2. 删除旧唯一约束（重建后才能加 NOT NULL）
    op.drop_constraint(
        "uq_med_nodule_imaging_tenant_exam_nodule",
        "med_nodule_imaging",
        type_="unique",
    )

    # 3. 改列：nullable=True → nullable=False, default='UNKNOWN'
    op.alter_column(
        "med_nodule_imaging",
        "nodule_no",
        existing_type=sa.String(20),
        nullable=False,
        server_default="UNKNOWN",
        comment="结节编号（源数据为空时填哨兵值 UNKNOWN，保证唯一约束有效）",
    )

    # 4. 重建唯一约束（现在 nodule_no 非空，约束对所有行有效）
    op.create_unique_constraint(
        "uq_med_nodule_imaging_tenant_exam_nodule",
        "med_nodule_imaging",
        ["tenant_id", "exam_id", "nodule_no"],
    )


def downgrade() -> None:
    # 1. 删除唯一约束
    op.drop_constraint(
        "uq_med_nodule_imaging_tenant_exam_nodule",
        "med_nodule_imaging",
        type_="unique",
    )

    # 2. 恢复列：nullable=False → nullable=True, 去掉 default
    op.alter_column(
        "med_nodule_imaging",
        "nodule_no",
        existing_type=sa.String(20),
        nullable=True,
        server_default=None,
        comment="结节编号（源数据可能为空）",
    )

    # 3. 重建原唯一约束
    op.create_unique_constraint(
        "uq_med_nodule_imaging_tenant_exam_nodule",
        "med_nodule_imaging",
        ["tenant_id", "exam_id", "nodule_no"],
    )
