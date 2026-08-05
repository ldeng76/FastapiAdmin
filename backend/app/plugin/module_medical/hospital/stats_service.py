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
    async def get_overview_service(
        cls,
        auth: AuthSchema,
        center: str | None = None,
        gender: str | None = None,
        modality: str | None = None,
        age_bucket: str | None = None,
        abo_blood_type: str | None = None,
        smoking_status: str | None = None,
    ) -> dict:
        """获取仪表板全量概览（维度数组结构）。"""
        try:
            overview = await get_dashboard_overview(
                auth.db,
                center=center,
                gender=gender,
                modality=modality,
                age_bucket=age_bucket,
                abo_blood_type=abo_blood_type,
                smoking_status=smoking_status,
            )
            return DashboardOverviewOut(**overview).model_dump()
        except Exception as e:
            log.error(f"[StatsService] 获取仪表板概览失败: {e!s}")
            raise
