"""医疗文件 — 数据访问层。"""

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.base_crud import CRUDBase

from .model import MedFilesModel


class MedFilesCRUD(CRUDBase[MedFilesModel, None, None]):
    """医疗文件 CRUD。"""

    def __init__(self, auth: AuthSchema) -> None:
        super().__init__(model=MedFilesModel, auth=auth)
