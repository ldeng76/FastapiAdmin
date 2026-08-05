"""数据统计模块 controller（自动发现挂到 /medical/statistics）。

为数据概览仪表板提供只读统计 API：
- `/statistics/overview` — 全量概览（维度数组结构，ADR-0007）
- `/statistics/age-buckets` — 年龄段字典
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ResponseSchema, SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .stats_query import AGE_BUCKET_OPTIONS
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
    center: str | None = Query(None, description="中心编码筛选"),
    gender: str | None = Query(None, description="性别筛选（0=未知, 1=男, 2=女, 9=其他）"),
    modality: str | None = Query(None, description="模态筛选（如 CT/MR/US 等）"),
    age_bucket: str | None = Query(
        None,
        description="年龄段筛选（0-17/18-29/30-39/40-49/50-59/60-69/70-79/80+）",
    ),
    abo_blood_type: str | None = Query(
        None, description="ABO血型筛选（1=A型, 2=B型, 3=O型, 4=AB型, 5=不详, 6=未查）"
    ),
    smoking_status: str | None = Query(
        None, description="吸烟状态筛选（1=从不, 2=既往, 3=现在, 9=未知）"
    ),
) -> JSONResponse:
    """仪表板全量概览（维度数组结构，ADR-0007）。"""
    result = await StatsService.get_overview_service(
        auth=auth,
        center=center,
        gender=gender,
        modality=modality,
        age_bucket=age_bucket,
        abo_blood_type=abo_blood_type,
        smoking_status=smoking_status,
    )
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
