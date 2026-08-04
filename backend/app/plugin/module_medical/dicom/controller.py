"""DICOMweb 控制器（供 OHIF Viewer 使用）。

实现标准 DICOMweb RESTful Services 接口：
- QIDO-RS（Query based on ID for DICOM Objects）：查询 Study/Series/Instance
- WADO-RS（Web Access to DICOM Objects）：获取实例二进制、元数据、渲染图像

与普通接口的区别：
- 响应格式：直接返回 DICOM JSON 数组，不使用 SuccessResponse 包装
- 路由类：不使用 OperationLogRoute（避免记录大量二进制数据）
- 认证：使用 Bearer Token（与现有认证体系兼容）
"""

from typing import Annotated
import os
from fastapi import APIRouter, Depends, Path, Query, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi import HTTPException
from .service import DicomService
from fastapi.responses import HTMLResponse

# DICOMweb 专用路由（不使用 OperationLogRoute，避免大文件日志）
DicomwebRouter = APIRouter(tags=["DICOMweb"])


@DicomwebRouter.get("/dicom/", response_class=HTMLResponse)
@DicomwebRouter.get("/dicom/viewer", response_class=HTMLResponse)
def dicom_viewer():
    dicom_static_path = os.getenv("DICOM_STATIC_DIR")
    print(dicom_static_path)
    if not dicom_static_path:
        raise HTTPException(status_code=500, detail="DICOM_STATIC_DIR 未配置")
    file_path = f"{dicom_static_path}/index.html"
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="DICOM模板不存在")
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    return content


# ======================================================================
# QIDO-RS：查询接口（返回 DICOM JSON 数组）
# ======================================================================

@DicomwebRouter.get(
    "/dicom/studies",
    summary="QIDO-RS: 查询 Study 列表",
    description="返回所有 Study 的 DICOM JSON 数组，支持 QIDO-RS 标准参数",
)
async def qido_query_studies(
    study_instance_uids: Annotated[str | None, Query(description="StudyInstanceUIDs (逗号分隔)")] = None,
    patient_id: Annotated[str | None, Query(description="PatientID")] = None,
    patient_name: Annotated[str | None, Query(description="PatientName")] = None,
    study_date: Annotated[str | None, Query(description="StudyDate (YYYYMMDD)")] = None,
    modalities_in_study: Annotated[str | None, Query(description="ModalitiesInStudy (逗号分隔)")] = None,
) -> JSONResponse:
    """QIDO-RS: 查询 Study 列表。"""
    result = DicomService.query_studies(
        study_instance_uids=study_instance_uids,
        patient_id=patient_id,
        patient_name=patient_name,
        study_date=study_date,
        modalities_in_study=modalities_in_study,
    )
    return JSONResponse(content=result, media_type="application/dicom+json")


@DicomwebRouter.get(
    "/dicom/studies/{study_uid}",
    summary="QIDO-RS: 查询单个 Study",
    description="按 StudyInstanceUID 查询单个 Study 的 DICOM JSON",
)
async def qido_query_study(
    study_uid: Annotated[str, Path(description="StudyInstanceUID")],
) -> JSONResponse:
    """QIDO-RS: 查询单个 Study。"""
    result = DicomService.query_study(study_uid)
    if result is None:
        return JSONResponse(
            content={"error": "Study not found"},
            status_code=404,
            media_type="application/dicom+json",
        )
    return JSONResponse(content=[result], media_type="application/dicom+json")


@DicomwebRouter.get(
    "/dicom/studies/{study_uid}/series",
    summary="QIDO-RS: 查询 Study 下的 Series 列表",
    description="按 StudyInstanceUID 查询所有 Series 的 DICOM JSON",
)
async def qido_query_series(
    study_uid: Annotated[str, Path(description="StudyInstanceUID")],
) -> JSONResponse:
    """QIDO-RS: 查询 Study 下的 Series。"""
    result = DicomService.query_series(study_uid)
    return JSONResponse(content=result, media_type="application/dicom+json")


@DicomwebRouter.get(
    "/dicom/series/{series_uid}",
    summary="QIDO-RS: 查询单个 Series",
    description="按 SeriesInstanceUID 查询单个 Series 的 DICOM JSON",
)
async def qido_query_series_by_uid(
    series_uid: Annotated[str, Path(description="SeriesInstanceUID")],
) -> JSONResponse:
    """QIDO-RS: 查询单个 Series。"""
    result = DicomService.query_series_by_uid(series_uid)
    if result is None:
        return JSONResponse(
            content={"error": "Series not found"},
            status_code=404,
            media_type="application/dicom+json",
        )
    return JSONResponse(content=[result], media_type="application/dicom+json")


@DicomwebRouter.get(
    "/dicom/studies/{study_uid}/series/{series_uid}/instances",
    summary="QIDO-RS: 查询 Series 下的 Instance 列表",
    description="按 StudyInstanceUID 和 SeriesInstanceUID 查询所有 Instance 的 DICOM JSON",
)
async def qido_query_instances(
    study_uid: Annotated[str, Path(description="StudyInstanceUID")],
    series_uid: Annotated[str, Path(description="SeriesInstanceUID")],
) -> JSONResponse:
    """QIDO-RS: 查询 Series 下的 Instance。"""
    result = DicomService.query_instances(series_uid)
    return JSONResponse(content=result, media_type="application/dicom+json")


@DicomwebRouter.get(
    "/dicom/series/{series_uid}/instances",
    summary="QIDO-RS: 查询 Series 下的 Instance 列表（简化路径）",
    description="按 SeriesInstanceUID 查询所有 Instance 的 DICOM JSON",
)
async def qido_query_instances_by_series(
    series_uid: Annotated[str, Path(description="SeriesInstanceUID")],
) -> JSONResponse:
    """QIDO-RS: 查询 Series 下的 Instance（简化路径）。"""
    result = DicomService.query_instances(series_uid)
    return JSONResponse(content=result, media_type="application/dicom+json")


# ======================================================================
# WADO-RS：获取实例二进制 / 元数据 / 渲染图像
# ======================================================================

# 注意：/dicom/instances/{sop_uid} 路由必须返回 DICOM 文件（application/dicom），
# 不能与 QIDO-RS 查询接口冲突。QIDO-RS 实例查询请使用 /metadata 路径。

@DicomwebRouter.get(
    "/dicom/studies/{study_uid}/metadata",
    summary="WADO-RS: 获取 Study 的 DICOM JSON 元数据",
    description="返回 Study 下所有 Instance 的完整 DICOM JSON 元数据",
)
async def wado_study_metadata(
    study_uid: Annotated[str, Path(description="StudyInstanceUID")],
) -> JSONResponse:
    """WADO-RS: Study 级元数据。"""
    result = DicomService.get_study_metadata(study_uid)
    return JSONResponse(content=result, media_type="application/dicom+json")


@DicomwebRouter.get(
    "/dicom/studies/{study_uid}/series/{series_uid}/metadata",
    summary="WADO-RS: 获取 Series 的 DICOM JSON 元数据",
    description="返回 Series 下所有 Instance 的完整 DICOM JSON 元数据",
)
async def wado_series_metadata(
    study_uid: Annotated[str, Path(description="StudyInstanceUID")],
    series_uid: Annotated[str, Path(description="SeriesInstanceUID")],
) -> JSONResponse:
    """WADO-RS: Series 级元数据。"""
    result = DicomService.get_series_metadata(series_uid)
    return JSONResponse(content=result, media_type="application/dicom+json")


@DicomwebRouter.get(
    "/dicom/instances/{sop_uid}/metadata",
    summary="WADO-RS: 获取 Instance 的 DICOM JSON 元数据",
    description="返回单个 Instance 的完整 DICOM JSON 元数据",
)
async def wado_instance_metadata(
    sop_uid: Annotated[str, Path(description="SOPInstanceUID")],
) -> JSONResponse:
    """WADO-RS: Instance 级元数据。"""
    result = DicomService.get_instance_metadata(sop_uid)
    if result is None:
        return JSONResponse(
            content={"error": "Instance not found"},
            status_code=404,
            media_type="application/dicom+json",
        )
    return JSONResponse(content=[result], media_type="application/dicom+json")


@DicomwebRouter.get(
    "/dicom/studies/{study_uid}/series/{series_uid}/instances/{sop_uid}",
    summary="WADO-RS: 获取 Instance 的 DICOM 二进制",
    description="返回原始 DICOM 文件（application/dicom），供 cornerstone/wadouri 加载",
)
async def wado_get_instance(
    study_uid: Annotated[str, Path(description="StudyInstanceUID")],
    series_uid: Annotated[str, Path(description="SeriesInstanceUID")],
    sop_uid: Annotated[str, Path(description="SOPInstanceUID")],
) -> FileResponse:
    """WADO-RS: Instance 二进制文件。"""
    path = DicomService.get_instance_file(sop_uid)
    return FileResponse(path=str(path), media_type="application/dicom")


@DicomwebRouter.get(
    "/dicom/instances/{sop_uid}",
    summary="WADO-RS: 获取 Instance 的 DICOM 二进制（简化路径）",
    description="按 SOPInstanceUID 返回原始 DICOM 文件",
)
async def wado_get_instance_by_uid(
    sop_uid: Annotated[str, Path(description="SOPInstanceUID")],
) -> FileResponse:
    """WADO-RS: Instance 二进制文件（简化路径）。"""
    path = DicomService.get_instance_file(sop_uid)
    return FileResponse(path=str(path), media_type="application/dicom")


@DicomwebRouter.get(
    "/dicom/instances/{sop_uid}/rendered",
    summary="WADO-RS: 获取 Instance 的渲染图像",
    description="将 DICOM 渲染为 PNG 图像，供 OHIF 直接显示",
)
async def wado_rendered_instance(
    sop_uid: Annotated[str, Path(description="SOPInstanceUID")],
    frame_number: Annotated[int | None, Query(description="帧号（多帧图像）")] = None,
    quality: Annotated[int, Query(description="JPEG 质量 (1-100)")] = 75,
) -> Response:
    """WADO-RS: 渲染 Instance 为 PNG。"""
    img_bytes, content_type = DicomService.get_rendered_instance(
        sop_uid, frame_number=frame_number, quality=quality
    )
    return Response(content=img_bytes, media_type=content_type)


@DicomwebRouter.get(
    "/dicom/studies/{study_uid}/series/{series_uid}/instances/{sop_uid}/frames/{frame_number}",
    summary="WADO-RS: 获取 Instance 指定帧（完整路径）",
    description="按 StudyUID/SeriesUID/SOPUID/FrameNumber 获取帧的原始像素数据（multipart/related）",
)
async def wado_get_instance_frame_fullpath(
    sop_uid: Annotated[str, Path(description="SOPInstanceUID")],
    frame_number: Annotated[int, Path(description="帧号")],
) -> Response:
    """WADO-RS: frames 完整路径。"""
    body, content_type = DicomService.get_instance_frame_multipart(
        sop_uid=sop_uid, frame_number=frame_number
    )
    return Response(content=body, media_type=content_type)


@DicomwebRouter.get(
    "/dicom/studies/{study_uid}/series/{series_uid}/instances/{sop_uid}/thumbnail",
    summary="WADO-RS: 获取 Instance 缩略图（完整路径）",
    description="按 StudyUID/SeriesUID/SOPUID 返回 PNG 缩略图，支持 viewport 参数缩放",
)
async def wado_get_instance_thumbnail_fullpath(
    sop_uid: Annotated[str, Path(description="SOPInstanceUID")],
    viewport: Annotated[str | None, Query(description="缩略图尺寸，格式: 宽,高 (如 256,256)")] = None,
) -> Response:
    """WADO-RS: thumbnail 完整路径。"""
    img_bytes, content_type = DicomService.get_thumbnail(
        sop_uid=sop_uid, viewport=viewport
    )
    return Response(content=img_bytes, media_type=content_type)

@DicomwebRouter.get(
    "/dicom/studies/{study_uid}/series/{series_uid}/thumbnail",
    summary="WADO-RS: 获取 Series 缩略图",
    description="按 StudyUID/SeriesUID 返回 PNG 缩略图（自动取中间帧），支持 viewport 参数缩放",
)
async def wado_get_series_thumbnail_fullpath(
    series_uid: Annotated[str, Path(description="SeriesInstanceUID")],
    viewport: Annotated[str | None, Query(description="缩略图尺寸，格式: 宽,高 (如 256,256)")] = None,
) -> Response:
    """WADO-RS: Series 级别缩略图。"""
    img_bytes, content_type = DicomService.get_series_thumbnail(
        series_uid=series_uid, viewport=viewport
    )
    return Response(content=img_bytes, media_type=content_type)


