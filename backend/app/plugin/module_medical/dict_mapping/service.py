"""医疗字典值映射 — 服务层。

核心职责：
- 映射规则的增删改查（参考 mapping_service.py 全量替换模式）
- 运行时归一化 normalize()：查 Redis Hash，命中返回标准值，未匹配写 unmatched
- 缓存刷新：写映射后刷新 Redis Hash
"""

from datetime import datetime
from typing import Any

from redis.asyncio.client import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.constant import PLATFORM_TENANT_ID
from app.common.enums import RedisInitKeyConfig
from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import log
from app.core.redis_crud import RedisCURD

from .crud import DictMappingCRUD, DictUnmatchedCRUD
from .model import DictMappingModel, DictUnmatchedModel
from .schema import (
    DictMappingCreateSchema,
    DictMappingOutSchema,
    DictMappingUpdateSchema,
    NormalizeBatchIn,
    NormalizeIn,
    NormalizeResult,
)


def _cache_key(tenant_id: int, dict_type: str) -> str:
    """Redis Hash key：system_dict_mapping:{tenant_id}:{dict_type}"""
    return f"{RedisInitKeyConfig.SYSTEM_DICT_MAPPING.key}:{tenant_id}:{dict_type}"


class DictMappingService:
    """医疗字典值映射服务。"""

    # ------------------------------------------------------------------
    # 映射规则 CRUD
    # ------------------------------------------------------------------

    @classmethod
    async def list_service(
        cls,
        auth: AuthSchema,
        hospital_id: int | None = None,
        dict_type_id: int | None = None,
        raw_label: str | None = None,
    ) -> list[dict]:
        """列出映射规则。"""
        search: dict[str, Any] = {}
        if hospital_id is not None:
            search["hospital_id"] = hospital_id
        if dict_type_id is not None:
            search["dict_type_id"] = dict_type_id
        if raw_label is not None:
            search["raw_label"] = raw_label

        items = await DictMappingCRUD(auth).list(search=search)
        return [DictMappingOutSchema.model_validate(obj).model_dump() for obj in items]

    @classmethod
    async def get_detail_service(cls, auth: AuthSchema, id: int) -> dict:
        """获取单条映射详情。"""
        obj = await DictMappingCRUD(auth).get(id=id)
        if not obj:
            raise CustomException(msg="映射规则不存在")
        return DictMappingOutSchema.model_validate(obj).model_dump()

    @classmethod
    async def create_service(
        cls, auth: AuthSchema, redis: Redis, data: DictMappingCreateSchema
    ) -> dict:
        """创建映射规则。"""
        # 唯一性检查（大小写归一）
        exist = await DictMappingCRUD(auth).get_by_raw_label(
            hospital_id=data.hospital_id,
            dict_type_id=data.dict_type_id,
            raw_label=data.raw_label,
        )
        if exist:
            raise CustomException(msg="该映射已存在（同一医院同一类型下 raw_label 重复）")

        obj = await DictMappingCRUD(auth).create(data=data)
        result = DictMappingOutSchema.model_validate(obj).model_dump()

        # 刷新缓存（传入 auth.db 以读取已 flush 的未提交行）
        await cls._refresh_cache(redis, auth.user.tenant_id, data.dict_type_id, db=auth.db)
        return result

    @classmethod
    async def update_service(
        cls,
        auth: AuthSchema,
        redis: Redis,
        id: int,
        data: DictMappingUpdateSchema,
    ) -> dict:
        """更新映射规则。"""
        obj = await DictMappingCRUD(auth).get(id=id)
        if not obj:
            raise CustomException(msg="映射规则不存在")

        updated = await DictMappingCRUD(auth).update(id=id, data=data)
        result = DictMappingOutSchema.model_validate(updated).model_dump()

        # 刷新缓存（用更新后对象的 dict_type_id，因为部分更新可能未传该字段）
        await cls._refresh_cache(redis, auth.user.tenant_id, updated.dict_type_id, db=auth.db)
        return result

    @classmethod
    async def delete_service(
        cls, auth: AuthSchema, redis: Redis, ids: list[int]
    ) -> None:
        """删除映射规则。"""
        # 先获取 dict_type_id 用于刷新缓存
        dict_type_ids: set[int] = set()
        for id_ in ids:
            obj = await DictMappingCRUD(auth).get(id=id_)
            if obj:
                dict_type_ids.add(obj.dict_type_id)

        await DictMappingCRUD(auth).delete(ids=ids)

        # 刷新缓存（传入 auth.db 以读取已 flush 的未提交行）
        for dtid in dict_type_ids:
            await cls._refresh_cache(redis, auth.user.tenant_id, dtid, db=auth.db)

    @classmethod
    async def batch_create_service(
        cls,
        auth: AuthSchema,
        redis: Redis,
        items: list[DictMappingCreateSchema],
    ) -> list[dict]:
        """批量创建映射规则（全量替换模式）。"""
        if not items:
            raise CustomException(msg="批量创建列表不能为空")

        # 按 (hospital_id, dict_type_id) 分组
        groups: dict[tuple[int, int], list[DictMappingCreateSchema]] = {}
        for item in items:
            key = (item.hospital_id, item.dict_type_id)
            groups.setdefault(key, []).append(item)

        results = []
        for (hospital_id, dict_type_id), group_items in groups.items():
            # 删除旧映射
            old_items = await DictMappingCRUD(auth).list(
                search={"hospital_id": hospital_id, "dict_type_id": dict_type_id}
            )
            if old_items:
                await DictMappingCRUD(auth).delete(ids=[o.id for o in old_items])

            # 批量新建
            for item in group_items:
                obj = await DictMappingCRUD(auth).create(data=item)
                results.append(DictMappingOutSchema.model_validate(obj).model_dump())

            # 刷新缓存（传入 auth.db 以读取已 flush 的未提交行）
            await cls._refresh_cache(redis, auth.user.tenant_id, dict_type_id, db=auth.db)

        return results

    # ------------------------------------------------------------------
    # 运行时归一化
    # ------------------------------------------------------------------

    @classmethod
    async def normalize_service(
        cls,
        auth: AuthSchema,
        redis: Redis,
        data: NormalizeIn,
    ) -> NormalizeResult:
        """单值归一化：查 Redis Hash，命中返回标准值，未匹配写 unmatched。"""
        from sqlalchemy.ext.asyncio import AsyncSession

        db: AsyncSession = auth.db

        # 先查 dict_type_id
        dict_type_id = await cls._get_dict_type_id(db, data.dict_type)
        if dict_type_id is None:
            return NormalizeResult(raw_label=data.raw_label, matched=False)

        tenant_id = auth.user.tenant_id if auth.user else PLATFORM_TENANT_ID

        # 查缓存
        cached = await cls._lookup_cache(redis, tenant_id, data.dict_type, data.raw_label)
        if cached is not None:
            return NormalizeResult(raw_label=data.raw_label, dict_value=cached, matched=True)

        # 缓存未命中：回源 DB 查映射
        mapping = await DictMappingCRUD(auth).get_by_raw_label(
            hospital_id=data.hospital_id,
            dict_type_id=dict_type_id,
            raw_label=data.raw_label,
        )
        if mapping and mapping.dict_data_id:
            # 查 dict_value
            dict_value = await cls._get_dict_value(db, mapping.dict_data_id)
            if dict_value:
                # 回填缓存
                await cls._set_cache(
                    redis, tenant_id, data.dict_type, data.raw_label, dict_value
                )
                return NormalizeResult(
                    raw_label=data.raw_label, dict_value=dict_value, matched=True
                )

        # 未匹配：写 unmatched（独立 session，不影响请求事务）
        async with async_db_session() as new_db:
            await DictUnmatchedCRUD(auth).upsert_unmatched(
                db=new_db,
                hospital_id=data.hospital_id,
                dict_type_id=dict_type_id,
                raw_label=data.raw_label,
                raw_value=None,
                tenant_id=tenant_id,
            )
            await new_db.commit()

        return NormalizeResult(raw_label=data.raw_label, matched=False)

    @classmethod
    async def normalize_batch_service(
        cls,
        auth: AuthSchema,
        redis: Redis,
        data: NormalizeBatchIn,
    ) -> list[NormalizeResult]:
        """批量归一化。"""
        results = []
        for raw_label in data.raw_labels:
            result = await cls.normalize_service(
                auth=auth,
                redis=redis,
                data=NormalizeIn(
                    hospital_id=data.hospital_id,
                    dict_type=data.dict_type,
                    raw_label=raw_label,
                ),
            )
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # 未匹配记录
    # ------------------------------------------------------------------

    @classmethod
    async def list_unmatched_service(
        cls,
        auth: AuthSchema,
        hospital_id: int | None = None,
        dict_type_id: int | None = None,
    ) -> list[dict]:
        """列出未匹配记录。"""
        search: dict[str, Any] = {}
        if hospital_id is not None:
            search["hospital_id"] = hospital_id
        if dict_type_id is not None:
            search["dict_type_id"] = dict_type_id

        items = await DictUnmatchedCRUD(auth).list(search=search)
        return [_unmatched_to_dict(obj) for obj in items]

    @classmethod
    async def resolve_unmatched_service(
        cls,
        auth: AuthSchema,
        redis: Redis,
        unmatched_id: int,
        mapping_id: int | None = None,
    ) -> None:
        """解决未匹配记录。"""
        obj = await DictUnmatchedCRUD(auth).get(id=unmatched_id)
        if not obj:
            raise CustomException(msg="未匹配记录不存在")

        obj.resolution = "resolve" if mapping_id else "ignore"
        user_id = auth.user.id if auth.user else None
        tenant_id = auth.user.tenant_id if auth.user else PLATFORM_TENANT_ID
        obj.resolved_by = user_id
        obj.resolved_at = datetime.now()
        obj.resolved_as_mapping_id = mapping_id
        obj.status = "2" if mapping_id else "1"
        await auth.db.flush()

        # 如果关联了映射，刷新缓存（传入 auth.db 以读取已 flush 的未提交行）
        if mapping_id:
            await cls._refresh_cache(redis, tenant_id, obj.dict_type_id, db=auth.db)

    # ------------------------------------------------------------------
    # 缓存
    # ------------------------------------------------------------------

    @classmethod
    async def refresh_cache_service(
        cls, auth: AuthSchema, redis: Redis, dict_type_id: int
    ) -> None:
        """手动刷新某类型的 Redis 缓存。"""
        tenant_id = auth.user.tenant_id if auth.user else PLATFORM_TENANT_ID
        await cls._refresh_cache(redis, tenant_id, dict_type_id)

    @classmethod
    async def _refresh_cache(
        cls,
        redis: Redis,
        tenant_id: int,
        dict_type_id: int,
        db: AsyncSession | None = None,
    ) -> None:
        """从 DB 加载某类型的所有映射到 Redis Hash。

        db 非空时直接用（请求事务已 flush，可见未提交行）；
        db 为空时开独立 session（手动刷新场景）。
        """
        async def _do_refresh(session: AsyncSession) -> tuple[str | None, dict[str, str]]:
            from app.api.v1.module_system.dict.model import DictDataModel, DictTypeModel

            # 查 dict_type 名
            dt_result = await session.execute(
                select(DictTypeModel).where(DictTypeModel.id == dict_type_id)
            )
            dict_type_obj = dt_result.scalars().first()
            if not dict_type_obj:
                log.warning("字典映射缓存刷新: dict_type_id=%s 不存在", dict_type_id)
                return None, {}

            dict_type_name = dict_type_obj.dict_type

            # JOIN 批量查映射 + 字典值，消除 N+1
            rows = (
                await session.execute(
                    select(DictMappingModel.raw_label, DictDataModel.dict_value)
                    .join(
                        DictDataModel,
                        DictMappingModel.dict_data_id == DictDataModel.id,
                    )
                    .where(DictMappingModel.dict_type_id == dict_type_id)
                )
            ).all()

            hash_data: dict[str, str] = {
                r[0].lower(): r[1] for r in rows if r[1]
            }
            return dict_type_name, hash_data

        try:
            if db is not None:
                dict_type_name, hash_data = await _do_refresh(db)
            else:
                async with async_db_session() as new_db:
                    dict_type_name, hash_data = await _do_refresh(new_db)

            if dict_type_name is None:
                return

            cache_k = _cache_key(tenant_id, dict_type_name)
            if hash_data:
                # 批量写入 Hash：用 redis.hset(mapping=...) 一次写入全部字段
                await redis.hset(name=cache_k, mapping=hash_data)
            else:
                # 无映射则删除 key
                await RedisCURD(redis).delete(cache_k)

            log.info(
                "字典映射缓存刷新: tenant=%s dict_type=%s count=%d",
                tenant_id, dict_type_name, len(hash_data),
            )
        except Exception as e:
            log.error("字典映射缓存刷新失败: %s", e)

    @classmethod
    async def _lookup_cache(
        cls, redis: Redis, tenant_id: int, dict_type: str, raw_label: str
    ) -> str | None:
        """从 Redis Hash 查单个映射。"""
        try:
            cache_k = _cache_key(tenant_id, dict_type)
            values = await RedisCURD(redis).hash_get(name=cache_k, keys=[raw_label.lower()])
            if values and values[0]:
                v = values[0]
                return v if isinstance(v, str) else v.decode() if isinstance(v, bytes) else str(v)
        except Exception:
            pass
        return None

    @classmethod
    async def _set_cache(
        cls, redis: Redis, tenant_id: int, dict_type: str, raw_label: str, dict_value: str
    ) -> None:
        """写入 Redis Hash 单个映射。"""
        try:
            cache_k = _cache_key(tenant_id, dict_type)
            await RedisCURD(redis).hash_set(name=cache_k, key=raw_label.lower(), value=dict_value)
        except Exception as e:
            log.warning("字典映射缓存写入失败: %s", e)

    @classmethod
    async def _get_dict_type_id(cls, db: AsyncSession, dict_type: str) -> int | None:
        """按 dict_type 字符串查 id。"""
        try:
            from app.api.v1.module_system.dict.model import DictTypeModel

            sql = select(DictTypeModel).where(DictTypeModel.dict_type == dict_type)
            result = await db.execute(sql)
            obj = result.scalars().first()
            return obj.id if obj else None
        except Exception:
            return None

    @classmethod
    async def _get_dict_value(cls, db: AsyncSession, dict_data_id: int) -> str | None:
        """按 dict_data_id 查 dict_value。"""
        try:
            from app.api.v1.module_system.dict.model import DictDataModel

            sql = select(DictDataModel).where(DictDataModel.id == dict_data_id)
            result = await db.execute(sql)
            obj = result.scalars().first()
            return obj.dict_value if obj else None
        except Exception:
            return None


def _unmatched_to_dict(obj: DictUnmatchedModel) -> dict:
    """未匹配记录转字典。"""
    dict_type_name = None
    if hasattr(obj, "dict_type") and obj.dict_type:
        dict_type_name = getattr(obj.dict_type, "dict_name", None)

    return {
        "id": obj.id,
        "hospital_id": obj.hospital_id,
        "dict_type_id": obj.dict_type_id,
        "dict_type_name": dict_type_name,
        "raw_label": obj.raw_label,
        "raw_value": obj.raw_value,
        "occurrence_count": obj.occurrence_count,
        "last_seen_at": obj.last_seen_at,
        "resolution": obj.resolution,
    }
