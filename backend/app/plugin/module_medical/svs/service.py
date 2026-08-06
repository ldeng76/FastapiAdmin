"""SVS 切片服务层（基于 OpenSlide）。

提供 SVS/SLD/NDPI 等切片文件的读取和瓦片服务，
供 OpenSeadragon 等前端查看器使用。
"""

from __future__ import annotations

import io
import hashlib
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from app.core.logger import log

# 可选依赖：OpenSlide
try:
    import openslide
    HAS_OPenslide = True
except ImportError:
    HAS_OPenslide = False
    log.warning("openslide-python 未安装，SVS 功能不可用。请执行: pip install openslide-python")


class SVSService:
    """SVS 切片服务。"""

    # Slide 缓存（key: slide_id, value: openslide.OpenSlide）
    _slides: dict[str, Any] = {}

    @classmethod
    def _check_dependency(cls) -> None:
        """检查 OpenSlide 依赖是否可用。"""
        if not HAS_OPenslide:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="服务器缺少 openslide-python 依赖，请执行: pip install openslide-python",
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

        # 如果已缓存，直接返回
        if slide_id in cls._slides:
            return cls._get_slide_info(slide_id, path)

        try:
            slide = openslide.open_slide(str(path))
            cls._slides[slide_id] = slide
            log.info(f"打开 SVS 文件: {path}, ID: {slide_id}")
        except Exception as e:
            log.error(f"打开 SVS 文件失败: {path}, 错误: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无法打开切片文件: {str(e)}",
            )

        return cls._get_slide_info(slide_id, path)

    @classmethod
    def _get_slide_info(cls, slide_id: str, path: Path) -> dict[str, Any]:
        """获取切片元信息。"""
        slide = cls._slides.get(slide_id)
        if slide is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Slide 未打开",
            )

        try:
            width, height = slide.dimensions
            level_count = slide.level_count
            level_downsamples = list(slide.level_downsamples)

            # 获取关键属性
            props = slide.properties
            properties = {
                "mpp_x": float(props.get("openslide.mpp-x", 0)) if props.get("openslide.mpp-x") else None,
                "mpp_y": float(props.get("openslide.mpp-y", 0)) if props.get("openslide.mpp-y") else None,
                "vendor": props.get("openslide.vendor"),
                "quickhash": props.get("openslide.quickhash-1"),
                "hash": props.get("openslide.hash"),
                "comment": props.get("openslide.comment"),
                "objective": props.get("openslide.objective-power"),
                "source_md5": props.get("openslide.source-md5"),
            }

            return {
                "slide_id": slide_id,
                "file_path": str(path),
                "width": width,
                "height": height,
                "level_count": level_count,
                "level_downsamples": level_downsamples,
                "level_dimensions": [
                    list(slide.level_dimensions[i]) for i in range(level_count)
                ],
                "properties": properties,
            }
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
        tile_size: int = 256,
    ) -> bytes:
        """获取指定瓦片。

        Args:
            slide_id: 切片 ID
            level: 层级（0 为最高分辨率）
            x: 瓦片 X 坐标
            y: 瓦片 Y 坐标
            tile_size: 瓦片大小（像素）

        Returns:
            JPEG 格式的瓦片数据
        """
        cls._check_dependency()
        slide = cls._slides.get(slide_id)
        if slide is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Slide 未找到: {slide_id}",
            )

        try:
            # 计算实际的图像坐标
            downsample = slide.level_downsamples[level]
            x_abs = int(x * tile_size * downsample)
            y_abs = int(y * tile_size * downsample)

            # 读取瓦片
            region = slide.read_region(
                (x_abs, y_abs),
                level,
                (tile_size, tile_size),
            )

            # 转为 JPEG
            img = region.convert("RGB")
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            return buffer.getvalue()

        except IndexError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Level {level} 不存在",
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
        slide = cls._slides.get(slide_id)
        if slide is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Slide 未找到: {slide_id}",
            )

        try:
            # 使用 OpenSlide 内置的缩略图方法
            thumb = slide.get_thumbnail((max_size, max_size))
            buffer = io.BytesIO()
            thumb.save(buffer, format="PNG")
            return buffer.getvalue()
        except Exception as e:
            log.error(f"获取缩略图失败: slide={slide_id}, 错误: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"获取缩略图失败: {str(e)}",
            )

    @classmethod
    def close_slide(cls, slide_id: str) -> None:
        """关闭切片并释放资源。"""
        slide = cls._slides.pop(slide_id, None)
        if slide is not None:
            try:
                slide.close()
                log.info(f"关闭 SVS 文件: {slide_id}")
            except Exception as e:
                log.warning(f"关闭切片失败: {slide_id}, 错误: {e}")

    @classmethod
    def list_available_slides(cls) -> list[str]:
        """列出已缓存的切片 ID。"""
        return list(cls._slides.keys())

    @classmethod
    def clear_cache(cls) -> None:
        """清理所有缓存。"""
        for slide_id in list(cls._slides.keys()):
            cls.close_slide(slide_id)
        log.info("SVS 缓存已清理")