"""数据统计模块 controller（自动发现挂到 /medical/statistics）。

为数据概览仪表板提供只读统计 API：
- `/statistics/overview` — 全量概览（维度数组结构，ADR-0007）
- `/statistics/age-buckets` — 年龄段字典
- `/statistics/patients` — 患者分页列表
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ResponseSchema, SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .stats_query import AGE_BUCKET_OPTIONS
from .stats_schema import PatientListQuery, StatsFiltersIn
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
    filters: StatsFiltersIn = Depends(),
) -> JSONResponse:
    """仪表板全量概览（维度数组结构，ADR-0007）。"""
    result = await StatsService.get_overview_service(auth=auth, filters=filters)
    return SuccessResponse(data=result, msg="获取数据概览成功")


@StatsRouter.get(
    "/statistics/age-buckets",
    summary="年龄段字典",
    description="返回可选的年龄段列表（供前端筛选项渲染）",
    response_model=ResponseSchema[list[dict]],
)
async def get_age_buckets_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:stats:query"]))],
) -> JSONResponse:
    """年龄段字典。"""
    return SuccessResponse(data=AGE_BUCKET_OPTIONS, msg="获取年龄段字典成功")


@StatsRouter.get(
    "/statistics/patients",
    summary="患者分页列表",
    description="分页查询患者列表，支持与统计概览相同的筛选条件",
    response_model=ResponseSchema[dict],
)
async def get_patient_list_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:stats:query"]))],
    query: PatientListQuery = Depends(),
) -> JSONResponse:
    """患者分页列表。"""
    result = await StatsService.get_patient_list_service(auth=auth, query=query)
    return SuccessResponse(data=result, msg="获取患者列表成功")
