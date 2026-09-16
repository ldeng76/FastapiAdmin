"""医疗文件模型（映射已有表 lnrs_anon_exam_file）。"""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import MappedBase


class MedFilesModel(MappedBase):
    """医疗文件表（仅映射现有字段，不附加 mixin 字段）。"""

    __tablename__ = "lnrs_anon_imaging_study"
    __table_args__ = (
        {"comment": "影像研究桥接表"},
    )

    id: Mapped[int] = mapped_column(
        "study_key",
        Integer, primary_key=True, autoincrement=True, comment="主键ID"
    )
    anon_exam_id: Mapped[str | None] = mapped_column(
        String(40), nullable=True, comment="检查ID"
    )
    file_name: Mapped[str | None] = mapped_column(
        "dicom_study_uid",
        String(255), nullable=True, comment="文件名"
    )
    patient_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="患者编号"
    )
    exam_type: Mapped[str | None] = mapped_column(
        "modality",
        String(32), nullable=True, comment="模态类型"
    )
    center_code: Mapped[str | None] = mapped_column(
        "center_code",
        String(32), nullable=True, comment="中心编码"
    )
    # file_type 数据库无对应列，占位属性（非 Mapped，不参与 SQL 映射）
    file_type: str = "dcm"
    file_path: Mapped[str | None] = mapped_column(
        "image_path",
        String(512), nullable=True, comment="文件路径"
    )
