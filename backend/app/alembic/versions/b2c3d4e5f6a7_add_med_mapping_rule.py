"""add med_mapping_rule table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-07

新建 med_mapping_rule 字段映射规则表（M2）。
存储各医院原始字段到统一表字段的映射规则，支持全量替换。
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "med_mapping_rule",
        # ModelMixin 字段
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键ID"),
        sa.Column("uuid", sa.String(length=64), nullable=False, comment="UUID全局唯一标识"),
        sa.Column("status", sa.String(length=10), nullable=False, comment="状态(0:正常 1:禁用)"),
        sa.Column("description", sa.Text(), nullable=True, comment="备注/描述"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_time", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, comment="是否已删除(0:未删除 1:已删除)"),
        sa.Column("deleted_time", sa.DateTime(), nullable=True, comment="删除时间"),
        # UserMixin 字段
        sa.Column("created_id", sa.Integer(), nullable=True, comment="创建人ID"),
        sa.Column("updated_id", sa.Integer(), nullable=True, comment="更新人ID"),
        sa.Column("deleted_id", sa.Integer(), nullable=True, comment="删除人ID"),
        # 业务字段
        sa.Column("hospital_id", sa.Integer(), nullable=False, comment="所属医院"),
        sa.Column("src_table", sa.String(length=100), nullable=False, comment="源表名"),
        sa.Column("src_field", sa.String(length=100), nullable=False, comment="源字段名"),
        sa.Column("tgt_table", sa.String(length=100), nullable=False, comment="目标表名"),
        sa.Column("tgt_field", sa.String(length=100), nullable=False, comment="目标字段名"),
        sa.Column("transform_type", sa.String(length=20), nullable=False, comment="转换类型(rename/constant/expression)"),
        sa.Column("transform_value", sa.Text(), nullable=True, comment="转换值"),
        sa.Column("sort", sa.Integer(), nullable=False, comment="执行顺序"),
        # 约束
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid", name="uq_med_mapping_rule_uuid"),
        sa.UniqueConstraint(
            "hospital_id", "src_table", "src_field", name="uq_med_mapping_rule"
        ),
        sa.ForeignKeyConstraint(
            ["hospital_id"], ["med_hospital.id"], onupdate="CASCADE", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["updated_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["deleted_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"
        ),
        comment="字段映射规则表",
    )

    # server_default（与 med_hospital 迁移一致）
    op.alter_column(
        "med_mapping_rule", "status",
        server_default="0", existing_type=sa.String(length=10), existing_nullable=False,
    )
    op.alter_column(
        "med_mapping_rule", "created_time",
        server_default=sa.text("CURRENT_TIMESTAMP"),
        existing_type=sa.DateTime(), existing_nullable=False,
    )
    op.alter_column(
        "med_mapping_rule", "updated_time",
        server_default=sa.text("CURRENT_TIMESTAMP"),
        existing_type=sa.DateTime(), existing_nullable=False,
    )
    op.alter_column(
        "med_mapping_rule", "is_deleted",
        server_default=sa.text("false"), existing_type=sa.Boolean(), existing_nullable=False,
    )
    op.alter_column(
        "med_mapping_rule", "transform_type",
        server_default="rename",
        existing_type=sa.String(length=20), existing_nullable=False,
    )
    op.alter_column(
        "med_mapping_rule", "sort",
        server_default="0", existing_type=sa.Integer(), existing_nullable=False,
    )

    # 索引
    op.create_index(op.f("ix_med_mapping_rule_id"), "med_mapping_rule", ["id"])
    op.create_index(op.f("ix_med_mapping_rule_uuid"), "med_mapping_rule", ["uuid"])
    op.create_index(op.f("ix_med_mapping_rule_status"), "med_mapping_rule", ["status"])
    op.create_index(op.f("ix_med_mapping_rule_created_time"), "med_mapping_rule", ["created_time"])
    op.create_index(op.f("ix_med_mapping_rule_updated_time"), "med_mapping_rule", ["updated_time"])
    op.create_index(op.f("ix_med_mapping_rule_is_deleted"), "med_mapping_rule", ["is_deleted"])
    op.create_index(op.f("ix_med_mapping_rule_deleted_time"), "med_mapping_rule", ["deleted_time"])
    op.create_index(op.f("ix_med_mapping_rule_created_id"), "med_mapping_rule", ["created_id"])
    op.create_index(op.f("ix_med_mapping_rule_updated_id"), "med_mapping_rule", ["updated_id"])
    op.create_index(op.f("ix_med_mapping_rule_deleted_id"), "med_mapping_rule", ["deleted_id"])
    op.create_index(op.f("ix_med_mapping_rule_hospital_id"), "med_mapping_rule", ["hospital_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_med_mapping_rule_hospital_id"), table_name="med_mapping_rule")
    op.drop_index(op.f("ix_med_mapping_rule_deleted_id"), table_name="med_mapping_rule")
    op.drop_index(op.f("ix_med_mapping_rule_updated_id"), table_name="med_mapping_rule")
    op.drop_index(op.f("ix_med_mapping_rule_created_id"), table_name="med_mapping_rule")
    op.drop_index(op.f("ix_med_mapping_rule_deleted_time"), table_name="med_mapping_rule")
    op.drop_index(op.f("ix_med_mapping_rule_is_deleted"), table_name="med_mapping_rule")
    op.drop_index(op.f("ix_med_mapping_rule_updated_time"), table_name="med_mapping_rule")
    op.drop_index(op.f("ix_med_mapping_rule_created_time"), table_name="med_mapping_rule")
    op.drop_index(op.f("ix_med_mapping_rule_status"), table_name="med_mapping_rule")
    op.drop_index(op.f("ix_med_mapping_rule_uuid"), table_name="med_mapping_rule")
    op.drop_index(op.f("ix_med_mapping_rule_id"), table_name="med_mapping_rule")
    op.drop_table("med_mapping_rule")
