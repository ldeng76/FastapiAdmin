"""医学数据模块 controller（自动发现为 /medical）。

只读端点：来源中心枚举 + 患者分页列表 + 患者多模态详情。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ResponseSchema, SuccessResponse
from app.core.base_params import PaginationQueryParam
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .schema import PatientDetailOut, PatientPageOut
from .service import PatientService

# 容器前缀由目录名自动生成为 /medical（module_medical 去 module_ 前缀）
# 故此处不再设 prefix，避免叠加成 /medical/medical
MedicalRouter = APIRouter(route_class=OperationLogRoute, tags=["医学数据"])


@MedicalRouter.get(
    "/centers",
    summary="来源中心枚举",
    description="枚举数据中出现的来源中心，供前端下拉筛选",
)
async def list_centers_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:patient:query"]))],
) -> JSONResponse:
    """来源中心枚举。"""
    result = await PatientService.centers_service(auth=auth)
    return SuccessResponse(data=result, msg="获取来源中心成功")


@MedicalRouter.get(
    "/patients",
    summary="患者分页列表",
    description="查询患者列表，支持按中心/关键词筛选",
    response_model=ResponseSchema[PatientPageOut],
)
async def get_patient_page_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:patient:query"]))],
    page: Annotated[PaginationQueryParam, Depends()],
    center: Annotated[str | None, Query(description="来源中心（省医/珠江/新桥）")] = None,
    keyword: Annotated[str | None, Query(description="患者编号/中心关键词")] = None,
) -> JSONResponse:
    """患者分页列表。"""
    result_dict = await PatientService.page_service(
        auth=auth,
        page_no=page.page_no,
        page_size=page.page_size,
        center=center,
        keyword=keyword,
    )
    return SuccessResponse(data=result_dict, msg="获取患者列表成功")


@MedicalRouter.get(
    "/patients/{patient_id}",
    summary="患者多模态详情",
    description="按患者维度聚合四模态数据（临床/基因/病理/影像）",
    response_model=ResponseSchema[PatientDetailOut],
)
async def get_patient_detail_controller(
    patient_id: Annotated[str, Path(description="患者编号")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:patient:query"]))],
    center: Annotated[str | None, Query(description="来源中心（同名跨院时消歧）")] = None,
) -> JSONResponse:
    """患者多模态详情。"""
    result_dict = await PatientService.detail_service(
        auth=auth, patient_id=patient_id, center=center
    )
    return SuccessResponse(data=result_dict, msg="获取患者多模态详情成功")
