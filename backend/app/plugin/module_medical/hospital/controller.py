"""医院管理 controller（自动发现挂到 /medical/hospital）。

M1：注册、列表、详情、更新。
M2：映射规则 CRUD（全量替换）+ 映射模板查看/应用。
M3：ETL 导入 + 数据查询（DuckDB → PostgreSQL）。
M5：上下线 + 就绪状态机推进（live ↔ data_imported）。

路由前缀说明：
- 容器前缀由顶级目录名自动生成为 /medical（module_medical 去 module_ 前缀）。
- 本文件位于 module_medical/hospital/ 子目录，仍挂到 /medical，故路由为 /medical/hospital/...
- 这里不设 prefix，路径全写在路由装饰器上，避免叠加。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse
from redis.asyncio.client import Redis

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ResponseSchema, SuccessResponse
from app.core.base_params import PaginationQueryParam
from app.core.dependencies import AuthPermission, redis_getter
from app.core.router_class import OperationLogRoute

from .anon_etl_http_service import AnonEtlService
from .patient_controller import PatientRouter
from .service import HospitalService
from .schema import (
    HospitalCreate,
    HospitalOut,
    HospitalUpdate,
    AnonImportTriggerRequest,
    AnonImportStatus,
    AnonDataSummaryOut,
)
from .stats_controller import StatsRouter

HospitalRouter = APIRouter(route_class=OperationLogRoute, tags=["医院管理"])

# 将统计数据路由挂载到医院路由上（共享 /medical 前缀）
HospitalRouter.include_router(StatsRouter)
HospitalRouter.include_router(PatientRouter)


@HospitalRouter.post(
    "/hospital",
    summary="注册医院",
    description="注册新医院，自动创建对应租户、初始管理员、配额",
    response_model=ResponseSchema[HospitalOut],
)
async def create_hospital_controller(
    data: HospitalCreate,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["hospital:create"]))],
) -> JSONResponse:
    """注册医院。"""
    result = await HospitalService.create_service(auth=auth, data=data)
    return SuccessResponse(data=result, msg="注册医院成功")


# 注意：GET /hospital 必须定义在 GET /hospital/{id} 之前，否则 "list" 会被误匹配为 {id}
@HospitalRouter.get(
    "/hospital",
    summary="医院分页列表",
    description="查询医院列表，支持名称/编码/就绪状态筛选",
    response_model=ResponseSchema[dict],
)
async def get_hospital_page_controller(
    page: Annotated[PaginationQueryParam, Depends()],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["hospital:query"]))],
    name: Annotated[str | None, Query(description="医院名称（模糊）")] = None,
    code: Annotated[str | None, Query(description="医院编码（模糊）")] = None,
    lifecycle_status: Annotated[
        str | None,
        Query(description="就绪状态(registered/mapping_configured/data_imported/live)"),
    ] = None,
    status: Annotated[str | None, Query(description="启用状态(0:正常 1:禁用)")] = None,
) -> JSONResponse:
    """医院分页列表。"""
    order_by = [{"id": "asc"}]
    if page.order_by:
        order_by = page.order_by
    search: dict[str, tuple[str, str]] = {}
    if name:
        search["name"] = ("like", name)
    if code:
        search["code"] = ("like", code)
    if lifecycle_status:
        search["lifecycle_status"] = ("eq", lifecycle_status)
    if status:
        search["status"] = ("eq", status)
    result_dict = await HospitalService.page_service(
        auth=auth,
        page_no=page.page_no if page.page_no is not None else 1,
        page_size=page.page_size if page.page_size is not None else 10,
        order_by=order_by,
        search=search,
    )
    return SuccessResponse(data=result_dict, msg="获取医院列表成功")


@HospitalRouter.get(
    "/hospital/{hospital_id}",
    summary="医院详情",
    description="获取医院详情（含租户关联信息）",
    response_model=ResponseSchema[HospitalOut],
)
async def get_hospital_detail_controller(
    hospital_id: Annotated[int, Path(description="医院ID")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["hospital:query"]))],
) -> JSONResponse:
    """医院详情。"""
    result = await HospitalService.detail_service(auth=auth, id=hospital_id)
    return SuccessResponse(data=result, msg="获取医院详情成功")


@HospitalRouter.put(
    "/hospital/{hospital_id}",
    summary="更新医院信息",
    description="更新医院基本信息（不允许修改编码/租户/就绪状态）",
    response_model=ResponseSchema[HospitalOut],
)
async def update_hospital_controller(
    hospital_id: Annotated[int, Path(description="医院ID")],
    data: HospitalUpdate,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["hospital:edit"]))],
) -> JSONResponse:
    """更新医院信息。"""
    result = await HospitalService.update_service(auth=auth, id=hospital_id, data=data)
    return SuccessResponse(data=result, msg="更新医院信息成功")


# =========================================================================== #
# M2：映射规则管理
# =========================================================================== #


@HospitalRouter.post(
    "/hospital/{hospital_id}/import/anon",
    summary="触发 anon ETL 导入（parquet → lnrs_anon_*）",
    description="按请求体指定 center_codes / data_dir_override 触发异步导入；不依赖 med_mapping_rule。",
    response_model=ResponseSchema[dict],  # {job_id, status}，原 EtlImportResponse 2026-07-24 删除
)
async def trigger_anon_import_controller(
    hospital_id: Annotated[int, Path(description="医院ID")],
    redis: Annotated[Redis, Depends(redis_getter)],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["hospital:import"]))],
    body: AnonImportTriggerRequest | None = None,
) -> JSONResponse:
    """触发 anon ETL 导入。

    请求体（可选）：
    - center_codes: ["shengyi","xinqiao","zhujiang"]；不传=全部 KNOWN_CENTERS
    - data_dir_override: parquet 路径；不传=用 hospital.data_dir
    """
    result = await AnonEtlService.trigger_import_service(
        auth=auth,
        hospital_id=hospital_id,
        redis=redis,
        center_codes=(body.center_codes if body else None),
        data_dir_override=(body.data_dir_override if body else None),
    )
    return SuccessResponse(data=result, msg="anon 导入任务已触发")


@HospitalRouter.get(
    "/hospital/{hospital_id}/import/anon/status",
    summary="查询 anon ETL 导入状态",
    description="查询医院最近一次 anon ETL 导入任务的状态",
    response_model=ResponseSchema[AnonImportStatus],
)
async def get_anon_import_status_controller(
    hospital_id: Annotated[int, Path(description="医院ID")],
    redis: Annotated[Redis, Depends(redis_getter)],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["hospital:query"]))],
) -> JSONResponse:
    """查询 anon ETL 导入状态。"""
    result = await AnonEtlService.get_import_status_service(
        hospital_id=hospital_id, redis=redis
    )
    return SuccessResponse(data=result, msg="获取 anon 导入状态成功")


@HospitalRouter.get(
    "/hospital/{hospital_id}/anon-data-summary",
    summary="获取医院 anon 数据摘要（lnrs_anon_* 各表行数）",
    description="供上线前校验和前端展示使用。数据源：lnrs_anon_* 表（parquet 直入）。",
    response_model=ResponseSchema[AnonDataSummaryOut],
)
async def get_anon_data_summary_controller(
    hospital_id: Annotated[int, Path(description="医院ID")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["hospital:query"]))],
    center_codes: Annotated[list[str] | None, Query(description="限定中心列表")] = None,
) -> JSONResponse:
    """获取医院 anon 数据摘要。"""
    from .service import HospitalService
    result = await HospitalService.get_anon_data_summary_service(
        auth=auth, id=hospital_id, center_codes=center_codes
    )
    return SuccessResponse(data=result, msg="获取 anon 数据摘要成功")


# =========================================================================== #
# M3b：ETL-1 (Excel → Parquet) — 多医院源数据落地
# =========================================================================== #
# 触发: 上传医院原始 Excel (含中文长字段名、inline string cell),
#       按 center config 转换为标准 snake_case 英文字段的 parquet,
#       输出到 data/<center>/*.parquet, 供 ETL-2 后续导入 PG。
# 不依赖 mapping rule (用 center config, 配置在 centers/<code>.py)。


@HospitalRouter.post(
    "/hospital/{hospital_id}/online",
    summary="上线医院",
    description="data_imported → live，需先完成数据导入",
    response_model=ResponseSchema[HospitalOut],
)
async def go_online_controller(
    hospital_id: Annotated[int, Path(description="医院ID")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["hospital:online"]))],
) -> JSONResponse:
    """上线医院。"""
    result = await HospitalService.go_online_service(auth=auth, id=hospital_id)
    return SuccessResponse(data=result, msg="医院上线成功")


@HospitalRouter.post(
    "/hospital/{hospital_id}/offline",
    summary="下线医院",
    description="live → data_imported，下线后可重新编辑映射和导入",
    response_model=ResponseSchema[HospitalOut],
)
async def go_offline_controller(
    hospital_id: Annotated[int, Path(description="医院ID")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["hospital:offline"]))],
) -> JSONResponse:
    """下线医院。"""
    result = await HospitalService.go_offline_service(auth=auth, id=hospital_id)
    return SuccessResponse(data=result, msg="医院下线成功")
