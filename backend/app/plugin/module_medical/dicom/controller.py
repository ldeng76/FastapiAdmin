"""DICOM 影像浏览 controller（自动发现挂到 /medical/dicom）。

只读端点：Study 列表 → Series 列表 → 切片列表 → 原始 .dcm 文件流。
前 3 个返回 JSON 元数据；切片文件接口返回 application/dicom 字节流，
供前端 cornerstone dicom-image-loader（wadouri scheme）解码，保留 HU 值以支持调窗/测量。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path
from fastapi.responses import FileResponse, JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ResponseSchema, SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .schema import InstanceOut, SeriesOut, StudyOut
from .service import DicomService

# 容器前缀由顶级目录名自动生成为 /medical（module_medical 去 module_ 前缀）
# 本文件位于 module_medical/dicom/ 子目录，仍挂到 /medical，故路由为 /medical/dicom/...
# 这里同样不设 prefix，避免叠加。
DicomRouter = APIRouter(route_class=OperationLogRoute, tags=["DICOM 影像"])


@DicomRouter.get(
    "/dicom/studies",
    summary="DICOM Study 列表",
    description="扫描 DICOM 数据目录，返回每个 Study（子目录）的概要信息",
    response_model=ResponseSchema[list[StudyOut]],
)
async def list_dicom_studies_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:dicom:query"]))],
) -> JSONResponse:
    """Study 列表。"""
    result = await DicomService.list_studies_service()
    return SuccessResponse(data=result, msg="获取 Study 列表成功")


@DicomRouter.get(
    "/dicom/studies/{study_id}/series",
    summary="DICOM Series 列表",
    description="返回指定 Study 下所有 Series 的元信息",
    response_model=ResponseSchema[list[SeriesOut]],
)
async def list_dicom_series_controller(
    study_id: Annotated[str, Path(description="Study 标识（目录名）")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:dicom:query"]))],
) -> JSONResponse:
    """Series 列表。"""
    result = await DicomService.list_series_service(study_id=study_id)
    return SuccessResponse(data=result, msg="获取 Series 列表成功")


@DicomRouter.get(
    "/dicom/series/{series_uid}/instances",
    summary="DICOM 切片列表（已排序）",
    description="返回指定 Series 的所有切片，已按解剖顺序（Z 轴）排序",
    response_model=ResponseSchema[list[InstanceOut]],
)
async def list_dicom_instances_controller(
    series_uid: Annotated[str, Path(description="SeriesInstanceUID")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:dicom:query"]))],
) -> JSONResponse:
    """切片列表（已排序）。"""
    result = await DicomService.list_instances_service(series_uid=series_uid)
    return SuccessResponse(data=result, msg="获取切片列表成功")


@DicomRouter.get(
    "/dicom/instances/{sop_uid}",
    summary="DICOM 原始文件",
    description="按 SOPInstanceUID 返回原始 .dcm 字节流，供 wadouri 加载",
)
async def get_dicom_instance_controller(
    sop_uid: Annotated[str, Path(description="SOPInstanceUID")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:dicom:query"]))],
) -> FileResponse:
    """原始 DICOM 文件流。

    返回 application/dicom，浏览器 cornerstone 在客户端解码，保留 HU 值。
    sop_uid 经索引器校验仅命中已扫描文件，杜绝路径穿越。
    """
    path = DicomService.get_instance_path_service(sop_uid=sop_uid)
    return FileResponse(path=str(path), media_type="application/dicom")
