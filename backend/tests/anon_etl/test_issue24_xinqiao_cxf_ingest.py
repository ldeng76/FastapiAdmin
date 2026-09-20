"""Issue 24 seam 测试：build_plan / validate_rows 纯函数（无 DB）。

覆盖：全链路 happy path、新患者占位、同日多 exam 平局、无日期三级兜底
（hash → (patient, fallback_date) → 新建）、兜底彻底失败、幂等重跑全跳、
崩后自愈（study 在 series 不在）、phi 去重、非法行过滤、重复 UID 去重。
"""

from __future__ import annotations

import hashlib
import sys
from datetime import date
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from app.plugin.module_medical.hospital.anonymize import compute_anon_exam_id  # noqa: E402

sys.path.insert(0, str(_BACKEND_ROOT / "etl2"))

from _issue24_ingest_xinqiao_cxf import (  # noqa: E402
    BATCH_ID,
    CENTER,
    SOURCE,
    CxfRow,
    build_plan,
    source_exam_hash,
    validate_rows,
)


def _row(
    uid: str = "1.2.840.113619.186.1.20240101090909000.1",
    pid: str = "00015498",
    *,
    exam_date: date | None = date(2024, 1, 1),
    n_files: int = 635,
    size: int = 152_977_430,
    series: int = 5,
    fallback: date | None = None,
) -> CxfRow:
    return CxfRow(
        study_uid=uid,
        pid=pid,
        exam_date=exam_date,
        n_files=n_files,
        total_size_bytes=size,
        series_count=series,
        study_root=f"/data/xq/3_cxf_archives/folders/001/{uid}",
        fallback_date=fallback,
    )


BASE = {
    "batch_id": BATCH_ID,
    "pt_of_pid": {"00015498": "PT_00000001"},
    "new_pids": set(),
    "exam_by_pt_date": {("PT_00000001", date(2024, 1, 1)): ["ANON_EXAM_aaa"]},
    "exam_by_hash": {},
    "existing_cxf_study_uids": set(),
    "existing_series_uids": set(),
    "existing_study_links": {},
    "phi_existing_hashes": set(),
}


class TestHappyPath:
    def test_dated_row_links_existing_exam(self):
        plan = build_plan([_row()], **BASE)
        assert len(plan.studies) == 1
        st = plan.studies[0]
        assert st["anon_exam_id"] == "ANON_EXAM_aaa"
        assert st["source"] == SOURCE
        assert st["center_code"] == CENTER
        assert st["sop_count"] == 635
        assert st["created_batch_id"] == BATCH_ID
        assert plan.series[0]["anon_exam_id"] == "ANON_EXAM_aaa"
        assert plan.series[0]["series_count"] == 5
        assert plan.series[0]["byte_size"] == 152_977_430
        assert plan.series[0]["file_count"] == 635
        assert plan.patients == []
        assert plan.exams == []
        assert plan.stats["exams_linked_by_date"] == 1

    def test_new_patient_placeholder_shape(self):
        kw = dict(BASE)
        kw["new_pids"] = {"00015498"}
        plan = build_plan([_row()], **kw)
        assert len(plan.patients) == 1
        p = plan.patients[0]
        assert p["patient_id"] == "PT_00000001"
        assert p["sex"] == "0"
        assert p["is_placeholder"] is True
        assert plan.stats["patients_new"] == 1

    def test_phi_hash_is_sha256_of_pt_id(self):
        plan = build_plan([_row()], **BASE)
        assert plan.phi_hashes == [
            hashlib.sha256(b"PT_00000001").hexdigest()
        ]


class TestTiebreak:
    def test_multi_candidates_pick_min_anon_exam_id(self):
        kw = dict(BASE)
        kw["exam_by_pt_date"] = {
            ("PT_00000001", date(2024, 1, 1)): ["ANON_EXAM_bbb", "ANON_EXAM_aaa"]
        }
        plan = build_plan([_row()], **kw)
        assert plan.studies[0]["anon_exam_id"] == "ANON_EXAM_aaa"
        assert plan.stats["ambiguous_links"] == 1


class TestNoDateFallback:
    def test_fallback_hash_hit_links_existing(self):
        uid = "1.2.392.200036.9116.2.5.1.37.2420784337.1551780125.716304"
        h = source_exam_hash(CENTER, uid)
        kw = dict(BASE)
        kw["exam_by_hash"] = {h: "ANON_EXAM_hashhit"}
        plan = build_plan([_row(uid, exam_date=None, fallback=date(2019, 3, 5))], **kw)
        assert plan.studies[0]["anon_exam_id"] == "ANON_EXAM_hashhit"
        assert plan.exams == []
        assert plan.stats["exams_linked_by_hash"] == 1

    def test_fallback_date_match_links_existing(self):
        uid = "1.2.392.200036.9116.2.5.1.37.2420784337.1551780125.716304"
        kw = dict(BASE)
        kw["exam_by_pt_date"] = {
            ("PT_00000001", date(2019, 3, 5)): ["ANON_EXAM_fb"]
        }
        plan = build_plan([_row(uid, exam_date=None, fallback=date(2019, 3, 5))], **kw)
        assert plan.studies[0]["anon_exam_id"] == "ANON_EXAM_fb"
        assert plan.stats["exams_linked_by_fallback_date"] == 1

    def test_fallback_miss_creates_exam(self):
        uid = "1.2.392.200036.9116.2.5.1.37.2420784337.1551780125.716304"
        plan = build_plan([_row(uid, exam_date=None, fallback=date(2019, 3, 5))], **BASE)
        assert len(plan.exams) == 1
        e = plan.exams[0]
        assert e["anon_exam_id"] == compute_anon_exam_id(CENTER, uid)
        assert e["patient_id"] == "PT_00000001"
        assert e["exam_date"] == date(2019, 3, 5)
        assert e["source_exam_hash"] == source_exam_hash(CENTER, uid)
        assert plan.studies[0]["anon_exam_id"] == e["anon_exam_id"]
        assert plan.series[0]["anon_exam_id"] == e["anon_exam_id"]
        assert plan.stats["exams_created"] == 1

    def test_no_fallback_at_all_stays_unlinked(self):
        plan = build_plan([_row(exam_date=None, fallback=None)], **BASE)
        assert plan.studies[0]["anon_exam_id"] is None
        assert plan.exams == []
        assert plan.stats["exams_unlinked"] == 1


class TestIdempotent:
    def test_existing_study_skipped(self):
        uid = "1.2.840.113619.186.1.20240101090909000.1"
        kw = dict(BASE)
        kw["existing_cxf_study_uids"] = {uid}
        kw["existing_series_uids"] = {uid}
        kw["phi_existing_hashes"] = [hashlib.sha256(b"PT_00000001").hexdigest()]
        plan = build_plan([_row(uid)], **kw)
        assert plan.studies == []
        assert plan.series == []
        assert plan.phi_hashes == []
        assert plan.stats["studies_existing"] == 1

    def test_crash_after_imaging_promote_self_heals_series(self):
        """study 已在库（上次 promote 中断在 series 之前）→ 只补 series，
        且 series.anon_exam_id 取既有 study 的链接值。"""
        uid = "1.2.840.113619.186.1.20240101090909000.1"
        kw = dict(BASE)
        kw["existing_cxf_study_uids"] = {uid}
        kw["existing_study_links"] = {uid: "ANON_EXAM_prev"}
        plan = build_plan([_row(uid)], **kw)
        assert plan.studies == []
        assert len(plan.series) == 1
        assert plan.series[0]["anon_exam_id"] == "ANON_EXAM_prev"
        assert plan.stats["studies_existing"] == 1
        assert plan.stats["series_new"] == 1

    def test_invalid_rows_filtered(self):
        bad_root = CxfRow(
            study_uid="u_bad_root",
            pid="00015498",
            exam_date=date(2024, 1, 1),
            n_files=3,
            total_size_bytes=10,
            series_count=1,
            study_root="/somewhere/else",
        )
        rows = [
            _row("u_ok"),
            _row("u_zero_files", n_files=0),
            _row("u_neg_size", size=-1),
            _row("u_zero_series", series=0),
            bad_root,
        ]
        good, bad = validate_rows(rows)
        assert [r.study_uid for r in good] == ["u_ok"]
        assert sorted(bad) == ["u_bad_root", "u_neg_size", "u_zero_files", "u_zero_series"]

    def test_duplicate_uid_deduped(self):
        plan = build_plan([_row(), _row()], **BASE)
        assert len(plan.studies) == 1
        assert plan.stats["rows_deduped"] == 1
