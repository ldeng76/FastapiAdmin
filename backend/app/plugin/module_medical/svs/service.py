"""SVS 切片服务层（基于 large-image SDK）。

使用 Kitware 的 large_image 库提供 SVS/SLD/NDPI/TIFF 等切片文件的
读取和瓦片服务，内置缓存、边界处理、关联图像等功能。

依赖：
- Windows: pip install openslide-bin openslide-python large-image large-image-source-openslide
- Linux:   yum install openslide openslide-devel && pip install openslide-python large-image large-image-source-openslide
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

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

    # slide_id -> large_image TileSource 对象
    _slides: dict[str, Any] = {}
    # slide_id -> file_path
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
    def _get_slide(cls, slide_id: str) -> Any:
        """获取已打开的 TileSource 对象。"""
        slide = cls._slides.get(slide_id)
        if slide is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Slide 未找到: {slide_id}，请先调用 open 接口",
            )
        return slide

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

        # 已缓存则直接返回
        if slide_id in cls._slides:
            return cls._build_slide_info(slide_id, str(path), cls._slides[slide_id])

        try:
            slide = large_image.getTileSource(str(path))
            cls._slides[slide_id] = slide
            cls._slide_paths[slide_id] = str(path)
            log.info(f"打开 SVS 文件: {path}, ID: {slide_id}")
            return cls._build_slide_info(slide_id, str(path), slide)
        except Exception as e:
            log.error(f"打开 SVS 文件失败: {path}, 错误: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无法打开切片文件: {str(e)}",
            )

    @classmethod
    def _build_slide_info(
        cls, slide_id: str, file_path: str, slide: Any
    ) -> dict[str, Any]:
        """从 large_image TileSource 构建前端所需的切片信息。

        约定：level 0 = 最高分辨率，与 OpenSlide 原生一致。
        """
        meta = slide.getMetadata()

        size_x = meta["sizeX"]
        size_y = meta["sizeY"]
        tile_width = meta.get("tileWidth", 256)
        tile_height = meta.get("tileHeight", 256)
        levels = meta.get("levels", 1)

        # 各层级尺寸和下采样系数
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
            "magnification": meta.get("magnification"),
            "mm_x": meta.get("mm_x"),
            "mm_y": meta.get("mm_y"),
        }

    @classmethod
    def get_slide_info(cls, slide_id: str) -> dict[str, Any]:
        """获取切片元信息。"""
        cls._check_dependency()
        slide = cls._get_slide(slide_id)
        file_path = cls._slide_paths.get(slide_id, "")
        return cls._build_slide_info(slide_id, file_path, slide)

    @classmethod
    def get_tile(
        cls,
        slide_id: str,
        level: int,
        x: int,
        y: int,
    ) -> bytes:
        """获取指定瓦片。

        large_image level 0 = 最高分辨率。
        超出范围的瓦片返回 404。

        Args:
            slide_id: 切片 ID
            level: 层级（0 为最高分辨率）
            x: 瓦片 X 坐标
            y: 瓦片 Y 坐标

        Returns:
            JPEG 格式的瓦片数据
        """
        cls._check_dependency()
        slide = cls._get_slide(slide_id)

        try:
            meta = slide.getMetadata()
            levels = meta.get("levels", 1)
            tile_width = meta.get("tileWidth", 256)
            tile_height = meta.get("tileHeight", 256)

            if level >= levels:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Level {level} 不存在",
                )

            # 计算该层级的瓦片网格
            downsample = 2 ** level
            level_w = max(1, meta["sizeX"] // downsample)
            level_h = max(1, meta["sizeY"] // downsample)
            tiles_x = (level_w + tile_width - 1) // tile_width
            tiles_y = (level_h + tile_height - 1) // tile_height

            # 完全超出范围
            if x >= tiles_x or y >= tiles_y:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"瓦片超出范围: level={level}, x={x}, y={y}",
                )

            # large_image getTile 参数: (x, y, z, **kwargs)
            # z 是金字塔层级，0 = 最高分辨率
            tile_data = slide.getTile(
                x,
                y,
                level,
                format=large_image.tilesource.TILE_FORMAT_IMAGE,
                encoding="JPEG",
            )

            # getTile 可能返回 bytes 或 PIL Image
            if isinstance(tile_data, bytes):
                return tile_data
            else:
                # PIL Image
                img = tile_data.convert("RGB")
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=85)
                return buffer.getvalue()

        except HTTPException:
            raise
        except Exception as e:
            log.error(
                f"获取瓦片失败: slide={slide_id}, level={level}, x={x}, y={y}, 错误: {e}"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"获取瓦片失败: {str(e)}",
            )

    @classmethod
    def get_thumbnail(cls, slide_id: str, max_size: int = 256) -> bytes:
        """获取切片缩略图。

        Args:
            slide_id: 切片 ID
            max_size: 最大尺寸（像素）

        Returns:
            PNG 格式的缩略图数据
        """
        cls._check_dependency()
        slide = cls._get_slide(slide_id)

        try:
            thumb_data, mime = slide.getThumbnail(
                width=max_size,
                height=max_size,
                encoding="PNG",
            )
            return thumb_data
        except Exception as e:
            log.error(f"获取缩略图失败: slide={slide_id}, 错误: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"获取缩略图失败: {str(e)}",
            )

    @classmethod
    def get_associated_image(
        cls, slide_id: str, image_name: str
    ) -> tuple[bytes, str]:
        """获取关联图像（label/macro 等）。

        Args:
            slide_id: 切片 ID
            image_name: 图像名称（label、macro）

        Returns:
            (图像数据, mime_type)
        """
        cls._check_dependency()
        slide = cls._get_slide(slide_id)

        try:
            # large_image 的 getAssociatedImage 返回 (data, mime)
            result = slide.getAssociatedImage(image_name, encoding="JPEG")
            if result is None:
                # 获取可用的关联图像列表
                available = slide.getAssociatedImagesList()
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"关联图像 '{image_name}' 不存在，可用: {available}",
                )
            img_data, mime = result
            return img_data, mime or "image/jpeg"
        except HTTPException:
            raise
        except Exception as e:
            log.error(
                f"获取关联图像失败: slide={slide_id}, name={image_name}, 错误: {e}"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"获取关联图像失败: {str(e)}",
            )

    @classmethod
    def list_available_slides(cls) -> list[str]:
        """列出已缓存的切片 ID。"""
        return list(cls._slides.keys())

    @classmethod
    def clear_cache(cls) -> None:
        """清理所有缓存。"""
        for slide_id, slide in cls._slides.items():
            try:
                if hasattr(slide, "close"):
                    slide.close()
            except Exception:
                pass
        cls._slides.clear()
        cls._slide_paths.clear()
        log.info("SVS 缓存已清理")
