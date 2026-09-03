"""患者多模态 service 层 — 编排 anon_medical_query，提供给 controller 调用。

数据源：lnrs_anon_* 表（PG）。DuckDB 直读 parquet 路径已于 2026-08-05 废弃。
"""

from __future__ import annotations

from typing import Any

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.base_params import PaginationQueryParam
from app.core.exceptions import CustomException

from .anon_medical_query import (
    anon_get_imaging_orphan_by_id,
    anon_get_imaging_orphan_path,
    anon_get_imaging_study_path,
    anon_get_patient_detail,
    anon_list_centers,
    anon_list_patient_imaging_orphans,
    anon_list_patient_imaging_studies,
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
        keyword: str | None,
        sex: str | None,
        smoking_status: str | None,
        page: PaginationQueryParam,
    ) -> dict[str, Any]:
        """患者分页列表。

        返回结构必须包含 page_no / page_size / has_next，前端 useTable 的
        ``isPageResultPayload`` 与 ``normalizePageResultLike`` 都依赖这三项做响应
        解包校验；任意一项缺失都会被识别为非法分页响应，从而回退为空列表。
        """
        items, total = await anon_list_patients(
            auth.db,
            keyword=keyword,
            sex=sex,
            smoking_status=smoking_status,
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

    @classmethod
    async def list_patient_imaging_studies_service(
        cls,
        auth: AuthSchema,
        patient_id: str,
        center: str | None,
        modality: str | None,
    ) -> list[dict[str, Any]]:
        """患者影像研究列表（study-level）。

        用途：前端"患者详情 → 查看影像"按钮拿到 study 列表，传给
        DicomViewer 拉 series/instances。

        返回元素 schema（与前端 DicomStudy 兼容）：
          - study_id     = dicom_study_uid
          - study_uid    = dicom_study_uid（冗余）
          - modality     = 'CT' / 'Pathology' / ...
          - image_path   = 磁盘绝对路径（前端不展示；后端 DICOMweb 拉字节用）
          - sop_count    = 切片数（仅展示）
          - source       = 数据来源盘标识
          - anon_exam_id = FK（脱敏）；离线灌库为空
          - patient_id   = PT_xxx（脱敏后）
        """
        rows = await anon_list_patient_imaging_studies(
            auth.db,
            patient_id=patient_id,
            center=center,
            modality=modality,
        )
        if not rows:
            # 不抛 404：详情接口本身已存在；返回空数组即可（前端按钮 disabled）
            return []
        return rows

    @classmethod
    async def get_patient_imaging_study_path_service(
        cls,
        auth: AuthSchema,
        patient_id: str,
        dicom_study_uid: str,
    ) -> str | None:
        """按 (patient_id, study_uid) 反查影像绝对路径。

        用于：1) dicom_image_bytes 接口安全校验；2) 调试与审计。
        不抛 404，返回 None。
        """
        return await anon_get_imaging_study_path(
            auth.db,
            patient_id=patient_id,
            dicom_study_uid=dicom_study_uid,
        )
    @classmethod
    async def list_patient_imaging_orphans_service(
        cls,
        auth: AuthSchema,
        patient_id: str,
        center: str | None = None,
        orphan_status: str | None = None,
    ) -> list[dict[str, Any]]:
        """患者孤儿研究列表(2026-09-03 新增)。

        与 list_patient_imaging_studies 平行:列 lnrs_anon_imaging_orphan 而非 imaging_study。
        """
        return await anon_list_patient_imaging_orphans(
            auth.db, patient_id=patient_id, center=center, orphan_status=orphan_status,
        )

    @classmethod
    async def get_patient_imaging_orphan_path_service(
        cls,
        auth: AuthSchema,
        patient_id: str,
        study_orphan_id: str,
    ) -> str | None:
        """按 (patient_id, study_orphan_id) 反查孤儿影像绝对路径。"""
        return await anon_get_imaging_orphan_path(
            auth.db, patient_id=patient_id, study_orphan_id=study_orphan_id,
        )

    @classmethod
    async def get_imaging_orphan_by_id_service(
        cls,
        auth: AuthSchema,
        study_orphan_id: str,
    ) -> dict[str, Any] | None:
        """按 study_orphan_id 全局反查孤儿详情(主表即中间表的体现)。"""
        return await anon_get_imaging_orphan_by_id(
            auth.db, study_orphan_id=study_orphan_id,
        )
