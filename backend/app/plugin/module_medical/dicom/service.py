"""DICOM 影像模块 service。

走 repository 的内存索引器，提供 Study/Series/Instance 三级只读查询，
以及按 SOPInstanceUID 取原始 .dcm 文件路径（供文件流接口）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import status

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.exceptions import CustomException
from app.core.logger import log

from .repository import indexer


class DicomService:
    """DICOM 影像只读服务。"""

    @classmethod
    async def list_studies_service(cls, auth: AuthSchema) -> list[dict[str, Any]]:
        """列出所有 Study。"""
        try:
            return indexer.list_studies()
        except Exception as e:
            log.error(f"扫描 DICOM Study 列表失败: {e!s}")
            raise CustomException(msg=f"读取 DICOM 数据失败: {e!s}")

    @classmethod
    async def list_series_service(
        cls, auth: AuthSchema, study_id: str
    ) -> list[dict[str, Any]]:
        """某 Study 下所有 Series。"""
        try:
            return indexer.list_series(study_id)
        except CustomException:
            raise
        except Exception as e:
            log.error(f"读取 Study {study_id} 序列失败: {e!s}")
            raise CustomException(msg=f"读取序列失败: {e!s}")

    @classmethod
    async def list_instances_service(
        cls, auth: AuthSchema, series_uid: str
    ) -> list[dict[str, Any]]:
        """某 Series 所有切片（已排序）。"""
        try:
            instances = indexer.list_instances(series_uid)
        except Exception as e:
            log.error(f"读取序列 {series_uid} 切片失败: {e!s}")
            raise CustomException(msg=f"读取切片失败: {e!s}")
        if not instances:
            raise CustomException(msg="序列不存在或无可用切片")
        return instances

    @classmethod
    async def get_instance_path_service(
        cls, auth: AuthSchema, sop_uid: str
    ) -> Path:
        """按 SOPInstanceUID 取原始 .dcm 文件路径。"""
        path = indexer.get_instance_path(sop_uid)
        if path is None:
            raise CustomException(
                msg="切片不存在或 SOPInstanceUID 无效",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return path
