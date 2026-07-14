"""医院数据访问层 — 继承 CRUDBase，复用通用 CRUD 逻辑。"""

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.base_crud import CRUDBase

from .model import HospitalModel
from .schema import HospitalCreate, HospitalOut, HospitalUpdate


class HospitalCRUD(CRUDBase[HospitalModel, HospitalCreate, HospitalUpdate]):
    """医院数据层"""

    def __init__(self, auth: AuthSchema) -> None:
        self.auth = auth
        super().__init__(model=HospitalModel, auth=auth)

    async def get_by_id_crud(
        self, id: int, preload: list[str] | None = None
    ) -> HospitalModel | None:
        return await self.get(id=id, preload=preload)

    async def page_crud(
        self,
        offset: int,
        limit: int,
        order_by: list[dict[str, str]] | None,
        search: dict | None = None,
        out_schema: type[HospitalOut] | None = None,
        preload: list[str] | None = None,
    ) -> dict:
        return await self.page(
            offset=offset,
            limit=limit,
            order_by=order_by or [{"id": "asc"}],
            search=search or {},
            out_schema=out_schema or HospitalOut,
            preload=preload or [],
        )

    async def create_crud(self, data: HospitalCreate | dict) -> HospitalModel | None:
        return await self.create(data=data)

    async def update_crud(self, id: int, data: HospitalUpdate | dict) -> HospitalModel | None:
        return await self.update(id=id, data=data)
