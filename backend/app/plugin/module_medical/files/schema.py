from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.common.enums import QueueEnum


class MedicalFiles(BaseModel):
    """医疗文件基础字段。"""

    id: int = Field(description="ID")
    file_name: str | None = Field(default=None, min_length=1, max_length=255, description="文件名")
    patient_id: str | None = Field(default=None, description="患者编号")
    exam_type: str | None = Field(default=None, description="模态类型")
    file_type: str | None = Field(default=None, description="文件类型")
    file_path: str | None = Field(default=None, description="文件路径")

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

    file_count: int = Field(description="影像文件数（lnrs_anon_imaging_study 行数）")
    patient_count: int = Field(
        description="有影像文件的患者数（lnrs_anon_imaging_study.patient_id 去重）"
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
        description="各业务模态影像文件数及占比（LEFT JOIN lnrs_anon_exam 按 exam.exam_type 分组；含 '__unlinked__' 桶表示未关联 exam 的影像文件）。",
    )
    by_exam_type_total: int = Field(
        description="by_exam_type 统计基数（含未关联 exam 的 study；与 file_count 一致）"
    )
    by_exam_type_unlinked: int = Field(
        description="by_exam_type 中未关联 exam 的 study 数（anon_exam_id IS NULL）"
    )
    by_center: list[GroupStatItem] = Field(
        default_factory=list, description="各中心影像文件数及占比（imaging_study.center_code 维度）"
    )


class FileExistenceOutSchema(BaseModel):
    """文件存在性校验响应。"""

    file_id: int | None = Field(default=None, description="命中记录的主键，查询不到时为 null")
    exists: bool = Field(description="文件或目录在磁盘上是否存在")
