"""医疗文件模型（映射已有表 lnrs_anon_exam_file）。"""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import MappedBase


class MedFilesModel(MappedBase):
    """医疗文件表（仅映射现有字段，不附加 mixin 字段）。"""

    __tablename__ = "lnrs_anon_exam_file"
    __table_args__ = (
        {"comment": "医疗文件表"},
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="主键ID"
    )
    file_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="文件名"
    )
    patient_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="患者编号"
    )
    exam_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="模态类型"
    )
    file_type: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment="文件类型"
    )
    file_size: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="文件大小"
    )
    file_path: Mapped[str | None] = mapped_column(
        String(512), nullable=True, comment="文件路径"
    )
