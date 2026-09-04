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
    ) -> None:
        exam_list = [s.strip() for s in exam_type.split(",")] if exam_type else None
        exam_list = [s for s in exam_list if s] if exam_list else None
        file_list = [s.strip() for s in file_type.split(",")] if file_type else None
        file_list = [s for s in file_list if s] if file_list else None

        self.exam_type = (QueueEnum.in_.value, exam_list) if exam_list else None
        self.file_type = (QueueEnum.in_.value, file_list) if file_list else None


class DictItemSchema(BaseModel):
    """通用字典项（label/value 对）。"""

    label: str = Field(description="展示名")
    value: str = Field(description="值")


class MedFilesDictOutSchema(BaseModel):
    """文件类型字典响应。"""

    file_type_options: list[DictItemSchema] = Field(
        description="当前数据库里实际出现过的文件类型字典（label 同 value）"
    )


class MedFilesStatisticsOutSchema(BaseModel):
    """医疗文件统计响应。"""

    file_count: int = Field(description="文件个数")
    patient_count: int = Field(description="去重后的患者个数")
    total_size_bytes: int = Field(description="所有文件总大小（字节）")
    total_size_text: str = Field(description="总大小易读文本，如 '12.34 GB'")


class FileExistenceOutSchema(BaseModel):
    file_id: int | None = Field(default=None, description="文件ID")
    exists: bool = Field(description="磁盘上文件是否存在")
