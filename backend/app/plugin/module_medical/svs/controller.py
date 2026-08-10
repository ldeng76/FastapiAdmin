"""SVS 切片查看器控制器。

提供 SVS/SLD/NDPI 等切片文件的 RESTful API，
供 OpenSeadragon 等前端查看器使用。
"""

from typing import Annotated

from fastapi import APIRouter, Path, Query, Response
from fastapi.responses import JSONResponse
from app.config.setting import settings
from .service import SVSService

# SVS 专用路由
SVSRouter = APIRouter(tags=["SVS"])


@SVSRouter.get(
    "/svs/slides/open",
    summary="打开 SVS 文件",
    description="打开指定路径的 SVS/SLD/NDPI 文件，返回切片元信息",
)
async def open_slide(
    file_path: Annotated[str | None, Query(description="切片文件路径，不传则使用默认路径")] = None,
) -> JSONResponse:
    """打开 SVS 文件并返回元信息。"""
    path = file_path or f"{settings.SVS_DATA_DIR}/WSI_sample/B1229048-2.svs"
    result = SVSService.open_slide(path)
    return JSONResponse(content=result)


@SVSRouter.get(
    "/svs/slides/{slide_id}",
    summary="获取切片元信息",
    description="获取已打开切片的元数据",
)
async def get_slide_info(
    slide_id: Annotated[str, Path(description="切片 ID")],
) -> JSONResponse:
    """获取切片元信息。"""
    result = SVSService.get_slide_info(slide_id)
    return JSONResponse(content=result)


@SVSRouter.get(
    "/svs/slides/{slide_id}/tile",
    summary="获取切片瓦片",
    description="获取指定层级和坐标的瓦片图像（JPEG 格式）",
)
async def get_tile(
    slide_id: Annotated[str, Path(description="切片 ID")],
    level: Annotated[int, Query(description="层级（0 为最高分辨率）", ge=0)],
    x: Annotated[int, Query(description="瓦片 X 坐标", ge=0)],
    y: Annotated[int, Query(description="瓦片 Y 坐标", ge=0)],
) -> Response:
    """获取切片瓦片。"""
    tile_data = SVSService.get_tile(
        slide_id=slide_id,
        level=level,
        x=x,
        y=y,
    )
    return Response(content=tile_data, media_type="image/jpeg")


@SVSRouter.get(
    "/svs/slides/{slide_id}/thumbnail",
    summary="获取切片缩略图",
    description="获取切片的缩略图（PNG 格式）",
)
async def get_thumbnail(
    slide_id: Annotated[str, Path(description="切片 ID")],
    max_size: Annotated[int, Query(description="最大尺寸（像素）", ge=64, le=1024)] = 256,
) -> Response:
    """获取切片缩略图。"""
    thumb_data = SVSService.get_thumbnail(
        slide_id=slide_id,
        max_size=max_size,
    )
    return Response(content=thumb_data, media_type="image/png")


@SVSRouter.get(
    "/svs/slides/{slide_id}/associated/{image_name}",
    summary="获取关联图像",
    description="获取切片的关联图像（label 标签图、macro 宏观图等，JPEG 格式）",
)
async def get_associated_image(
    slide_id: Annotated[str, Path(description="切片 ID")],
    image_name: Annotated[str, Path(description="图像名称（label/macro）")],
) -> Response:
    """获取关联图像。"""
    img_data, mime = SVSService.get_associated_image(slide_id, image_name)
    media_type = mime if mime else "image/jpeg"
    return Response(content=img_data, media_type=media_type)


@SVSRouter.get(
    "/svs/slides",
    summary="列出已打开的切片",
    description="列出当前已缓存的所有切片",
)
async def list_slides() -> JSONResponse:
    """列出已打开的切片。"""
    slides = SVSService.list_available_slides()
    return JSONResponse(content={"slides": slides, "count": len(slides)})


@SVSRouter.delete(
    "/svs/slides/cache",
    summary="清理切片缓存",
    description="关闭所有切片并清理缓存",
)
async def clear_cache() -> JSONResponse:
    """清理所有缓存。"""
    SVSService.clear_cache()
    return JSONResponse(content={"message": "缓存已清理"})
