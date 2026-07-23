"""数据统计模块 service — 为仪表板提供聚合统计。

返回 {filters, kpis, dimensions} 结构（ADR-0007）。
"""

from __future__ import annotations

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.logger import log

from .stats_query import get_dashboard_overview
from .stats_schema import DashboardOverviewOut


class StatsService:
    """数据统计服务"""

    @classmethod
    async def get_overview_service(cls, auth: AuthSchema) -> dict:
        """获取仪表板全量概览（维度数组结构）。"""
        try:
            overview = await get_dashboard_overview(auth.db)
            return DashboardOverviewOut(**overview).model_dump()
        except Exception as e:
            log.error(f"[StatsService] 获取仪表板概览失败: {e!s}")
            raise
