"""医疗字典值映射 — 数据访问层。"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.base_crud import CRUDBase
from app.core.exceptions import CustomException

from .model import DictMappingModel, DictUnmatchedModel


class DictMappingCRUD(CRUDBase[DictMappingModel, None, None]):
    """映射规则 CRUD。"""

    def __init__(self, auth: AuthSchema) -> None:
        super().__init__(model=DictMappingModel, auth=auth)

    async def get_by_raw_label(
        self, hospital_id: int, dict_type_id: int, raw_label: str
    ) -> DictMappingModel | None:
        """按 (hospital_id, dict_type_id, lower(raw_label)) 查映射。"""
        sql = select(self.model).where(
            self.model.hospital_id == hospital_id,
            self.model.dict_type_id == dict_type_id,
            func.lower(self.model.raw_label) == raw_label.lower(),
        )
        sql = await self._CRUDBase__filter_permissions(sql)
        result = await self.auth.db.execute(sql)
        return result.scalars().first()

    async def list_by_dict_type(
        self, hospital_id: int, dict_type_id: int
    ) -> list[DictMappingModel]:
        """列出某医院某类型的所有映射。"""
        sql = select(self.model).where(
            self.model.hospital_id == hospital_id,
            self.model.dict_type_id == dict_type_id,
        )
        sql = await self._CRUDBase__filter_permissions(sql)
        result = await self.auth.db.execute(sql)
        return list(result.scalars().all())


class DictUnmatchedCRUD(CRUDBase[DictUnmatchedModel, None, None]):
    """未匹配记录 CRUD。"""

    def __init__(self, auth: AuthSchema) -> None:
        super().__init__(model=DictUnmatchedModel, auth=auth)

    async def upsert_unmatched(
        self,
        db: AsyncSession,
        hospital_id: int,
        dict_type_id: int,
        raw_label: str,
        raw_value: str | None,
        tenant_id: int,
    ) -> DictUnmatchedModel:
        """原子 UPSERT 未匹配记录：存在则累加 occurrence_count，不存在则新建。

        使用 PostgreSQL INSERT ... ON CONFLICT DO UPDATE 避免 SELECT-then-INSERT 竞态。
        """
        # 防御性租户校验：非超管不能写入其他租户的未匹配记录
        if self.auth.user and not self.auth.user.is_superuser:
            if tenant_id != self.auth.user.tenant_id:
                raise CustomException(msg="无权写入其他租户的未匹配记录")

        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = pg_insert(DictUnmatchedModel).values(
            tenant_id=tenant_id,
            hospital_id=hospital_id,
            dict_type_id=dict_type_id,
            raw_label=raw_label,
            raw_value=raw_value,
            occurrence_count=1,
            last_seen_at=datetime.now(),
            status="0",
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["hospital_id", "dict_type_id", "raw_label"],
            set_={
                "occurrence_count": DictUnmatchedModel.occurrence_count + 1,
                "last_seen_at": datetime.now(),
                "raw_value": raw_value,
            },
        ).returning(DictUnmatchedModel)

        result = await db.execute(stmt)
        return result.scalars().one()
