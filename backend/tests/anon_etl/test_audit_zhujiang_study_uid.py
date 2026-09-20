"""audit_zhujiang_study_uid.py 调研脚本的 seam 单测。

Issue 14: 珠江 lnrs_anon_imaging_study.dicom_study_uid 与 DICOM header (0008,0020) 一致性调研。

seam 划分（与脚本函数一一对应）：
- sample_studies(conn, n)        → 抽样
- read_study_uid(image_path)     → DICOM header 解析
- audit_one(sample)              → 比对
- write_report(report_path, results, *, sampled_n) → 报告生成

scripts/ 与 backend/ 平级，需把项目根加进 sys.path 才能 import。
"""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/ 与 backend/ 平级，需把项目根加进 sys.path 才能 import
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))  # noqa: E402 — 须在 pytest import 前注入
import pytest  # noqa: E402 — 在 sys.path hook 之后必须紧跟

# ---------- DICOM fixture 工具 ----------


def _make_dcm(path: Path, study_uid: str, series_uid: str, sop_uid: str,
              modality: str = "CT", sop_class: str = "1.2.840.10008.5.1.4.1.1.2") -> None:
    """生成最小 DICOM 文件（含 Study/Series/SOP UID + 模态）。"""
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


@pytest.fixture()
def fake_study_dir(tmp_path: Path) -> Path:
    """造一个 zhujiang 风格的 study 根目录：内含 3 个无扩展名 DICOM。"""
    study_uid = "1.2.999.fake.study.match"
    series_uid = "1.2.999.fake.series.match"
    for i in range(3):
        _make_dcm(
            tmp_path / f"0001_00000{i + 1}_{series_uid}.{i + 1}",
            study_uid=study_uid,
            series_uid=series_uid,
            sop_uid=f"1.2.999.fake.sop.{i + 1}",
        )
    return tmp_path


# ---------- seam 1: read_study_uid ----------


class TestReadStudyUid:
    def test_returns_header_study_uid(self, fake_study_dir: Path) -> None:
        from scripts.audit_zhujiang_study_uid import read_study_uid

        assert read_study_uid(fake_study_dir) == "1.2.999.fake.study.match"

    def test_empty_directory_raises(self, tmp_path: Path) -> None:
        from scripts.audit_zhujiang_study_uid import read_study_uid

        with pytest.raises(FileNotFoundError):
            read_study_uid(tmp_path)

    def test_missing_path_raises(self, tmp_path: Path) -> None:
        from scripts.audit_zhujiang_study_uid import read_study_uid

        with pytest.raises(FileNotFoundError):
            read_study_uid(tmp_path / "does-not-exist")


# ---------- seam 2: audit_one ----------


class TestAuditOne:
    def test_match_when_dir_uid_equals_header(self, fake_study_dir: Path) -> None:
        from scripts.audit_zhujiang_study_uid import StudySample, audit_one

        sample = StudySample(
            patient_id="PT_999",
            dicom_study_uid="1.2.999.fake.study.match",
            image_path=fake_study_dir,
        )
        result = audit_one(sample)
        assert result.match is True
        assert result.header_study_uid == "1.2.999.fake.study.match"
        assert result.error is None

    def test_mismatch_when_dir_uid_differs(self, fake_study_dir: Path) -> None:
        from scripts.audit_zhujiang_study_uid import StudySample, audit_one

        sample = StudySample(
            patient_id="PT_999",
            dicom_study_uid="1.2.999.different.uid.value",
            image_path=fake_study_dir,
        )
        result = audit_one(sample)
        assert result.match is False
        assert result.error is None

    def test_error_when_path_missing(self, tmp_path: Path) -> None:
        from scripts.audit_zhujiang_study_uid import StudySample, audit_one

        sample = StudySample(
            patient_id="PT_999",
            dicom_study_uid="1.2.999.fake.study.match",
            image_path=tmp_path / "missing",
        )
        result = audit_one(sample)
        assert result.match is False
        assert result.error is not None


# ---------- seam 3: write_report ----------


class TestWriteReport:
    def test_report_contains_match_rate_and_first_few_rows(self, tmp_path: Path) -> None:
        from scripts.audit_zhujiang_study_uid import (
            AuditResult,
            write_report,
        )

        results = [
            AuditResult(
                patient_id="PT_001",
                dicom_study_uid="1.2.A",
                header_study_uid="1.2.A",
                match=True,
                error=None,
            ),
            AuditResult(
                patient_id="PT_002",
                dicom_study_uid="1.2.B",
                header_study_uid="1.2.C",
                match=False,
                error=None,
            ),
        ]
        report = tmp_path / "report.md"
        write_report(report, results, sampled_n=2)
        text = report.read_text(encoding="utf-8")
        # Acceptance criteria 强制要求：每条 (patient_id, dicom_study_uid, header_study_uid, match) 四列
        assert "| patient_id | dicom_study_uid | header_study_uid | match |" in text
        # 汇总匹配率
        assert "匹配率" in text or "match rate" in text.lower()
        # 1 mismatch 至少 1 行
        assert "1.2.B" in text and "1.2.C" in text
        # 明细表数据行数 = 2（精确：截到"典型不匹配案例"章节之前，避免重复计）
        明细_section = text.split("典型不匹配案例", 1)[0]
        data_rows = sum(
            1
            for line in 明细_section.splitlines()
            if line.startswith("| PT_")
        )
        assert data_rows == 2

    def test_report_handles_all_match(self, tmp_path: Path) -> None:
        from scripts.audit_zhujiang_study_uid import (
            AuditResult,
            write_report,
        )

        results = [
            AuditResult(
                patient_id="PT_001",
                dicom_study_uid="1.2.A",
                header_study_uid="1.2.A",
                match=True,
                error=None,
            ),
        ]
        report = tmp_path / "report.md"
        write_report(report, results, sampled_n=1)
        text = report.read_text(encoding="utf-8")
        assert "100" in text


# ---------- seam 4: sample_studies（mock conn，不连真实 DB） ----------


class TestSampleStudies:
    def test_returns_requested_count(self) -> None:
        from scripts.audit_zhujiang_study_uid import sample_studies

        class FakeConn:
            def execute(self, _sql, _params=None):
                class _Cur:
                    def fetchall(inner_self):
                        return [
                            ("PT_001", "1.2.A", "/data/zhujiang/001"),
                            ("PT_002", "1.2.B", "/data/zhujiang/002"),
                            ("PT_003", "1.2.C", "/data/zhujiang/003"),
                        ]
                return _Cur()

        conn = FakeConn()
        samples = sample_studies(conn, n=3)
        assert len(samples) == 3
        assert samples[0].patient_id == "PT_001"
        assert samples[0].dicom_study_uid == "1.2.A"
        assert samples[0].image_path == Path("/data/zhujiang/001")

    def test_filters_center_code_in_query(self) -> None:
        """保证 SQL 把 center_code 写死为 zhujiang（防止错误拉到他中心）。"""
        from scripts.audit_zhujiang_study_uid import sample_studies

        captured = {}

        class FakeConn:
            def execute(self, sql, params=None):
                captured["sql"] = sql
                captured["params"] = params

                class _Cur:
                    def fetchall(inner_self):
                        return []
                return _Cur()

        sample_studies(FakeConn(), n=5)
        assert "zhujiang" in captured["sql"]
        assert captured["params"] == (5,)


# ---------- 集成：audit_many（编排） ----------


class TestAuditMany:
    def test_orchestration(self, fake_study_dir: Path) -> None:
        from scripts.audit_zhujiang_study_uid import StudySample, audit_many

        samples = [
            StudySample(
                patient_id="PT_OK",
                dicom_study_uid="1.2.999.fake.study.match",
                image_path=fake_study_dir,
            ),
            StudySample(
                patient_id="PT_BAD",
                dicom_study_uid="1.2.999.different.uid",
                image_path=fake_study_dir,
            ),
        ]
        results = audit_many(samples)
        assert len(results) == 2
        assert results[0].match is True
        assert results[1].match is False
