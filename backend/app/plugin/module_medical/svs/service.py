"""SVS 切片服务层（基于 large-image SDK）。

使用 Kitware 的 large_image 库提供 SVS/SLD/NDPI/TIFF 等切片文件的
读取和瓦片服务，内置缓存、边界处理、关联图像等功能。

依赖：
- Windows: pip install openslide-bin openslide-python large-image large-image-source-openslide
- Linux:   yum install openslide openslide-devel && pip install openslide-python large-image large-image-source-openslide
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from large_image.exceptions import TileSourceXYZRangeError, TileSourceError

from app.core.logger import log

# 可选依赖：large_image
try:
    import large_image
    # 手动注册 openslide source（entry point 在某些环境下不自动注册）
    try:
        from large_image_source_openslide import OpenslideFileTileSource
        if "openslide" not in large_image.tilesource.AvailableTileSources:
            large_image.tilesource.AvailableTileSources["openslide"] = OpenslideFileTileSource
    except ImportError:
        pass

    HAS_LARGE_IMAGE = True
except ImportError:
    HAS_LARGE_IMAGE = False
    log.warning("large-image 未安装，SVS 功能不可用。")


class SVSService:
    """SVS 切片服务（基于 large-image SDK）。"""

    # slide_id -> file_path 映射（large_image 自带 tile source 缓存）
    _slide_paths: dict[str, str] = {}

    @classmethod
    def _check_dependency(cls) -> None:
        """检查 large_image 依赖是否可用。"""
        if not HAS_LARGE_IMAGE:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="服务器缺少 large-image 依赖",
            )

    @classmethod
    def _path_safety_check(cls, file_path: str) -> Path:
        """路径安全校验。"""
        path = Path(file_path).resolve()
        if not path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"文件不存在: {file_path}",
            )
        if not path.is_file():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不是文件: {file_path}",
            )
        return path

    @classmethod
    def _get_slide_id(cls, file_path: str) -> str:
        """根据文件路径生成唯一 ID。"""
        return hashlib.md5(file_path.encode()).hexdigest()[:16]

    @classmethod
    def _get_tile_source(cls, slide_id: str) -> Any:
        """获取已打开的 tile source。"""
        file_path = cls._slide_paths.get(slide_id)
        if file_path is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Slide 未找到: {slide_id}，请先调用 open 接口",
            )
        try:
            return large_image.getTileSource(file_path)
        except TileSourceError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无法打开切片文件: {str(e)}",
            )

    @classmethod
    def open_slide(cls, file_path: str) -> dict[str, Any]:
        """打开 SVS 文件并返回元信息。

        Args:
            file_path: SVS 文件的绝对路径

        Returns:
            包含切片元数据的字典
        """
        cls._check_dependency()
        path = cls._path_safety_check(file_path)
        slide_id = cls._get_slide_id(file_path)

        # 记录 slide_id -> file_path 映射
        cls._slide_paths[slide_id] = str(path)

        try:
            ts = large_image.getTileSource(str(path))
            meta = ts.getMetadata()
            return cls._build_slide_info(slide_id, str(path), meta)
        except TileSourceError as e:
            log.error(f"打开 SVS 文件失败: {path}, 错误: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无法打开切片文件: {str(e)}",
            )
        except TileSourceError as e:
            log.error(f"打开 SVS 文件失败: {path}, 错误: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"打开切片文件失败: {str(e)}",
            )

    @classmethod
    def _build_slide_info(cls, slide_id: str, file_path: str, meta: dict) -> dict[str, Any]:
        """从 large_image metadata 构建前端所需的切片信息。"""
        levels = meta["levels"]
        size_x = meta["sizeX"]
        size_y = meta["sizeY"]
        tile_width = meta["tileWidth"]
        tile_height = meta["tileHeight"]

        # 计算各层级尺寸和下采样系数
        level_dimensions = []
        level_downsamples = []
        for level in range(levels):
            downsample = 2 ** level
            level_downsamples.append(float(downsample))
            level_dimensions.append([
                max(1, size_x // downsample),
                max(1, size_y // downsample),
            ])

        return {
            "slide_id": slide_id,
            "file_path": file_path,
            "width": size_x,
            "height": size_y,
            "tile_width": tile_width,
            "tile_height": tile_height,
            "level_count": levels,
            "level_downsamples": level_downsamples,
            "level_dimensions": level_dimensions,
            "mm_x": meta.get("mm_x"),
            "mm_y": meta.get("mm_y"),
            "magnification": meta.get("magnification"),
        }

    @classmethod
    def get_slide_info(cls, slide_id: str) -> dict[str, Any]:
        """获取切片元信息。"""
        cls._check_dependency()
        file_path = cls._slide_paths.get(slide_id)
        if file_path is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Slide 未找到: {slide_id}",
            )
        try:
            ts = large_image.getTileSource(file_path)
            meta = ts.getMetadata()
            return cls._build_slide_info(slide_id, file_path, meta)
        except Exception as e:
            log.error(f"获取切片信息失败: {slide_id}, 错误: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"获取切片信息失败: {str(e)}",
            )

    @classmethod
    def get_tile(
        cls,
        slide_id: str,
        level: int,
        x: int,
        y: int,
    ) -> bytes:
        """获取指定瓦片。

        large_image 自动处理边界，超出范围会抛出 TileSourceXYZRangeError。

        Args:
            slide_id: 切片 ID
            level: 层级（0 为最高分辨率）
            x: 瓦片 X 坐标
            y: 瓦片 Y 坐标

        Returns:
            JPEG 格式的瓦片数据
        """
        cls._check_dependency()
        ts = cls._get_tile_source(slide_id)

        try:
            tile_data = ts.getTile(
                x, y, level,
                format=large_image.tilesource.TILE_FORMAT_IMAGE,
                encoding="JPEG",
            )
            return bytes(tile_data)
        except TileSourceXYZRangeError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"瓦片超出范围: level={level}, x={x}, y={y}",
            )
        except Exception as e:
            log.error(f"获取瓦片失败: slide={slide_id}, level={level}, x={x}, y={y}, 错误: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"获取瓦片失败: {str(e)}",
            )

    @classmethod
    def get_thumbnail(
        cls,
        slide_id: str,
        max_size: int = 256,
    ) -> bytes:
        """获取切片缩略图。

        Args:
            slide_id: 切片 ID
            max_size: 最大尺寸（像素）

        Returns:
            PNG 格式的缩略图数据
        """
        cls._check_dependency()
        ts = cls._get_tile_source(slide_id)

        try:
            thumb_data, _mime = ts.getThumbnail(
                width=max_size,
                height=max_size,
                encoding="PNG",
            )
            return bytes(thumb_data)
        except Exception as e:
            log.error(f"获取缩略图失败: slide={slide_id}, 错误: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"获取缩略图失败: {str(e)}",
            )

    @classmethod
    def get_associated_image(
        cls,
        slide_id: str,
        image_name: str,
    ) -> tuple[bytes, str]:
        """获取关联图像（label/macro 等）。

        Args:
            slide_id: 切片 ID
            image_name: 图像名称（label、macro）

        Returns:
            (图像数据, mime_type)
        """
        cls._check_dependency()
        ts = cls._get_tile_source(slide_id)

        try:
            img_data, mime = ts.getAssociatedImage(image_name, encoding="JPEG")
            return bytes(img_data), mime
        except Exception as e:
            log.error(f"获取关联图像失败: slide={slide_id}, name={image_name}, 错误: {e}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"关联图像 '{image_name}' 不可用: {str(e)}",
            )

    @classmethod
    def list_available_slides(cls) -> list[str]:
        """列出已缓存的切片 ID。"""
        return list(cls._slide_paths.keys())

    @classmethod
    def clear_cache(cls) -> None:
        """清理所有缓存。"""
        cls._slide_paths.clear()
        try:
            large_image.tilesource.utilities.CacheCache.caches = {}
        except Exception:
            pass
        log.info("SVS 缓存已清理")
