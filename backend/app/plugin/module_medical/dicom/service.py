"""DICOM 影像模块 service。

走 repository 的内存索引器，提供 Study/Series/Instance 三级只读查询，
以及按 SOPInstanceUID 取原始 .dcm 文件路径（供文件流接口）。

性能：以下方法均为同步实现（FastAPI 默认在线程池中运行同步 callable，
避免在事件循环上阻塞文件 I/O 与 pydicom 解析）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import status

from app.config.setting import settings
from app.core.exceptions import CustomException
from app.core.logger import log

from .repository import indexer


class DicomService:
    """DICOM 影像只读服务。"""

    @classmethod
    def list_studies_service(cls) -> list[dict[str, Any]]:
        """列出所有 Study。"""
        try:
            return indexer.list_studies()
        except CustomException:
            raise
        except OSError as e:
            log.error("扫描 DICOM Study 列表失败: %s", e)
            raise CustomException(msg="读取 DICOM 数据失败")

    @classmethod
    def list_series_service(cls, study_id: str) -> list[dict[str, Any]]:
        """某 Study 下所有 Series。"""
        try:
            return indexer.list_series(study_id)
        except CustomException:
            raise
        except OSError as e:
            log.error("读取 Study %s 序列失败: %s", study_id, e)
            raise CustomException(msg="读取序列失败")

    @classmethod
    def list_instances_service(cls, series_uid: str) -> list[dict[str, Any]]:
        """某 Series 所有切片（已排序）。"""
        try:
            instances = indexer.list_instances(series_uid)
        except CustomException:
            raise
        except OSError as e:
            log.error("读取序列 %s 切片失败: %s", series_uid, e)
            raise CustomException(msg="读取切片失败")
        if not instances:
            raise CustomException(
                msg="序列不存在或无可用切片",
                code=status.HTTP_404_NOT_FOUND,
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return instances

    @classmethod
    def get_instance_path_service(cls, sop_uid: str) -> Path:
        """按 SOPInstanceUID 取原始 .dcm 文件路径。"""
        path = indexer.get_instance_path(sop_uid)
        if path is None:
            raise CustomException(
                msg="切片不存在或 SOPInstanceUID 无效",
                code=status.HTTP_404_NOT_FOUND,
                status_code=status.HTTP_404_NOT_FOUND,
            )
        # 防御性：即使索引本身已校验过，再确认最终路径仍在数据根目录内。
        try:
            root = Path(settings.DICOM_DATA_DIR).resolve()
            if not path.resolve(strict=False).is_relative_to(root):
                raise CustomException(
                    msg="切片路径非法",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
        except OSError as e:
            log.error("解析 DICOM 路径失败: %s", e)
            raise CustomException(
                msg="切片不可访问",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return path
