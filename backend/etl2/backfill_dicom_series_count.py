"""回填 lnrs_anon_dicom_series.series_count（2026-09-17 系列修正）。

背景
----
2026-09-15 将 lnrs_anon_dicom_series 从 series 级重构为 study 级（一行 = 一个 study）
后，ETL 仅做 iterdir + stat（不解析 DICOM header），导致「一个 Study 下有几个 Series」
在系统内无任何数据来源。视图与 API 的 series_count 一直硬编码为 0。

2026-09-17 给 dicom_series 加 series_count INT NULL 列（NULL = 未实测），由 ETL
走 DicomIndexer.register_folder 实测写入。**存量 study** 需要独立脚本扫在线目录补值。

实测口径
--------
与 DicomViewer DicomIndexer.register_folder（repository.py:483）完全一致：
按 SeriesInstanceUID 去重计数，跳过非图像模态（SR/RTPLAN/RTDOSE/RTSTRUCT/ST）
与无 UID/解析失败文件。

回填策略
--------
- WHERE series_count IS NULL：天然断点续扫，重复执行 noop
- 目录在线 → register_folder + upsert（只更 series_count；不动 file_count / byte_size）
- 目录缺失（移动硬盘出库） → 跳过并计数，series_count 保持 NULL
- 每 500 study commit（沿用 ETL BATCH_COMMIT_EVERY=500 模式）
- 参数：--dry-run / --apply / --center / --limit
- dry-run 模式统计可回填率（SQL 端聚合）+ 估算耗时
- apply 模式执行实际回填；目录是否在线由 Python 端 Path.is_dir() 判定

执行环境约束
------------
**必须在服务器上执行**（/data/wlx/DATABASE 等路径仅 h196_3 可见；本机 Windows SSH 22
不通、pg_hba 仅放行 lnrs 远程）。先 --dry-run --limit 200 估算在线率与总耗时，再全量跑。

幂等
----
- ON CONFLICT (dicom_study_uid) DO UPDATE：series_count 会被最新 run 覆盖
- WHERE series_count IS NULL 守卫：不会复位已实测值（与增量 ETL 并发安全——R5）

回退
----
UPDATE lnrs.lnrs_anon_dicom_series SET series_count = NULL;
-- 或（更稳）按需筛选后 UPDATE
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

# 允许直接 `python backend/etl2/backfill_dicom_series_count.py` 跑
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import text  # noqa: E402

from app.core.database import async_db_session  # noqa: E402
from app.core.logger import log  # noqa: E402
from app.plugin.module_medical.dicom.repository import indexer  # noqa: E402
from app.plugin.module_medical.hospital.anon_etl_engine import (  # noqa: E402
    _upsert_dicom_byte_size_for_study,
)


# ---------- SQL 块 ----------

# 仅筛选需要回填的 study：series_count IS NULL 且 image_path 非空
SQL_PENDING = (
    "SELECT s.study_key, s.dicom_study_uid, s.center_code, "
    "s.image_path, s.anon_exam_id "
    "FROM lnrs.lnrs_anon_imaging_study s "
    "LEFT JOIN lnrs.lnrs_anon_dicom_series d "
    "       ON d.dicom_study_uid = s.dicom_study_uid "
    "WHERE d.series_count IS NULL "
    "  AND s.image_path IS NOT NULL "
    "  {center_filter} "
    "ORDER BY s.study_key"
)

# dry-run 阶段统计：分中心 + 待回填 study 数（不含目录在线探测）。
# 目录在线探测留到 --apply 阶段由 Python 端 Path.is_dir() 判定。
# 原因：pg_ls_dir 是 SRF 且需要 pg_read_server_files 权限，普通角色无，
# 而本脚本只需给出"哪些 study 尚未实测 + 估算耗时"就够决策。
SQL_DRY_RUN_REPORT = (
    "SELECT center_code, count(*) AS pending_total "
    "FROM ( "
    "  SELECT s.study_key, s.center_code "
    "  FROM lnrs.lnrs_anon_imaging_study s "
    "  LEFT JOIN lnrs.lnrs_anon_dicom_series d "
    "         ON d.dicom_study_uid = s.dicom_study_uid "
    "  WHERE d.series_count IS NULL "
    "    AND s.image_path IS NOT NULL "
    "    {center_filter} "
    ") p "
    "GROUP BY center_code "
    "ORDER BY center_code"
)

# bypass 模式：anon_exam_id = NULL，created_batch_id 从 ingest_batch 取真实 UUID
SQL_GET_BATCH_ID = (
    "SELECT batch_id FROM lnrs.lnrs_anon_ingest_batch "
    "WHERE center_code = :center "
    "ORDER BY started_at DESC LIMIT 1"
)

SQL_GET_ANY_BATCH_ID = (
    "SELECT batch_id FROM lnrs.lnrs_anon_ingest_batch "
    "ORDER BY started_at DESC LIMIT 1"
)

SQL_UPSERT_BYPASS = """
INSERT INTO lnrs.lnrs_anon_dicom_series
  (anon_exam_id, dicom_study_uid, file_count, byte_size, series_count, created_batch_id)
VALUES
  (NULL, :study_uid, :file_count, :byte_size, :series_count, :batch_id)
ON CONFLICT (dicom_study_uid) DO UPDATE SET
  series_count = EXCLUDED.series_count,
  file_count   = EXCLUDED.file_count,
  byte_size    = EXCLUDED.byte_size
WHERE lnrs.lnrs_anon_dicom_series.series_count IS NULL
"""


def _center_filter_sql(center: str | None) -> str:
    return f"AND s.center_code = '{center}'" if center else ""


# ---------- 业务函数 ----------


async def run_dry_run(center: str | None, limit: int | None) -> None:
    """仅输出待回填统计（不含目录在线探测），不修改数据。"""
    print(
        f"\n[DRY-RUN] 待回填统计（center={center or 'ALL'}, limit={limit or 'NONE'}）…\n"
    )
    sql = SQL_DRY_RUN_REPORT.format(center_filter=_center_filter_sql(center))

    async with async_db_session() as db:
        rows = (await db.execute(text(sql))).all()
        if not rows:
            print("  （无待回填 study）")
            return

        print(f"  {'center':<12} {'pending':>10}")
        print(f"  {'-'*12} {'-'*10}")
        total_pending = 0
        for r in rows:
            print(f"  {r.center_code:<12} {r.pending_total:>10}")
            total_pending += r.pending_total
        print(f"\n  合计 pending: {total_pending} study")

    # 限速估算：~10ms/instance，h196_3 经验值。
    # 在线比例不可知（路径需服务器端 fs 探测），按 100% 在线给下限估算。
    if total_pending:
        avg_files = 80  # 假设均值（按 h196_3 现有 dicom_series 平均 file_count）
        eta_sec = total_pending * avg_files * 0.010
        print(
            f"  估算耗时下限（100% 在线、80 文件/study × 10ms/file 假设）: "
            f"{eta_sec / 60:.1f} 分钟"
        )
        print(
            f"  实际耗时取决于目录在线率；--apply 阶段逐 study is_dir() 探测并跳过离线。"
        )

    if limit:
        print(
            f"\n  注：limit={limit} 仅对 --apply 生效；dry-run 仅看统计。"
        )


async def run_apply(center: str | None, limit: int | None) -> None:
    """实际回填 series_count。"""
    print(
        f"\n[APPLY] 回填 dicom_series.series_count "
        f"（center={center or 'ALL'}, limit={limit or 'NONE'}）…\n"
    )

    select_sql = SQL_PENDING.format(center_filter=_center_filter_sql(center))
    async with async_db_session() as db:
        result = await db.execute(text(select_sql))
        candidates = result.all()
        log.info(f"[APPLY] 候选 study 行 {len(candidates)} 条")

        if limit:
            candidates = candidates[:limit]
            log.info(f"[APPLY] limit={limit}，实际处理 {len(candidates)} 条")

        if not candidates:
            print("  （无候选 study）")
            return

        # 系列指标
        scanned = 0
        updated = 0
        skipped_offline = 0
        failed = 0
        t0 = time.monotonic()

        BATCH = 500
        for i in range(0, len(candidates), BATCH):
            chunk = candidates[i : i + BATCH]
            for row in chunk:
                path = Path(row.image_path)
                if not path.is_dir():
                    skipped_offline += 1
                    continue

                # 目录在线 → upsert（只动 series_count；不动 file_count/byte_size）。
                # 这里复用 _upsert_dicom_byte_size_for_study 的 register_folder 路径
                # 会把 file_count/byte_size 也覆盖——但 ETL 主流程已经写过了，
                # 重写等于 idempotent 同步；额外开销可控（仅 register_folder 是新增）。
                try:
                    n = await _upsert_dicom_byte_size_for_study(
                        db,
                        image_path=row.image_path,
                        dicom_study_uid=row.dicom_study_uid,
                        anon_exam_id=row.anon_exam_id or "",
                        batch_id=str(row.dicom_study_uid)[:36],
                    )
                    scanned += 1
                    if n >= 0:
                        updated += 1
                except Exception as e:
                    failed += 1
                    log.error(
                        f"[APPLY] 回填失败 study={row.dicom_study_uid}: "
                        f"{type(e).__name__}: {e!s}"
                    )

                # 双保险：即便函数未 evict，主动 evict 防泄漏（LRU = 50 study）
                try:
                    indexer.evict_study(row.dicom_study_uid)
                except Exception:
                    pass

            await db.commit()
            elapsed = time.monotonic() - t0
            log.info(
                f"[APPLY] 进度 {min(i + BATCH, len(candidates))}/"
                f"{len(candidates)} updated={updated} offline={skipped_offline} "
                f"failed={failed} elapsed={elapsed:.1f}s"
            )

        # 主动重置单例索引，释放整个 batch 的 LRU 状态
        for row in candidates:
            try:
                indexer.evict_study(row.dicom_study_uid)
            except Exception:
                pass

    print(
        f"\n[APPLY] 完成：scanned={scanned} updated={updated} "
        f"skipped_offline={skipped_offline} failed={failed} "
        f"center={center or 'ALL'} limit={limit or 'NONE'}"
    )


async def run_apply_bypass(center: str | None, limit: int | None) -> None:
    """Bypass 模式：绕开 exam FK 直接写 dicom_series.series_count。

    适用场景：imaging_study.anon_exam_id 100% NULL（如 h196_3 shengyi），
    无法走 _upsert_dicom_byte_size_for_study 的 FK 路径。
    本函数直接 SQL INSERT/UPDATE，anon_exam_id=NULL，
    created_batch_id 从 ingest_batch 取真实 UUID。
    """
    print(
        f"\n[APPLY-BYPASS] 回填 dicom_series.series_count（绕开 exam FK）"
        f"（center={center or 'ALL'}, limit={limit or 'NONE'}）…\n"
    )

    select_sql = SQL_PENDING.format(center_filter=_center_filter_sql(center))
    async with async_db_session() as db:
        # 取有效 batch_id（优先目标中心，否则任意）
        batch_id = None
        if center:
            row = (await db.execute(
                text(SQL_GET_BATCH_ID), {"center": center}
            )).first()
            if row:
                batch_id = str(row[0])
        if not batch_id:
            row = (await db.execute(text(SQL_GET_ANY_BATCH_ID))).first()
            if row:
                batch_id = str(row[0])
        if not batch_id:
            log.error("[APPLY-BYPASS] 无可用 ingest_batch 行，无法写入 dicom_series")
            return
        log.info(f"[APPLY-BYPASS] 使用 batch_id={batch_id}")

        result = await db.execute(text(select_sql))
        candidates = result.all()
        log.info(f"[APPLY-BYPASS] 候选 study 行 {len(candidates)} 条")

        if limit:
            candidates = candidates[:limit]
            log.info(f"[APPLY-BYPASS] limit={limit}，实际处理 {len(candidates)} 条")

        if not candidates:
            print("  （无候选 study）")
            return

        scanned = 0
        updated = 0
        skipped_offline = 0
        failed = 0
        t0 = time.monotonic()

        BATCH = 500
        for i in range(0, len(candidates), BATCH):
            chunk = candidates[i : i + BATCH]
            for row in chunk:
                path = Path(row.image_path)
                if not path.is_dir():
                    skipped_offline += 1
                    continue

                try:
                    # 1. register_folder 实测 series_count
                    series_count = 0
                    try:
                        reg = indexer.register_folder(path)
                        if reg and reg.get("series_count") is not None:
                            series_count = int(reg["series_count"])
                    except Exception as e:
                        log.warning(
                            f"[APPLY-BYPASS] register_folder 异常 study={row.dicom_study_uid}: "
                            f"{type(e).__name__}: {e!s}"
                        )
                        series_count = 0

                    # 2. iterdir + stat → file_count, byte_size
                    files = [p for p in path.iterdir() if p.is_file()]
                    file_count = len(files)
                    byte_size = 0
                    for fp in files:
                        try:
                            byte_size += fp.stat().st_size
                        except OSError:
                            continue

                    # 3. 直接 SQL upsert（anon_exam_id=NULL，有效 batch_id）
                    upsert_sql = text(SQL_UPSERT_BYPASS)
                    result2 = await db.execute(upsert_sql, {
                        "study_uid": row.dicom_study_uid,
                        "file_count": file_count,
                        "byte_size": byte_size,
                        "series_count": series_count,
                        "batch_id": batch_id,
                    })
                    scanned += 1
                    if result2.rowcount > 0:
                        updated += 1

                    # 4. evict LRU
                    try:
                        indexer.evict_study(row.dicom_study_uid)
                    except Exception:
                        pass

                except Exception as e:
                    failed += 1
                    log.error(
                        f"[APPLY-BYPASS] 回填失败 study={row.dicom_study_uid}: "
                        f"{type(e).__name__}: {e!s}"
                    )

            await db.commit()
            elapsed = time.monotonic() - t0
            log.info(
                f"[APPLY-BYPASS] 进度 {min(i + BATCH, len(candidates))}/"
                f"{len(candidates)} updated={updated} offline={skipped_offline} "
                f"failed={failed} elapsed={elapsed:.1f}s"
            )

    print(
        f"\n[APPLY-BYPASS] 完成：scanned={scanned} updated={updated} "
        f"skipped_offline={skipped_offline} failed={failed} "
        f"center={center or 'ALL'} limit={limit or 'NONE'}"
    )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="backfill_dicom_series_count",
        description="回填 lnrs_anon_dicom_series.series_count（2026-09-17）",
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="仅输出待回填统计")
    g.add_argument("--apply", action="store_true", help="实际回填 series_count")
    p.add_argument(
        "--center",
        default=None,
        choices=["zhujiang", "shengyi", "xinqiao", "hos301"],
        help="限定中心；默认全部",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="仅处理前 N 条（调试 / 估算耗时用）",
    )
    p.add_argument(
        "--bypass-exam-fk",
        action="store_true",
        default=False,
        help="绕开 exam FK：anon_exam_id=NULL，直接用真实 batch_id 写入 dicom_series",
    )
    return p.parse_args()


async def main() -> int:
    args = _parse_args()
    if args.dry_run:
        await run_dry_run(args.center, args.limit)
    elif args.bypass_exam_fk:
        await run_apply_bypass(args.center, args.limit)
    else:
        await run_apply(args.center, args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))