"""回填 dicom_series.series_count → 写入 stage 表（issue-20「先暂存再上」）。
（issue-20：写入目标为 lnrs.lnrs_stage_dicom_series，promote 命令再幂等上生产表。）
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
- 目录在线 → register_folder 实测 series_count，upsert 进 **stage 表**
  lnrs.lnrs_stage_dicom_series（issue-20：本脚本不再直写生产表；
  生产表由 promote_stage_dicom_series.py 幂等 promote）
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

回退
----
本脚本只写 stage 表，生产表在 promote 前完全不变：
- 弃数据：TRUNCATE lnrs.lnrs_stage_dicom_series;（不影响生产）
- 已 promote 后回退：见 backend/etl2/README.md「回退」一节
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

from _script_guard import add_target_argument, gate  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.database import async_db_session  # noqa: E402
from app.core.logger import log  # noqa: E402
from app.plugin.module_medical.dicom.repository import indexer  # noqa: E402

# ---------- SQL 块 ----------

# 仅筛选需要回填的 study：series_count IS NULL 且 image_path 非空。
# FROM/JOIN/WHERE 由 SQL_PENDING / SQL_DRY_RUN_REPORT / SQL_ESTIMATE 共享——谓词单源，避免漂移。
SQL_PENDING_BASE = (
    "FROM lnrs.lnrs_anon_imaging_study s "
    "LEFT JOIN lnrs.lnrs_anon_dicom_series d "
    "       ON d.dicom_study_uid = s.dicom_study_uid "
    "WHERE d.series_count IS NULL "
    "  AND s.image_path IS NOT NULL "
    "  {center_filter} "
)

SQL_PENDING = (
    "SELECT s.study_key, s.dicom_study_uid, s.center_code, "
    "s.image_path, s.anon_exam_id "
    + SQL_PENDING_BASE
    + "ORDER BY s.study_key"
)

# dry-run 阶段统计：分中心 + 待回填 study 数（不含目录在线探测）。
# 目录在线探测留到 --apply 阶段由 Python 端 Path.is_dir() 判定。
# 原因：pg_ls_dir 是 SRF 且需要 pg_read_server_files 权限，普通角色无，
# 而本脚本只需给出"哪些 study 尚未实测 + 估算耗时"就够决策。
SQL_DRY_RUN_REPORT = (
    "SELECT center_code, count(*) AS pending_total "
    "FROM ( "
    "  SELECT s.study_key, s.center_code "
    + SQL_PENDING_BASE
    + ") p "
    "GROUP BY center_code "
    "ORDER BY center_code"
)

# 闸 banner 用：预计影响行数（与 SQL_PENDING / --dry-run 同口径，共享谓词派生）
SQL_ESTIMATE = "SELECT count(*) " + SQL_PENDING_BASE

# stage 表（issue-20）：本脚本所有写入只进 stage，生产表由 promote 命令上
STAGE_TABLE = "lnrs.lnrs_stage_dicom_series"

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

SQL_UPSERT_STAGE = f"""
INSERT INTO {STAGE_TABLE}
  (anon_exam_id, dicom_study_uid, file_count, byte_size, series_count, created_batch_id)
VALUES
  (:anon_exam_id, :study_uid, :file_count, :byte_size, :series_count, :batch_id)
ON CONFLICT (dicom_study_uid) DO UPDATE SET
  series_count = EXCLUDED.series_count,
  file_count   = EXCLUDED.file_count,
  byte_size    = EXCLUDED.byte_size
"""


def _center_filter_sql(center: str | None) -> str:
    return f"AND s.center_code = '{center}'" if center else ""


async def _estimate_pending(center: str | None, limit: int | None) -> int:
    """预计影响行数（--dry-run 同口径：series_count IS NULL 的待回填 study 数）。"""
    sql = SQL_ESTIMATE.format(center_filter=_center_filter_sql(center))
    async with async_db_session() as db:
        n = (await db.execute(text(sql))).scalar()
    n = int(n or 0)
    return min(n, limit) if limit else n


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
        print(f"  {'-' * 12} {'-' * 10}")
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
            "  实际耗时取决于目录在线率；--apply 阶段逐 study is_dir() 探测并跳过离线。"
        )

    if limit:
        print(
            f"\n  注：limit={limit} 仅对 --apply 生效；dry-run 仅看统计。"
        )


def _measure_folder(path: Path) -> tuple[int, int]:
    """study 目录 → (file_count, byte_size)。与 anon_etl_engine 口径一致：iterdir+stat。"""
    files = [p for p in path.iterdir() if p.is_file()]
    byte_size = 0
    for fp in files:
        try:
            byte_size += fp.stat().st_size
        except OSError:
            continue
    return len(files), byte_size


def _measure_series_count(path: Path, study_uid: str) -> int:
    """register_folder 实测 series_count（与 DicomViewer 口径一致）；异常兜底 0。"""
    try:
        reg = indexer.register_folder(path)
        if reg and reg.get("series_count") is not None:
            return int(reg["series_count"])
    except Exception as e:
        log.warning(
            f"[APPLY] register_folder 异常 study={study_uid}: "
            f"{type(e).__name__}: {e!s}"
        )
    return 0


async def _resolve_batch_id(db, center: str | None) -> str | None:
    """created_batch_id：优先目标中心最近 batch，否则任意最近 batch；无则 None。"""
    if center:
        row = (await db.execute(
            text(SQL_GET_BATCH_ID), {"center": center}
        )).first()
        if row:
            return str(row[0])
    row = (await db.execute(text(SQL_GET_ANY_BATCH_ID))).first()
    return str(row[0]) if row else None


async def run_apply(center: str | None, limit: int | None) -> None:
    """实际回填 series_count（写入 stage 表，不直写生产表）。"""
    print(
        f"\n[APPLY] 回填 dicom_series.series_count "
        f"（center={center or 'ALL'}, limit={limit or 'NONE'}）…\n"
    )

    select_sql = SQL_PENDING.format(center_filter=_center_filter_sql(center))
    async with async_db_session() as db:
        batch_id = await _resolve_batch_id(db, center)
        if not batch_id:
            log.error("[APPLY] 无可用 ingest_batch 行，无法写入 stage 表")
            return
        log.info(f"[APPLY] 使用 batch_id={batch_id}")
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

                # 目录在线 → 实测后 upsert 进 stage 表（issue-20）。
                # series_count 走 register_folder 实测（与 DicomViewer 口径一致）；
                # anon_exam_id 取 imaging_study 当前值，NULL 直接传 None
                # （Issue 7 修复 Defect 3：不得传空串）。
                try:
                    file_count, byte_size = _measure_folder(path)
                    if not file_count:
                        # 目录在线但无文件 → 不写行（与 anon_etl_engine 口径一致）
                        continue
                    series_count = _measure_series_count(path, row.dicom_study_uid)
                    result2 = await db.execute(text(SQL_UPSERT_STAGE), {
                        "anon_exam_id": row.anon_exam_id,
                        "study_uid": row.dicom_study_uid,
                        "file_count": file_count,
                        "byte_size": byte_size,
                        "series_count": series_count,
                        "batch_id": batch_id,
                    })
                    scanned += 1
                    if result2.rowcount > 0:
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
    """Bypass 模式：绕开 exam FK 直接写 stage 表的 series_count。

    适用场景：imaging_study.anon_exam_id 100% NULL（如 h196_3 shengyi）。
    本函数直接 SQL INSERT/UPDATE 进 lnrs.lnrs_stage_dicom_series（issue-20：
    不直写生产表），anon_exam_id=NULL，created_batch_id 取真实 batch UUID。
    """
    print(
        f"\n[APPLY-BYPASS] 回填 dicom_series.series_count（绕开 exam FK）"
        f"（center={center or 'ALL'}, limit={limit or 'NONE'}）…\n"
    )

    select_sql = SQL_PENDING.format(center_filter=_center_filter_sql(center))
    async with async_db_session() as db:
        # 取有效 batch_id（优先目标中心，否则任意）
        batch_id = await _resolve_batch_id(db, center)
        if not batch_id:
            log.error("[APPLY-BYPASS] 无可用 ingest_batch 行，无法写入 stage 表")
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
                    # 跳过 register_folder（DicomIndexer 每 study 解析 DICOM 元数据极慢，对 zhujiang 86k study 估时 90+ h）；
                    #    series_count 留 NULL，等 DicomViewer 实时按需算（R 列定义允许 NULL）。
                    #    shengyi 已实测：byte_size + file_count 是必需列；series_count 可后补。
                    series_count = None
                    file_count, byte_size = _measure_folder(path)

                    # upsert 进 stage 表（anon_exam_id=NULL，有效 batch_id）
                    result2 = await db.execute(text(SQL_UPSERT_STAGE), {
                        "anon_exam_id": None,
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
    add_target_argument(p)
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
    # 安全闸（issue-21）：写生产库必须 --target 显式声明；沙箱库 lnrs_dev 免声明。
    # banner 与拒绝判断在任何 DB 连接之前完成（闸本身不依赖 DB 可达）。
    # issue-20：写入目标只有 stage 表；生产表由 promote 命令另行上（promote 自带闸）。
    writing = not args.dry_run
    gate(
        schema="lnrs",
        tables=[STAGE_TABLE],
        declared=args.target,
        estimated_rows=None,
        action="write" if writing else "read",
    )
    # 闸放行后补报预计影响行数（--dry-run 同口径，SQL_ESTIMATE）
    est = await _estimate_pending(args.center, args.limit)
    print(f"[WRITE-GATE] 预计影响行数（--dry-run 口径）: {est} study")
    if args.dry_run:
        await run_dry_run(args.center, args.limit)
    elif args.bypass_exam_fk:
        await run_apply_bypass(args.center, args.limit)
    else:
        await run_apply(args.center, args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
