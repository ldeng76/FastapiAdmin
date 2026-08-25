"""NIfTI 医学影像查看器控制器。

提供 NIfTI 文件的 RESTful API 接口，
供前端 nifti-imaging 查看器使用。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.dependencies import AuthPermission
from app.plugin.module_medical.files.service import MedFilesService
from .service import NIfTIService

# NIfTI 专用路由
NIfTIRouter = APIRouter(tags=["NIfTI"])


@NIfTIRouter.get(
    "/nifti/file",
    summary="按文件ID获取 NIfTI 文件内容",
    description="按 med_files 表的 file_id 获取 NIfTI (.nii, .nii.gz) 文件内容，返回二进制数据供前端解析",
)
async def get_nifti_file(
    file_id: Annotated[int, Query(description="med_files 表的文件ID", ge=1)],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:files:query"]))],
) -> Response:
    """按文件ID获取 NIfTI 文件内容。"""
    path, _ = await MedFilesService.get_file_stream_service(auth=auth, file_id=file_id)
    content = NIfTIService.read_file(str(path))
    return Response(content=content, media_type="application/octet-stream")


@NIfTIRouter.get(
    "/nifti/file/info",
    summary="按文件ID获取 NIfTI 文件信息",
    description="按 med_files 表的 file_id 获取 NIfTI 文件元信息（大小、修改时间等）",
)
async def get_nifti_file_info(
    file_id: Annotated[int, Query(description="med_files 表的文件ID", ge=1)],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:files:query"]))],
) -> JSONResponse:
    """按文件ID获取 NIfTI 文件信息。"""
    path, _ = await MedFilesService.get_file_stream_service(auth=auth, file_id=file_id)
    info = NIfTIService.get_file_info(str(path))
    return JSONResponse(content=info)
