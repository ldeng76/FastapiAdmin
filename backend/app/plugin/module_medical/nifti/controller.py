"""NIfTI 医学影像查看器控制器。

提供 NIfTI 文件的 RESTful API 接口，
供前端 nifti-imaging 查看器使用。
"""

from typing import Annotated
from app.config.setting import settings
from fastapi import APIRouter, Query, Response
from fastapi.responses import JSONResponse

from .service import NIfTIService

# NIfTI 专用路由
NIfTIRouter = APIRouter(tags=["NIfTI"])


@NIfTIRouter.get(
    "/nifti/file",
    summary="获取 NIfTI 文件内容",
    description="获取指定路径的 NIfTI (.nii, .nii.gz) 文件内容，返回二进制数据供前端解析",
)
async def get_nifti_file(
    file_path: Annotated[str, Query(description="NIfTI 文件的绝对路径")],
) -> Response:
    """获取 NIfTI 文件内容。"""
    file_path =f"{settings.NII_DATA_DIR}/case_5.nii"
    content = NIfTIService.read_file(file_path)
    return Response(content=content, media_type="application/octet-stream")


@NIfTIRouter.get(
    "/nifti/file/info",
    summary="获取 NIfTI 文件信息",
    description="获取指定路径的 NIfTI 文件元信息（大小、修改时间等）",
)
async def get_nifti_file_info(
    file_path: Annotated[str, Query(description="NIfTI 文件的绝对路径")],
) -> JSONResponse:
    """获取 NIfTI 文件信息。"""
    info = NIfTIService.get_file_info(file_path)
    return JSONResponse(content=info)
