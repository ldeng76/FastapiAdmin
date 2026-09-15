from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

from app.common.enums import QueueEnum


class MedicalFiles(BaseModel):
    """医疗文件基础字段。"""

    id: int = Field(description="ID")
    file_name: str | None = Field(default=None, min_length=1, max_length=255, description="文件名")
    patient_id: str | None = Field(default=None, description="患者编号")
    exam_type: str | None = Field(default=None, description="模态类型")
    file_type: str | None = Field(default=None, description="文件类型")
    # file_size: int | None = Field(default=None, description="文件大小")
    file_path: str | None = Field(default=None, description="文件路径")


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
        file_type: str | None = Query(
            None, description="文件类型（多选，逗号分隔，如 dcm,nii）"
        ),
        center_type: str | None = Query(
            None, description="中心筛选（多选，逗号分隔，如 sy,sh）"
        ),
    ) -> None:
        exam_list = [s.strip() for s in exam_type.split(",")] if exam_type else None
        exam_list = [s for s in exam_list if s] if exam_list else None
        file_list = [s.strip() for s in file_type.split(",")] if file_type else None
        file_list = [s for s in file_list if s] if file_list else None
        center_list = [s.strip() for s in center_type.split(",")] if center_type else None
        center_list = [s for s in center_list if s] if center_list else None

        self.exam_type = (QueueEnum.in_.value, exam_list) if exam_list else None
        self.file_type = (QueueEnum.in_.value, file_list) if file_list else None
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

    file_count: int = Field(description="文件个数")
    patient_count: int = Field(description="有文件的患者数（MedFilesModel 去重）")
    exam_count: int = Field(description="检查量（AnonExamModel 行数）")
    total_size_bytes: int | None = Field(
        default=None,
        description="所有文件总大小（字节）。当前数据源未落库文件大小字段，固定为 null，待 ETL-2 回填 lnrs_anon_dicom_series.byte_size 后恢复聚合。",
    )
    total_size_text: str | None = Field(
        default=None,
        description="总大小易读文本，如 '12.34 GB'。数据不可得时为 null，前端应显示 —。",
    )
    by_exam_type: list[GroupStatItem] = Field(
        default_factory=list, description="各模态文件数及占比"
    )
    by_file_type: list[GroupStatItem] = Field(
        default_factory=list, description="各文件类型文件数及占比"
    )


class FileExistenceOutSchema(BaseModel):
    """文件存在性校验响应。"""

    file_id: int | None = Field(default=None, description="命中记录的主键，查询不到时为 null")
    exists: bool = Field(description="文件或目录在磁盘上是否存在")
