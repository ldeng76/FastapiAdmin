"""ETL-1 CLI 入口 (开发期调试用)。

用法:
    cd backend
    python -m app.plugin.module_medical.hospital.etl1 \
        --center shengyi \
        --xlsx ../docs/demodata/shengyi_valid_dicom_and_record/搜索导出.xlsx \
        --out ../data/shengyi \
        [--only patient,visit_record] \
        [--dry-run]

或直接用 backend venv:
    backend/.venv/Scripts/python.exe -m app.plugin.module_medical.hospital.etl1 ...
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 让脚本在 backend/ 目录下直接跑 (相对 import 解析)
_BACKEND_DIR = Path(__file__).resolve().parents[5]   # etl1 -> hospital -> module_medical -> plugin -> app -> backend
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.core.logger import log  # noqa: E402
from app.plugin.module_medical.hospital.etl1 import get_center_config, list_centers, run_etl1  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="ETL-1: Excel → Parquet")
    parser.add_argument("--center", required=True, choices=None,
                        help=f"医院代号; 已注册: {list_centers()} (在脚本启动后才能列出)")
    parser.add_argument("--xlsx", required=True, help="Excel 文件路径")
    parser.add_argument("--out", default=None, help="输出目录 (默认 data/<center>)")
    parser.add_argument("--only", default=None,
                        help="只处理这些 target_table, 逗号分隔 (开发期增量调试)")
    parser.add_argument("--dry-run", action="store_true", help="只解析不写文件")
    parser.add_argument("--verbose", action="store_true", help="DEBUG 日志")
    args = parser.parse_args()

    if args.verbose:
        from loguru import logger as _l
        _l.remove()
        _l.add(sys.stderr, level="DEBUG")

    try:
        center = get_center_config(args.center)
    except KeyError as e:
        log.error("未知 center: {} (已注册: {})", args.center, list_centers())
        return 2

    only = args.only.split(",") if args.only else None
    xlsx = Path(args.xlsx).resolve()
    if not xlsx.exists():
        log.error("xlsx 不存在: {}", xlsx)
        return 1
    # CLI 传入的 out 路径相对当前工作目录解析 (不是 BASE_DIR);
    # 不传时用 center.output_dir (相对仓库根, 由 _resolve_out_dir 处理)
    out_dir = Path(args.out).resolve() if args.out else None

    stats = run_etl1(
        center=center,
        xlsx_path=xlsx,
        out_dir=out_dir,
        only_tables=only,
        dry_run=args.dry_run,
        on_table_done=lambda t, n: log.info("[CLI] {} → {} 行", t, n),
    )

    log.info("=== ETL-1 完成 ===")
    for t, n in stats.items():
        log.info("  {:30s} {:>10d}", t, n if n >= 0 else -1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
