"""DICOM 影像模块 Pydantic schema。

仅暴露浏览/阅片所需的元数据：Study → Series → Instance（切片）三级。
切片已按解剖顺序（ImagePositionPatient 的 Z 轴）排序后返回。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class StudyOut(BaseModel):
    """一次检查（按 StudyInstanceUID 分组，每个 UID 独立一行）。"""

    study_id: str = Field(..., description="Study 标识（通常为 StudyInstanceUID，匿名化时为目录名/文件名）")
    patient_id: str | None = Field(None, description="患者编号")
    patient_name: str | None = Field(None, description="患者姓名")
    study_uid: str | None = Field(None, description="StudyInstanceUID")
    study_description: str | None = Field(None, description="检查描述")
    study_date: str | None = Field(None, description="检查日期")
    modality: str | None = Field(None, description="模态（CT/MR 等）")
    series_count: int = Field(0, description="序列数量")


class SeriesOut(BaseModel):
    """一个序列（一组连续切片）。"""

    series_uid: str = Field(..., description="SeriesInstanceUID")
    series_description: str | None = Field(None, description="序列描述")
    modality: str | None = Field(None, description="模态")
    instance_count: int = Field(0, description="切片数量")
    rows: int | None = Field(None, description="图像行数")
    columns: int | None = Field(None, description="图像列数")
    slice_thickness: float | None = Field(None, description="层厚(mm)")
    pixel_spacing: list[float] | None = Field(None, description="像素间距(mm) [行,列]")
    default_window_width: float | None = Field(None, description="默认窗宽")
    default_window_center: float | None = Field(None, description="默认窗位")


class InstanceOut(BaseModel):
    """一张切片（已排序）。"""

    sop_uid: str = Field(..., description="SOPInstanceUID（拉取原始 DICOM 的 key）")
    index: int = Field(..., description="序列内序号（从 1 开始，按 Z 轴排序）")
    instance_number: str | None = Field(None, description="InstanceNumber（原始编号）")
    position_z: float | None = Field(None, description="Z 坐标(mm)")
    window_width: float | None = Field(None, description="窗宽")
    window_center: float | None = Field(None, description="窗位")


class DicomStudyDetailOut(BaseModel):
    """study_id → 其下所有 series（含 series 元信息）。"""

    study_id: str
    series: list[SeriesOut] = Field(default_factory=list, description="序列列表")
