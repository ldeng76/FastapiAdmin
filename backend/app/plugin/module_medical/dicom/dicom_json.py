"""DICOM JSON 编码工具（DICOMweb 标准 PS3.18 Annex F）。

将 pydicom Dataset 转换为 DICOM JSON 格式，供 OHIF Viewer 使用。
DICOM JSON 规范：tag 用 8 位十六进制，每个值用 {vr, Value} 结构表示。
"""

from __future__ import annotations

from typing import Any

import pydicom
from pydicom.dataset import Dataset
from pydicom.multival import MultiValue
from pydicom.sequence import Sequence
from pydicom.valuerep import PersonName


# 这些 VR 的值必须是数值（不是字符串，而是真正的数字）
_NUMERIC_VRS = {"US", "SS", "UL", "SL", "FL", "FD", "DS", "IS", "AS"}

# 这些 VR 的值需要用字符串表示
_STRING_VRS = {
    "AE", "CS", "DA", "DT", "LO", "LT", "MD",
    "MO", "PN", "SH", "ST", "TM", "UC", "UI", "UR", "UT",
}

# 需要用 base64 编码的二进制 VR
_BINARY_VRS = {"OB", "OD", "OF", "OL", "OW", "OV"}


def _tag_to_key(tag: int) -> str:
    """将 DICOM tag (int) 转为 8 位十六进制字符串。"""
    return f"{tag:08X}"


def _encode_value(elem: pydicom.DataElement) -> dict[str, Any] | None:
    """将单个 DataElement 编码为 DICOM JSON 值对象。"""
    vr = elem.VR
    val = elem.value

    # Sequence 类型递归编码
    if vr == "SQ":
        items = []
        for item in val:
            if isinstance(item, Dataset):
                items.append(dataset_to_dicom_json(item))
        return {"vr": vr, "Value": items} if items else {"vr": vr}

    # PersonName 类型
    if isinstance(val, PersonName):
        return {"vr": vr, "Value": [str(val)]}

    # MultiValue 类型（pydicom 多值属性，如 PixelSpacing, ImagePositionPatient 等）
    if isinstance(val, MultiValue):
        values = []
        for v in val:
            encoded = _encode_scalar(vr, v)
            if encoded is not None:
                values.append(encoded)
        return {"vr": vr, "Value": values} if values else {"vr": vr}

    # 普通列表/元组
    if isinstance(val, (list, tuple)):
        values = []
        for v in val:
            encoded = _encode_scalar(vr, v)
            if encoded is not None:
                values.append(encoded)
        return {"vr": vr, "Value": values} if values else {"vr": vr}

    # 单值
    encoded = _encode_scalar(vr, val)
    if encoded is not None:
        return {"vr": vr, "Value": [encoded]}
    return {"vr": vr}


def _encode_scalar(vr: str, val: Any) -> Any:
    """将单个标量值按 VR 转为 JSON 兼容格式。"""
    if val is None:
        return None

    # 数值类 VR（包括 DS, IS, AS 等，保持原始数值类型）
    if vr in _NUMERIC_VRS:
        # 已经是数值类型
        if isinstance(val, (int, float)):
            return float(val) if isinstance(val, float) else int(val)
        # 尝试转为 float（处理 DSfloat, ISfloat 等 pydicom 自定义类型）
        try:
            return float(val)
        except (ValueError, TypeError):
            pass
        # 字符串形式的数值
        if isinstance(val, str):
            try:
                return float(val) if "." in val or "e" in val.lower() else int(val)
            except (ValueError, TypeError):
                return val
        # bytes 形式
        if isinstance(val, bytes):
            try:
                s = val.decode("utf-8")
                return float(s) if "." in s or "e" in s.lower() else int(s)
            except (ValueError, TypeError, UnicodeDecodeError):
                return None
        return val

    # 字符串类 VR
    if vr in _STRING_VRS:
        if isinstance(val, bytes):
            try:
                return val.decode("utf-8")
            except UnicodeDecodeError:
                return val.decode("latin-1")
        return str(val)

    # OB/OW 等二进制数据 - base64 编码
    if vr in _BINARY_VRS:
        import base64
        if isinstance(val, bytes):
            return base64.b64encode(val).decode("ascii")
        return None

    # 默认：转为字符串
    if isinstance(val, bytes):
        try:
            return val.decode("utf-8")
        except UnicodeDecodeError:
            return val.decode("latin-1", errors="replace")
    return str(val)


# 这些 tag 在 metadata 响应中应该被排除（符合 DICOMweb 标准）
_EXCLUDED_TAGS = {
    0x7FE00010,  # PixelData
}


def dataset_to_dicom_json(ds: Dataset) -> dict[str, dict[str, Any]]:
    """将 pydicom Dataset 转为 DICOM JSON 对象。

    返回格式: {"0020000D": {"vr": "UI", "Value": ["1.2.3..."]}, ...}

    注意：PixelData (7FE00010) 被排除，因为它太大且不符合 DICOMweb metadata 标准。
    OHIF Viewer 应该通过 WADO-RS frames 接口或直接获取 DICOM 文件来获取像素数据。
    """
    result: dict[str, dict[str, Any]] = {}
    for elem in ds:
        if elem.tag.is_private:
            continue
        if elem.tag in _EXCLUDED_TAGS:
            continue
        key = _tag_to_key(elem.tag)
        encoded = _encode_value(elem)
        if encoded is not None:
            result[key] = encoded
    return result


def dataset_to_json_array(ds_list: list[Dataset]) -> list[dict[str, dict[str, Any]]]:
    """将 Dataset 列表转为 DICOM JSON 数组。"""
    return [dataset_to_dicom_json(ds) for ds in ds_list]
