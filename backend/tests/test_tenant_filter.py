"""租户过滤器测试 — 校验 __platform_data_shared__ 在 SELECT 分支的放开逻辑。

核心回归点：平台共享数据（tenant_id=1）应能被非平台租户读取，
而普通租户数据仍严格隔离。
"""

from __future__ import annotations

import pytest
from sqlalchemy import Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

# 导入即注册 do_orm_execute 事件监听器
import app.core.tenant_filter  # noqa: F401
from app.core.tenant import clear_current_tenant, set_current_tenant


class _Base(DeclarativeBase):
    pass


class _SharedDict(_Base):
    __tablename__ = "t_shared_dict"
    __platform_data_shared__ = True
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(20))


class _OwnedRow(_Base):
    __tablename__ = "t_owned_row"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(20))


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    _Base.metadata.create_all(engine)
    with Session(engine) as s:
        # 平台数据 tenant_id=1，租户 2 的数据 tenant_id=2
        s.add_all([
            _SharedDict(id=1, tenant_id=1, label="platform"),
            _SharedDict(id=2, tenant_id=2, label="tenant2"),
            _OwnedRow(id=1, tenant_id=1, label="platform"),
            _OwnedRow(id=2, tenant_id=2, label="tenant2"),
        ])
        s.commit()
        yield s
    clear_current_tenant()


def test_shared_dict_visible_to_other_tenant(session):
    """租户 2 读取共享字典时，应同时看到平台(1)与自身(2)数据。"""
    set_current_tenant(2, is_super_admin=False)
    labels = {r.label for r in session.execute(select(_SharedDict)).scalars()}
    assert labels == {"platform", "tenant2"}


def test_shared_dict_column_select(session):
    """列级查询（如 dict_value/dict_label）同样放开平台数据。"""
    set_current_tenant(2, is_super_admin=False)
    rows = session.execute(select(_SharedDict.tenant_id, _SharedDict.label)).all()
    assert {tid for tid, _ in rows} == {1, 2}


def test_owned_row_still_isolated(session):
    """非共享表仍严格租户隔离，租户 2 看不到平台数据。"""
    set_current_tenant(2, is_super_admin=False)
    labels = {r.label for r in session.execute(select(_OwnedRow)).scalars()}
    assert labels == {"tenant2"}


def test_platform_tenant_sees_own_only(session):
    """平台租户(1)自身查询不重复放开，仅命中 tenant_id=1。"""
    set_current_tenant(1, is_super_admin=False)
    labels = {r.label for r in session.execute(select(_SharedDict)).scalars()}
    assert labels == {"platform"}
