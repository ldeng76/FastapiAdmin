"""数据统计模块 service — 为仪表板提供聚合统计。

返回 {filters, kpis, dimensions} 结构（ADR-0007）。
"""

from __future__ import annotations

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.logger import log

from .stats_query import get_dashboard_overview
from .stats_schema import DashboardOverviewOut, PatientListOut, PatientListQuery, StatsFiltersIn


class StatsService:
    """数据统计服务"""

    @classmethod
    async def get_overview_service(
        cls,
        auth: AuthSchema,
        filters: StatsFiltersIn,
    ) -> dict:
        """获取仪表板全量概览（维度数组结构）。"""
        try:
            overview = await get_dashboard_overview(auth.db, filters=filters)
            return DashboardOverviewOut(**overview).model_dump()
        except Exception as e:
            log.error(f"[StatsService] 获取仪表板概览失败: {e!s}")
            raise

    @classmethod
    async def get_patient_list_service(
        cls,
        auth: AuthSchema,
        query: PatientListQuery,
    ) -> dict:
        """获取患者分页列表。"""
        try:
            from .stats_query import StatsQuery

            filters = StatsFiltersIn(**query.model_dump(exclude={"current", "size"}))
            stats_query = StatsQuery(auth.db, filters=filters)
            result = await stats_query.patient_list(
                current=query.current, size=query.size
            )
            return PatientListOut(**result).model_dump()
        except Exception as e:
            log.error(f"[StatsService] 获取患者列表失败: {e!s}")
            raise
