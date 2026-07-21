"""ETL-2 脱敏落库 CLI 入口。

用法：
    python -m app.plugin.module_medical.hospital.anon_etl \\
        --centers shengyi,xinqiao,zhujiang \\
        --data-root ../../data

参数：
- --centers: 逗号分隔的中心列表，默认全部 (shengyi,xinqiao,zhujiang)
- --data-root: ETL-1 产出物根目录，默认读 settings.LNRS_DATA_ROOT
- --dry-run: 仅打印将要处理的中心与文件清单，不连库

环境变量：
- ENVIRONMENT=dev（让 Settings 加载 env/.env.dev）
- LNRS_ANON_SECRET（覆盖 HMAC 密钥）
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.config.setting import settings
from app.core.logger import log
from app.plugin.module_medical.hospital.anon_etl import KNOWN_CENTERS, run_anon_etl
from app.plugin.module_medical.hospital.anon_etl_engine import _CENTER_PARQUET_SPECS


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="anon_etl",
        description="ETL-2: data/*.parquet → 脱敏 → lnrs_anon_* (PostgreSQL)",
    )
    p.add_argument(
        "--centers",
        default=",".join(KNOWN_CENTERS),
        help=f"逗号分隔的中心列表，默认全部 ({','.join(KNOWN_CENTERS)})",
    )
    p.add_argument(
        "--data-root",
        default=None,
        help="ETL-1 产出物根目录，默认读 settings.LNRS_DATA_ROOT",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="仅打印将要处理的中心与文件清单，不连库",
    )
    return p.parse_args()


def _dry_run(centers: list[str], data_root: Path) -> int:
    """打印处理计划，返回将处理的源表总数。"""
    total = 0
    print(f"[DRY-RUN] data_root = {data_root}")
    print(f"[DRY-RUN] LNRS_ANON_SECRET_VERSION = {settings.LNRS_ANON_SECRET_VERSION}")
    for c in centers:
        cdir = data_root / c
        print(f"[DRY-RUN] 中心 {c}: data_dir={cdir} exists={cdir.exists()}")
        specs = _CENTER_PARQUET_SPECS.get(c, [])
        for spec in specs:
            pq = cdir / f"{spec['src_table']}.parquet"
            exists = pq.exists()
            size = pq.stat().st_size if exists else 0
            tag = f"{size} bytes" if exists else "MISSING"
            print(f"[DRY-RUN]    - {spec['src_table']:<22} [{tag}] kind={spec['kind']}")
            if exists:
                total += 1
        # visit_record 显式提示
        visit_pq = cdir / "visit_record.parquet"
        if visit_pq.exists():
            print(
                f"[DRY-RUN]    - visit_record.parquet     [{visit_pq.stat().st_size} bytes] "
                f"SKIP (visit 桥未启用)"
            )
    print(f"[DRY-RUN] 将处理 {total} 个源表（不含跳过的 visit_record）")
    return total


def main() -> int:
    args = _parse_args()
    centers = [c.strip() for c in args.centers.split(",") if c.strip()]
    data_root = Path(args.data_root).resolve() if args.data_root else None

    if args.dry_run:
        root = data_root or Path(settings.LNRS_DATA_ROOT).resolve()
        _dry_run(centers, root)
        return 0

    log.info(f"ETL-2 启动: centers={centers} data_root={data_root or '(settings)'}")
    results = asyncio.run(run_anon_etl(centers=centers, data_root=data_root))

    # 汇总打印
    print("\n" + "=" * 60)
    print("ETL-2 汇总")
    print("=" * 60)
    failed = []
    for r in results:
        status = r["status"]
        rows = r.get("rows", {})
        total_rows = sum(rows.values()) if isinstance(rows, dict) else 0
        line = f"  {r['center']:<12} {status:<8} rows={rows}"
        if status == "failed":
            line += f"  error={r.get('error', '')}"
            failed.append(r["center"])
        print(line)
    print("=" * 60)
    if failed:
        print(f"❌ 失败中心: {failed}")
        return 1
    print("✅ 全部成功")
    return 0


if __name__ == "__main__":
    sys.exit(main())
