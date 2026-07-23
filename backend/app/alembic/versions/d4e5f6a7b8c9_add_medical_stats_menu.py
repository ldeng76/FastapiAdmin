"""add medical stats dashboard menu

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-21

为数据统计仪表板添加后端菜单项 + 权限点。
前端通过菜单动态路由加载 views/module_medical/dashboard/index.vue。
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 获取 sys_menu 表元数据
    metadata = sa.MetaData()
    menu_table = sa.Table(
        "sys_menu",
        metadata,
        sa.Column("id", sa.Integer()),
        sa.Column("parent_id", sa.Integer()),
        sa.Column("name", sa.String()),
        sa.Column("type", sa.Integer()),  # 1=目录 2=菜单 3=按钮
        sa.Column("icon", sa.String()),
        sa.Column("order", sa.Integer()),
        sa.Column("permission", sa.String()),
        sa.Column("route_name", sa.String()),
        sa.Column("route_path", sa.String()),
        sa.Column("component_path", sa.String()),
        sa.Column("status", sa.String()),
        sa.Column("keep_alive", sa.Boolean()),
        sa.Column("hidden", sa.Boolean()),
        sa.Column("always_show", sa.Boolean()),
        sa.Column("title", sa.String()),
        sa.Column("affix", sa.Boolean()),
        sa.Column("redirect", sa.String()),
        sa.Column("description", sa.String()),
    )

    conn = op.get_bind()

    # 查找"医学数据"目录的 id（type=1 的父级目录，名称含 "医学" 或权限含 module_medical）
    result = conn.execute(
        sa.select(menu_table.c.id).where(
            menu_table.c.permission.is_(None),
            sa.or_(
                menu_table.c.name.like("%医学%"),
                menu_table.c.name.like("%医疗%"),
                menu_table.c.component_path.like("%module_medical%"),
            ),
        )
    ).first()

    parent_id = result[0] if result else None

    # 如果没有找到医学父目录，则不插入（保持幂等）
    if parent_id is None:
        return

    # 检查是否已存在（幂等）
    existing = conn.execute(
        sa.select(menu_table.c.id).where(menu_table.c.route_path == "dashboard")
    ).first()
    if existing:
        return

    # 插入仪表板菜单项
    conn.execute(
        menu_table.insert().values(
            parent_id=parent_id,
            name="数据概览",
            type=2,  # 菜单
            icon="ri:dashboard-line",
            order=0,  # 排在最前
            permission="module_medical:stats:query",
            route_name="Dashboard",
            route_path="dashboard",
            component_path="module_medical/dashboard/index",
            status="0",
            keep_alive=True,
            hidden=False,
            always_show=False,
            title="数据概览",
            affix=False,
            redirect=None,
            description="医疗数据概览仪表板（ETL2 脱敏数据）",
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM sys_menu WHERE route_path = 'dashboard' AND component_path = 'module_medical/dashboard/index'")
    )
