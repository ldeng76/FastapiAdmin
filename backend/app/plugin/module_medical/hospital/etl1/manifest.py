"""生成 conversion_manifest.json (仿 zhujiang_xinqiao_parq/_meta/)。

记录:
- 源文件 (路径/大小/sha256)
- 各目标表行数
- duckdb/python 版本
- 启动/结束时间
- 中心码
"""

from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from app.core.logger import log

from .config import CenterConfig


def _sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    """流式计算大文件 sha256 (200MB xlsx 不能一次读入内存)。

    2026-07-19 扩展: 若 path 是目录, 遍历目录内所有 *.csv / *.xlsx 按文件名排序
    后拼接 sha256; 用于新桥 CSV 来源。
    """
    if path.is_file():
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                b = f.read(chunk)
                if not b:
                    break
                h.update(b)
        return h.hexdigest()
    if path.is_dir():
        h = hashlib.sha256()
        # 按文件名排序确保 sha256 稳定
        files = sorted(
            p for p in path.rglob("*")
            if p.is_file() and p.suffix.lower() in (".csv", ".xlsx", ".parquet")
        )
        for fp in files:
            # 路径前缀参与 sha256 (防同名文件跨目录混淆)
            rel = fp.relative_to(path).as_posix().encode("utf-8")
            h.update(rel)
            h.update(b"\x00")
            with open(fp, "rb") as f:
                while True:
                    b = f.read(chunk)
                    if not b:
                        break
                    h.update(b)
            h.update(b"\x00")
        return h.hexdigest()
    raise FileNotFoundError(f"sha256 源不存在: {path}")


def write_manifest(
    center: CenterConfig,
    xlsx_path: Path,
    out_dir: Path,
    stats: dict[str, int],
) -> Path:
    """写 _meta/conversion_manifest.json 到 out_dir 下。返回 manifest 路径。"""
    meta_dir = out_dir / "_meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = meta_dir / "conversion_manifest.json"

    # size 计算: 单文件取 stat; 目录取所有 .csv / .xlsx 之和
    if xlsx_path.is_file():
        size_bytes = xlsx_path.stat().st_size
        source_kind_for_size = "file"
    else:
        size_bytes = sum(
            p.stat().st_size
            for p in xlsx_path.rglob("*")
            if p.is_file() and p.suffix.lower() in (".csv", ".xlsx", ".parquet")
        )
        source_kind_for_size = "directory"
    manifest: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "center_code": center.code,
        "center_display_name": center.display_name,
        "source_kind": center.source_kind,
        "duckdb_version": duckdb.__version__,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "source_file": {
            "path": str(xlsx_path.resolve()),
            "exists": True,
            "kind": source_kind_for_size,
            "size_bytes": size_bytes,
            "sha256": _sha256_of(xlsx_path),
        },
        "output_dir": str(out_dir.resolve()),
        "target_tables": {
            tbl: {
                "rows": n,
                "parquet_file": f"{tbl}.parquet",
                "parquet_size_bytes": (
                    (out_dir / f"{tbl}.parquet").stat().st_size
                    if (out_dir / f"{tbl}.parquet").exists()
                    else 0
                ),
            }
            for tbl, n in stats.items()
        },
        "total_rows": sum(v for v in stats.values() if v > 0),
    }

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("ETL1: manifest 已写 {}", manifest_path)
    return manifest_path
