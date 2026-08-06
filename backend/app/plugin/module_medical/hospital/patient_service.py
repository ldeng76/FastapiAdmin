"""患者多模态 service 层 — 编排 anon_medical_query，提供给 controller 调用。

数据源：lnrs_anon_* 表（PG）。DuckDB 直读 parquet 路径已于 2026-08-05 废弃。
"""

from __future__ import annotations

from typing import Any

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.base_params import PaginationQueryParam
from app.core.exceptions import CustomException

from .anon_medical_query import (
    anon_get_patient_detail,
    anon_list_centers,
    anon_list_patients,
)


class PatientService:
    """患者多模态 service。"""

    @classmethod
    async def list_centers_service(cls, auth: AuthSchema) -> list[str]:
        """枚举数据中出现的中心（前端下拉用）。"""
        return await anon_list_centers(auth.db)

    @classmethod
    async def list_patients_service(
        cls,
        auth: AuthSchema,
        center: str | None,
        keyword: str | None,
        page: PaginationQueryParam,
    ) -> dict[str, Any]:
        """患者分页列表。

        返回结构必须包含 page_no / page_size / has_next，前端 useTable 的
        ``isPageResultPayload`` 与 ``normalizePageResultLike`` 都依赖这三项做响应
        解包校验；任意一项缺失都会被识别为非法分页响应，从而回退为空列表。
        """
        items, total = await anon_list_patients(
            auth.db,
            center=center,
            keyword=keyword,
            offset=page.offset,
            limit=page.limit,
        )
        page_size = page.limit or 10
        page_no = (page.offset // page_size) + 1 if page_size else 1
        return {
            "items": items,
            "total": total,
            "page_no": page_no,
            "page_size": page_size,
            "has_next": page.offset + page.limit < total,
        }

    @classmethod
    async def get_patient_detail_service(
        cls,
        auth: AuthSchema,
        patient_id: str,
        center: str | None,
    ) -> dict[str, Any]:
        """患者多模态详情（4 模态 Tab 数据源）。"""
        result = await anon_get_patient_detail(auth.db, patient_id, center)
        if not result:
            raise CustomException(
                msg=f"患者不存在: {patient_id}",
                code=404,
                status_code=404,
            )
        return result
