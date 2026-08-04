"""DICOM 影像数据访问层（pydicom 直读本地 .dcm，不入库）。

设计要点：
- DICOM_DATA_DIR 下每个子目录可包含多个 Study；按 StudyInstanceUID 分组。
- 仅读取必要的元数据 tag（stop_before_pixels + specific_tags），不读像素，扫描快。
- 索引结果内存缓存，按目录 mtime 失效，避免重复扫描。
- 切片按解剖顺序排序：优先 ImagePositionPatient 的 Z 分量；缺失时回退 InstanceNumber。
  绝不用文件名/序号排序——斜切或乱序文件名会导致翻片跳层。
- 只索引可显示的图像实例（CT/MR 等单帧 MONOCHROME/RGB），跳过 SR 结构化报告等非图像。
- study_id 默认使用 StudyInstanceUID；匿名化数据回退到目录名。
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
    # Patient
    "PatientID",
    "PatientName",
    "PatientSex",
    "PatientBirthDate",
    # Study
    "StudyInstanceUID",
    "StudyDescription",
    "StudyDate",
    "StudyTime",
    "StudyID",
    "AccessionNumber",
    # Series
    "SeriesInstanceUID",
    "SeriesDescription",
    "SeriesNumber",
    "Modality",
    "Manufacturer",
    # Instance
    "SOPClassUID",
    "SOPInstanceUID",
    "InstanceNumber",
    "NumberOfFrames",
    # Image
    "Rows",
    "Columns",
    "BitsAllocated",
    "BitsStored",
    "HighBit",
    "PixelRepresentation",
    "SamplesPerPixel",
    "PhotometricInterpretation",
    "PixelSpacing",
    "ImagePositionPatient",
    "ImageOrientationPatient",
    "SliceThickness",
    "WindowCenter",
    "WindowWidth",
    # Frame of Reference
    "FrameOfReferenceUID",
]

# 可显示的图像 SOP Class UID（排除 SR/RT Plan 等非图像）
# 扩展白名单：涵盖 CT/MR/CR/US/XA/PET/NM/Enhanced 等
_IMAGE_SOP_CLASSES = {
    # CT
    "1.2.840.10008.5.1.4.1.1.2",       # CT Image Storage
    "1.2.840.10008.5.1.4.1.1.2.1",     # Enhanced CT Image Storage
    "1.2.840.10008.5.1.4.1.1.2.2",     # Legacy Converted Enhanced CT Image Storage
    # MR
    "1.2.840.10008.5.1.4.1.1.4",       # MR Image Storage
    "1.2.840.10008.5.1.4.1.1.4.1",     # Enhanced MR Image Storage
    "1.2.840.10008.5.1.4.1.1.4.2",     # MR Spectroscopy Storage
    "1.2.840.10008.5.1.4.1.1.4.3",     # Enhanced MR Color Image Storage
    "1.2.840.10008.5.1.4.1.1.4.4",     # Legacy Converted Enhanced MR Image Storage
    # CR / X-Ray
    "1.2.840.10008.5.1.4.1.1.1",       # Computed Radiography Image Storage
    "1.2.840.10008.5.1.4.1.1.1.1",     # Digital X-Ray Image Storage
    "1.2.840.10008.5.1.4.1.1.1.1.1",   # Digital Mammography X-Ray Image Storage
    "1.2.840.10008.5.1.4.1.1.1.2",     # Digital Intra-Oral X-Ray Image Storage
    # Secondary Capture
    "1.2.840.10008.5.1.4.1.1.7",       # Secondary Capture Image Storage
    "1.2.840.10008.5.1.4.1.1.7.1",     # Multi-frame Single Bit SC
    "1.2.840.10008.5.1.4.1.1.7.2",     # Multi-frame Grayscale Word SC
    "1.2.840.10008.5.1.4.1.1.7.3",     # Multi-frame Grayscale Byte SC
    "1.2.840.10008.5.1.4.1.1.7.4",     # Multi-frame True Color SC
    # Ultrasound
    "1.2.840.10008.5.1.4.1.1.6.1",     # Ultrasound Image Storage
    "1.2.840.10008.5.1.4.1.1.6.2",     # Ultrasound Multi-frame Image Storage
    # Nuclear Medicine / PET
    "1.2.840.10008.5.1.4.1.1.20",      # Nuclear Medicine Image Storage
    "1.2.840.10008.5.1.4.1.1.128",     # PET Image Storage
    "1.2.840.10008.5.1.4.1.1.128.1",   # Legacy Converted Enhanced PET Image Storage
    # X-Ray Angiographic / RF
    "1.2.840.10008.5.1.4.1.1.12.1",    # X-Ray Angiographic Image Storage
    "1.2.840.10008.5.1.4.1.1.12.1.1",  # Enhanced XA Image Storage
    "1.2.840.10008.5.1.4.1.1.12.2",    # X-Ray RF Image Storage
    "1.2.840.10008.5.1.4.1.1.12.2.1",  # Enhanced RF Image Storage
    # VL / Endoscopic
    "1.2.840.10008.5.1.4.1.1.77.1",    # VL Endoscopic Image Storage
    "1.2.840.10008.5.1.4.1.1.77.1.1",  # Video Endoscopic Image Storage
    "1.2.840.10008.5.1.4.1.1.77.2",    # VL Microscopic Image Storage
    "1.2.840.10008.5.1.4.1.1.77.3",    # VL Slide-Coordinates Microscopic Image Storage
    "1.2.840.10008.5.1.4.1.1.77.4",    # VL Photographic Image Storage
    # Derm
    "1.2.840.10008.5.1.4.1.1.78.1",    # Dermoscopic Photography Image Storage
    # Ophthalmic
    "1.2.840.10008.5.1.4.1.1.8",       # Ophthalmic Photography 8 Bit
    "1.2.840.10008.5.1.4.1.1.9",       # Ophthalmic Photography 16 Bit
    "1.2.840.10008.5.1.4.1.1.10",      # Stereometric Relationship Storage
    "1.2.840.10008.5.1.4.1.1.14.1",    # Ophthalmic Tomography Image Storage
    # Volumetric
    "1.2.840.10008.5.1.4.1.1.13.1.1",  # Breast Tomosynthesis Image Storage
    "1.2.840.10008.5.1.4.1.1.13.1.2",  # Breast Projection X-Ray Image Storage
    "1.2.840.10008.5.1.4.1.1.13.1.3",  # Enhanced Breast Tomosynthesis
}

# 不可显示的模态（跳过：SR 报告、RT 计划等）
_NON_IMAGE_MODALITIES = {"SR", "RTPLAN", "RTDOSE", "RTSTRUCT", "ST"}


class _StudyIndex:
    """单个 Study 的索引与缓存。

    一个目录下可能包含多个 Study（按 StudyInstanceUID 区分），
    每个 Study 有独立的 _StudyIndex，但共享同一个 study_dir。
    """

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
        # 所属目录的 mtime（用于失效检测）
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
            cls._instance._dir_mtimes: dict[str, float] = {}  # type: ignore[attr-defined]
            cls._instance._dirty_dirs: set[str] = set()  # type: ignore[attr-defined]
        return cls._instance

    # ------------------------------------------------------------------ #
    # 对外查询
    # ------------------------------------------------------------------ #
    def list_studies(self) -> list[dict[str, Any]]:
        """列出所有 Study（按 StudyInstanceUID 分组，每个 UID 独立一行）。"""
        root = self._root()
        if not root.exists():
            return []
        # 扫描所有子目录（若 mtime 变化则重新扫描）
        for sub in sorted(p for p in root.iterdir() if p.is_dir()):
            self._scan_dir_if_stale(sub)
        # 返回所有有效 study
        results: list[dict[str, Any]] = []
        for idx in self._studies.values():
            if not idx.series:
                continue
            meta = dict(idx.study_meta)
            meta["study_id"] = idx.study_id
            meta["study_uid"] = idx.study_uid
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
        self.list_studies()  # 确保已扫描
        for idx in self._studies.values():
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
        self.list_studies()
        for idx in self._studies.values():
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
            return pydicom.dcmread(str(path), force=True)
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
        """按 study_id 查找 Study（study_id 即 StudyInstanceUID）。"""
        if not study_id or "/" in study_id or "\\" in study_id or ".." in study_id:
            from app.core.exceptions import CustomException
            raise CustomException(msg="非法的 study_id")
        self.list_studies()  # 确保已扫描
        idx = self._studies.get(study_id)
        if idx is None or not idx.series:
            from app.core.exceptions import CustomException
            raise CustomException(msg="Study 不存在")
        return idx

    def _find_study_by_series(self, series_uid: str) -> _StudyIndex | None:
        for idx in list(self._studies.values()):
            if series_uid in idx.series:
                return idx
        # 可能是新数据，全量刷新一次再查
        self.list_studies()
        for idx in self._studies.values():
            if series_uid in idx.series:
                return idx
        return None

    def _scan_dir_if_stale(self, study_dir: Path) -> None:
        """若目录 mtime 变化则重新扫描（按 StudyUID 分组建索引）。"""
        dir_key = str(study_dir)
        try:
            cur_mtime = study_dir.stat().st_mtime
        except OSError:
            return
        old_mtime = self._dir_mtimes.get(dir_key)
        if old_mtime is not None and abs(cur_mtime - old_mtime) < 1.0:
            return  # 未变化
        self._scan_dir(study_dir, cur_mtime)

    def _scan_dir(self, study_dir: Path, mtime: float) -> None:
        """扫描目录下所有 DICOM 文件，按 StudyInstanceUID 分组建索引。

        每个 StudyInstanceUID 创建独立的 _StudyIndex，study_id 使用 UID。
        匿名化数据（无 StudyUID）回退使用文件名/目录名。
        """
        dir_key = str(study_dir)

        # 收集文件
        files = [p for p in study_dir.iterdir() if p.is_file()]
        if not files:
            files = [p for p in study_dir.rglob("*") if p.is_file()]

        # 按 StudyUID 分组原始数据
        groups: dict[str, dict[str, Any]] = {}  # study_id -> group_data

        for fp in files:
            try:
                ds = pydicom.dcmread(
                    str(fp), stop_before_pixels=True, specific_tags=_SPECIFIC_TAGS,
                    force=True,
                )
            except (InvalidDicomError, OSError, IsADirectoryError):
                continue
            except Exception:
                continue

            sop_class = getattr(ds, "SOPClassUID", "")
            modality = getattr(ds, "Modality", "") or ""
            if modality in _NON_IMAGE_MODALITIES:
                continue
            if sop_class and sop_class not in _IMAGE_SOP_CLASSES:
                continue

            study_uid_val = str(getattr(ds, "StudyInstanceUID", "") or "")
            series_uid = getattr(ds, "SeriesInstanceUID", None)
            sop_uid = getattr(ds, "SOPInstanceUID", None)
            if not series_uid or not sop_uid:
                continue

            # 确定 study_id：优先用 StudyUID，匿名化回退用文件名（无后缀）
            if study_uid_val:
                study_id = study_uid_val
            else:
                study_id = fp.name  # 文件名（不含后缀）
            # 获取或创建分组
            if study_id not in groups:
                groups[study_id] = {
                    "study_uid": study_uid_val or None,
                    "series_map": {},
                    "sop_to_path": {},
                    "study_meta": None,
                }
            g = groups[study_id]

            # 计算 Z 坐标
            position_z = None
            ipp = getattr(ds, "ImagePositionPatient", None)
            if ipp is not None and len(ipp) >= 3:
                try:
                    position_z = float(ipp[2])
                except (TypeError, ValueError):
                    position_z = None
            instance_number = getattr(ds, "InstanceNumber", None)

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
            g["series_map"].setdefault(str(series_uid), []).append(inst)
            g["sop_to_path"][str(sop_uid)] = fp

            # 填充 study 级元数据（仅首个有效文件）
            if g["study_meta"] is None:
                patient_name = _person_name(getattr(ds, "PatientName", None))
                patient_id = getattr(ds, "PatientID", None)
                if not patient_id:
                    patient_id = study_dir.name
                if not patient_name:
                    patient_name = fp.name
                g["study_meta"] = {
                    "patient_id": patient_id,
                    "patient_name": patient_name,
                    "study_uid": study_uid_val or None,
                    "study_description": getattr(ds, "StudyDescription", None),
                    "study_date": getattr(ds, "StudyDate", None),
                    "modality": modality or None,
                }

        # 为每个分组创建/更新 _StudyIndex
        existing_study_ids = {
            sid for sid, idx in self._studies.items()
            if str(idx.study_dir) == dir_key
        }
        new_study_ids = set(groups.keys())

        # 删除该目录下不再存在的 study
        for sid in existing_study_ids - new_study_ids:
            idx = self._studies.pop(sid, None)
            if idx and idx.study_uid:
                self._study_uid_to_id.pop(idx.study_uid, None)

        # 创建/更新 study
        for study_id, g in groups.items():
            with self._scan_lock:
                idx = self._studies.get(study_id)
                if idx is None:
                    idx = _StudyIndex(study_id, study_dir)
                    self._studies[study_id] = idx
                elif str(idx.study_dir) != dir_key:
                    # study_id 冲突但目录不同，跳过（不应发生）
                    continue

                # 填充数据
                idx.study_uid = g["study_uid"]
                idx.study_meta = g["study_meta"] or {}

                # 排序 + 建索引
                for suid, insts in g["series_map"].items():
                    insts.sort(key=_sort_key)
                    for i, inst in enumerate(insts):
                        idx.sop_to_index[inst["sop_uid"]] = (suid, i + 1)

                idx.series = g["series_map"]
                idx.sop_to_path = g["sop_to_path"]
                idx.mtime = mtime

                # 更新 UID 反向索引
                if idx.study_uid:
                    self._study_uid_to_id[idx.study_uid] = study_id

        self._dir_mtimes[dir_key] = mtime


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
