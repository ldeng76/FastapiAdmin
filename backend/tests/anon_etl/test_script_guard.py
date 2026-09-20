"""ad-hoc 执行脚本安全闸（issue-21）单元测试。

覆盖 PRD 两条主路径：未声明 → 拒绝（退出码 2，stderr 说明如何声明）/
已声明 → 放行；以及：

- 沙箱库（lnrs_dev）免声明但仍打印目标库名；
- 声明库名与当前库名不符 → 拒绝（防环境串台）;
- 只读调用（action="read"）永不拒绝；
- banner 含目标库 / schema / 表 / 预计行数（estimated_rows=None → "未知"）；
- count_parquet_rows：文件缺失 → None，正常文件 → 行数。

不连库：monkeypatch settings.DATABASE_NAME 模拟不同目标库。
背景：docs/etl2/prd/issue-21-adhoc-script-write-guard.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

# 执行脚本在 backend/etl2/（带下划线前缀的 issue 执行脚本惯例）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "etl2"))

from _script_guard import (  # noqa: E402
    REFUSED_EXIT_CODE,
    add_target_argument,
    count_parquet_rows,
    gate,
)

from app.config.setting import settings  # noqa: E402

TABLES = ["lnrs.lnrs_anon_dicom_series"]


@pytest.fixture
def prod_db(monkeypatch):
    """模拟生产目标（h196_3/h42 真库的 DATABASE_NAME=postgres）。"""
    monkeypatch.setattr(settings, "DATABASE_NAME", "postgres")
    return "postgres"


@pytest.fixture
def sandbox_db(monkeypatch):
    """模拟沙箱目标 lnrs_dev（env/.env.test 的 DATABASE_NAME）。"""
    monkeypatch.setattr(settings, "DATABASE_NAME", "lnrs_dev")
    return "lnrs_dev"


class TestRefuseWhenUndeclared:
    def test_write_without_target_refused(self, prod_db):
        with pytest.raises(SystemExit) as exc:
            gate(schema="lnrs", tables=TABLES, action="write")
        assert exc.value.code == REFUSED_EXIT_CODE == 2

    def test_reject_message_tells_how_to_declare(self, prod_db, capsys):
        with pytest.raises(SystemExit):
            gate(schema="lnrs", tables=TABLES, action="write")
        err = capsys.readouterr().err
        assert "--target production" in err
        # 告知用户实际命中的库名，而不是含糊的"生产库"
        assert "postgres" in err

    def test_banner_printed_before_refusal(self, prod_db, capsys):
        with pytest.raises(SystemExit):
            gate(schema="lnrs", tables=TABLES, action="write", estimated_rows=7)
        out = capsys.readouterr().out
        assert "postgres" in out
        assert "lnrs.lnrs_anon_dicom_series" in out
        assert "7" in out


class TestAllowWhenDeclared:
    def test_declared_production_alias_allowed(self, prod_db):
        db = gate(schema="lnrs", tables=TABLES, declared="production", action="write")
        assert db == "postgres"

    def test_declared_exact_db_name_allowed(self, prod_db):
        db = gate(schema="lnrs", tables=TABLES, declared="postgres", action="write")
        assert db == "postgres"

    def test_declared_case_insensitive_allowed(self, prod_db):
        db = gate(schema="lnrs", tables=TABLES, declared="Production", action="write")
        assert db == "postgres"

    def test_declared_mismatch_refused(self, prod_db):
        # 声明 lnrs 但实际目标是 postgres → 拒绝（声明必须与当前库对得上）
        with pytest.raises(SystemExit) as exc:
            gate(schema="lnrs", tables=TABLES, declared="lnrs", action="write")
        assert exc.value.code == REFUSED_EXIT_CODE


class TestSandbox:
    def test_sandbox_write_without_target_allowed(self, sandbox_db):
        db = gate(schema="lnrs", tables=TABLES, action="write")
        assert db == "lnrs_dev"

    def test_sandbox_banner_still_prints_db_name(self, sandbox_db, capsys):
        gate(schema="lnrs", tables=TABLES, action="write")
        out = capsys.readouterr().out
        assert "lnrs_dev" in out


class TestReadOnly:
    def test_read_action_never_refused(self, prod_db):
        db = gate(schema="lnrs", tables=TABLES, action="read")
        assert db == "postgres"


class TestBanner:
    def test_banner_unknown_when_no_estimate(self, prod_db, capsys):
        gate(schema="lnrs", tables=TABLES, action="read", estimated_rows=None)
        assert "未知" in capsys.readouterr().out

    def test_banner_lists_all_tables(self, prod_db, capsys):
        gate(
            schema="lnrs",
            tables=["lnrs.lnrs_anon_exam", "lnrs.lnrs_anon_report_text"],
            action="read",
        )
        out = capsys.readouterr().out
        assert "lnrs.lnrs_anon_exam" in out
        assert "lnrs.lnrs_anon_report_text" in out


class TestAddTargetArgument:
    def test_default_none(self):
        p = argparse.ArgumentParser()
        add_target_argument(p)
        assert p.parse_args([]).target is None

    def test_explicit_value(self):
        p = argparse.ArgumentParser()
        add_target_argument(p)
        assert p.parse_args(["--target", "production"]).target == "production"


class TestCountParquetRows:
    def test_missing_file_returns_none(self, tmp_path):
        assert count_parquet_rows(tmp_path / "nope.parquet") is None

    def test_counts_rows(self, tmp_path):
        import duckdb

        pq = tmp_path / "t.parquet"
        duckdb.sql(
            f"COPY (SELECT 1 AS a UNION ALL SELECT 2 UNION ALL SELECT 3) "
            f"TO '{pq}' (FORMAT PARQUET)"
        )
        assert count_parquet_rows(pq) == 3
