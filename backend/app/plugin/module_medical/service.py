"""医学数据模块 service。

M4 变更：从 DuckDB 直读 parquet（repository.py）迁移到 PostgreSQL 查询（hospital/medical_query.py）。
API response shape 保持不变，前端无需修改。

分页返回结构与系统约定一致：{page_no, page_size, total, has_next, items}。
"""

from __future__ import annotations

from fastapi import status
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.exceptions import CustomException
from app.core.logger import log

from .hospital.medical_query import get_patient_detail, list_centers, list_patients
from .schema import PatientDetailOut, PatientListOut, PatientPageOut

# 分页上限：防止极端大页撑爆内存 / 把 DB 拖垮
MAX_PAGE_SIZE = 200


class PatientService:
    """患者多模态数据服务。"""

    @classmethod
    async def centers_service(cls, auth: AuthSchema) -> list[str]:
        """来源中心枚举。"""
        return await list_centers(db=auth.db)

    @classmethod
    async def page_service(
        cls,
        auth: AuthSchema,
        page_no: int = 1,
        page_size: int = 10,
        center: str | None = None,
        keyword: str | None = None,
    ) -> PatientPageOut:
        """患者分页列表。"""
        # 入参校验 — 即便非 HTTP 调用方也要防御
        if page_no < 1 or page_size < 1:
            raise CustomException(msg="page_no 和 page_size 必须为正整数")
        page_size = min(page_size, MAX_PAGE_SIZE)
        if keyword is not None:
            keyword = keyword.strip() or None
        if center is not None:
            center = center.strip() or None

        offset = (page_no - 1) * page_size
        items, total = await list_patients(
            db=auth.db,
            center=center,
            keyword=keyword,
            offset=offset,
            limit=page_size,
        )
        return PatientPageOut(
            page_no=page_no,
            page_size=page_size,
            total=total,
            has_next=(offset + page_size) < total,
            items=[PatientListOut(**item) for item in items],
        )

    @classmethod
    async def detail_service(
        cls,
        auth: AuthSchema,
        patient_id: str,
        center: str | None = None,
    ) -> PatientDetailOut:
        """患者多模态详情。"""
        try:
            detail = await get_patient_detail(db=auth.db, patient_id=patient_id, center=center)
        except SQLAlchemyError:
            log.exception("读取患者多模态数据失败 %s", patient_id)
            raise CustomException(msg="读取患者多模态数据失败")
        if not detail:
            raise CustomException(
                msg="患者不存在或无多模态数据",
                code=status.HTTP_404_NOT_FOUND,
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return PatientDetailOut(**detail)
