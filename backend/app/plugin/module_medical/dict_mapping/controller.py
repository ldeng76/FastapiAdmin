"""医疗字典值映射 — API 控制器。

自动发现挂载到 /medical/dict-mapping/*。
"""

from typing import Annotated, Optional

from fastapi import APIRouter, Body, Depends, Path
from fastapi.responses import JSONResponse
from redis.asyncio.client import Redis

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ResponseSchema, SuccessResponse
from app.core.base_params import PaginationQueryParam
from app.core.dependencies import AuthPermission, redis_getter
from app.core.logger import log
from app.core.router_class import OperationLogRoute

from .schema import (
    BackfillIn,
    DictMappingBatchSchema,
    DictMappingCreateSchema,
    DictMappingOutSchema,
    DictMappingQueryParam,
    DictMappingUpdateSchema,
    DictUnmatchedOutSchema,
    DictUnmatchedQueryParam,
    NormalizeBatchIn,
    NormalizeIn,
    UnmatchedResolveSchema,
)
from .service import DictMappingService

DictMappingRouter = APIRouter(
    route_class=OperationLogRoute, tags=["医疗字典映射"],
)


# ------------------------------------------------------------------
# 映射规则 CRUD
# ------------------------------------------------------------------


@DictMappingRouter.get(
    "/mapping/list",
    summary="查询映射规则",
    response_model=ResponseSchema[list[DictMappingOutSchema]],
)
async def list_mapping_controller(
    page: Annotated[PaginationQueryParam, Depends()],
    search: Annotated[DictMappingQueryParam, Depends()],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:dict_mapping:query"]))],
) -> JSONResponse:
    """查询映射规则（必须在 {id} 路由之前声明）。"""
    items = await DictMappingService.list_service(
        auth=auth,
        hospital_id=search.hospital_id[1] if search.hospital_id else None,
        dict_type_id=search.dict_type_id[1] if search.dict_type_id else None,
        raw_label=search.raw_label[1] if search.raw_label else None,
    )
    return SuccessResponse(data=items, msg="查询映射规则成功")


@DictMappingRouter.get(
    "/mapping/detail/{id}",
    summary="获取映射规则详情",
    response_model=ResponseSchema[DictMappingOutSchema],
)
async def get_mapping_detail_controller(
    id: Annotated[int, Path(description="映射规则ID", ge=1)],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:dict_mapping:query"]))],
) -> JSONResponse:
    """获取映射规则详情。"""
    result = await DictMappingService.get_detail_service(auth=auth, id=id)
    return SuccessResponse(data=result, msg="获取映射规则详情成功")


@DictMappingRouter.post(
    "/mapping/create",
    summary="创建映射规则",
    response_model=ResponseSchema[DictMappingOutSchema],
)
async def create_mapping_controller(
    data: DictMappingCreateSchema,
    redis: Annotated[Redis, Depends(redis_getter)],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:dict_mapping:create"]))],
) -> JSONResponse:
    """创建映射规则。"""
    result = await DictMappingService.create_service(auth=auth, redis=redis, data=data)
    log.info(f"创建映射规则成功: {result}")
    return SuccessResponse(data=result, msg="创建映射规则成功")


@DictMappingRouter.put(
    "/mapping/update/{id}",
    summary="修改映射规则",
    response_model=ResponseSchema[DictMappingOutSchema],
)
async def update_mapping_controller(
    data: DictMappingUpdateSchema,
    redis: Annotated[Redis, Depends(redis_getter)],
    id: Annotated[int, Path(description="映射规则ID", ge=1)],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:dict_mapping:update"]))],
) -> JSONResponse:
    """修改映射规则。"""
    result = await DictMappingService.update_service(auth=auth, redis=redis, id=id, data=data)
    log.info(f"修改映射规则成功: {result}")
    return SuccessResponse(data=result, msg="修改映射规则成功")


@DictMappingRouter.delete(
    "/mapping/delete",
    summary="删除映射规则",
    response_model=ResponseSchema[None],
)
async def delete_mapping_controller(
    redis: Annotated[Redis, Depends(redis_getter)],
    ids: Annotated[list[int], Body(description="ID列表")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:dict_mapping:delete"]))],
) -> JSONResponse:
    """删除映射规则。"""
    await DictMappingService.delete_service(auth=auth, redis=redis, ids=ids)
    log.info(f"删除映射规则成功: {ids}")
    return SuccessResponse(msg="删除映射规则成功")


@DictMappingRouter.post(
    "/mapping/batch",
    summary="批量创建映射规则",
    response_model=ResponseSchema[list[DictMappingOutSchema]],
)
async def batch_create_mapping_controller(
    data: DictMappingBatchSchema,
    redis: Annotated[Redis, Depends(redis_getter)],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:dict_mapping:create"]))],
) -> JSONResponse:
    """批量创建映射规则（全量替换模式）。"""
    results = await DictMappingService.batch_create_service(
        auth=auth, redis=redis, items=data.items
    )
    log.info(f"批量创建映射规则成功: {len(results)} 条")
    return SuccessResponse(data=results, msg="批量创建映射规则成功")


# ------------------------------------------------------------------
# 运行时归一化
# ------------------------------------------------------------------


@DictMappingRouter.post(
    "/normalize",
    summary="单值归一化",
    response_model=ResponseSchema[dict],
)
async def normalize_controller(
    data: NormalizeIn,
    redis: Annotated[Optional[Redis], Depends(redis_getter)],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:dict_mapping:query"]))],
) -> JSONResponse:
    """单值归一化：医院原始标签 → 标准字典值。"""
    result = await DictMappingService.normalize_service(auth=auth, redis=redis, data=data)
    return SuccessResponse(data=result.model_dump(), msg="归一化成功")


@DictMappingRouter.post(
    "/normalize/batch",
    summary="批量归一化",
    response_model=ResponseSchema[list[dict]],
)
async def normalize_batch_controller(
    data: NormalizeBatchIn,
    redis: Annotated[Optional[Redis], Depends(redis_getter)],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:dict_mapping:query"]))],
) -> JSONResponse:
    """批量归一化。"""
    results = await DictMappingService.normalize_batch_service(
        auth=auth, redis=redis, data=data
    )
    return SuccessResponse(
        data=[r.model_dump() for r in results], msg="批量归一化成功"
    )


# ------------------------------------------------------------------
# 未匹配记录
# ------------------------------------------------------------------


@DictMappingRouter.get(
    "/unmatched/list",
    summary="查询未匹配记录",
    response_model=ResponseSchema[list[DictUnmatchedOutSchema]],
)
async def list_unmatched_controller(
    search: Annotated[DictUnmatchedQueryParam, Depends()],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:dict_mapping:query"]))],
) -> JSONResponse:
    """查询未匹配记录。"""
    items = await DictMappingService.list_unmatched_service(
        auth=auth,
        hospital_id=search.hospital_id[1] if search.hospital_id else None,
        dict_type_id=search.dict_type_id[1] if search.dict_type_id else None,
    )
    return SuccessResponse(data=items, msg="查询未匹配记录成功")


@DictMappingRouter.post(
    "/unmatched/resolve/{id}",
    summary="解决未匹配记录",
    response_model=ResponseSchema[None],
)
async def resolve_unmatched_controller(
    id: Annotated[int, Path(description="未匹配记录ID", ge=1)],
    data: UnmatchedResolveSchema,
    redis: Annotated[Redis, Depends(redis_getter)],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:dict_mapping:update"]))],
) -> JSONResponse:
    """解决未匹配记录（关联映射或标记忽略）。"""
    await DictMappingService.resolve_unmatched_service(
        auth=auth, redis=redis, unmatched_id=id, mapping_id=data.mapping_id
    )
    return SuccessResponse(msg="处理未匹配记录成功")


# ------------------------------------------------------------------
# 缓存管理
# ------------------------------------------------------------------


@DictMappingRouter.post(
    "/cache/refresh",
    summary="刷新映射缓存",
    response_model=ResponseSchema[None],
)
async def refresh_cache_controller(
    dict_type_id: Annotated[int, Body(description="字典类型ID", ge=1)],
    redis: Annotated[Redis, Depends(redis_getter)],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:dict_mapping:update"]))],
) -> JSONResponse:
    """手动刷新某类型的 Redis 映射缓存。"""
    await DictMappingService.refresh_cache_service(
        auth=auth, redis=redis, dict_type_id=dict_type_id
    )
    return SuccessResponse(msg="刷新缓存成功")


# ------------------------------------------------------------------
# Backfill（骨架）
# ------------------------------------------------------------------


@DictMappingRouter.post(
    "/backfill",
    summary="回填历史数据（骨架）",
    response_model=ResponseSchema[dict],
)
async def backfill_controller(
    data: BackfillIn,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_medical:dict_mapping:update"]))],
) -> JSONResponse:
    """回填历史数据（完整实现留待后续）。"""
    # 骨架：仅返回参数，不做实际操作
    return SuccessResponse(
        data={"status": "not_implemented", "params": data.model_dump()},
        msg="回填功能待实现",
    )
