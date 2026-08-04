"""DICOMweb 服务层（供 OHIF Viewer 使用）。

实现标准 DICOMweb 协议的服务接口：
- QIDO-RS：查询 Study/Series/Instance（返回 DICOM JSON）
- WADO-RS：获取 DICOM 实例二进制、元数据、渲染图像
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import status
from pydicom.pixel_data_handlers.util import convert_color_space

from app.config.setting import settings
from app.core.exceptions import CustomException
from app.core.logger import log

from .dicom_json import dataset_to_dicom_json
from .repository import indexer


class DicomService:
    """DICOMweb 服务（OHIF Viewer 对接层）。"""

    # ------------------------------------------------------------------ #
    # QIDO-RS：查询接口（返回 DICOM JSON 数组）
    # ------------------------------------------------------------------ #
    @classmethod
    def query_studies(
        cls,
        study_instance_uids: str | None = None,
        patient_id: str | None = None,
        patient_name: str | None = None,
        study_date: str | None = None,
        modalities_in_study: str | None = None,
    ) -> list[dict[str, Any]]:
        """查询 Study 列表（DICOM JSON 格式）。

        支持 OHIF QIDO-RS 参数：StudyInstanceUIDs, PatientID, PatientName, StudyDate, ModalitiesInStudy。
        """
        studies = indexer.list_studies()
        results: list[dict[str, Any]] = []

        # 解析 StudyInstanceUIDs（支持逗号分隔多个 UID）
        target_uids: set[str] | None = None
        if study_instance_uids:
            target_uids = set(study_instance_uids.split(","))

        for s in studies:
            # 过滤 StudyInstanceUIDs
            if target_uids:
                study_uid = s.get("study_uid") or s.get("study_id")
                if study_uid not in target_uids:
                    continue

            # 过滤 PatientID
            if patient_id and s.get("patient_id") != patient_id:
                continue

            # 过滤 PatientName
            if patient_name and patient_name.lower() not in (s.get("patient_name") or "").lower():
                continue

            # 过滤 StudyDate
            if study_date and s.get("study_date") != study_date:
                continue

            # 过滤 ModalitiesInStudy
            if modalities_in_study:
                study_mods = s.get("modality", "") or ""
                if study_mods not in modalities_in_study.split(","):
                    continue

            # 转为 DICOM JSON
            dicom_json = _study_meta_to_dicom_json(s)
            results.append(dicom_json)

        return results

    @classmethod
    def query_study(cls, study_uid: str) -> dict[str, Any] | None:
        """查询单个 Study（DICOM JSON 格式）。"""
        study = indexer.get_study_by_uid(study_uid)
        if study is None:
            return None
        return _study_meta_to_dicom_json(study)

    @classmethod
    def query_series(cls, study_uid: str) -> list[dict[str, Any]]:
        """查询 Study 下所有 Series（DICOM JSON 格式）。"""
        series_list = indexer.list_series_by_study_uid(study_uid)
        results: list[dict[str, Any]] = []
        for s in series_list:
            results.append(_series_meta_to_dicom_json(s, study_uid))
        return results

    @classmethod
    def query_series_by_uid(cls, series_uid: str) -> dict[str, Any] | None:
        """查询单个 Series（DICOM JSON 格式）。"""
        series = indexer.get_series_by_uid(series_uid)
        if series is None:
            return None
        # 需要找到对应的 study_uid
        study_uid = _find_study_uid_for_series(series_uid)
        return _series_meta_to_dicom_json(series, study_uid)

    @classmethod
    def query_instances(cls, series_uid: str) -> list[dict[str, Any]]:
        """查询 Series 下所有 Instance（DICOM JSON 格式）。"""
        instances = indexer.list_instances(series_uid)
        results: list[dict[str, Any]] = []
        for inst in instances:
            results.append(_instance_meta_to_dicom_json(inst))
        return results

    @classmethod
    def query_instance(cls, sop_uid: str) -> dict[str, Any] | None:
        """查询单个 Instance（DICOM JSON 格式）。"""
        inst = indexer.get_instance_by_uid(sop_uid)
        if inst is None:
            return None
        return _instance_meta_to_dicom_json(inst)

    # ------------------------------------------------------------------ #
    # WADO-RS：获取二进制 / metadata / rendered
    # ------------------------------------------------------------------ #
    @classmethod
    def get_instance_file(cls, sop_uid: str) -> Path:
        """获取 DICOM 原始文件路径（WADO-RS 二进制）。"""
        path = indexer.get_instance_path(sop_uid)
        if path is None:
            raise CustomException(
                msg="Instance 不存在",
                code=status.HTTP_404_NOT_FOUND,
                status_code=status.HTTP_404_NOT_FOUND,
            )
        # 路径安全校验
        try:
            root = Path(settings.DICOM_DATA_DIR).resolve()
            if not path.resolve(strict=False).is_relative_to(root):
                raise CustomException(
                    msg="路径非法",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
        except OSError as e:
            log.error("解析 DICOM 路径失败: %s", e)
            raise CustomException(
                msg="文件不可访问",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return path

    @classmethod
    def get_instance_metadata(cls, sop_uid: str) -> dict[str, Any] | None:
        """获取 Instance 的 DICOM JSON 元数据（WADO-RS /metadata）。"""
        ds = indexer.get_instance_dataset(sop_uid)
        if ds is None:
            return None
        return dataset_to_dicom_json(ds)

    @classmethod
    def get_series_metadata(cls, series_uid: str) -> list[dict[str, Any]]:
        """获取 Series 下所有 Instance 的 DICOM JSON 元数据。"""
        instances = indexer.list_instances(series_uid)
        results: list[dict[str, Any]] = []
        for inst in instances:
            ds = indexer.get_instance_dataset(inst["sop_uid"])
            if ds is not None:
                results.append(dataset_to_dicom_json(ds))
        return results

    @classmethod
    def get_study_metadata(cls, study_uid: str) -> list[dict[str, Any]]:
        """获取 Study 下所有 Instance 的 DICOM JSON 元数据。"""
        series_list = indexer.list_series_by_study_uid(study_uid)
        results: list[dict[str, Any]] = []
        for s in series_list:
            instances = indexer.list_instances(s["series_uid"])
            for inst in instances:
                ds = indexer.get_instance_dataset(inst["sop_uid"])
                if ds is not None:
                    results.append(dataset_to_dicom_json(ds))
        return results

    @classmethod
    def get_rendered_instance(
        cls,
        sop_uid: str,
        frame_number: int | None = None,
        quality: int = 75,
    ) -> tuple[bytes, str]:
        """获取渲染后的 PNG 图像（WADO-RS /rendered）。

        返回 (image_bytes, content_type)。
        """
        ds = indexer.get_instance_dataset(sop_uid)
        if ds is None:
            raise CustomException(
                msg="Instance 不存在",
                code=status.HTTP_404_NOT_FOUND,
                status_code=status.HTTP_404_NOT_FOUND,
            )

        try:
            from PIL import Image as PILImage
        except ImportError:
            raise CustomException(
                msg="服务器缺少 Pillow 依赖，无法渲染图像",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # 获取像素数据
        if not hasattr(ds, "pixel_array"):
            raise CustomException(
                msg="Instance 无像素数据",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        pixel_array = ds.pixel_array

        # 多帧支持
        if pixel_array.ndim == 3:
            # 判断是否为多帧灰度数据 (frames, height, width)
            if pixel_array.shape[2] not in (3, 4):
                # 多帧灰度数据，取指定帧或第一帧
                if frame_number is not None and frame_number > 0:
                    if frame_number <= pixel_array.shape[0]:
                        pixel_array = pixel_array[frame_number - 1]
                    else:
                        raise CustomException(
                            msg=f"Frame {frame_number} 不存在",
                            status_code=status.HTTP_404_NOT_FOUND,
                        )
                else:
                    # 默认取第一帧
                    pixel_array = pixel_array[0]
            else:
                # RGB/RGBA 数据
                if frame_number is not None and frame_number > 0:
                    if frame_number <= pixel_array.shape[0]:
                        pixel_array = pixel_array[frame_number - 1]
                    else:
                        raise CustomException(
                            msg=f"Frame {frame_number} 不存在",
                            status_code=status.HTTP_404_NOT_FOUND,
                        )

        # 转换为 PIL Image
        bits_allocated = getattr(ds, "BitsAllocated", 8)
        photometric = getattr(ds, "PhotometricInterpretation", "MONOCHROME2")

        if pixel_array.ndim == 2:
            # 单通道灰度
            if bits_allocated <= 8:
                mode = "L"
            else:
                mode = "I;16" if bits_allocated <= 16 else "F"
            img = PILImage.fromarray(pixel_array, mode=mode)
        elif pixel_array.ndim == 3:
            # RGB 或多帧
            if photometric in ("RGB", "YBR_FULL", "YBR_FULL_422", "YBR_ICT", "YBR_RCT"):
                # 转换颜色空间
                try:
                    convert_color_space(ds, "RGB")
                    pixel_array = ds.pixel_array
                except Exception:
                    pass
            if pixel_array.shape[2] == 3:
                img = PILImage.fromarray(pixel_array, mode="RGB")
            elif pixel_array.shape[2] == 4:
                img = PILImage.fromarray(pixel_array, mode="RGBA")
            else:
                img = PILImage.fromarray(pixel_array)
        else:
            raise CustomException(
                msg="无法解码像素数据",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # MONOCHROME1 反色
        if photometric == "MONOCHROME1":
            img = PILImage.fromarray(255 - np.array(img))

        # 转为 PNG
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue(), "image/png"

    @classmethod
    def get_instance_frames(
        cls,
        sop_uid: str,
        frame_number: int,
    ) -> tuple[bytes, str]:
        """获取指定帧的原始像素数据（WADO-RS /frames/{frameNumber}）。

        返回 (multipart_bytes, content_type)。
        """
        ds = indexer.get_instance_dataset(sop_uid)
        if ds is None:
            raise CustomException(
                msg="Instance 不存在",
                code=status.HTTP_404_NOT_FOUND,
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if not hasattr(ds, "pixel_array"):
            raise CustomException(
                msg="Instance 无像素数据",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        pixel_array = ds.pixel_array

        # 多帧提取
        if pixel_array.ndim >= 3:
            if frame_number <= 0 or frame_number > pixel_array.shape[0]:
                raise CustomException(
                    msg=f"Frame {frame_number} 不存在",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
            frame_data = pixel_array[frame_number - 1]
        else:
            if frame_number != 1:
                raise CustomException(
                    msg=f"Frame {frame_number} 不存在（单帧图像）",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
            frame_data = pixel_array

        # 将帧数据编码为原始字节
        buf = io.BytesIO()
        try:
            import numpy as np
            np.save(buf, frame_data, allow_pickle=False)
        except Exception:
            # 回退：直接 tobytes
            raw_bytes = frame_data.tobytes() if hasattr(frame_data, "tobytes") else bytes(frame_data)
            buf.write(raw_bytes)

        return buf.getvalue(), "application/octet-stream"

    @classmethod
    def get_instance_frame_multipart(
        cls,
        sop_uid: str,
        frame_number: int,
    ) -> tuple[bytes, str]:
        """获取指定帧的 multipart/related 响应（WADO-RS frames 完整路径）。

        返回 (body_bytes, content_type)。
        """
        # 复用 get_instance_file 的路径安全校验
        file_path = cls.get_instance_file(sop_uid)

        import pydicom
        try:
            ds = pydicom.dcmread(str(file_path), force=True)
        except Exception as e:
            log.error("读取 DICOM 失败: %s", e)
            raise CustomException(
                msg="读取 DICOM 失败",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if not hasattr(ds, "pixel_array"):
            raise CustomException(
                msg="Instance 无像素数据",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        pixel_array = ds.pixel_array

        # 提取指定帧
        if pixel_array.ndim >= 3:
            if frame_number <= 0 or frame_number > pixel_array.shape[0]:
                raise CustomException(
                    msg=f"Frame {frame_number} 不存在 (共 {pixel_array.shape[0]} 帧)",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
            frame_data = pixel_array[frame_number - 1]
        else:
            if frame_number != 1:
                raise CustomException(
                    msg=f"Frame {frame_number} 不存在（单帧图像）",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
            frame_data = pixel_array

        raw_bytes = frame_data.tobytes() if hasattr(frame_data, "tobytes") else bytes(frame_data)
        boundary = b"--dicom-frame-boundary"
        body = (
            boundary + b"\r\n"
            b"Content-Type: application/octet-stream\r\n"
            b"Content-Length: " + str(len(raw_bytes)).encode() + b"\r\n"
            b"\r\n" + raw_bytes + b"\r\n"
            + boundary + b"--\r\n"
        )
        content_type = "multipart/related; type=application/octet-stream; boundary=dicom-frame-boundary"
        return body, content_type

    @classmethod
    def get_thumbnail(
        cls,
        sop_uid: str,
        viewport: str | None = None,
    ) -> tuple[bytes, str]:
        """获取 Instance 的 PNG 缩略图（WADO-RS thumbnail）。

        返回 (image_bytes, content_type)。
        """
        # 复用 get_instance_file 的路径安全校验
        file_path = cls.get_instance_file(sop_uid)

        import pydicom
        try:
            ds = pydicom.dcmread(str(file_path), force=True)
        except Exception as e:
            log.error("读取 DICOM 失败: %s", e)
            raise CustomException(
                msg="读取 DICOM 失败",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if not hasattr(ds, "pixel_array"):
            raise CustomException(
                msg="Instance 无像素数据",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from PIL import Image as PILImage
        except ImportError:
            raise CustomException(
                msg="服务器缺少 Pillow 依赖，无法生成缩略图",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        pixel_array = ds.pixel_array
        photometric = getattr(ds, "PhotometricInterpretation", "MONOCHROME2")

        # 取第一帧（多帧取第 1 帧作为缩略图）
        frame = pixel_array
        if pixel_array.ndim == 3:
            if photometric in ("RGB", "YBR_FULL", "YBR_FULL_422") and pixel_array.shape[2] in (3, 4):
                frame = pixel_array
            else:
                frame = pixel_array[0]
        elif pixel_array.ndim > 3:
            frame = pixel_array[0]

        # 转为 PIL Image
        import numpy as np

        if frame.ndim == 2:
            # 灰度图：归一化到 8-bit
            if frame.dtype != np.uint8:
                f_min = float(frame.min())
                f_max = float(frame.max())
                if f_max > f_min:
                    scaled = (frame.astype(np.float32) - f_min) / (f_max - f_min) * 255.0
                    frame_u8 = scaled.astype(np.uint8)
                else:
                    frame_u8 = np.zeros_like(frame, dtype=np.uint8)
            else:
                frame_u8 = frame
            img = PILImage.fromarray(frame_u8, mode="L")
            # MONOCHROME1 反色
            if photometric == "MONOCHROME1":
                img = PILImage.eval(img, lambda x: 255 - x)
        elif frame.ndim == 3 and frame.shape[2] == 3:
            img = PILImage.fromarray(frame, mode="RGB")
        elif frame.ndim == 3 and frame.shape[2] == 4:
            img = PILImage.fromarray(frame, mode="RGBA")
        else:
            raise CustomException(
                msg="不支持的像素格式",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # 解析 viewport 并缩放（保持比例）
        target_w, target_h = None, None
        if viewport:
            try:
                parts = viewport.split(",")
                if len(parts) >= 2:
                    target_w = max(1, int(parts[0]))
                    target_h = max(1, int(parts[1]))
            except (ValueError, TypeError):
                target_w, target_h = None, None

        if target_w and target_h:
            orig_w, orig_h = img.size
            ratio = min(target_w / orig_w, target_h / orig_h)
            new_w = max(1, int(orig_w * ratio))
            new_h = max(1, int(orig_h * ratio))
            img = img.resize((new_w, new_h), PILImage.LANCZOS)

        # 输出 PNG
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue(), "image/png"

    @classmethod
    def get_series_thumbnail(
        cls,
        series_uid: str,
        viewport: str | None = None,
    ) -> tuple[bytes, str]:
        """获取 Series 的 PNG 缩略图（取该 Series 的中间帧 Instance）。"""
        instances = indexer.list_instances(series_uid)
        if not instances:
            raise CustomException(
                msg="Series 下无 Instance，无法生成缩略图",
                code=status.HTTP_404_NOT_FOUND,
                status_code=status.HTTP_404_NOT_FOUND,
            )
        # 取中间帧作为代表
        mid_idx = len(instances) // 2
        sop_uid = instances[mid_idx]["sop_uid"]
        return cls.get_thumbnail(sop_uid=sop_uid, viewport=viewport)

def _study_meta_to_dicom_json(meta: dict[str, Any]) -> dict[str, Any]:
    """将 Study 元数据转为 DICOM JSON 对象。"""
    result: dict[str, Any] = {}

    # PatientID (0010,0020)
    if meta.get("patient_id"):
        result["00100020"] = {"vr": "LO", "Value": [str(meta["patient_id"])]}

    # PatientName (0010,0010)
    if meta.get("patient_name"):
        result["00100010"] = {"vr": "PN", "Value": [str(meta["patient_name"])]}

    # StudyInstanceUID (0020,000D)
    if meta.get("study_uid"):
        result["0020000D"] = {"vr": "UI", "Value": [str(meta["study_uid"])]}

    # StudyDescription (0008,1030)
    if meta.get("study_description"):
        result["00081030"] = {"vr": "LO", "Value": [str(meta["study_description"])]}

    # StudyDate (0008,0020)
    if meta.get("study_date"):
        result["00080020"] = {"vr": "DA", "Value": [str(meta["study_date"])]}

    # ModalitiesInStudy (0008,0061)
    if meta.get("modality"):
        result["00080061"] = {"vr": "CS", "Value": [str(meta["modality"])]}

    # NumberOfStudyRelatedSeries (0020,1206)
    if meta.get("series_count"):
        result["00201206"] = {"vr": "US", "Value": [int(meta["series_count"])]}

    return result


def _series_meta_to_dicom_json(meta: dict[str, Any], study_uid: str | None = None) -> dict[str, Any]:
    """将 Series 元数据转为 DICOM JSON 对象。"""
    result: dict[str, Any] = {}

    # SeriesInstanceUID (0020,000E)
    if meta.get("series_uid"):
        result["0020000E"] = {"vr": "UI", "Value": [str(meta["series_uid"])]}

    # StudyInstanceUID (0020,000D)
    if study_uid:
        result["0020000D"] = {"vr": "UI", "Value": [str(study_uid)]}

    # SeriesDescription (0008,103E)
    if meta.get("series_description"):
        result["0008103E"] = {"vr": "LO", "Value": [str(meta["series_description"])]}

    # Modality (0008,0060)
    if meta.get("modality"):
        result["00080060"] = {"vr": "CS", "Value": [str(meta["modality"])]}

    # NumberOfSeriesRelatedInstances (0020,1208)
    if meta.get("instance_count"):
        result["00201208"] = {"vr": "US", "Value": [int(meta["instance_count"])]}

    # Rows (0028,0010)
    if meta.get("rows"):
        result["00280010"] = {"vr": "US", "Value": [int(meta["rows"])]}

    # Columns (0028,0011)
    if meta.get("columns"):
        result["00280011"] = {"vr": "US", "Value": [int(meta["columns"])]}

    # SliceThickness (0018,0050)
    if meta.get("slice_thickness"):
        result["00180050"] = {"vr": "DS", "Value": [float(meta["slice_thickness"])]}

    # PixelSpacing (0028,0030)
    if meta.get("pixel_spacing"):
        result["00280030"] = {"vr": "DS", "Value": meta["pixel_spacing"]}

    # WindowCenter (0028,1050)
    if meta.get("window_center"):
        result["00281050"] = {"vr": "DS", "Value": [float(meta["window_center"])]}

    # WindowWidth (0028,1051)
    if meta.get("window_width"):
        result["00281051"] = {"vr": "DS", "Value": [float(meta["window_width"])]}

    return result


def _instance_meta_to_dicom_json(meta: dict[str, Any]) -> dict[str, Any]:
    """将 Instance 元数据转为 DICOM JSON 对象。"""
    result: dict[str, Any] = {}

    # SOPInstanceUID (0008,0018)
    if meta.get("sop_uid"):
        result["00080018"] = {"vr": "UI", "Value": [str(meta["sop_uid"])]}

    # SeriesInstanceUID (0020,000E)
    if meta.get("series_uid"):
        result["0020000E"] = {"vr": "UI", "Value": [str(meta["series_uid"])]}

    # InstanceNumber (0020,0013)
    if meta.get("instance_number"):
        result["00200013"] = {"vr": "IS", "Value": [str(meta["instance_number"])]}

    return result


def _find_study_uid_for_series(series_uid: str) -> str | None:
    """反向查找 Series 所属的 Study UID。"""
    # 扫描所有 study
    studies = indexer.list_studies()
    for s in studies:
        if s.get("study_uid"):
            series_list = indexer.list_series_by_study_uid(s["study_uid"])
            for ser in series_list:
                if ser["series_uid"] == series_uid:
                    return s["study_uid"]
    return None
