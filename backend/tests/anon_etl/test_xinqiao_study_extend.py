"""issue-12 新桥 viewer 适配 — study 索引扩展的 seam 测试。

seam 划分（与新加的两个函数对应）：
- discover_sibling_series_dirs(center_code, patient_id, image_path) → list[Path]
  纯函数：从 image_path 推断同 study 的所有 series 目录（布局 A/B/D 需要扫兄弟，
  布局 C / zhujiang / shengyi 直接返回 [image_path]）。

- ensure_study_indexed(study_uid, *, conn=None) → dict | None
  编排：PG 反查 (center_code, patient_id, image_path) → 调 discover → register_folder
  每个兄弟目录。

这两个函数解决「新桥布局 A/B/D 的 image_path 是字典序最小 series 目录，viewer
只看得到 1/N series」的根因：service 入口加 hook 让 indexer 把同 study 所有
兄弟目录都 register。
"""
from __future__ import annotations

from pathlib import Path

# scripts/ 不存在；本测试在 backend/tests/anon_etl/ 下，sys.path 不需要改

# ---------- DICOM fixture 工具（与 test_audit_zhujiang_study_uid 同款） ----------


def _make_dcm(path: Path, study_uid: str, series_uid: str, sop_uid: str,
              modality: str = "CT", sop_class: str = "1.2.840.10008.5.1.4.1.1.2") -> None:
    """生成最小 DICOM 文件。"""
    from pydicom.dataset import FileDataset, FileMetaDataset

    file_meta = FileMetaDataset()
    file_meta.TransferSyntaxUID = "1.2.840.10008.1.2.1"
    file_meta.MediaStorageSOPClassUID = sop_class
    file_meta.MediaStorageSOPInstanceUID = sop_uid
    ds = FileDataset(str(path), {}, file_meta=file_meta, preamble=b"\0" * 128)
    ds.PatientID = "TEST"
    ds.PatientName = "TEST"
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid
    ds.SOPInstanceUID = sop_uid
    ds.SOPClassUID = sop_class
    ds.Modality = modality
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    path.parent.mkdir(parents=True, exist_ok=True)
    ds.save_as(str(path))


# ---------- seam 1: discover_sibling_series_dirs ----------


class TestDiscoverSiblingSeriesDirs:
    """布局识别：从 image_path 推断同 study 的全部 series 目录。"""

    def test_layout_a_returns_all_img_pid_siblings(self, tmp_path: Path) -> None:
        """新桥布局 A：image_path 是 `img_<PID>_<UID>`，兄弟目录都在同 parent 下
        且都匹配 `img_<PID>_*` 前缀。
        """
        from app.plugin.module_medical.dicom.service import DicomService

        root = tmp_path / "xinqiao" / "4_tjj"
        # image_path 指向字典序最小 series 目录（只有 1 个 .dcm）
        image_path = root / "img_00720185_1.2.840.A.1"
        image_path.mkdir(parents=True)
        # 兄弟目录（同前缀但不同 SeriesUID）
        (root / "img_00720185_1.2.840.A.2").mkdir()
        (root / "img_00720185_1.2.840.A.3").mkdir()
        # 不相关的目录（不同 PID / 不同 prefix）— 不应被收
        (root / "img_99999999_X").mkdir()
        (root / "other_dir").mkdir()

        siblings = DicomService.discover_sibling_series_dirs(
            center_code="xinqiao",
            patient_id="00720185",
            image_path=image_path,
        )
        names = sorted(p.name for p in siblings)
        assert names == [
            "img_00720185_1.2.840.A.1",
            "img_00720185_1.2.840.A.2",
            "img_00720185_1.2.840.A.3",
        ]

    def test_layout_b_handles_letter_prefix_pid(self, tmp_path: Path) -> None:
        """布局 B 中存在字母前缀 PID（plan-xinqiao §0.5 实测 8 个）。"""
        from app.plugin.module_medical.dicom.service import DicomService

        root = tmp_path / "xinqiao" / "5_yxl"
        image_path = root / "img_T04774748_X1"
        image_path.mkdir(parents=True)
        (root / "img_T04774748_X2").mkdir()

        siblings = DicomService.discover_sibling_series_dirs(
            center_code="xinqiao",
            patient_id="T04774748",
            image_path=image_path,
        )
        assert len(siblings) == 2
        assert all("T047747" in p.name for p in siblings)

    def test_layout_c_md5_returns_self(self, tmp_path: Path) -> None:
        """布局 C：image_path 是 study 根（无 img_<PID>_ 前缀），
        没兄弟，返回 [image_path]。
        """
        from app.plugin.module_medical.dicom.service import DicomService

        # MD5 是 32 hex
        md5_dir = tmp_path / "5_yxl" / "abcdef0123456789abcdef0123456789"
        md5_dir.mkdir(parents=True)
        image_path = md5_dir / "1.2.840.STUDYUIDXYZ"
        image_path.mkdir()

        siblings = DicomService.discover_sibling_series_dirs(
            center_code="xinqiao",
            patient_id="some_pid",
            image_path=image_path,
        )
        assert siblings == [image_path]

    def test_zhujiang_returns_self(self, tmp_path: Path) -> None:
        """zhujiang study 目录命名是 `<PID>_<StudyUID>/`，无 `img_` 前缀；
        函数应返回 [image_path]。
        """
        from app.plugin.module_medical.dicom.service import DicomService

        image_path = tmp_path / "zhujiang_dicom" / "20250111" / "4564470_1.2.840.X"
        image_path.mkdir(parents=True)

        siblings = DicomService.discover_sibling_series_dirs(
            center_code="zhujiang",
            patient_id="4564470",
            image_path=image_path,
        )
        assert siblings == [image_path]

    def test_missing_parent_returns_self(self, tmp_path: Path) -> None:
        """image_path 父目录不存在（容错）：返回 [image_path]，不抛。"""
        from app.plugin.module_medical.dicom.service import DicomService

        image_path = tmp_path / "nonexistent_parent" / "img_X_Y"

        siblings = DicomService.discover_sibling_series_dirs(
            center_code="xinqiao",
            patient_id="X",
            image_path=image_path,
        )
        assert siblings == [image_path]


# ---------- seam 2: ensure_study_indexed ----------


class TestEnsureStudyIndexed:
    """编排：PG 反查 + discover + register_folder。"""

    def test_registers_all_sibling_dirs_for_xinqiao(self, tmp_path: Path) -> None:
        """新桥布局 A：image_path 是字典序最小 series，函数要 register_folder
        同 study 的所有 series 兄弟。
        """
        from app.plugin.module_medical.dicom.service import DicomService

        study_uid = "1.2.999.fake.study.A"
        series_a = "1.2.999.fake.series.A.1"
        series_b = "1.2.999.fake.series.A.2"

        root = tmp_path / "xinqiao" / "4_tjj"
        for s_uid in (series_a, series_b):
            d = root / f"img_00720185_{s_uid}"
            d.mkdir(parents=True)
            for i in range(2):
                _make_dcm(
                    d / f"instance_{i}.dcm",
                    study_uid=study_uid,
                    series_uid=s_uid,
                    sop_uid=f"{s_uid}.{i}",
                )
        # image_path = 字典序最小
        image_path = root / f"img_00720185_{series_a}"

        # Mock PG 连接：返回 (center_code='xinqiao', patient_id='00720185', image_path)
        class FakeConn:
            def execute(self, _sql, _params=None):
                class _Cur:
                    def fetchone(inner_self):
                        return ("xinqiao", "00720185", str(image_path))
                return _Cur()

        registered: list[str] = []
        original_register_folder = DicomService.register_folder.__func__

        @classmethod
        def spy_register_folder(cls, folder_path):
            registered.append(str(folder_path))
            return original_register_folder(cls, folder_path)

        try:
            DicomService.register_folder = spy_register_folder  # type: ignore[assignment]
            result = DicomService.ensure_study_indexed(
                study_uid=study_uid,
                conn=FakeConn(),
            )
        finally:
            DicomService.register_folder = original_register_folder.__get__(DicomService)  # type: ignore[assignment]

        # 2 个 series 兄弟目录都被 register_folder
        assert sorted(registered) == [
            str(image_path),
            str(root / f"img_00720185_{series_b}"),
        ]
        # 返回值给 service 调用方
        assert result is not None
        assert result["study_uid"] == study_uid
        assert result["center_code"] == "xinqiao"

    def test_unknown_study_uid_returns_none(self, tmp_path: Path) -> None:
        """PG 查不到 study_uid 时返回 None，不抛、不 register。"""
        from app.plugin.module_medical.dicom.service import DicomService

        class FakeConn:
            def execute(self, _sql, _params=None):
                class _Cur:
                    def fetchone(inner_self):
                        return None
                return _Cur()

        result = DicomService.ensure_study_indexed(
            study_uid="1.2.999.not.exist",
            conn=FakeConn(),
        )
        assert result is None

    def test_zhujiang_only_registers_image_path(self, tmp_path: Path) -> None:
        """zhujiang study 目录 = image_path 本身，无兄弟；只 register 一次。"""
        from app.plugin.module_medical.dicom.service import DicomService

        study_uid = "1.2.999.fake.zhujiang.study"
        image_path = tmp_path / "zhujiang" / "20250101" / f"123_{study_uid}"
        image_path.mkdir(parents=True)
        _make_dcm(
            image_path / "instance.dcm",
            study_uid=study_uid,
            series_uid="1.2.999.fake.zhujiang.series",
            sop_uid="1.2.999.fake.zhujiang.sop.0",
        )

        class FakeConn:
            def execute(self, _sql, _params=None):
                class _Cur:
                    def fetchone(inner_self):
                        return ("zhujiang", "123", str(image_path))
                return _Cur()

        registered: list[str] = []
        original_register_folder = DicomService.register_folder.__func__

        @classmethod
        def spy_register_folder(cls, folder_path):
            registered.append(str(folder_path))
            return original_register_folder(cls, folder_path)

        try:
            DicomService.register_folder = spy_register_folder  # type: ignore[assignment]
            DicomService.ensure_study_indexed(
                study_uid=study_uid,
                conn=FakeConn(),
            )
        finally:
            DicomService.register_folder = original_register_folder.__get__(DicomService)  # type: ignore[assignment]

        assert registered == [str(image_path)]


# ---------- 集成：ensure 后 query_study / list_series 能拿齐所有 series ----------


class TestEnsureStudyIndexedIntegration:
    """end-to-end：ensure 后 query_study / list_series 能拿齐 4_tjj study 的所有 series。"""

    def test_query_series_returns_all_after_ensure(self, tmp_path: Path) -> None:
        from app.plugin.module_medical.dicom.repository import indexer
        from app.plugin.module_medical.dicom.service import DicomService

        study_uid = "1.2.999.fake.int.study"
        # 4 个 series，每个 2 个 instance
        for i in range(4):
            d = tmp_path / "4_tjj" / f"img_00720185_1.2.999.fake.s.{i}"
            d.mkdir(parents=True)
            for j in range(2):
                _make_dcm(
                    d / f"i{j}.dcm",
                    study_uid=study_uid,
                    series_uid=f"1.2.999.fake.s.{i}",
                    sop_uid=f"_{i}_{j}",
                )
        image_path = tmp_path / "4_tjj" / "img_00720185_1.2.999.fake.s.0"

        class FakeConn:
            def execute(self, _sql, _params=None):
                class _Cur:
                    def fetchone(inner_self):
                        return ("xinqiao", "00720185", str(image_path))
                return _Cur()

        try:
            indexer.evict_study(study_uid)  # 清理
            DicomService.ensure_study_indexed(
                study_uid=study_uid,
                conn=FakeConn(),
            )
            # 验证 indexer 已聚合 4 个 series × 2 instance
            series_list = indexer.list_series_by_study_uid(study_uid)
            assert len(series_list) == 4, (
                f"应聚合 4 个 series，实际 {len(series_list)}"
            )
            instances_total = sum(s["instance_count"] for s in series_list)
            assert instances_total == 8, (
                f"应 8 个 instance，实际 {instances_total}"
            )
        finally:
            indexer.evict_study(study_uid)
            # 清理 tmp_path 下造的 .dcm
            import shutil
            shutil.rmtree(tmp_path, ignore_errors=True)
