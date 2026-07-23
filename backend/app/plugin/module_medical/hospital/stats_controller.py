"""数据统计模块 controller（自动发现挂到 /medical/statistics）。

为数据概览仪表板提供只读统计 API：
- `/statistics/overview` — 全量概览（维度数组结构，ADR-0007）
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ResponseSchema, SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .stats_service import StatsService

StatsRouter = APIRouter(route_class=OperationLogRoute, tags=["数据统计"])


@StatsRouter.get(
    "/statistics/overview",
    summary="仪表板全量概览",
    description="一次性获取所有维度的统计数据（filters + kpis + dimensions 数组结构）",
    response_model=ResponseSchema[dict],
)
async def get_overview_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:stats:query"]))],
) -> JSONResponse:
    """仪表板全量概览（维度数组结构，ADR-0007）。"""
    result = await StatsService.get_overview_service(auth=auth)
    return SuccessResponse(data=result, msg="获取数据概览成功")
