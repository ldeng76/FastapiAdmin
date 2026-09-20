"""backfill_xinqiao_series_counts_from_pacs.plan_updates 的 seam 测试。

覆盖：一致跳过、fc/sz 单边变化、库内缺失行忽略（cxf 未入库）、
PACS 多余 uid 忽略、非法值守卫（fc<1 / sz<0 / None）。
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from etl2.backfill_xinqiao_series_counts_from_pacs import plan_updates  # noqa: E402


def test_no_change_when_equal():
    pacs = {"u1": (3, 100), "u2": (1, 50)}
    updates, skipped = plan_updates(pacs, [("u1", 3, 100), ("u2", 1, 50)])
    assert updates == []
    assert skipped == 0


def test_series_count_change_only():
    pacs = {"u1": (12, 100)}
    updates, _ = plan_updates(pacs, [("u1", 1, 100)])
    assert updates == [("u1", 12, 100)]


def test_byte_size_change_only():
    pacs = {"u1": (3, 395_231_908)}
    updates, _ = plan_updates(pacs, [("u1", 3, 391_737_708)])
    assert updates == [("u1", 3, 395_231_908)]


def test_db_row_missing_uid_kept_out():
    # PACS 有 cxf 未入库 uid，库内无 → 忽略，不产出更新
    pacs = {"u1": (3, 100), "cxf1": (5, 200)}
    updates, _ = plan_updates(pacs, [("u1", 3, 100)])
    assert updates == []


def test_db_uid_not_in_pacs_ignored():
    updates, _ = plan_updates({}, [("u1", 1, 10)])
    assert updates == []


def test_null_db_values_count_as_zero_and_update():
    pacs = {"u1": (2, 300)}
    updates, _ = plan_updates(pacs, [("u1", None, None)])
    assert updates == [("u1", 2, 300)]


def test_invalid_pacs_values_skipped():
    pacs = {
        "a": (0, 100),  # fc < 1
        "b": (None, 100),  # fc None
        "c": (3, -1),  # sz < 0
        "d": (3, None),  # sz None
    }
    updates, skipped = plan_updates(pacs, [(k, 1, 1) for k in pacs])
    assert updates == []
    assert skipped == 4


def test_equal_rows_and_extra_db_uid_skipped():
    # PACS 值与库内相等的行跳过；库内多出的 uid（不在 PACS）忽略
    pacs = {"u1": (1, 10)}
    updates, _ = plan_updates(pacs, [("u1", 1, 10), ("u2", None, None)])
    assert updates == []
