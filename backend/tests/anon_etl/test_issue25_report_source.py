"""Issue 25 seam 测试：行级增量决策与正文口径（纯函数，无 DB）。"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT / "etl2"))

from _issue25_ingest_xinqiao_report_source import (  # noqa: E402
    content_body_md5,
    decide_row,
    recombined_body,
)


class TestDecideRow:
    def test_ingest_new_exam(self):
        assert (
            decide_row(
                exam_hash_in_db=False, content_key_in_db=False, resolved_date="2024-01-02"
            )
            == "ingest"
        )

    def test_skip_ingested_by_exam_hash(self):
        """同 exam_id 已入库 → 跳过（即使内容键未命中，如 108 对交叉配对方向）。"""
        assert (
            decide_row(
                exam_hash_in_db=True, content_key_in_db=False, resolved_date="2024-01-02"
            )
            == "skip_ingested"
        )

    def test_skip_duplicate_content(self):
        """Accession 行与已入库报告内容三键全等 → 跳过。"""
        assert (
            decide_row(
                exam_hash_in_db=False, content_key_in_db=True, resolved_date="2024-01-02"
            )
            == "skip_duplicate_content"
        )

    def test_drop_no_date_when_fallback_failed(self):
        """262 行兜底失败 → 不入。"""
        assert (
            decide_row(
                exam_hash_in_db=False, content_key_in_db=False, resolved_date=None
            )
            == "drop_no_date"
        )


    def test_hash_hit_beats_content_miss_only_for_same_exam(self):
        """hash 命中优先于 content 未命中：幂等重跑全 skip_ingested。"""
        assert (
            decide_row(
                exam_hash_in_db=True, content_key_in_db=False, resolved_date="2024-05-06"
            )
            == "skip_ingested"
        )


    def test_hash_hit_priority_over_no_date(self):
        """hash 命中（已灌行）优先于无日期：幂等重跑分类稳定。"""
        assert (
            decide_row(
                exam_hash_in_db=True, content_key_in_db=True, resolved_date=None
            )
            == "skip_ingested"
        )

    def test_content_md5_stable(self):
        k1 = content_body_md5("a", "b")
        k2 = content_body_md5("a", "b")
        assert k1 == k2
        assert k1 == hashlib.md5("a\n\nb".encode()).hexdigest()

    def test_truncation_applied_like_engine(self):
        """超长正文按引擎 MAX_BODY_LEN 截断，md5 口径与库内一致。"""
        long_text = "x" * (150_000)
        body = recombined_body(long_text, None)
        assert len(body) == 100_000
        assert content_body_md5(long_text, None) == hashlib.md5(
            body.encode()
        ).hexdigest()
