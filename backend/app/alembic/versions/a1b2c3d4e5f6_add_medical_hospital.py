"""add medical hospital table

Revision ID: a1b2c3d4e5f6
Revises: 0306640395d9
Create Date: 2026-07-07

新建 med_hospital 医院注册表（平台级元数据）。
M1 阶段仅建此一张表；med_mapping_rule（M2）、med_patient 等医疗数据表（M3）后续迁移再建。

注意：
- down_revision 必须是当前 HEAD 0306640395d9（v3.1.0 插件系统），不能用 002。
- 表结构对应 HospitalModel(ModelMixin, UserMixin)，不继承 TenantMixin。
- 包含 ModelMixin 全部字段（id/uuid/status/description/created_time/updated_time/is_deleted/deleted_time）
  和 UserMixin 全部字段（created_id/updated_id/deleted_id）。
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "0306640395d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "med_hospital",
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
        sa.Column("code", sa.String(length=50), nullable=False, comment="医院编码"),
        sa.Column("name", sa.String(length=100), nullable=False, comment="医院名称"),
        sa.Column("full_name", sa.String(length=200), nullable=True, comment="医院全称"),
        sa.Column(
            "tenant_id", sa.Integer(), nullable=False, comment="关联租户ID"
        ),
        sa.Column(
            "lifecycle_status",
            sa.String(length=20),
            nullable=False,
            comment="就绪状态(registered/mapping_configured/data_imported/live)",
        ),
        sa.Column("contact_name", sa.String(length=64), nullable=True, comment="联系人"),
        sa.Column("contact_phone", sa.String(length=20), nullable=True, comment="联系电话"),
        sa.Column("contact_email", sa.String(length=128), nullable=True, comment="联系邮箱"),
        sa.Column("address", sa.String(length=255), nullable=True, comment="机构地址"),
        sa.Column("last_import_time", sa.DateTime(), nullable=True, comment="最近导入时间"),
        sa.Column("last_import_rows", sa.Integer(), nullable=False, comment="最近导入行数"),
        sa.Column("import_error", sa.Text(), nullable=True, comment="导入失败时的错误信息"),
        # 约束
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid", name="uq_med_hospital_uuid"),
        sa.UniqueConstraint("code", name="uq_med_hospital_code"),
        sa.UniqueConstraint("tenant_id", name="uq_med_hospital_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["sys_tenant.id"], onupdate="CASCADE", ondelete="RESTRICT"
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
        comment="医院注册表（平台级元数据）",
    )

    # ModelMixin 默认值（迁移需显式指定 server_default，因 ORM default 不会被 alembic 自动捕获）
    op.alter_column(
        "med_hospital", "status",
        server_default="0", existing_type=sa.String(length=10), existing_nullable=False,
    )
    op.alter_column(
        "med_hospital", "created_time",
        server_default=sa.text("CURRENT_TIMESTAMP"),
        existing_type=sa.DateTime(), existing_nullable=False,
    )
    op.alter_column(
        "med_hospital", "updated_time",
        server_default=sa.text("CURRENT_TIMESTAMP"),
        existing_type=sa.DateTime(), existing_nullable=False,
    )
    op.alter_column(
        "med_hospital", "is_deleted",
        server_default=sa.text("false"), existing_type=sa.Boolean(), existing_nullable=False,
    )
    op.alter_column(
        "med_hospital", "lifecycle_status",
        server_default="registered",
        existing_type=sa.String(length=20), existing_nullable=False,
    )
    op.alter_column(
        "med_hospital", "last_import_rows",
        server_default="0", existing_type=sa.Integer(), existing_nullable=False,
    )

    # 索引
    op.create_index(op.f("ix_med_hospital_id"), "med_hospital", ["id"])
    op.create_index(op.f("ix_med_hospital_uuid"), "med_hospital", ["uuid"])
    op.create_index(op.f("ix_med_hospital_status"), "med_hospital", ["status"])
    op.create_index(op.f("ix_med_hospital_created_time"), "med_hospital", ["created_time"])
    op.create_index(op.f("ix_med_hospital_updated_time"), "med_hospital", ["updated_time"])
    op.create_index(op.f("ix_med_hospital_is_deleted"), "med_hospital", ["is_deleted"])
    op.create_index(op.f("ix_med_hospital_deleted_time"), "med_hospital", ["deleted_time"])
    op.create_index(op.f("ix_med_hospital_created_id"), "med_hospital", ["created_id"])
    op.create_index(op.f("ix_med_hospital_updated_id"), "med_hospital", ["updated_id"])
    op.create_index(op.f("ix_med_hospital_deleted_id"), "med_hospital", ["deleted_id"])
    op.create_index(op.f("ix_med_hospital_lifecycle_status"), "med_hospital", ["lifecycle_status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_med_hospital_lifecycle_status"), table_name="med_hospital")
    op.drop_index(op.f("ix_med_hospital_deleted_id"), table_name="med_hospital")
    op.drop_index(op.f("ix_med_hospital_updated_id"), table_name="med_hospital")
    op.drop_index(op.f("ix_med_hospital_created_id"), table_name="med_hospital")
    op.drop_index(op.f("ix_med_hospital_deleted_time"), table_name="med_hospital")
    op.drop_index(op.f("ix_med_hospital_is_deleted"), table_name="med_hospital")
    op.drop_index(op.f("ix_med_hospital_updated_time"), table_name="med_hospital")
    op.drop_index(op.f("ix_med_hospital_created_time"), table_name="med_hospital")
    op.drop_index(op.f("ix_med_hospital_status"), table_name="med_hospital")
    op.drop_index(op.f("ix_med_hospital_uuid"), table_name="med_hospital")
    op.drop_index(op.f("ix_med_hospital_id"), table_name="med_hospital")
    op.drop_table("med_hospital")
