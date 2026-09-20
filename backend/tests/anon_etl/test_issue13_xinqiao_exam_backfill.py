"""issue-13 xinqiao exam 灌库 + 回填 — 无日期残留 study 选择函数的 seam 测试。

seam 划分（与 _issue13_ingest_xinqiao_ct_exam.pick_residual_exam 对应）：

xinqiao 33,110 个可匹配 study 中，31,098 个有 StudyInstanceUID 内嵌日期，
剩余 2,012 个无日期 study 由 pick_residual_exam 确定性兜底（纯函数，
输入 study 文件数 + 同患者 CT exam 候选，输出选中 exam + 规则名）：

  1. candidates 为空 → None（患者无 CT exam，study 保持 NULL）
  2. 唯一候选 → 直接选（'single'，无需日期/文件数）
  3. 多候选且恰有一个 map_file_sum == study_file_count → 选它（'filecount'，
     ct_dicom_map 的 per-exam 在盘文件数与 study 实测文件数精确相等 → 同一检查）
  4. 其余（0 个或多个文件数匹配）→ anon_exam_id 字典序最小（'tiebreak'，
     与 issue-1 平局规则一致，确定性可复现）

调研实测（docs/etl2/verify_result/xinqiao-exam-source-20260920.md §4）：
2,012 残留 = 795 single + 1,217 多候选；实际执行 filecount 命中 1,216、
tiebreak 1（执行前分析预测见调研文档 §4）。
"""
from __future__ import annotations

import sys
from pathlib import Path

# _issue13 脚本在 backend/etl2/（带下划线前缀的 issue 执行脚本惯例）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "etl2"))

from _issue13_ingest_xinqiao_ct_exam import pick_residual_exam  # noqa: E402


def _cand(eid: str, nfiles: int | None) -> dict:
    return {"anon_exam_id": eid, "map_file_sum": nfiles}


class TestPickResidualExam:
    def test_no_candidates_returns_none(self) -> None:
        assert pick_residual_exam(632, []) is None

    def test_single_candidate_picked_regardless_of_file_sum(self) -> None:
        # 唯一候选：文件数未知/不匹配都直接选（无歧义可言）
        got = pick_residual_exam(632, [_cand("ANON_EXAM_a", None)])
        assert got == ("ANON_EXAM_a", "single")
        got = pick_residual_exam(632, [_cand("ANON_EXAM_a", 100)])
        assert got == ("ANON_EXAM_a", "single")

    def test_filecount_exact_match_wins(self) -> None:
        # 3 候选恰一文件数相等 → filecount 规则（即使字典序不是最小）
        cands = [
            _cand("ANON_EXAM_a", 100),
            _cand("ANON_EXAM_b", 632),
            _cand("ANON_EXAM_c", 250),
        ]
        assert pick_residual_exam(632, cands) == ("ANON_EXAM_b", "filecount")

    def test_filecount_match_beats_earlier_candidate(self) -> None:
        # 字典序最小的候选文件数不等时不得误选
        cands = [
            _cand("ANON_EXAM_a", 999),
            _cand("ANON_EXAM_z", 42),
        ]
        assert pick_residual_exam(42, cands) == ("ANON_EXAM_z", "filecount")

    def test_no_filecount_match_falls_to_tiebreak_min_id(self) -> None:
        cands = [
            _cand("ANON_EXAM_c", 10),
            _cand("ANON_EXAM_a", 20),
            _cand("ANON_EXAM_b", 30),
        ]
        assert pick_residual_exam(632, cands) == ("ANON_EXAM_a", "tiebreak")

    def test_ambiguous_filecount_falls_to_tiebreak_min_id(self) -> None:
        # 两个候选文件数都相等（如同文件数的两次检查）→ 平局规则
        cands = [
            _cand("ANON_EXAM_c", 632),
            _cand("ANON_EXAM_a", 632),
        ]
        assert pick_residual_exam(632, cands) == ("ANON_EXAM_a", "tiebreak")

    def test_none_file_sums_treated_as_no_match(self) -> None:
        # map 未覆盖（None）不参与 filecount 匹配 → tiebreak
        cands = [
            _cand("ANON_EXAM_b", None),
            _cand("ANON_EXAM_a", None),
        ]
        assert pick_residual_exam(632, cands) == ("ANON_EXAM_a", "tiebreak")

    def test_deterministic(self) -> None:
        cands = [
            _cand("ANON_EXAM_d", 5),
            _cand("ANON_EXAM_b", 5),
            _cand("ANON_EXAM_c", 7),
        ]
        first = pick_residual_exam(7, cands)
        for _ in range(5):
            assert pick_residual_exam(7, cands) == first
