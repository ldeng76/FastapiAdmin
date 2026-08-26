#!/usr/bin/env python3
"""make_manifest.py — 写 _meta/conversion_manifest.json
记录源文件 SHA256、行数、DuckDB 版本、libreoffice 版本、空表说明。
"""
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

OUT = Path(sys.argv[1])
SRC = Path(sys.argv[2])
META = OUT / "_meta" / "conversion_manifest.json"

DUCKDB = "/home/dzy/.duckdb/cli/latest/duckdb"

SOURCE_FILES = [
    "5万例时序影像_带病理_新_1.csv",
    "胸外历史病人编码后手术记录.csv",
    "胸外科历史病人入院记录文书数据-22年.csv",
    "CT与病理数据.xlsx",
    "精准医学V2_副本.xls",
    "历史病历查询.xls",
]

TABLES = [
    "patient",
    "pathology_specimen",
    "surgery_record",
    "nodule_imaging",
    "genetic_test",
    "ihc_result",
    "follow_up",
]

# 哪些表是 schema-only fallback
EMPTY_TABLES = {"genetic_test", "ihc_result", "follow_up"}


def sha256_of(path: Path) -> str:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def duckdb_version() -> str:
    try:
        out = subprocess.run([DUCKDB, "--version"], capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except Exception as e:
        return f"error: {e}"


def soffice_version() -> str:
    try:
        out = subprocess.run(["libreoffice", "--version"], capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except Exception as e:
        return f"error: {e}"


def parquet_row_count(p: Path) -> int | None:
    if not p.exists():
        return None
    try:
        out = subprocess.run(
            [DUCKDB, "-csv", "-c", f"SELECT count(*) FROM '{p}'"],
            capture_output=True, text=True, check=True,
        )
        return int(out.stdout.strip().splitlines()[1])
    except Exception:
        return None


def main():
    src_dir = SRC / "_字段与原始数据"
    out_dir = OUT

    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "duckdb_version": duckdb_version(),
        "libreoffice_version": soffice_version(),
        "source_dir": str(src_dir),
        "output_dir": str(out_dir),
        "source_files": {},
        "tables": {},
    }

    for name in SOURCE_FILES:
        p = src_dir / name
        manifest["source_files"][name] = {
            "path": str(p),
            "exists": p.exists(),
            "size_bytes": p.stat().st_size if p.exists() else None,
            "sha256": sha256_of(p),
        }

    for tbl in TABLES:
        p = out_dir / f"{tbl}.parquet"
        rc = parquet_row_count(p)
        manifest["tables"][tbl] = {
            "path": str(p),
            "exists": p.exists(),
            "row_count": rc,
            "is_schema_only": tbl in EMPTY_TABLES,
        }

    META.parent.mkdir(parents=True, exist_ok=True)
    META.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"manifest written: {META}  ({META.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
