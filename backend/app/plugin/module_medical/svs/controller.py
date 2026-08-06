"""SVS 切片查看器控制器。

提供 SVS/SLD/NDPI 等切片文件的 RESTful API，
供 OpenSeadragon 等前端查看器使用。
"""

from typing import Annotated

from fastapi import APIRouter, Path, Query, Response
from fastapi.responses import JSONResponse

from .service import SVSService

# SVS 专用路由
SVSRouter = APIRouter(tags=["SVS"])


@SVSRouter.get(
    "/svs/slides/open",
    summary="打开 SVS 文件",
    description="打开指定路径的 SVS/SLD/NDPI 文件，返回切片元信息",
)
async def open_slide(
    file_path: Annotated[str, Query(description="切片文件的绝对路径")],
) -> JSONResponse:
    """打开 SVS 文件并返回元信息。"""
    result = SVSService.open_slide(file_path)
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
    slides = SVSService.list_available_slides()
    if slide_id not in slides:
        return JSONResponse(
            content={"detail": f"Slide 未找到: {slide_id}"},
            status_code=404,
        )
    # 重新打开以获取最新信息
    # 注：这里简化处理，实际项目中应该存储 file_path
    return JSONResponse(
        content={"detail": "请使用 /svs/slides/open 接口打开文件后获取信息"},
        status_code=400,
    )


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
    tile_size: Annotated[int, Query(description="瓦片大小（像素）", ge=64, le=1024)] = 256,
) -> Response:
    """获取切片瓦片。"""
    tile_data = SVSService.get_tile(
        slide_id=slide_id,
        level=level,
        x=x,
        y=y,
        tile_size=tile_size,
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


@SVSRouter.post(
    "/svs/slides/{slide_id}/close",
    summary="关闭切片",
    description="关闭指定切片并释放资源",
)
async def close_slide(
    slide_id: Annotated[str, Path(description="切片 ID")],
) -> JSONResponse:
    """关闭切片。"""
    SVSService.close_slide(slide_id)
    return JSONResponse(content={"message": f"切片 {slide_id} 已关闭"})


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