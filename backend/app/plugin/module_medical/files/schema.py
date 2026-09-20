from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.common.enums import QueueEnum


class MedicalFiles(BaseModel):
    """医疗文件基础字段。"""

    id: int = Field(description="ID")
    anon_exam_id: str | None = Field(default=None, description="检查ID")
    file_name: str | None = Field(default=None, min_length=1, max_length=255, description="文件名")
    patient_id: str | None = Field(default=None, description="患者编号")
    exam_type: str | None = Field(default=None, description="模态类型")
    file_type: str | None = Field(default=None, description="文件类型")
    file_size: int | None = Field(default=0, description="文件大小（字节，取自 dicom_series.byte_size）")

    @field_validator("file_name", mode="before")
    @classmethod
    def _normalize_file_name(cls, v):
        """file_name 数据库无对应列（占位属性）；空串统一转成 None，避免 min_length 校验失败。"""
        return v or None

    @field_validator("file_type", mode="before")
    @classmethod
    def _force_file_type_dcm(cls, v):
        """file_type 暂时固定返回 dcm，不读数据库 center_code。"""
        return "dcm"


class MedicalFilesOutSchema(MedicalFiles):
    """医疗文件响应模型。"""

    model_config = ConfigDict(from_attributes=True)


class MedicalFilesQueryParam:
    """医疗文件查询参数。

    exam_type / file_type 支持逗号分隔的多选值，为空则不过滤。
    用法：?exam_type=CT,PETCT&file_type=dicom
    """

    def __init__(
        self,
        exam_type: str | None = Query(
            None, description="模态类型（多选，逗号分隔，如 CT,PETCT）"
        ),
        # file_type: str | None = Query(
        #     None, description="文件类型（多选，逗号分隔，如 dcm,nii）"
        # ),  # 暂时没用，固定返回 dcm
        center_type: str | None = Query(
            None, description="中心筛选（多选，逗号分隔，如 sy,sh）"
        ),
    ) -> None:
        exam_list = [s.strip() for s in exam_type.split(",")] if exam_type else None
        exam_list = [s for s in exam_list if s] if exam_list else None
        # file_list = [s.strip() for s in file_type.split(",")] if file_type else None
        # file_list = [s for s in file_list if s] if file_list else None
        center_list = [s.strip() for s in center_type.split(",")] if center_type else None
        center_list = [s for s in center_list if s] if center_list else None

        self.exam_type = (QueueEnum.in_.value, exam_list) if exam_list else None
        self.file_type = None  # 暂时没用，固定返回 dcm（响应层处理）
        self.center_type = (QueueEnum.in_.value, center_list) if center_list else None


class DictItemSchema(BaseModel):
    """通用字典项（label/value 对）。"""

    label: str = Field(description="展示名")
    value: str = Field(description="值")


class MedFilesDictOutSchema(BaseModel):
    """文件类型字典响应。"""

    file_type_options: list[DictItemSchema] = Field(
        description="当前数据库里实际出现过的文件类型字典（label 同 value）"
    )


class GroupStatItem(BaseModel):
    """分组统计单项。"""

    value: str = Field(description="分组原始值")
    label: str = Field(description="展示名（模态取字典翻译，文件类型同 value）")
    count: int = Field(description="该组文件数")
    percentage: float = Field(description="占比（0-100，保留两位小数）")


class MedFilesStatisticsOutSchema(BaseModel):
    """医疗文件统计响应。"""

    file_count: int = Field(description="影像文件数")
    record_count: int = Field(description="影像记录行数（lnrs_anon_imaging_study 行数）")
    patient_count: int = Field(
        description="有影像文件的患者数（lnrs_anon_imaging_study.patient_id 去重）"
    )
    exam_patient_count: int = Field(
        description=(
            "有检查记录的患者数（lnrs_anon_exam.patient_id 去重）。"
            "注意：与 medicalDashboard 的「患者总量」不同 —— 后者查 lnrs_anon_patient 全集。"
            "两者之差为「入过册但从未做过任何检查的患者」。"
            "2026-09-20 由 lnrs_anon_patient 切换为 exam 口径。"
        ),
    )
    exam_count: int = Field(
        description="检查量（lnrs_anon_exam 行数；与影像文件数不同——一次临床检查可能 0/N 个影像文件）"
    )
    total_size_bytes: int = Field(
        description="所有文件总大小（字节）。2026-09-15 dicom_series 落库后从 dicom_series.byte_size 累加。",
    )
    total_size_text: str = Field(
        description="总大小易读文本，如 '8.76 TB'。",
    )
    by_exam_type: list[GroupStatItem] = Field(
        default_factory=list,
        description="各模态影像文件数及占比（imaging_study.modality 维度）",
    )


class FileExistenceOutSchema(BaseModel):
    """文件存在性校验响应。"""

    file_id: int | None = Field(default=None, description="命中记录的主键，查询不到时为 null")
    exists: bool = Field(description="文件或目录在磁盘上是否存在")
