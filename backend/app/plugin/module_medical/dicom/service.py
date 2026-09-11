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
    # 文件注册（供外部模块调用，把 DICOM 文件/整个 study 文件夹注册到 indexer 内存索引）
    # ------------------------------------------------------------------ #
    @classmethod
    def register_file(cls, file_path: Path) -> dict[str, Any] | None:
        """注册单个 DICOM 文件到 indexer 内存索引。

        注册后即可通过 StudyInstanceUID 走 DICOMweb 接口预览。
        返回 {"study_uid", "series_uid", "sop_uid"}；失败返回 None。
        """
        return indexer.register_file(file_path)

    @classmethod
    def register_folder(cls, folder_path: Path) -> dict[str, Any] | None:
        """批量注册一个 study 文件夹里全部 DICOM 文件。

        典型场景：一个文件夹就是一个完整 Study，
        里面是很多「单帧独立文件」的 instances，可能没有 .dcm 后缀。
        返回 {"study_uid", "series_count", "instance_count"}；目录里没图像返回 None。
        """
        return indexer.register_folder(folder_path)

    # ------------------------------------------------------------------ #
    # QIDO-RS：查询接口（扁平字段 + DICOM JSON tag 双写）
    #
    # 为什么"双写"？因为当前路由（/dicom/studies, /dicom/series/{series}/instances 等）
    # 被两套消费方共用：
    #   1) 自研 Vue DicomViewer（内部契约：扁平字段 study_id / series_uid /
    #      sop_uid / window_width / window_center / position_z / index 等）。
    #   2) 标准 DICOMweb / OHIF Viewer（QIDO-RS：按 tag 键，如 0020000D /
    #      00080018 / 00281050 / ...，vr + Value 数组）。
    #
    # 任何一方缺失字段都会直接触发"整个片子全灰"：
    #   - DicomViewer 拿不到 sop_uid → wadouri: 路径拼不出来 → 404 → 无图
    #   - DicomViewer 拿不到 window_width/window_center → 跳过 applyWindow
    #     → cornerstone 默认 min-max stretch 在 SV1 解码结果上非常灰
    #   - OHIF 拿不到 0020000E 等 tag → QIDO 序列不展开
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
        """查询 Study 列表（扁平 + DICOM JSON tag 双写）。"""
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

            # 扁平字段（Vue DicomViewer 用）+ DICOM JSON tag（OHIF 用）
            merged: dict[str, Any] = {}
            # 先写扁平原始字段
            for k, v in (s or {}).items():
                if v is None:
                    continue
                merged[k] = v
            # 再叠 DICOM JSON tag（同名校验不会发生，因为 key 完全不同域）
            merged.update(_study_meta_to_dicom_json(s))
            # 兜底 study_id：Vue DicomViewer loadStudy 按 study_id === props.studyId 匹配
            if not merged.get("study_id"):
                merged["study_id"] = merged.get("study_uid") or ""
            results.append(merged)

        return results

    @classmethod
    def query_study(cls, study_uid: str) -> dict[str, Any] | None:
        """查询单个 Study（扁平 + DICOM JSON tag 双写）。"""
        study = indexer.get_study_by_uid(study_uid)
        if study is None:
            return None
        merged: dict[str, Any] = {}
        for k, v in (study or {}).items():
            if v is None:
                continue
            merged[k] = v
        merged.update(_study_meta_to_dicom_json(study))
        if not merged.get("study_id"):
            merged["study_id"] = merged.get("study_uid") or ""
        return merged

    @classmethod
    def query_series(cls, study_uid: str) -> list[dict[str, Any]]:
        """查询 Study 下所有 Series（扁平 + DICOM JSON tag 双写）。"""
        series_list = indexer.list_series_by_study_uid(study_uid)
        results: list[dict[str, Any]] = []
        for s in series_list:
            merged: dict[str, Any] = {}
            for k, v in (s or {}).items():
                if v is None:
                    continue
                merged[k] = v
            merged.update(_series_meta_to_dicom_json(s, study_uid))
            results.append(merged)
        return results

    @classmethod
    def query_series_by_uid(cls, series_uid: str) -> dict[str, Any] | None:
        """查询单个 Series（扁平 + DICOM JSON tag 双写）。"""
        series = indexer.get_series_by_uid(series_uid)
        if series is None:
            return None
        study_uid = _find_study_uid_for_series(series_uid)
        merged: dict[str, Any] = {}
        for k, v in (series or {}).items():
            if v is None:
                continue
            merged[k] = v
        merged.update(_series_meta_to_dicom_json(series, study_uid))
        return merged

    @classmethod
    def query_instances(cls, series_uid: str) -> list[dict[str, Any]]:
        """查询 Series 下所有 Instance（扁平 + DICOM JSON tag 双写）。

        注：Vue DicomViewer 直接消费扁平字段（sop_uid / index / position_z
        / window_width / window_center）来拼 wadouri: imageId 以及应用默认
        窗位；任何一个字段缺失都会表现为"主图全灰 / 切片全乱序"。
        """
        instances = indexer.list_instances(series_uid)
        results: list[dict[str, Any]] = []
        for inst in instances:
            merged: dict[str, Any] = {}
            for k, v in (inst or {}).items():
                if v is None:
                    continue
                merged[k] = v
            merged.update(_instance_meta_to_dicom_json(inst))
            results.append(merged)
        return results

    @classmethod
    def query_instance(cls, sop_uid: str) -> dict[str, Any] | None:
        """查询单个 Instance（扁平 + DICOM JSON tag 双写）。"""
        inst = indexer.get_instance_by_uid(sop_uid)
        if inst is None:
            return None
        merged: dict[str, Any] = {}
        for k, v in (inst or {}).items():
            if v is None:
                continue
            merged[k] = v
        merged.update(_instance_meta_to_dicom_json(inst))
        return merged

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

    # ------------------------------------------------------------------ #
    # WADO-RS：辅助常量与工具
    # ------------------------------------------------------------------ #
    # TransferSyntaxUID → frames part Content-Type（告诉 cornerstone 选哪条解码管线）
    # 注意：DICOM PS3.18 Table 6.1.3-1 把 JPEG Baseline/Lossless/SV1 统一写成 image/jpeg，
    # 但 cornerstoneWADOImageLoader 的 getTransferSyntaxForContentType() 在没命中
    # transfer-syntax 参数时会用 Content-Type 做兜底映射，它的默认字典是：
    #   image/jpeg         → .4.50 Baseline（仅 8-bit，浏览器 Image.decode 可解）
    #   image/jll          → .4.70 SV1 Lossless（走 jpeg-lossless-decoder-js）
    # 所以 .4.57/.4.70 若写成 image/jpeg，前端会用 Baseline 管线去解 Lossless 字节，
    # 结果 huffman 表不匹配 → 输出全 0 像素 → "主图整图灰色"（而缩略图是后端渲染 PNG，所以一直正常）。
    # 这里用 cornerstone 识别的 image/jll 来精确命中 SV1 解码器。
    _TS_FRAME_CONTENT_TYPE: dict[str, str] = {
        "1.2.840.10008.1.2.1":     "application/octet-stream",  # Explicit VR Little Endian
        "1.2.840.10008.1.2.2":     "application/octet-stream",  # Explicit VR Big Endian
        "1.2.840.10008.1.2":       "application/octet-stream",  # Implicit VR Little Endian
        # JPEG Baseline (Process 1) / Extended (Process 2 & 4)
        "1.2.840.10008.1.2.4.50":  "image/jpeg",
        "1.2.840.10008.1.2.4.51":  "image/jpeg",
        # JPEG Lossless (Process 14) / JPEG Lossless SV1 (Process 14 Selection Value 1)
        # → 用 cornerstone 专用 image/jll 映射 1.2.840.10008.1.2.4.70，避免被当成 Baseline
        "1.2.840.10008.1.2.4.57":  "image/jll",
        "1.2.840.10008.1.2.4.70":  "image/jll",
        # JPEG-LS / JPEG-LS Lossless
        "1.2.840.10008.1.2.4.80":  "image/jls",
        "1.2.840.10008.1.2.4.81":  "image/jls",
        # JPEG 2000 (Lossless / Lossy)
        "1.2.840.10008.1.2.4.90":  "image/jp2",
        "1.2.840.10008.1.2.4.91":  "image/jp2",
        # RLE Lossless
        "1.2.840.10008.1.2.5":     "image/x-dicom-rle",
    }

    @classmethod
    def _frame_content_type_for(cls, ds: "pydicom.Dataset") -> tuple[str, str]:
        """返回 (transfer_syntax_uid, frame_part_content_type)。

        压缩封装用对应 MIME 触发客户端解码；未压缩 / 未知 → application/octet-stream。
        """
        transfer_syntax = ""
        fm = getattr(ds, "file_meta", None)
        if fm is not None:
            transfer_syntax = str(getattr(fm, "TransferSyntaxUID", "") or "")

        ctype = cls._TS_FRAME_CONTENT_TYPE.get(transfer_syntax)
        if ctype:
            return transfer_syntax, ctype

        # 兜底：如果 PixelData 明显是封装头（压缩），但 TransferSyntaxUID 缺失或
        # 不在已知映射里，则默认走 JPEG Lossless 管线（本项目绝大多数 CT/MRI
        # 压片使用 JPEG Lossless SV1 .4.70；image/jll 命中 cornerstone 的
        # .4.70 解码器，比 image/jpeg → .4.50 Baseline 错配风险小）。
        try:
            from pydicom.tag import Tag
            ptag = Tag(0x7FE0, 0x0010)
            if ptag in ds:
                raw = ds[ptag].value
                if isinstance(raw, (bytes, bytearray)) and bytes(raw[:4]) == b"\xFE\xFF\x00\xE0":
                    return transfer_syntax, "image/jll"
        except Exception:
            pass
        return transfer_syntax, "application/octet-stream"

    @classmethod
    def _normalize_metadata_numerics(
        cls,
        result: dict[str, Any],
    ) -> None:
        """确保 Cornerstone 关心的数值 tag（DS/US/SS/FL/FD/IS/AS）都成了 JSON Number。

        dcmjs / Cornerstone 读取 DICOM JSON 时，DS ("200.0" 字符串) 和
        FL/FD 的数值字段如果是字符串，**不会自动 parseInt / parseFloat**：
          - (0028,1052/1053) RescaleIntercept/Slope 字符串 → Modality LUT 跳过
            → 直接用 stored values 进 VOI window，stored 值对 CT 范围大概 0..3000
            → WC=60 WW=400 的窗口几乎全落在 0..460 里，只有极少量像素落在
              窗口内被拉到全白，剩下"整个片子都是灰色"
          - (0028,1050/1051) WindowCenter/Width 字符串 → VOI 窗口不生效
          - (0028,0100~0103) Bits/HighBit/PixelRepresentation 字符串 →
            解析 16-bit MONOCHROME2 像素时按 8-bit 读 → 全灰/错乱

        虽然 dicom_json.py 里 `_encode_scalar` 已经按 VR 转了，但 pydicom 有些
        MultiValue / MultiValue(int) 等边界情况可能漏过，这里做二次保险。
        只在 "Cornerstone 关心的 tag" 上做，不扫全部 tag 以省时间。
        """

        # key = tag8 (十六进制大写)，value = 期望的类型（int|float） + 是否多值允许
        CRITICAL_TAGS: dict[str, tuple[type, bool]] = {
            # ---- Image Pixel Description Module ----
            "00280002": (int, False),    # SamplesPerPixel (US)
            "00280010": (int, False),    # Rows (US)
            "00280011": (int, False),    # Columns (US)
            "00280100": (int, False),    # BitsAllocated (US)
            "00280101": (int, False),    # BitsStored (US)
            "00280102": (int, False),    # HighBit (US)
            "00280103": (int, False),    # PixelRepresentation (US): 0 unsigned / 1 signed
            "00280006": (int, False),    # PlanarConfiguration (US)
            # ---- Modality & VOI LUT ----
            "00281052": (float, False),  # RescaleIntercept (DS)
            "00281053": (float, False),  # RescaleSlope (DS)
            "00281050": (float, True),   # WindowCenter (DS, multi-valued)
            "00281051": (float, True),   # WindowWidth  (DS, multi-valued)
            "00281054": (str, False),    # RescaleType (LO): 字符串保留
            # ---- Pixel Spacing / Image Position / Image Orientation (float multi-valued) ----
            "00280030": (float, True),   # PixelSpacing (DS)
            "00200032": (float, True),   # ImagePositionPatient (DS)
            "00200037": (float, True),   # ImageOrientationPatient (DS)
            "00200011": (int, False),    # SeriesNumber (IS)
            "00200013": (int, False),    # InstanceNumber (IS)
            "00200100": (int, False),    # TemporalPositionIdentifier (IS)
            "00280008": (int, False),    # NumberOfFrames (IS) - optional
            # ---- CT X-ray ----
            "00181150": (float, False),  # ExposureTime (IS)
            "00181151": (float, False),  # XRayTubeCurrent (IS)
            "00181120": (float, False),  # GantryDetectorTilt (DS)
            "00181140": (str, False),    # RotationDirection (CS): 字符串
        }

        for tag, (num_type, multi) in CRITICAL_TAGS.items():
            node = result.get(tag)
            if node is None:
                continue
            vals = node.get("Value")
            if not isinstance(vals, list) or not vals:
                continue

            coerced: list[Any] = []
            for v in vals:
                if v is None:
                    continue
                if num_type is str:
                    coerced.append(str(v))
                    continue
                if isinstance(v, bool):
                    coerced.append(int(v) if num_type is int else float(v))
                    continue
                if isinstance(v, num_type) or (num_type is float and isinstance(v, (int, float))):
                    coerced.append(num_type(v))
                    continue
                try:
                    if num_type is int:
                        coerced.append(int(float(v)))
                    else:
                        coerced.append(float(v))
                except (ValueError, TypeError):
                    # 不能转的就丢（Cornerstone 缺 tag 会走合理默认）
                    pass
            if coerced:
                node["Value"] = coerced if multi else [coerced[0]]
            else:
                # 全坏掉 → 移除这个 tag，避免 cornerstone 读到字符串"nan"之类的直接跳过
                if tag in result:
                    del result[tag]

        # ---- Rescale Intercept/Slope 缺失时注入默认值 ----
        # CT 的 HU 换算依赖 rescale；如果没有 cornerstone 不会把 stored 值换成 HU，
        # 用 WC/WW 的"HU窗口"直接去夹 stored 范围会导致整张图灰。
        if "00281052" not in result:
            result["00281052"] = {"vr": "DS", "Value": [0.0]}
        if "00281053" not in result or (
            isinstance(result["00281053"].get("Value"), list)
            and len(result["00281053"]["Value"]) > 0
            and result["00281053"]["Value"][0] == 0
        ):
            # Slope=0 会让 cornerstone 爆 0 除
            result["00281053"] = {"vr": "DS", "Value": [1.0]}

        # ---- WindowCenter / WindowWidth 缺失时：按 Modality 注入兜底 ----
        wc = result.get("00281050", {}).get("Value", []) if "00281050" in result else []
        ww = result.get("00281051", {}).get("Value", []) if "00281051" in result else []
        wc_valid: list[float] = [w for w in wc if isinstance(w, (int, float)) and not isinstance(w, bool)]
        ww_valid: list[float] = [w for w in ww if isinstance(w, (int, float)) and not isinstance(w, bool) and float(w) > 0]
        if not wc_valid or not ww_valid:
            modality = ""
            if "00080060" in result and isinstance(result["00080060"].get("Value"), list) and result["00080060"]["Value"]:
                modality = str(result["00080060"]["Value"][0] or "").upper()
            fallback = {
                "CT":   {"wc": [40.0, 300.0, 1500.0],   "ww": [400.0, 1500.0, 2500.0]},  # brain / soft-tissue / bone
                "MR":   {"wc": [500.0],  "ww": [2000.0]},
                "PT":   {"wc": [2.0],    "ww": [4.0]},
                "US":   {"wc": [128.0],  "ww": [256.0]},
                "CR":   {"wc": [2048.0], "ww": [4095.0]},
                "DX":   {"wc": [2048.0], "ww": [4095.0]},
                "XA":   {"wc": [2048.0], "ww": [4095.0]},
            }
            pick = fallback.get(modality, {"wc": [0.0], "ww": [255.0]})
            result["00281050"] = {"vr": "DS", "Value": [float(x) for x in pick["wc"]]}
            result["00281051"] = {"vr": "DS", "Value": [float(x) for x in pick["ww"]]}
            wc_valid, ww_valid = result["00281050"]["Value"], result["00281051"]["Value"]

        # ---- WC/WW 去重：飞利浦部分 CT 序列把同一个窗口写两遍 (60,60)/(400,400)
        # cornerstone 当成两个独立 window，UI 会重复但不影响显示；但如果
        # "两个 WC 相同 / 两个 WW 不同" 时，就会出现 "index 错配对"（例如 WC=[60,-600]
        # WW=[400,400] → 窗口#2 被当成 WC=-600,WW=400 的 bone？实际上那是 60/1500 软组织窗，
        # 导致 viewer 默认展示的窗口对不上，整张图"灰蒙蒙一片没有对比度"）。
        # 正确做法：把 WC/WW 打包成对，去重；如果两者长度不一样就截成最短。
        pairs: list[tuple[float, float]] = []
        for pair in zip(wc_valid, ww_valid):
            if pair not in pairs:
                pairs.append(pair)
        if not pairs:
            pairs = [(40.0, 400.0)]
        result["00281050"] = {"vr": "DS", "Value": [p[0] for p in pairs]}
        result["00281051"] = {"vr": "DS", "Value": [p[1] for p in pairs]}

        # ---- PhotometricInterpretation 缺失兜底 (CT 基本是 MONOCHROME2) ----
        if "00280004" not in result:
            result["00280004"] = {"vr": "CS", "Value": ["MONOCHROME2"]}

    @classmethod
    def get_instance_metadata(cls, sop_uid: str) -> dict[str, Any] | None:
        """获取 Instance 的 DICOM JSON 元数据（WADO-RS /metadata）。

        - 若 RGB 图像的 PlanarConfiguration=1，会被改为 0
          （与 frames 接口实际返回的字节布局保持一致，供 OHIF/cornerstone 正确解析）。
        - 显式写入 (0002,0010) TransferSyntaxUID / (0002,0001) FileMetaInformationVersion
          到结果里；cornerstoneWADOImageLoader / dcmjs 会用 (00020010) 选解码管线和反解 TS，
          否则即使 frames 返回正确格式字节，它也可能拿不到 "这个字节流属于什么传输语法"。
        - 对 Cornerstone 关心的数值 tag 做二次标准化，保证 DS/US/FL/FD 全是 JSON Number。
        """
        ds = indexer.get_instance_dataset(sop_uid)
        if ds is None:
            return None

        ts_uid, _ = cls._frame_content_type_for(ds)

        result = dataset_to_dicom_json(ds)

        # 写入 File Meta Information Group (0002,xxxx) — 虽然 DICOM JSON 规范允许没有 meta，
        # 但实际 WADO-RS metadata 回 (00020010) 会让解码器选择更稳。
        result.setdefault("00020001", {"vr": "OB", "InlineBinary": "AAE="})  # version 0x00 0x01
        if ts_uid:
            result["00020010"] = {"vr": "UI", "Value": [ts_uid]}

        # 关键数值 tag 标准化 + 兜底挂窗/rescale
        cls._normalize_metadata_numerics(result)

        # 若已转成按像素交错，同步把 PlanarConfiguration 改为 0
        try:
            samples_per_pixel = int(getattr(ds, "SamplesPerPixel", 1) or 1)
            planar = int(getattr(ds, "PlanarConfiguration", 0) or 0)
            photometric = str(getattr(ds, "PhotometricInterpretation", "") or "")
        except Exception:
            samples_per_pixel = 1
            planar = 0
            photometric = ""
        if samples_per_pixel >= 3 and planar == 1 and photometric in (
            "RGB", "RGBA", "YBR_FULL", "YBR_FULL_422", "YBR_PARTIAL_422"
        ):
            # (0028,0006) PlanarConfiguration → 0（按像素交错）。
            # 注意别写成 (0028,0106)：那是 Smallest Image Pixel Value，
            # 写错会导致 PlanarConfiguration 仍是 1，客户端把交错字节按平面解读，
            # 出现 R/G/B 通道错乱（frames 接口发的确是交错字节）。
            result["00280006"] = {"vr": "US", "Value": [0]}
        return result

    @classmethod
    def get_series_metadata(cls, series_uid: str) -> list[dict[str, Any]]:
        """获取 Series 下所有 Instance 的 DICOM JSON 元数据。"""
        instances = indexer.list_instances(series_uid)
        results: list[dict[str, Any]] = []
        for inst in instances:
            ds = indexer.get_instance_dataset(inst["sop_uid"])
            if ds is not None:
                results.append(cls.get_instance_metadata(inst["sop_uid"]))
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
                    results.append(cls.get_instance_metadata(inst["sop_uid"]))
        return results

    @classmethod
    def _parse_float_list(cls, value: Any) -> list[float]:
        """把 DICOM 元素 (可能 MultiValue/str/int/float/list) 统一成 list[float]，空则返回 []。"""
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            out: list[float] = []
            for v in value:
                try:
                    out.append(float(v))
                except (ValueError, TypeError):
                    continue
            return out
        try:
            return [float(value)]
        except (ValueError, TypeError):
            # MultiValue/DSFloat 能直接转，字符串数字也能
            pass
        if isinstance(value, str):
            parts = [p for p in value.replace("\\", ",").split(",") if p.strip()]
            out = []
            for p in parts:
                try:
                    out.append(float(p.strip()))
                except (ValueError, TypeError):
                    continue
            return out
        return []

    @classmethod
    def _default_windows_by_modality(cls, ds: "pydicom.Dataset") -> list[tuple[float, float]]:
        """当 DICOM 文件自身完全没写 WC/WW 时，才给一个"不挑"的显示窗口。

        规则：按 stored 值的 1%~99% 分位数做窗口，**不做按 Modality 的"特定窗位"强行注入**。
        这样缩略图和主图的灰度不会被人为调成骨窗/脑窗/肺窗等"特定调调"，只是让像素范围能落在 0~255
        上。如果文件里自己写了 WindowCenter/WindowWidth，这里永远不会走到。
        """
        # 调用方会确保 arr 传进来；这里先声明，后面在 render_gray_8bit 里真算。
        return []

    @classmethod
    def _render_gray_8bit(
        cls,
        ds: "pydicom.Dataset",
        pixel_array: "np.ndarray",
    ) -> tuple["np.ndarray", str]:
        """DICOM 标准灰度渲染（缩略图 /rendered 共用同一条路，绝不做"缩略图特调"）。

        仅两步：
          1) Modality LUT: HU = stored * RescaleSlope + RescaleIntercept
          2) VOI LUT:      clamp(HU, WC-WW/2, WC+WW/2) → linear to 0..255

        严格规则：
          - 如果文件里有 WindowCenter / WindowWidth（无论字符串/数字/重复值）→ 用它的第一对
          - 没有的话 → 按 stored 值 1%~99% 分位数自动求窗（丢弃 1% 极端像素比如冷热点伪影，
            避免一张图里的单个超亮像素把 99% 的正常像素都挤到中间灰带里）。
          - 不做 min→0 max→255 的"全范围拉伸"（那会导致"整张都是灰色"）。
          - 不按 Modality 做默认骨窗/脑窗/肺窗的特调（避免缩略图和主图因为用不同默认窗口而看起来不一样）。
        """
        photometric = str(getattr(ds, "PhotometricInterpretation", "MONOCHROME2") or "") or "MONOCHROME2"

        # ---------- 1) Modality LUT ----------
        ri_list = cls._parse_float_list(getattr(ds, "RescaleIntercept", None))
        rs_list = cls._parse_float_list(getattr(ds, "RescaleSlope", None))
        intercept = ri_list[0] if ri_list else 0.0
        slope = rs_list[0] if rs_list else 1.0
        if slope == 0:
            slope = 1.0

        arr = pixel_array.astype(np.float32)
        if intercept != 0.0 or slope != 1.0:
            arr = arr * slope + intercept

        # ---------- 2) VOI Window: 优先用文件自己写的 ----------
        wc_list = cls._parse_float_list(getattr(ds, "WindowCenter", None))
        ww_list = cls._parse_float_list(getattr(ds, "WindowWidth", None))
        pairs: list[tuple[float, float]] = []
        for wc, ww in zip(wc_list, ww_list):
            if ww > 0:
                pairs.append((float(wc), float(ww)))

        if not pairs:
            # 文件没写窗口：1%~99% 分位数求一个显示友好的自动窗
            flat = arr.ravel()
            lo_val = float(np.quantile(flat, 0.01))
            hi_val = float(np.quantile(flat, 0.99))
            if hi_val <= lo_val:
                lo_val, hi_val = float(flat.min()), float(flat.max())
            center = (lo_val + hi_val) / 2.0
            width = max(hi_val - lo_val, 1.0)
            pairs = [(float(center), float(width))]

        window_center, window_width = pairs[0]
        ww = float(max(window_width, 1.0))
        wc = float(window_center)
        low = wc - (ww - 1.0) / 2.0
        high = wc + (ww - 1.0) / 2.0

        clipped = np.clip(arr, low, high)
        if high > low:
            out_u8 = ((clipped - low) / (high - low) * 255.0 + 0.5).astype(np.uint8)
        else:
            out_u8 = np.zeros_like(arr, dtype=np.uint8)
        return out_u8, photometric

    @classmethod
    def _decode_pixel_array(cls, ds: "pydicom.Dataset", frame_number: int | None = None):
        """取 ds 的像素 numpy 数组（多帧时可指定帧号）。

        SV1 (JPEG Lossless Process 14 Selection Value 1) 等压缩封装像素解码在 Pillow
        原生不支持，只有装了 gdcm>=3.0.10 或 pylibjpeg+pylibjpeg-libjpeg，pydicom 才能
        通过 pixel_array 解出来。没有装就直接抛明确的异常，不要让调用方拿到空像素数组当
        作图片显示（视觉上是整张灰色）。
        """
        from pydicom.tag import Tag

        ptag = Tag(0x7FE0, 0x0010)
        if ptag not in ds:
            raise CustomException(
                msg="Instance 无像素数据",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        ts_uid, _ = cls._frame_content_type_for(ds)
        is_compressed_ts = ts_uid and ts_uid in {
            ts for ts, ctype in cls._TS_FRAME_CONTENT_TYPE.items() if ctype != "application/octet-stream"
        }

        nf = int(getattr(ds, "NumberOfFrames", 1) or 1)

        # 方案 A：压缩封装 → 先尝试 Pillow 解普通 JPEG (SOF0/SOF2 baseline/progressive)
        # JPEG Lossless SV1 / JPEG-LS / JPEG 2000 Pillow 原生不支持，直接跳过这条路
        if is_compressed_ts and ts_uid in {"1.2.840.10008.1.2.4.50", "1.2.840.10008.1.2.4.51"}:
            try:
                frame_bytes = cls._extract_frame_bytes_from_pixel_data(
                    ds, 1 if frame_number is None else frame_number
                )
            except Exception:
                frame_bytes = None

            if frame_bytes:
                try:
                    from PIL import Image as PILImage
                    with PILImage.open(io.BytesIO(frame_bytes)) as im:
                        if im.mode == "I;16":
                            arr = np.array(im).astype(np.uint16)
                        elif im.mode == "L":
                            arr = np.array(im).astype(np.uint8)
                        elif im.mode in ("RGB", "RGBA"):
                            arr = np.array(im)
                        else:
                            arr = np.array(im.convert("I"))
                            if arr.dtype not in (np.uint8, np.uint16, np.int32):
                                arr = np.array(im.convert("L"))
                        return arr
                except Exception as e:
                    log.warning("Pillow 解 JPEG baseline 帧失败（%s），降级 pixel_array: %s", ts_uid, e)

        # 方案 B：走 pydicom pixel_array（真·需要 gdcm / pylibjpeg-libjpeg 等解码插件）
        try:
            pixel_array = ds.pixel_array
        except RuntimeError as e:
            msg = str(e)
            # 典型报错里带 "gdcm - requires gdcm..." 或 "pylibjpeg - requires pylibjpeg..."
            hint = ""
            if "gdcm" in msg and "pylibjpeg" in msg:
                hint = "（推荐生产环境：pip install pylibjpeg pylibjpeg-libjpeg）"
            log.error(
                "pixel_array 解码失败：缺少 DICOM 像素解码插件。TransferSyntax=%s%s %s",
                ts_uid or "(unknown)", hint, msg
            )
            raise CustomException(
                msg=f"无法解码 DICOM 像素：缺少解码插件 (gdcm>=3.0.10 或 pylibjpeg+pylibjpeg-libjpeg)。{hint}",
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if frame_number is None:
            return pixel_array

        if pixel_array.ndim == 2:
            if frame_number != 1:
                raise CustomException(
                    msg=f"Frame {frame_number} 不存在（单帧图像）",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
            return pixel_array

        # ndim >= 3
        total_frames = pixel_array.shape[0]
        if pixel_array.ndim == 3 and pixel_array.shape[2] in (3, 4):
            # 单帧彩色（第 3 维是 samples 不是 frame）
            if frame_number != 1:
                raise CustomException(
                    msg=f"Frame {frame_number} 不存在（单帧彩色图像）",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
            return pixel_array
        if frame_number < 1 or frame_number > total_frames:
            raise CustomException(
                msg=f"Frame {frame_number} 不存在（共 {total_frames} 帧）",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return pixel_array[frame_number - 1]

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
        from pydicom.tag import Tag
        if Tag(0x7FE0, 0x0010) not in ds:
            raise CustomException(
                msg="Instance 无像素数据",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from PIL import Image as PILImage
        except ImportError:
            raise CustomException(
                msg="服务器缺少 Pillow 依赖，无法渲染图像",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        pixel_array = cls._decode_pixel_array(ds, frame_number=frame_number)

        # 多帧：若解出来是 ndim==3 且 last dim 非 3/4 → 视为 (frames,H,W)，默认取第一帧
        if pixel_array.ndim >= 3:
            if pixel_array.ndim == 3 and pixel_array.shape[2] not in (3, 4):
                pixel_array = pixel_array[0]
            elif pixel_array.ndim > 3:
                pixel_array = pixel_array[0]

        if pixel_array.ndim == 2:
            # 灰度图：按 Modality LUT + VOI Window 挂窗到 0~255
            frame_u8, photometric = cls._render_gray_8bit(ds, pixel_array)
            img = PILImage.fromarray(frame_u8, mode="L")
            # MONOCHROME1 反色（0=白 255=黑）
            if photometric == "MONOCHROME1":
                img = PILImage.fromarray(255 - np.array(img, dtype=np.uint8))
        elif pixel_array.ndim == 3 and pixel_array.shape[2] == 3:
            img = PILImage.fromarray(pixel_array, mode="RGB")
        elif pixel_array.ndim == 3 and pixel_array.shape[2] == 4:
            img = PILImage.fromarray(pixel_array, mode="RGBA")
        else:
            raise CustomException(
                msg="不支持的像素格式",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # 转为 PNG
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue(), "image/png"

    @classmethod
    def _frame_from_pixel_array(cls, pixel_array: Any, frame_number: int) -> Any:
        """从解码后的 pixel_array 中按 frame_number 取出单帧。

        关键：只有「帧维」才在 shape[0]。单帧彩色（RGB/RGBA）的形状是
        (Rows, Columns, Samples)，最后一维是采样数而不是帧数；若误把 shape[0]
        当帧数，512 行的图会被切成 1 行（只取到第 0 行 800×3 个字节）。

        形状判定：
          - ndim == 2                       → 单帧灰度 (H, W)
          - ndim == 3 且 shape[2] ∈ (3, 4)  → 单帧彩色 (H, W, SPP)
          - ndim == 3 其他                  → 多帧灰度 (Frames, H, W)
          - ndim >= 4                       → 多帧彩色 (Frames, H, W, SPP)

        单帧图像仅接受 frame_number == 1，其余抛 404。
        """
        if pixel_array.ndim == 2 or (
            pixel_array.ndim == 3 and pixel_array.shape[2] in (3, 4)
        ):
            is_multi_frame = False
        else:
            is_multi_frame = True

        if not is_multi_frame:
            if frame_number != 1:
                raise CustomException(
                    msg=f"Frame {frame_number} 不存在（单帧图像）",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
            return pixel_array

        total_frames = int(pixel_array.shape[0])
        if frame_number < 1 or frame_number > total_frames:
            raise CustomException(
                msg=f"Frame {frame_number} 不存在（共 {total_frames} 帧）",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return pixel_array[frame_number - 1]

    @classmethod
    def _frame_to_bytes(cls, frame_data: Any) -> bytes:
        """把单帧数组转成 WADO-RS 的裸像素字节。

        pydicom 在 reshape 阶段已按 PlanarConfiguration 做过转置（见
        pydicom.pixel_data_handlers.util.reshape_pixel_array），因此
        ``tobytes()`` 出来的 C 序就是「按像素交错」的 RGBRGB...，
        与 /metadata 中把 PlanarConfiguration 改写为 0 的行为保持一致。
        这里不要再做平面→交错转换，否则会把正确数据二次打乱。
        """
        if hasattr(frame_data, "tobytes"):
            return frame_data.tobytes()
        return bytes(frame_data)

    @classmethod
    def get_instance_frames(
        cls,
        sop_uid: str,
        frame_number: int,
    ) -> tuple[bytes, str]:
        """获取指定帧的原始像素数据（非 multipart 的简化 frames 接口）。

        与 get_instance_frame_multipart 同策略：
        - 压缩 TS：不解压，按封装字节直通，并返回匹配的 Content-Type（image/jpeg 等）
        - 未压缩 TS：pixel_array 解码，失败回退 encaps 切字节，返回 application/octet-stream
        """
        from pydicom.tag import Tag

        ds = indexer.get_instance_dataset(sop_uid)
        if ds is None:
            raise CustomException(
                msg="Instance 不存在",
                code=status.HTTP_404_NOT_FOUND,
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if Tag(0x7FE0, 0x0010) not in ds:
            raise CustomException(
                msg="Instance 无像素数据",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        transfer_syntax, part_content_type = cls._frame_content_type_for(ds)
        is_compressed_ts = transfer_syntax and transfer_syntax in (
            ts for ts, ctype in cls._TS_FRAME_CONTENT_TYPE.items() if ctype != "application/octet-stream"
        )

        raw_bytes: bytes
        if is_compressed_ts:
            # 压缩封装 → 不解压直通，客户端自解
            raw_bytes = cls._extract_frame_bytes_from_pixel_data(ds, frame_number)
            return raw_bytes, part_content_type

        # 未压缩 → 尝试 pixel_array 解码
        try:
            pixel_array = ds.pixel_array
            frame_data = cls._frame_from_pixel_array(pixel_array, frame_number)
            # 直接返回裸像素字节（按像素交错）。此前用 np.save 封装成 .npy 容器，
            # 客户端按 application/octet-stream 裸像素解析必然失败。
            return cls._frame_to_bytes(frame_data), "application/octet-stream"
        except CustomException:
            raise
        except Exception as e:
            log.warning("pixel_array 解码失败，回退到 PixelData 字节切分: %s", e)

        raw_bytes = cls._extract_frame_bytes_from_pixel_data(ds, frame_number)
        return raw_bytes, part_content_type

    @classmethod
    def get_instance_frame_multipart(
        cls,
        sop_uid: str,
        frame_number: int,
    ) -> tuple[bytes, str]:
        """获取指定帧的 multipart/related 响应（WADO-RS frames 完整路径）。

        决策顺序：
          1) 若 DICOM TransferSyntax 为压缩封装格式（JPEG Baseline / JPEG Lossless /
             JPEG2000 / RLE 等）：不解压，直通 PixelData 封装字节，Content-Type
             设为 application/octet-stream 或带传输语法 ID，由 OHIF/cornerstone
             自身的 JPEG/RLE 解码器在客户端渲染（服务器不用装 gdcm/pylibjpeg）。
          2) 未压缩格式：优先 pixel_array 解码，失败再回退到字节切分。

        返回 (body_bytes, content_type)。
        """
        # 复用 get_instance_file 的路径安全校验
        file_path = cls.get_instance_file(sop_uid)

        import pydicom
        from pydicom.tag import Tag

        try:
            ds = pydicom.dcmread(str(file_path), force=True)
        except Exception as e:
            log.error("读取 DICOM 失败: %s", e)
            raise CustomException(
                msg="读取 DICOM 失败",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if Tag(0x7FE0, 0x0010) not in ds:
            raise CustomException(
                msg="Instance 无像素数据",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # 读 TransferSyntax：若明确是压缩封装，直接直通封装字节（客户端解压缩）
        transfer_syntax, _part_ct_first = cls._frame_content_type_for(ds)
        is_compressed_ts = bool(transfer_syntax) and transfer_syntax in {
            ts for ts, ctype in cls._TS_FRAME_CONTENT_TYPE.items() if ctype != "application/octet-stream"
        }

        raw_bytes: bytes
        if is_compressed_ts:
            # 压缩封装：用 encaps 解包，跳过 pixel_array（避免要求 gdcm / pylibjpeg）
            raw_bytes = cls._extract_frame_bytes_from_pixel_data(ds, frame_number)
        else:
            # 未压缩：走 pixel_array 解码，失败再回退字节切分
            try:
                pixel_array = ds.pixel_array
                frame_data = cls._frame_from_pixel_array(pixel_array, frame_number)
                # pydicom 已按 PlanarConfiguration 转置，tobytes() 即按像素交错，
                # 与 /metadata 里 PlanarConfiguration=0 的声明一致，无需再转换。
                raw_bytes = cls._frame_to_bytes(frame_data)
            except CustomException:
                raise
            except Exception as e:
                log.warning(
                    "pixel_array 解码失败，回退到 PixelData 字节切分: %s", e
                )
                raw_bytes = cls._extract_frame_bytes_from_pixel_data(ds, frame_number)

        # WADO-RS frames 响应（DICOM PS3.18 §6.1.3.1 + §8.8 Retrieve Frames 规范）：
        #
        # 顶层 Content-Type（最关键）：
        #   multipart/related; type="application/octet-stream"; transfer-syntax="<TS_UID>"; boundary=xxx
        #
        # --- 为什么这样写？（这是 thumbnail 能出图、主图 frames 一直错误的根因）---
        # 缩略图走 /thumbnail，返回的是服务端渲染好的 image/png，浏览器直接显示，所以一直正常。
        # 主图走 /frames 则把像素字节丢给 CornerstoneWADOImageLoader 选 codec 解出来再挂窗：
        #   - 如果 top header type 写 image/jpeg → Cornerstone 走 "Web Image Loader"，
        #     用浏览器 Image.decode() 解；浏览器**不支持 JPEG Lossless SV1** → decode error / 全黑 / 发生错误请重试。
        #   - 如果 part Content-Type 写 application/octet-stream 但 top header 没写
        #     transfer-syntax 参数 → Cornerstone 当成"未压缩裸像素"去读 JPEG 压缩字节 → 整张图均匀灰色。
        #
        # 正确的 WADO-RS 选 codec 规则是：按顶层 `transfer-syntax="<TS_UID>"`（dcm-parameter，
        # PS3.18 6.1.3.1.8.1.2 明确定义）。例如：
        #   1.2.840.10008.1.2.4.70 (SV1) → jpeg-lossless-decoder-js （纯 JS，绕开浏览器 Image.decode）
        #   1.2.840.10008.1.2.4.81      → JPEG-LS codec
        #   1.2.840.10008.1.2.4.91      → JPEG 2000 openjpeg
        #   1.2.840.10008.1.2.5         → RLE decoder
        #   1.2.840.10008.1.2.1         → 直接按原生像素数组解
        #
        # 同时我们在 /metadata 注入了 (0002,0010) TransferSyntaxUID 做兜底，两者一致就命中正确分支。
        boundary = b"--dicom-frame-boundary"

        # ---- Part Content-Type（每个 frame 的头）最关键：按 TransferSyntax 精确写 ----
        # WADO-RS §6.1.3.1.8.2 / PS3.18 Table 6.1.3-1 明确定义：
        #   image/jpeg        - JPEG Baseline / JPEG Extended / JPEG Lossless (Process 14 SV1 在内 .4.50/.4.51/.4.57/.4.70)
        #   image/jls         - JPEG-LS (.4.80/.4.81)
        #   image/jp2         - JPEG 2000 JP2/JPX (.4.90/.4.91)
        #   image/x-dicom-rle - RLE Lossless (.1.2.5)
        #   application/octet-stream - 原生未压缩像素 (.1.2/.1.2.1/.1.2.2)
        #
        # 如果 part Content-Type 写错（例如 JPEG Lossless SV1 写成 application/octet-stream），
        # cornerstoneWADOImageLoader 会把 JPEG 字节流当成"未压缩 16-bit 像素"解读 → 整张
        # 图均匀灰色（这正是你现在看到的"主图灰，缩略图正常"的原因：缩略图是服务端渲染 PNG，
        # 主图是 cornerstone 接错 codec 自己在客户端算的 16-bit 错位像素）。
        _, part_content_type = cls._frame_content_type_for(ds)
        if not part_content_type:
            part_content_type = "application/octet-stream"

        if not transfer_syntax:
            # 极少数文件没带 TS UID：降级只声明 application/octet-stream，Cornerstone 会按字节头猜
            top_content_type = (
                'multipart/related; type="application/octet-stream"; boundary=dicom-frame-boundary'
            )
        else:
            # 顶层 type 要和 part Content-Type 一致（PS3.18 6.1.3.1：type 取 part content-type 的值）
            top_content_type = (
                f'multipart/related; type="{part_content_type}"; '
                f'transfer-syntax="{transfer_syntax}"; boundary=dicom-frame-boundary'
            )

        body = (
            boundary + b"\r\n"
            + f"Content-Type: {part_content_type}\r\n".encode("ascii")
            + b"\r\n" + raw_bytes + b"\r\n"
            + boundary + b"--\r\n"
        )
        return body, top_content_type

    @classmethod
    def _extract_frame_bytes_from_pixel_data(
        cls, ds: "pydicom.Dataset", frame_number: int
    ) -> bytes:
        """从 PixelData 按字节切分指定帧，不触发像素解码。

        - 碎片封装（Encapsulated）：用 pydicom.encaps 解包
        - 原始未封装：按 BitsAllocated * Rows * Columns * SamplesPerPixel 计算每帧字节数

        判断封装会优先用 TransferSyntaxUID；若缺失，会尝试 decode_data_sequence，
        成功即视为封装（JPEG 压缩数据几乎都走封装格式写入，哪怕 file_meta 被剥掉）。
        """
        from pydicom.encaps import decode_data_sequence

        # 稳当地拿到 PixelData 原始字节（不触发任何 decode）
        from pydicom.tag import Tag
        ptag = Tag(0x7FE0, 0x0010)
        if ptag not in ds:
            raise CustomException(
                msg="Instance 无像素数据 (0028,0100)",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        raw_val = ds[ptag].value
        if isinstance(raw_val, (bytes, bytearray)):
            pixel_bytes = bytes(raw_val)
        else:
            pixel_bytes = bytes(raw_val)

        # 读 TransferSyntaxUID（兼容 file_meta 缺失或 force=True 读裸数据集的场景）
        transfer_syntax = ""
        fm = getattr(ds, "file_meta", None)
        if fm is not None:
            transfer_syntax = str(getattr(fm, "TransferSyntaxUID", "") or "")

        # 封装传输语法白名单
        is_encapsulated = bool(transfer_syntax) and (
            transfer_syntax.startswith("1.2.840.10008.1.2.4.")
            or transfer_syntax == "1.2.840.10008.1.2.5"      # RLE Lossless
        )

        number_of_frames = int(getattr(ds, "NumberOfFrames", 1) or 1)

        if is_encapsulated:
            try:
                frames = decode_data_sequence(pixel_bytes)
            except Exception as e:
                log.warning("封装帧解析失败，退回整段 PixelData: %s", e)
                frames = None

            if frames:
                if frame_number < 1 or frame_number > len(frames):
                    raise CustomException(
                        msg=f"Frame {frame_number} 不存在（共 {len(frames)} 帧）",
                        status_code=status.HTTP_404_NOT_FOUND,
                    )
                return bytes(frames[frame_number - 1])

        # 仍无法判定封装：如果开头有封装特征字节（Item tag FFFE,E000）也尝试一次
        if not is_encapsulated and pixel_bytes[:4] == b"\xFE\xFF\x00\xE0":
            try:
                frames = decode_data_sequence(pixel_bytes)
                if frames:
                    if frame_number < 1 or frame_number > len(frames):
                        raise CustomException(
                            msg=f"Frame {frame_number} 不存在（共 {len(frames)} 帧）",
                            status_code=status.HTTP_404_NOT_FOUND,
                        )
                    return bytes(frames[frame_number - 1])
            except CustomException:
                raise
            except Exception:
                pass

        # 未封装 / 封装解析失败后回退：按未压缩像素尺寸切
        bits_allocated = int(getattr(ds, "BitsAllocated", 8) or 8)
        rows = int(getattr(ds, "Rows", 0) or 0)
        cols = int(getattr(ds, "Columns", 0) or 0)
        samples_per_pixel = int(getattr(ds, "SamplesPerPixel", 1) or 1)
        bytes_per_frame = (bits_allocated // 8) * rows * cols * samples_per_pixel

        if bytes_per_frame == 0 or number_of_frames <= 1:
            if frame_number != 1:
                # 单帧（或元信息缺失无法切片）：frame 必须=1
                # 但如果 pixel_bytes 够大且明确不是多帧，给个更精准的错
                raise CustomException(
                    msg=f"Frame {frame_number} 不存在（单帧 SOP 仅 frame=1）",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
            # 返回整段（单帧 = 所有 pixel_bytes）
            return pixel_bytes

        if frame_number < 1 or frame_number > number_of_frames:
            raise CustomException(
                msg=f"Frame {frame_number} 不存在（共 {number_of_frames} 帧）",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        start = (frame_number - 1) * bytes_per_frame
        end = start + bytes_per_frame
        return pixel_bytes[start:end]

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
        from pydicom.tag import Tag
        try:
            ds = pydicom.dcmread(str(file_path), force=True)
        except Exception as e:
            log.error("读取 DICOM 失败: %s", e)
            raise CustomException(
                msg="读取 DICOM 失败",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if Tag(0x7FE0, 0x0010) not in ds:
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

        # 解码像素 + 和 Cornerstone 一致的 Modality LUT + VOI Window 挂窗
        pixel_array = cls._decode_pixel_array(ds, frame_number=1)

        # 如果解出来仍是多帧，缩略图取第一帧
        if pixel_array.ndim >= 3:
            if pixel_array.ndim == 3 and pixel_array.shape[2] not in (3, 4):
                # (frames, H, W) → frames[0]
                pixel_array = pixel_array[0]
            elif pixel_array.ndim > 3:
                pixel_array = pixel_array[0]

        if pixel_array.ndim == 2:
            # 灰度：严格按 Rescale + WC/WW 挂窗（不要再用 min→0 max→255 拉伸，否则整张图灰蒙蒙没有对比度）
            frame_u8, photometric = cls._render_gray_8bit(ds, pixel_array)
            img = PILImage.fromarray(frame_u8, mode="L")
            if photometric == "MONOCHROME1":
                img = PILImage.fromarray(255 - np.array(img, dtype=np.uint8))
        elif pixel_array.ndim == 3 and pixel_array.shape[2] == 3:
            img = PILImage.fromarray(pixel_array, mode="RGB")
        elif pixel_array.ndim == 3 and pixel_array.shape[2] == 4:
            img = PILImage.fromarray(pixel_array, mode="RGBA")
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
    """将 Instance 元数据转为 DICOM JSON 对象。

    注：QIDO-RS 的 Instance 结果虽然只"要求"必需 UID/序号，但自研 Vue viewer
    在 wadouri 模式下仍通过扁平字段取 window_center/window_width/position_z；
    这里把 DICOM JSON tag 也补齐，以便 OHIF/自研两套消费者都不缺关键信息：
      - 00281050/51  WC/WW（VOI）
      - 00200032       ImagePositionPatient（Z 轴排序）
      - 00201041       SliceLocation（兜底排序）
    """
    result: dict[str, Any] = {}

    # SOPInstanceUID (0008,0018)
    if meta.get("sop_uid"):
        result["00080018"] = {"vr": "UI", "Value": [str(meta["sop_uid"])]}

    # SeriesInstanceUID (0020,000E)
    if meta.get("series_uid"):
        result["0020000E"] = {"vr": "UI", "Value": [str(meta["series_uid"])]}

    # InstanceNumber (0020,0013)
    if meta.get("instance_number") not in (None, ""):
        try:
            result["00200013"] = {"vr": "IS", "Value": [int(float(meta["instance_number"]))]}
        except (ValueError, TypeError):
            result["00200013"] = {"vr": "IS", "Value": [str(meta["instance_number"])]}

    # WindowCenter (0028,1050)
    if meta.get("window_center") not in (None, ""):
        try:
            result["00281050"] = {"vr": "DS", "Value": [float(meta["window_center"])]}
        except (ValueError, TypeError):
            pass

    # WindowWidth (0028,1051)
    _ww = meta.get("window_width")
    if _ww not in (None, ""):
        try:
            ww = float(_ww)
            if ww > 0:
                result["00281051"] = {"vr": "DS", "Value": [ww]}
        except (ValueError, TypeError):
            pass

    # ImagePositionPatient (0020,0032)：从 position_z 拼一个粗略值（仅用于 Z 轴排序，不用于测量）
    pos_z = meta.get("position_z")
    if pos_z not in (None, ""):
        try:
            z = float(pos_z)
            # 只明确知道 Z；X/Y 填 0.0 不至于把序列定位搞崩
            result["00200032"] = {"vr": "DS", "Value": [0.0, 0.0, z]}
        except (ValueError, TypeError):
            pass

    # SliceLocation (0020,1041)
    if pos_z not in (None, ""):
        try:
            result["00201041"] = {"vr": "DS", "Value": [float(pos_z)]}
        except (ValueError, TypeError):
            pass

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
