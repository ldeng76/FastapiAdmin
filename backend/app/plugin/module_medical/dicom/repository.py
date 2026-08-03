"""DICOM 影像数据访问层（pydicom 直读本地 .dcm，不入库）。

设计要点：
- DICOM_DATA_DIR 下每个子目录视为一个 Study；目录名为 study_id。
- 仅读取必要的元数据 tag（stop_before_pixels + specific_tags），不读像素，扫描快。
- 索引结果内存缓存，按目录 mtime 失效，避免重复扫描。
- 切片按解剖顺序排序：优先 ImagePositionPatient 的 Z 分量；缺失时回退 InstanceNumber。
  绝不用文件名/序号排序——斜切或乱序文件名会导致翻片跳层。
- 只索引可显示的图像实例（CT/MR 等单帧 MONOCHROME/RGB），跳过 SR 结构化报告等非图像。
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pydicom
from pydicom.errors import InvalidDicomError

from app.config.setting import settings

# 读头时只取这些 tag（含像素尺寸/窗/位置），其余忽略以提速
_SPECIFIC_TAGS = [
    "PatientID",
    "PatientName",
    "StudyInstanceUID",
    "StudyDescription",
    "StudyDate",
    "SeriesInstanceUID",
    "SeriesDescription",
    "Modality",
    "SOPClassUID",
    "SOPInstanceUID",
    "InstanceNumber",
    "Rows",
    "Columns",
    "SliceThickness",
    "PixelSpacing",
    "ImagePositionPatient",
    "ImageOrientationPatient",
    "WindowCenter",
    "WindowWidth",
    "PhotometricInterpretation",
    "SamplesPerPixel",
]

# 可显示的图像 SOP Class UID（排除 SR/RT Plan 等非图像）
_IMAGE_SOP_CLASSES = {
    "1.2.840.10008.5.1.4.1.1.2",      # CT Image Storage
    "1.2.840.10008.5.1.4.1.1.4",      # MR Image Storage
    "1.2.840.10008.5.1.4.1.1.7",      # Secondary Capture（截图）
    "1.2.840.10008.5.1.4.1.1.1",      # Computed Radiography
    "1.2.840.10008.5.1.4.1.1.12.1",   # X-Ray Angiographic
}

# 不可显示的模态（跳过：SR 报告、RT 计划等）
_NON_IMAGE_MODALITIES = {"SR", "RTPLAN", "RTDOSE", "RTSTRUCT", "ST"}


class _StudyIndex:
    """单个 Study 目录的索引与缓存。"""

    def __init__(self, study_id: str, study_dir: Path) -> None:
        self.study_id = study_id
        self.study_dir = study_dir
        # StudyInstanceUID
        self.study_uid: str | None = None
        # SeriesInstanceUID -> list[instance dict]（已排序）
        self.series: dict[str, list[dict[str, Any]]] = {}
        # study 级元数据
        self.study_meta: dict[str, Any] = {}
        # sop_uid -> 文件绝对路径（供按 UID 取原始文件）
        self.sop_to_path: dict[str, Path] = {}
        # sop_uid -> (series_uid, index)
        self.sop_to_index: dict[str, tuple[str, int]] = {}
        self.mtime: float = 0.0


class DicomIndexer:
    """DICOM 目录扫描 + 内存缓存（线程安全，按 mtime 失效）。

    单例：整个进程共享一份索引。
    """

    _instance: DicomIndexer | None = None
    _lock = threading.Lock()

    def __new__(cls) -> DicomIndexer:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._studies: dict[str, _StudyIndex] = {}  # type: ignore[attr-defined]
            cls._instance._scan_lock = threading.RLock()  # type: ignore[attr-defined]
            cls._instance._study_uid_to_id: dict[str, str] = {}  # type: ignore[attr-defined]
        return cls._instance

    # ------------------------------------------------------------------ #
    # 对外查询
    # ------------------------------------------------------------------ #
    def list_studies(self) -> list[dict[str, Any]]:
        """列出所有 Study（每个子目录一个）。"""
        root = self._root()
        if not root.exists():
            return []
        results: list[dict[str, Any]] = []
        for sub in sorted(p for p in root.iterdir() if p.is_dir()):
            idx = self._get_or_scan(sub)
            if not idx.series:
                continue  # 空目录或无可用图像
            meta = dict(idx.study_meta)
            meta["study_id"] = idx.study_id
            meta["series_count"] = len(idx.series)
            results.append(meta)
        return results

    def list_instances(self, series_uid: str) -> list[dict[str, Any]]:
        """某 Series 所有切片（已按 Z 轴排序）。"""
        idx = self._find_study_by_series(series_uid)
        if idx is None:
            return []
        instances = idx.series.get(series_uid, [])
        return [
            {
                "sop_uid": inst["sop_uid"],
                "index": i + 1,
                "instance_number": inst.get("instance_number"),
                "position_z": inst.get("position_z"),
                "window_width": inst.get("window_width"),
                "window_center": inst.get("window_center"),
            }
            for i, inst in enumerate(instances)
        ]

    def get_instance_path(self, sop_uid: str) -> Path | None:
        """按 SOPInstanceUID 取原始 .dcm 文件路径（用于文件流接口）。

        安全性：sop_uid 必须命中已扫描索引，杜绝路径穿越。
        """
        if not sop_uid or "/" in sop_uid or "\\" in sop_uid or ".." in sop_uid:
            return None
        for idx in self._studies.values():
            self._refresh_if_stale(idx)
            if sop_uid in idx.sop_to_path:
                p = idx.sop_to_path[sop_uid]
                return p if p.exists() else None
        return None

    # ------------------------------------------------------------------ #
    # DICOM-Web 按 UID 查询（OHIF Viewer 需要）
    # ------------------------------------------------------------------ #
    def get_study_by_uid(self, study_uid: str) -> dict[str, Any] | None:
        """按 StudyInstanceUID 查询 Study 元数据。"""
        idx = self._find_study_by_uid(study_uid)
        if idx is None:
            return None
        meta = dict(idx.study_meta)
        meta["study_id"] = idx.study_id
        meta["series_count"] = len(idx.series)
        return meta

    def get_series_by_uid(self, series_uid: str) -> dict[str, Any] | None:
        """按 SeriesInstanceUID 查询 Series 元数据。"""
        idx = self._find_study_by_series(series_uid)
        if idx is None:
            return None
        instances = idx.series.get(series_uid, [])
        if not instances:
            return None
        first = instances[0]
        return {
            "series_uid": series_uid,
            "series_description": first.get("series_description"),
            "modality": first.get("modality"),
            "instance_count": len(instances),
            "rows": first.get("rows"),
            "columns": first.get("columns"),
            "slice_thickness": first.get("slice_thickness"),
            "pixel_spacing": first.get("pixel_spacing"),
            "default_window_width": first.get("window_width"),
            "default_window_center": first.get("window_center"),
        }

    def list_series_by_study_uid(self, study_uid: str) -> list[dict[str, Any]]:
        """按 StudyInstanceUID 列出所有 Series。"""
        idx = self._find_study_by_uid(study_uid)
        if idx is None:
            return []
        out: list[dict[str, Any]] = []
        for series_uid, instances in idx.series.items():
            first = instances[0] if instances else {}
            out.append(
                {
                    "series_uid": series_uid,
                    "series_description": first.get("series_description"),
                    "modality": first.get("modality"),
                    "instance_count": len(instances),
                    "rows": first.get("rows"),
                    "columns": first.get("columns"),
                    "slice_thickness": first.get("slice_thickness"),
                    "pixel_spacing": first.get("pixel_spacing"),
                    "default_window_width": first.get("window_width"),
                    "default_window_center": first.get("window_center"),
                }
            )
        return out

    def get_instance_by_uid(self, sop_uid: str) -> dict[str, Any] | None:
        """按 SOPInstanceUID 获取 Instance 元数据。"""
        path = self.get_instance_path(sop_uid)
        if path is None:
            return None
        for idx in self._studies.values():
            self._refresh_if_stale(idx)
            if sop_uid in idx.sop_to_index:
                series_uid, index = idx.sop_to_index[sop_uid]
                instances = idx.series.get(series_uid, [])
                for i, inst in enumerate(instances):
                    if inst["sop_uid"] == sop_uid:
                        return {
                            "sop_uid": inst["sop_uid"],
                            "index": i + 1,
                            "instance_number": inst.get("instance_number"),
                            "position_z": inst.get("position_z"),
                            "window_width": inst.get("window_width"),
                            "window_center": inst.get("window_center"),
                            "series_uid": series_uid,
                        }
        return None

    def get_instance_dataset(self, sop_uid: str) -> pydicom.Dataset | None:
        """按 SOPInstanceUID 获取完整 pydicom Dataset（供 metadata 接口使用）。"""
        path = self.get_instance_path(sop_uid)
        if path is None:
            return None
        try:
            return pydicom.dcmread(str(path))
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    # UID 反向索引
    # ------------------------------------------------------------------ #
    def _find_study_by_uid(self, study_uid: str) -> _StudyIndex | None:
        """按 StudyInstanceUID 查找 Study 索引。"""
        # 确保所有 study 已扫描
        self.list_studies()
        study_id = self._study_uid_to_id.get(study_uid)
        if study_id:
            idx = self._studies.get(study_id)
            if idx and idx.series:
                return idx
        return None

    # ------------------------------------------------------------------ #
    # 扫描与缓存
    # ------------------------------------------------------------------ #
    def _root(self) -> Path:
        return Path(settings.DICOM_DATA_DIR)

    def _require_study(self, study_id: str) -> _StudyIndex:
        if not study_id or "/" in study_id or "\\" in study_id or ".." in study_id:
            from app.core.exceptions import CustomException

            raise CustomException(msg="非法的 study_id")
        study_dir = self._root() / study_id
        if not study_dir.exists() or not study_dir.is_dir():
            from app.core.exceptions import CustomException

            raise CustomException(msg="Study 不存在")
        return self._get_or_scan(study_dir)

    def _find_study_by_series(self, series_uid: str) -> _StudyIndex | None:
        for idx in list(self._studies.values()):
            self._refresh_if_stale(idx)
            if series_uid in idx.series:
                return idx
        # 可能是新数据，全量刷新一次再查
        self.list_studies()
        for idx in self._studies.values():
            if series_uid in idx.series:
                return idx
        return None

    def _get_or_scan(self, study_dir: Path) -> _StudyIndex:
        study_id = study_dir.name
        with self._scan_lock:
            idx = self._studies.get(study_id)
            if idx is None:
                idx = _StudyIndex(study_id, study_dir)
                self._studies[study_id] = idx
            self._refresh_if_stale(idx)
            return idx

    def _refresh_if_stale(self, idx: _StudyIndex) -> None:
        """目录 mtime 变化或未扫描时重新扫描。"""
        try:
            cur_mtime = idx.study_dir.stat().st_mtime
        except OSError:
            return
        if idx.series or idx.study_meta:
            if abs(cur_mtime - idx.mtime) < 1.0:
                return  # 未变化
        self._scan(idx, cur_mtime)

    def _scan(self, idx: _StudyIndex, mtime: float) -> None:
        """扫描目录下所有 DICOM 文件，建索引。"""
        series_map: dict[str, list[dict[str, Any]]] = {}
        sop_to_path: dict[str, Path] = {}
        study_meta: dict[str, Any] = {}

        files = [p for p in idx.study_dir.iterdir() if p.is_file()]
        # 兼容嵌套目录（递归找文件）
        if not files:
            files = [p for p in idx.study_dir.rglob("*") if p.is_file()]

        for fp in files:
            try:
                ds = pydicom.dcmread(
                    str(fp), stop_before_pixels=True, specific_tags=_SPECIFIC_TAGS
                )
            except (InvalidDicomError, OSError, IsADirectoryError):
                continue
            except Exception:
                # 非 DICOM 文件或损坏，跳过
                continue

            sop_class = getattr(ds, "SOPClassUID", "")
            modality = getattr(ds, "Modality", "") or ""
            # 跳过非图像（SR 报告等）
            if modality in _NON_IMAGE_MODALITIES:
                continue
            # 跳过未识别的非图像 SOP Class（如 SR 1.2.840.10008.5.1.4.1.1.88.67）
            if sop_class and sop_class not in _IMAGE_SOP_CLASSES:
                continue

            series_uid = getattr(ds, "SeriesInstanceUID", None)
            sop_uid = getattr(ds, "SOPInstanceUID", None)
            if not series_uid or not sop_uid:
                continue

            # 计算 Z 坐标（用于排序）
            position_z = None
            ipp = getattr(ds, "ImagePositionPatient", None)
            if ipp is not None and len(ipp) >= 3:
                try:
                    position_z = float(ipp[2])
                except (TypeError, ValueError):
                    position_z = None
            instance_number = getattr(ds, "InstanceNumber", None)

            # 窗宽窗位（可能多值，取第一个）
            wc = _first_window_value(getattr(ds, "WindowCenter", None))
            ww = _first_window_value(getattr(ds, "WindowWidth", None))
            pixel_spacing = getattr(ds, "PixelSpacing", None)
            if pixel_spacing is not None:
                pixel_spacing = [float(x) for x in pixel_spacing]

            inst = {
                "sop_uid": str(sop_uid),
                "instance_number": str(instance_number) if instance_number is not None else None,
                "position_z": position_z,
                "window_width": ww,
                "window_center": wc,
                "modality": modality,
                "series_description": getattr(ds, "SeriesDescription", None),
                "rows": getattr(ds, "Rows", None),
                "columns": getattr(ds, "Columns", None),
                "slice_thickness": _safe_float(getattr(ds, "SliceThickness", None)),
                "pixel_spacing": pixel_spacing,
                "filepath": str(fp),
            }
            series_map.setdefault(str(series_uid), []).append(inst)
            sop_to_path[str(sop_uid)] = fp

            # 取首个有效文件填充 study 级元数据
            if not study_meta:
                uid = str(getattr(ds, "StudyInstanceUID", "")) or None
                study_meta = {
                    "patient_id": getattr(ds, "PatientID", None),
                    "patient_name": _person_name(getattr(ds, "PatientName", None)),
                    "study_uid": uid,
                    "study_description": getattr(ds, "StudyDescription", None),
                    "study_date": getattr(ds, "StudyDate", None),
                    "modality": modality or None,
                }
                # 填充 study_uid 反向索引
                if uid:
                    idx.study_uid = uid
                    self._study_uid_to_id[uid] = idx.study_id

        # 每个 series 内按 Z 轴排序（核心），回退 InstanceNumber
        for uid, insts in series_map.items():
            insts.sort(key=_sort_key)
            # 建 sop -> index 映射
            for i, inst in enumerate(insts):
                idx.sop_to_index[inst["sop_uid"]] = (uid, i + 1)

        idx.series = series_map
        idx.study_meta = study_meta
        idx.sop_to_path = sop_to_path
        idx.mtime = mtime


def _first_window_value(val: Any) -> float | None:
    """窗宽/窗位可能是单值、MultiValue 或 DSfloat，取第一个。"""
    if val is None:
        return None
    try:
        if hasattr(val, "__iter__") and not isinstance(val, str):
            return float(val[0]) if len(val) else None
        return float(val)
    except (TypeError, ValueError):
        return None


def _safe_float(val: Any) -> float | None:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _person_name(val: Any) -> str | None:
    """PatientName 可能是 PersonName 对象，取其字符串。"""
    if val is None:
        return None
    s = str(val).strip()
    return s or None


def _sort_key(inst: dict[str, Any]) -> tuple:
    """排序键：优先 Z 坐标，缺失时回退 InstanceNumber（数值），再回退 sop_uid。

    返回元组而非单一值，确保 None 与数值可比（None 排在最后）。
    """
    z = inst.get("position_z")
    inum = inst.get("instance_number")
    # 用 (has_value, value) 元组：has_value=True 的排前面，None 排后面
    if z is not None:
        return (1, z, 0, "")
    if inum is not None:
        try:
            return (0, float(inum), 0, inst.get("sop_uid", ""))
        except (TypeError, ValueError):
            return (0, 0.0, 0, inst.get("sop_uid", ""))
    return (-1, 0.0, 0, inst.get("sop_uid", ""))


# 模块级单例
indexer = DicomIndexer()
