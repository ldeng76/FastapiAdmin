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

from .mapping_service import MappingRuleService
from .service import HospitalService
from .schema import (
    HospitalCreate,
    HospitalDataSummaryOut,
    HospitalOut,
    HospitalUpdate,
    MappingRuleBatch,
    MappingRuleOut,
    MappingTemplateDetailOut,
    TemplateOut,
    EtlImportResponse,
    EtlImportStatus,
    Etl1RunRequest,
    Etl1RunResponse,
    Etl1Status,
)
from .etl_service import EtlService
from .etl1.service import Etl1Service

HospitalRouter = APIRouter(route_class=OperationLogRoute, tags=["医院管理"])


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


@HospitalRouter.get(
    "/hospital/{hospital_id}/mappings",
    summary="查看医院映射规则",
    description="返回指定医院的全部字段映射规则",
    response_model=ResponseSchema[list[MappingRuleOut]],
)
async def list_mappings_controller(
    hospital_id: Annotated[int, Path(description="医院ID")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["hospital:mapping:query"]))],
) -> JSONResponse:
    """查看医院映射规则。"""
    result = await MappingRuleService.list_service(auth=auth, hospital_id=hospital_id)
    return SuccessResponse(data=result, msg="获取映射规则成功")


@HospitalRouter.put(
    "/hospital/{hospital_id}/mappings",
    summary="全量替换医院映射规则",
    description="全量替换该医院的映射规则集（先删除旧规则，再批量插入新规则）",
    response_model=ResponseSchema[list[MappingRuleOut]],
)
async def replace_mappings_controller(
    hospital_id: Annotated[int, Path(description="医院ID")],
    data: MappingRuleBatch,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["hospital:mapping:edit"]))],
) -> JSONResponse:
    """全量替换医院映射规则。"""
    result = await MappingRuleService.replace_service(
        auth=auth, hospital_id=hospital_id, data=data
    )
    return SuccessResponse(data=result, msg="替换映射规则成功")


@HospitalRouter.post(
    "/hospital/{hospital_id}/mappings/apply-template",
    summary="应用映射模板到医院",
    description="将指定模板的规则全量替换到该医院（覆盖现有规则）",
    response_model=ResponseSchema[list[MappingRuleOut]],
)
async def apply_template_controller(
    hospital_id: Annotated[int, Path(description="医院ID")],
    template_code: Annotated[str, Query(description="模板编码（如 zhujiang_xinqiao）")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["hospital:mapping:edit"]))],
) -> JSONResponse:
    """应用映射模板到医院。"""
    result = await MappingRuleService.apply_template_service(
        auth=auth, hospital_id=hospital_id, template_code=template_code
    )
    return SuccessResponse(data=result, msg="应用模板成功")


# =========================================================================== #
# M2：映射模板查看
# =========================================================================== #


@HospitalRouter.get(
    "/mapping-templates",
    summary="映射模板列表",
    description="列出所有可用的预置映射模板（不含规则详情）",
    response_model=ResponseSchema[list[TemplateOut]],
)
async def list_templates_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["hospital:mapping:query"]))],
) -> JSONResponse:
    """映射模板列表。"""
    result = await MappingRuleService.list_templates_service(auth=auth)
    return SuccessResponse(data=result, msg="获取模板列表成功")


@HospitalRouter.get(
    "/mapping-templates/{template_code}",
    summary="映射模板详情",
    description="查看指定模板的完整规则列表",
    response_model=ResponseSchema[MappingTemplateDetailOut],
)
async def get_template_controller(
    template_code: Annotated[str, Path(description="模板编码")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["hospital:mapping:query"]))],
) -> JSONResponse:
    """映射模板详情。"""
    result = await MappingRuleService.get_template_service(
        auth=auth, template_code=template_code
    )
    return SuccessResponse(data=result, msg="获取模板详情成功")


# =========================================================================== #
# M3：ETL 导入
# =========================================================================== #


@HospitalRouter.post(
    "/hospital/{hospital_id}/import",
    summary="触发 ETL 数据导入",
    description="按映射规则将医院 data_dir 下的 parquet 导入 PostgreSQL；后台异步执行",
    response_model=ResponseSchema[EtlImportResponse],
)
async def trigger_import_controller(
    hospital_id: Annotated[int, Path(description="医院ID")],
    redis: Annotated[Redis, Depends(redis_getter)],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["hospital:import"]))],
) -> JSONResponse:
    """触发 ETL 导入。"""
    result = await EtlService.trigger_import_service(
        auth=auth, hospital_id=hospital_id, redis=redis
    )
    return SuccessResponse(data=result, msg="导入任务已触发")


@HospitalRouter.get(
    "/hospital/{hospital_id}/import/status",
    summary="查询 ETL 导入状态",
    description="查询医院最近一次 ETL 导入任务的状态（pending/running/completed/failed）",
    response_model=ResponseSchema[EtlImportStatus],
)
async def get_import_status_controller(
    hospital_id: Annotated[int, Path(description="医院ID")],
    redis: Annotated[Redis, Depends(redis_getter)],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["hospital:query"]))],
) -> JSONResponse:
    """查询 ETL 导入状态。"""
    result = await EtlService.get_import_status_service(
        hospital_id=hospital_id, redis=redis
    )
    return SuccessResponse(data=result, msg="获取导入状态成功")


# =========================================================================== #
# M3b：ETL-1 (Excel → Parquet) — 多医院源数据落地
# =========================================================================== #
# 触发: 上传医院原始 Excel (含中文长字段名、inline string cell),
#       按 center config 转换为标准 snake_case 英文字段的 parquet,
#       输出到 data/<center>/*.parquet, 供 ETL-2 后续导入 PG。
# 不依赖 mapping rule (用 center config, 配置在 centers/<code>.py)。


@HospitalRouter.post(
    "/hospital/{hospital_id}/etl1/run",
    summary="触发 ETL-1: Excel → Parquet",
    description=(
        "按 center config 把医院原始 Excel 转换为标准 parquet。"
        "后台异步执行, 立即返回 job_id 供轮询。"
        "触发条件: 医院已注册 (任何 lifecycle_status 都可跑); 不依赖 mapping rule。"
    ),
    response_model=ResponseSchema[Etl1RunResponse],
)
async def trigger_etl1_controller(
    hospital_id: Annotated[int, Path(description="医院ID")],
    body: Etl1RunRequest,
    redis: Annotated[Redis, Depends(redis_getter)],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["hospital:import"]))],
) -> JSONResponse:
    """触发 ETL-1 (Excel → Parquet)。"""
    result = await Etl1Service.trigger_run_service(
        auth=auth,
        hospital_id=hospital_id,
        xlsx_path=body.xlsx_path,
        center_code=body.center_code,
        only_tables=body.only_tables,
        dry_run=body.dry_run,
        redis=redis,
    )
    return SuccessResponse(data=result, msg="ETL-1 任务已触发")


@HospitalRouter.get(
    "/hospital/{hospital_id}/etl1/status",
    summary="查询 ETL-1 任务状态",
    description="查询医院最近一次 ETL-1 任务的状态 (pending/running/completed/failed) + 进度",
    response_model=ResponseSchema[Etl1Status],
)
async def get_etl1_status_controller(
    hospital_id: Annotated[int, Path(description="医院ID")],
    redis: Annotated[Redis, Depends(redis_getter)],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["hospital:query"]))],
) -> JSONResponse:
    """查询 ETL-1 任务状态。"""
    result = await Etl1Service.get_run_status_service(
        hospital_id=hospital_id, redis=redis
    )
    return SuccessResponse(data=result, msg="获取 ETL-1 状态成功")


# =========================================================================== #
# M5：上下线 + 就绪状态机
# =========================================================================== #


@HospitalRouter.get(
    "/hospital/{hospital_id}/data-summary",
    summary="医院数据摘要",
    description="查询医院各业务表的行数，供上线前校验",
    response_model=ResponseSchema[HospitalDataSummaryOut],
)
async def get_data_summary_controller(
    hospital_id: Annotated[int, Path(description="医院ID")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["hospital:query"]))],
) -> JSONResponse:
    """医院数据摘要。"""
    result = await HospitalService.get_data_summary_service(
        auth=auth, id=hospital_id
    )
    return SuccessResponse(data=result, msg="获取数据摘要成功")


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
