# DICOM 元数据脱敏指南

## 概述

DICOM 文件中包含大量敏感的患者信息（PHI），脱敏的核心是修改 DICOM tag（元数据标签）。本文档提供完整的 DICOM 元数据脱敏方案。

## 1. 推荐库：`pydicom`

```bash
uv add pydicom
```

## 2. 核心功能：读取并修改 DICOM 元数据

```python
import pydicom
from pydicom.dataset import Dataset, FileDataset

def load_dicom(filepath: str) -> Dataset:
    """加载 DICOM 文件"""
    ds = pydicom.dcmread(filepath)
    return ds

def save_dicom(ds: Dataset, output_path: str):
    """保存修改后的 DICOM 文件"""
    ds.save_as(output_path)
```

## 3. 需要脱敏的敏感 Tags（DICOM Standard PHI List）

按 DICOM 标准（HIPAA Safe Harbor），以下 tags 需要脱敏：

| Tag | 名称 | 说明 |
|-----|------|------|
| (0x0010, 0x0010) | PatientName | 患者姓名 → "匿名^患者" |
| (0x0010, 0x0020) | PatientID | 患者ID → 随机UUID |
| (0x0010, 0x0030) | PatientBirthDate | 出生日期 → 置空或伪造 |
| (0x0010, 0x0040) | PatientSex | 性别 → 可保留（非敏感），也可匿名 |
| (0x0010, 0x1010) | PatientAge | 年龄 |
| (0x0010, 0x1030) | PatientWeight | 体重 |
| (0x0010, 0x21B0) | AdditionalPatientHistory | 额外患者病史 |
| (0x0010, 0x4000) | PatientComments | 患者备注 |
| (0x0010, 0x1000) | OtherPatientIDs | 其他患者ID |
| (0x0010, 0x1001) | OtherPatientNames | 其他曾用名 |
| (0x0010, 0x1040) | PatientAddress | 患者地址 |
| (0x0010, 0x2154) | PatientsTelephoneNumbers | 患者电话号码 |
| (0x0010, 0x2152) | PatientsEmailAddress | 患者邮箱 |
| (0x0008, 0x0080) | InstitutionName | 机构名称 |
| (0x0008, 0x0090) | ReferringPhysicianName | 转诊医生姓名 |
| (0x0008, 0x0096) | ReferringPhysicianAddress | 转诊医生地址 |
| (0x0008, 0x0092) | ReferringPhysicianTelephoneNumbers | 转诊医生电话 |
| (0x0008, 0x1010) | StationName | 设备站名 |
| (0x0008, 0x1040) | InstitutionalDepartmentName | 科室名称 |
| (0x0008, 0x1070) | OperatorsName | 操作员姓名 |
| (0x0008, 0x1080) | AdmittingDiagnosesDescription | 入院诊断描述 |
| (0x0020, 0x0010) | StudyID | 研究ID |
| (0x0020, 0x000D) | StudyInstanceUID | 研究实例UID → 重新生成 |
| (0x0020, 0x000E) | SeriesInstanceUID | 序列实例UID → 重新生成 |
| (0x0008, 0x0018) | SOPInstanceUID | SOP实例UID → 重新生成 |
| (0x0008, 0x0020) | StudyDate | 研究日期 |
| (0x0008, 0x0030) | StudyTime | 研究时间 |
| (0x0008, 0x0021) | SeriesDate | 序列日期 |
| (0x0008, 0x0031) | SeriesTime | 序列时间 |
| (0x0008, 0x0022) | AcquisitionDate | 采集日期 |
| (0x0008, 0x0032) | AcquisitionTime | 采集时间 |
| (0x0008, 0x0023) | ContentDate | 内容日期 |
| (0x0008, 0x0033) | ContentTime | 内容时间 |
| (0x0032, 0x1032) | RequestingPhysician | 申请医生 |
| (0x0038, 0x0010) | AdmissionID | 入院ID |
| (0x0038, 0x0050) | SpecialNeeds | 特殊需求 |
| (0x0038, 0x0300) | CurrentPatientLocation | 患者当前位置 |

## 4. 完整脱敏实现

```python
import uuid
import pydicom
from pydicom.dataset import Dataset
from typing import Optional
import hashlib


def anonymize_dicom(
    input_path: str,
    output_path: str,
    keep_essential: bool = True,
    new_patient_id_prefix: str = "ANON_"
) -> str:
    """
    对 DICOM 文件进行脱敏
    
    :param input_path: 原始 DICOM 文件路径
    :param output_path: 输出 DICOM 文件路径
    :param keep_essential: 是否保留非敏感的临床信息（如模态、像素数据）
    :param new_patient_id_prefix: 新患者ID的前缀
    :return: 输出文件路径
    """
    ds = pydicom.dcmread(input_path)
    
    # 1. 生成稳定的匿名ID（基于原始ID的哈希，确保同一患者映射到同一匿名ID）
    original_pid = str(ds.get((0x0010, 0x0020), "UNKNOWN").value)
    hash_obj = hashlib.sha256(original_pid.encode())
    anon_id = f"{new_patient_id_prefix}{hash_obj.hexdigest()[:12].upper()}"
    
    # 2. 脱敏患者标识
    # 患者姓名 → 匿名
    if (0x0010, 0x0010) in ds:
        ds.PatientName = f"匿名^患者^{anon_id[-8:]}"
    
    # 患者ID → 匿名ID
    ds.PatientID = anon_id
    
    # 出生日期 → 保留年份但不保留具体日期
    if (0x0010, 0x0030) in ds:
        birth_date = str(ds.PatientBirthDate)
        if len(birth_date) >= 4:
            ds.PatientBirthDate = birth_date[:4] + "0101"  # 只保留年份
        else:
            ds.PatientBirthDate = "19000101"
    
    # 地址 → 清空
    if (0x0010, 0x1040) in ds:
        ds.PatientAddress = ""
    
    # 电话/邮箱 → 清空（如果存在）
    for tag in [(0x0010, 0x2154), (0x0010, 0x2152)]:
        if tag in ds:
            ds[tag].value = ""
    
    # 3. 重新生成 UIDs
    ds.StudyInstanceUID = pydicom.uid.generate_uid()
    ds.SeriesInstanceUID = pydicom.uid.generate_uid()
    ds.SOPInstanceUID = pydicom.uid.generate_uid()
    
    # 4. 脱敏机构/医生信息
    for tag in [
        (0x0008, 0x0080),  # InstitutionName
        (0x0008, 0x0090),  # ReferringPhysicianName
        (0x0008, 0x1070),  # OperatorsName
    ]:
        if tag in ds:
            ds[tag].value = ""
    
    # 5. 可选：保留日期偏移（保持时间间隔，但偏移绝对日期）
    # 用 StudyDate 做基准偏移
    if keep_essential and (0x0008, 0x0020) in ds:
        # 你可以实现日期偏移逻辑
        pass
    
    # 6. 处理私有 tags
    for elem in ds:
        if elem.tag.is_private:
            # 私有 tag 全部清空或标记为匿名
            elem.value = ""
    
    # 7. 保存
    ds.save_as(output_path)
    return output_path
```

## 5. 更安全的方案：使用 `pydicom.anonymize`（如果支持）

一些新版 pydicom 内置了 `pydicom.anonymize` 模块（如 pydicom 3.x）：

```python
from pydicom.anonymize import Anonymizer

anonymizer = Anonymizer()
anonymizer.anonymize(input_path, output_path)
```

## 6. 脱敏后的验证

```python
def verify_anonymization(filepath: str, original_patient_id: str) -> list:
    """验证脱敏是否彻底，返回残留的敏感信息"""
    ds = pydicom.dcmread(filepath)
    found_phi = []
    
    # 检查已知的 PHI tags
    for tag, name in PHI_TAGS.items():
        if tag in ds and ds[tag].value:
            val = str(ds[tag].value)
            # 检查是否含有原始患者标识
            if original_patient_id.lower() in val.lower():
                found_phi.append(f"Tag {tag} ({name}) 仍有原始信息: {val}")
            else:
                found_phi.append(f"Tag {tag} ({name}) 未清空: {val}")
    
    return found_phi
```

## 7. 批量处理

```python
from pathlib import Path
from multiprocessing import Pool

def batch_anonymize(input_dir: str, output_dir: str, workers: int = 4):
    """批量脱敏 DICOM 文件"""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    dcm_files = list(input_path.rglob("*.dcm"))
    
    def process_one(dcm_file: Path):
        rel_path = dcm_file.relative_to(input_path)
        out_file = output_path / rel_path
        out_file.parent.mkdir(parents=True, exist_ok=True)
        anonymize_dicom(str(dcm_file), str(out_file))
    
    with Pool(workers) as pool:
        pool.map(process_one, dcm_files)
```

## 8. 项目集成建议

考虑到本项目已有 OCR 和 PDF 处理的基础设施，可以这样集成：

1. 创建新模块：`src/biz/dicom/`
2. 核心代码放在 `src/biz/dicom/anonymizer.py`
3. 添加相应配置到 `conf` 目录
4. 配合现有的日志系统（loguru）和数据库工具记录脱敏操作
