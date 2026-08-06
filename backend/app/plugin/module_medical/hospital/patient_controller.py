"""患者多模态 controller（自动发现挂到 /medical）。

为患者列表/详情页提供只读 API：
- `/centers`        — 枚举中心（前端下拉）
- `/patients`       — 患者分页列表
- `/patients/{id}`  — 患者多模态详情（临床/基因/病理/影像 4 模态）

注意：/patients 必须在 /patients/{patient_id} 之前声明，
否则 FastAPI 会把 "list" 误匹配为 patient_id。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ResponseSchema, SuccessResponse
from app.core.base_params import PaginationQueryParam
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .patient_service import PatientService

PatientRouter = APIRouter(route_class=OperationLogRoute, tags=["患者多模态"])


@PatientRouter.get(
    "/centers",
    summary="枚举来源中心",
    description="动态枚举 lnrs_anon_patient 中实际出现的 center_code",
    response_model=ResponseSchema[list[str]],
)
async def list_centers_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:patient:query"]))],
) -> JSONResponse:
    """中心列表（前端下拉选项）。"""
    result = await PatientService.list_centers_service(auth=auth)
    return SuccessResponse(data=result, msg="获取中心列表成功")


@PatientRouter.get(
    "/patients",
    summary="患者分页列表",
    description="支持按中心/关键词筛选，按 center_code + patient_id 排序",
    response_model=ResponseSchema[dict],
)
async def list_patients_controller(
    page: Annotated[PaginationQueryParam, Depends()],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:patient:query"]))],
    center: Annotated[
        str | None,
        Query(description="中心编码（精确匹配 center_code）"),
    ] = None,
    keyword: Annotated[
        str | None,
        Query(description="患者编号/中心 关键词（ILIKE 模糊匹配）"),
    ] = None,
) -> JSONResponse:
    """患者分页列表。"""
    result = await PatientService.list_patients_service(
        auth=auth, center=center, keyword=keyword, page=page,
    )
    return SuccessResponse(data=result, msg="获取患者列表成功")


@PatientRouter.get(
    "/patients/{patient_id}",
    summary="患者多模态详情",
    description=(
        "返回 4 模态详情（临床/基因/病理/影像）；"
        "clinical 数组包含就诊/手术/检验/医嘱/其他检查行,"
        "每行带 _table 折叠面板标签和 _modality 模态标记；"
        "JSONB 字段已就地顶层展开。"
    ),
    response_model=ResponseSchema[dict],
)
async def get_patient_detail_controller(
    patient_id: Annotated[str, Path(description="患者编号 PT_xxxxxxxx")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:patient:query"]))],
    center: Annotated[
        str | None,
        Query(description="中心编码（可选，限定单中心）"),
    ] = None,
) -> JSONResponse:
    """患者多模态详情。"""
    result = await PatientService.get_patient_detail_service(
        auth=auth, patient_id=patient_id, center=center,
    )
    return SuccessResponse(data=result, msg="获取患者详情成功")
