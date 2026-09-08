"""患者多模态 controller（自动发现挂到 /medical）。

为患者列表/详情页提供只读 API：
- `/centers`        — 枚举中心（前端下拉）
- `/patients`       — 患者分页列表
- `/patients/{id}`  — 患者多模态详情（临床/基因/病理/影像 4 模态）

注意：/patients 必须在 /patients/{patient_id} 之前声明，
否则 FastAPI 会把 "list" 误匹配为 patient_id。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ResponseSchema, SuccessResponse
from app.core.base_params import PaginationQueryParam
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .patient_service import PatientService
from .stats_schema import StatsFiltersIn


PatientRouter = APIRouter(route_class=OperationLogRoute, tags=["患者多模态"])

# 允许排序的字段白名单（对应 AnonPatientModel 的 ORM 属性名，防止注入任意列）
ALLOWED_SORT_FIELDS = {
    "patient_id", "birth_date", "sex",
    "abo_blood_type", "rh_blood_type","bmi",
    "smoking_status", "first_nodule_date",
    "latest_lung_rads"
}
# 允许的排序方式
ALLOWED_SORT_ORDERS = {"asc", "desc"}


def _normalize_order_by(raw: list[dict[str, str]] | None) -> list[dict[str, str]] | None:
    """把 PaginationQueryParam 传入的 order_by 过滤到白名单内。

    非法字段/方向会被静默跳过；过滤后为空时返回 None，由 query 层走默认排序
    (center_code asc, patient_id asc)，避免 PaginationQueryParam 的兜底
    updated_time 字段报错。
    """
    if not raw:
        return None
    result: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        for field, direction in item.items():
            if field not in ALLOWED_SORT_FIELDS:
                continue
            direction = str(direction).lower()
            if direction not in ALLOWED_SORT_ORDERS:
                continue
            result.append({field: direction})
    return result or None


@PatientRouter.get(
    "/patients",
    summary="患者分页列表",
    description=(
        "筛选条件与 /statistics/overview 完全一致（共用 StatsFiltersIn）："
        "sex / modality / age_bucket / abo_blood_type / "
        "rh_blood_type / smoking_status / bmi_bucket / patient_id / "
        "is_placeholders / latest_lung_rads；"
        "通过 order_by 控制排序，可选字段: patient_id/birth_date/sex/"
        "abo_blood_type/rh_blood_type/smoking_status/first_nodule_date/bmi"
    ),
    response_model=ResponseSchema[dict],
)
async def list_patients_controller(
    page: Annotated[PaginationQueryParam, Depends()],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:patient:query"]))],
    filters: StatsFiltersIn = Depends(),
) -> JSONResponse:
    """患者分页列表（筛选逻辑与仪表板统计概览共用）。

    order_by：JSON 数组格式，如 [{"birth_date":"desc"},{"patient_id":"asc"}]；
    可排序字段 patient_id/birth_date/sex/abo_blood_type/rh_blood_type/
    smoking_status/first_nodule_date/bmi；不传时按 (center_code, patient_id) 升序。
    """
    order_by = _normalize_order_by(page.order_by)
    result = await PatientService.list_patients_service(
        auth=auth,
        filters=filters,
        page=page,
        order_by=order_by,
    )
    return SuccessResponse(data=result, msg="获取患者列表成功")


@PatientRouter.get(
    "/patients/{patient_id}",
    summary="患者多模态详情",
    description=(
        "返回 4 模态详情（临床/基因/病理/影像）；"
        "clinical 数组包含就诊/手术/检验/医嘱/其他检查行,"
        "每行带 _table 折叠面板标签和 _modality 模态标记；"
        "JSONB 字段已就地顶层展开。"
    ),
    response_model=ResponseSchema[dict],
)
async def get_patient_detail_controller(
    patient_id: Annotated[str, Path(description="患者编号 PT_xxxxxxxx")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:patient:query"]))],
    center: Annotated[
        str | None,
        Query(description="中心编码（可选，限定单中心）"),
    ] = None,
) -> JSONResponse:
    """患者多模态详情。"""
    result = await PatientService.get_patient_detail_service(
        auth=auth, patient_id=patient_id, center=center,
    )
    return SuccessResponse(data=result, msg="获取患者详情成功")

# =========================================================================== #
# M3c: 影像研究桥接（2026-08-28 新增）
#  端点：
#    GET /patients/{patient_id}/imaging-studies
#        → 列出该患者的所有影像研究（study-level），前端"查看影像"按钮调用
#    GET /patients/{patient_id}/imaging-studies/{study_uid}/path
#        → 反查某 study 的影像绝对路径（dicom_image_bytes 接口安全校验用）
# =========================================================================== #


@PatientRouter.get(
    "/patients/{patient_id}/imaging-studies",
    summary="患者影像研究列表（study-level）",
    description=(
        "按 patient_id 列出该患者的所有影像研究；"
        "返回元素含 study_id (= dicom_study_uid)、image_path、sop_count、source 等；"
        "前端 DicomViewer 直接消费 study_id 拉 series/instances。"
    ),
    response_model=ResponseSchema[list],
)
async def list_patient_imaging_studies_controller(
    patient_id: Annotated[str, Path(description="患者编号 PT_xxxxxxxx")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:patient:query"]))],
    center: Annotated[
        str | None,
        Query(description="中心编码（可选，限定单中心）"),
    ] = None,
    modality: Annotated[
        str | None,
        Query(description="影像模态过滤：CT / Pathology / ...（可选）"),
    ] = None,
) -> JSONResponse:
    """患者影像研究列表。"""
    result = await PatientService.list_patient_imaging_studies_service(
        auth=auth, patient_id=patient_id, center=center, modality=modality,
    )
    return SuccessResponse(data=result, msg="获取患者影像研究列表成功")


@PatientRouter.get(
    "/patients/{patient_id}/imaging-studies/{study_uid}/path",
    summary="反查某 study 的影像绝对路径",
    description="按 (patient_id, study_uid) 反查 lnrs_anon_imaging_study.image_path；用于 dicom_image_bytes 接口安全校验",
    response_model=ResponseSchema[dict],
)
async def get_patient_imaging_study_path_controller(
    patient_id: Annotated[str, Path(description="患者编号 PT_xxxxxxxx")],
    study_uid: Annotated[str, Path(description="DICOM StudyInstanceUID")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:patient:query"]))],
) -> JSONResponse:
    """反查某 study 的影像绝对路径。"""
    path = await PatientService.get_patient_imaging_study_path_service(
        auth=auth, patient_id=patient_id, dicom_study_uid=study_uid,
    )
    return SuccessResponse(
        data={"image_path": path} if path else {},
        msg="获取影像路径成功" if path else "未找到对应影像",
    )
# =========================================================================== #
# M3-2026-09-03: 孤儿研究桥接
#  端点：
#    GET /patients/{patient_id}/imaging-orphans
#        → 列出该患者的孤儿研究（orphan-level），与 /imaging-studies 平行
#    GET /patients/{patient_id}/imaging-orphans/{study_orphan_id}/path
#        → 反查某 orphan 的影像绝对路径
#    GET /imaging-orphans/{study_orphan_id}
#        → 按业务 ID 全局反查孤儿详情（不依赖 patient_id；主表即中间表的体现）
# =========================================================================== #


@PatientRouter.get(
    "/patients/{patient_id}/imaging-orphans",
    summary="患者孤儿研究列表",
    description=(
        "按 patient_id 列出 lnrs_anon_imaging_orphan 中该患者的孤儿记录；"
        "返回元素含 study_orphan_id (= OR_<12hex>)、image_path、orphan_kind、orphan_status 等。"
    ),
    response_model=ResponseSchema[list],
)
async def list_patient_imaging_orphans_controller(
    patient_id: Annotated[str, Path(description="患者编号 PT_xxxxxxxx")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:patient:query"]))],
    center: Annotated[
        str | None,
        Query(description="中心编码（可选，限定单中心）"),
    ] = None,
    orphan_status: Annotated[
        str | None,
        Query(description="孤儿状态过滤（discovered / reviewed / pending_ingest / ingested / rejected / archived）"),
    ] = None,
) -> JSONResponse:
    """患者孤儿研究列表。"""
    result = await PatientService.list_patient_imaging_orphans_service(
        auth=auth, patient_id=patient_id, center=center, orphan_status=orphan_status,
    )
    return SuccessResponse(data=result, msg="获取患者孤儿列表成功")


@PatientRouter.get(
    "/patients/{patient_id}/imaging-orphans/{study_orphan_id}/path",
    summary="反查孤儿研究绝对路径",
    description="按 (patient_id, study_orphan_id) 反查 lnrs_anon_imaging_orphan.image_path",
    response_model=ResponseSchema[dict],
)
async def get_patient_imaging_orphan_path_controller(
    patient_id: Annotated[str, Path(description="患者编号 PT_xxxxxxxx")],
    study_orphan_id: Annotated[str, Path(description="孤儿编号 OR_<12hex>(48 bit 空间)")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:patient:query"]))],
) -> JSONResponse:
    """反查孤儿研究绝对路径。"""
    path = await PatientService.get_patient_imaging_orphan_path_service(
        auth=auth, patient_id=patient_id, study_orphan_id=study_orphan_id,
    )
    return SuccessResponse(
        data={"image_path": path} if path else {},
        msg="获取孤儿路径成功" if path else "未找到对应孤儿",
    )


@PatientRouter.get(
    "/imaging-orphans/{study_orphan_id}",
    summary="按业务 ID 反查孤儿详情（全局）",
    description=(
        "不依赖 patient_id；按 study_orphan_id 单独反查整行。"
        "study_orphan_id 由 (center_code, rel_path_from_dicom_root) SHA256[:8] 哈希派生。"
        "主表本身即 ID↔磁盘元数据映射表，无需另建映射表。"
    ),
    response_model=ResponseSchema[dict],
)
async def get_imaging_orphan_by_id_controller(
    study_orphan_id: Annotated[str, Path(description="孤儿编号 OR_<12hex>(48 bit 空间)")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:patient:query"]))],
) -> JSONResponse:
    """按业务 ID 全局反查孤儿详情。"""
    result = await PatientService.get_imaging_orphan_by_id_service(
        auth=auth, study_orphan_id=study_orphan_id,
    )
    return SuccessResponse(data=result or {}, msg="获取孤儿详情成功" if result else "未找到该孤儿")
