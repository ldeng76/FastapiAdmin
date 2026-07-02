"""医学数据模块 service。

不走 CRUDBase（数据来自 parquet 文件），直接调用 repository。
分页返回结构与系统约定一致：{page_no, page_size, total, has_next, items}。
"""

from __future__ import annotations

from typing import Any

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.exceptions import CustomException
from app.core.logger import log

from . import repository


class PatientService:
    """患者多模态数据服务。"""

    @classmethod
    async def page_service(
        cls,
        auth: AuthSchema,
        page_no: int = 1,
        page_size: int = 10,
        center: str | None = None,
        keyword: str | None = None,
    ) -> dict[str, Any]:
        """患者分页列表。"""
        offset = (page_no - 1) * page_size
        items, total = repository.list_patients(
            center=center, keyword=keyword, offset=offset, limit=page_size
        )
        return {
            "page_no": page_no,
            "page_size": page_size,
            "total": total,
            "has_next": (offset + page_size) < total,
            "items": items,
        }

    @classmethod
    async def detail_service(
        cls,
        auth: AuthSchema,
        patient_id: str,
        center: str | None = None,
    ) -> dict[str, Any]:
        """患者多模态详情。"""
        try:
            detail = repository.get_patient_detail(patient_id=patient_id, center=center)
        except Exception as e:
            log.error(f"读取患者多模态数据失败 {patient_id}: {e!s}")
            raise CustomException(msg=f"读取数据失败: {e!s}")
        if not detail:
            raise CustomException(msg="患者不存在或无多模态数据")
        return detail
