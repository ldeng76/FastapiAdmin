"""回填 lnrs_anon_dicom_series.series_count —— 多进程加速版（2026-09-17 性能迭代）。

性能演进（h196_3 实测，详见 docs/etl2/prd/plan-restore-series-count.md 实施记录）
-----------------------------------------------------------------------
单进程直读 NFS:            0.05-0.1 study/s（10-20s/study，NFS 小文件 IOPS）
多进程直读 register_folder: 0.77 study/s（NFS 服务端每客户端 ~1000 READ RPC/s
                            封顶 × 256KB rsize（服务端 clamped）≈ 330MB/s；
                            读全文件 = ~1400 RPC/study）
多进程 tar→tmpfs staging:   1.0-1.1 study/s（瓶颈同上，全文件 RPC 量不变）
**迭代 3 采样快速路径**:     30-43 study/s（超目标 2-3/s 10 倍以上）

迭代 3 原理
-----------
image_path 实测恒为「单 series 叶目录」布局
（/06_disk/<part>/<patient>/<study_uid>/<series_uid>/*.*；3,888 个目录样本
全部 0 子目录 + 数千次 register_folder 全量解析 series_count 均为 0/1）：
- scandir 一次 READDIR（READDIRPLUS 属性缓存命中，stat 零 RPC）→ file_count/byte_size
- 采样前 5 + 后 2 个文件头（16KB/个）按 register_file 完全相同的跳过规则
  判定 series_count（单 series → 1）
- 异常（混入第二个 series / 采样全部不可解析/坏文件）→ 回退
  indexer.register_folder 全量（与 ETL 主路径零口径偏差，罕见路径）
约 22-25 RPC/study（vs 全文件 ~1400），受 NFS 服务端 RPC 速率限制 ≈ 30-43/s。

结构
----
- 主进程：同步 SQLAlchemy（app.core.database.db_session）单连接，SELECT 候选
  → executemany 批量 upsert（anon_exam_id=NULL，0024 后可空）→ 每 COMMIT_EVERY
  条 commit。
- worker：ProcessPoolExecutor（Linux fork，继承主进程 indexer 单例，独立 LRU）。
- 多挂载点：--mounts 指定同 export 的多个挂载点，crc32(study_uid) 稳定分片。
- --staging 可选：全量 tar 到 tmpfs 再 register_folder（兜底模式，慢，仅当
  快速路径结果存疑时使用）。
- 断点续扫：WHERE series_count IS NULL。幂等：ON CONFLICT ... WHERE
  series_count IS NULL。

执行
----
    ENVIRONMENT=h196_3 uv run python etl2/backfill_dicom_series_count_mp.py \
        --apply --center shengyi --workers 24 \
        --mounts /data,/mnt/nfs_b,/mnt/nfs_c,/mnt/nfs_d
"""
import argparse
import io
import os
import shutil
import subprocess
import sys
import time
import zlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pydicom  # noqa: E402

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import text  # noqa: E402

from app.core.database import db_session  # noqa: E402
from app.core.logger import log  # noqa: E402

# 主进程先 import indexer（fork 后 worker 继承其状态；worker 内不再 import）
from app.plugin.module_medical.dicom.repository import (  # noqa: E402
    _IMAGE_SOP_CLASSES,
    _NON_IMAGE_MODALITIES,
    _SPECIFIC_TAGS,
    indexer,
)

# 快速路径采样参数（迭代 3）：image_path 实测恒为「单 series 叶目录」
#（3,888 个目录样本全部 0 子目录 + 数千次全量解析 series_count 均为 0/1），
# 故采样少数文件头即可确定 series_count；发现混入第二个 series 或采样文件
# 全部不可解析时回退 register_folder 全量（精确口径兜底，罕见）。
_SAMPLE_HEAD = 5
_SAMPLE_TAIL = 2
_SAMPLE_READ_BYTES = 16384

# ---------- SQL ----------

SQL_PENDING = (
    "SELECT s.dicom_study_uid, s.center_code, s.image_path "
    "FROM lnrs.lnrs_anon_imaging_study s "
    "LEFT JOIN lnrs.lnrs_anon_dicom_series d "
    "       ON d.dicom_study_uid = s.dicom_study_uid "
    "WHERE d.series_count IS NULL "
    "  AND s.image_path IS NOT NULL "
    "  {center_filter} "
    "ORDER BY s.study_key"
)

SQL_UPSERT = """
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

SQL_GET_ANY_BATCH_ID = (
    "SELECT batch_id FROM lnrs.lnrs_anon_ingest_batch "
    "ORDER BY started_at DESC LIMIT 1"
)

COMMIT_EVERY = 500
PROGRESS_EVERY = 200
SUBMIT_BATCH = 1000

# ---------- worker（fork 继承 indexer 单例） ----------

# 结果元组: (study_uid, status, file_count, byte_size, series_count)
# status: ok | no_dicom | failed （offline 由主进程预筛，不进 worker）


def _sample_file_is_image(path_str: str) -> str | None:
    """读文件前 16KB 解析，返回 SeriesInstanceUID；按 register_file 的跳过
    规则判定非图像/无效则返回 None。解析异常返回 ""（不可解析，非跳过）。"""
    try:
        with open(path_str, "rb") as fh:
            buf = fh.read(_SAMPLE_READ_BYTES)
        ds = pydicom.dcmread(
            io.BytesIO(buf), stop_before_pixels=True,
            specific_tags=_SPECIFIC_TAGS, force=True,
        )
    except Exception:
        return ""
    sop_class = str(getattr(ds, "SOPClassUID", "") or "")
    modality = str(getattr(ds, "Modality", "") or "")
    if modality in _NON_IMAGE_MODALITIES:
        return None
    if sop_class and sop_class not in _IMAGE_SOP_CLASSES:
        if not (getattr(ds, "Rows", None) and getattr(ds, "Columns", None)):
            return None
    if not str(getattr(ds, "StudyInstanceUID", "") or ""):
        return None
    if not str(getattr(ds, "SeriesInstanceUID", "") or ""):
        return None
    if not str(getattr(ds, "SOPInstanceUID", "") or ""):
        return None
    return str(getattr(ds, "SeriesInstanceUID"))


def _worker_process(study_uid: str, image_path: str) -> tuple:
    """处理单个 study（迭代 3 快速路径）：
    1. scandir（1 次 READDIR；READDIRPLUS 属性缓存命中，stat 不再发 RPC）
       → file_count/byte_size
    2. 采样前 _SAMPLE_HEAD + 后 _SAMPLE_TAIL 个文件头（16KB/个）判定
       series_count（恒为单 series 叶目录布局）
    3. 异常（混入多 series / 采样全部不可解析）→ 回退 register_folder
       全量（精确口径，罕见路径）
    """
    path = Path(image_path)

    # 1) file_count / byte_size（与 ETL _upsert_dicom_byte_size_for_study 同口径）
    file_count = 0
    byte_size = 0
    file_names: list[str] = []
    try:
        with os.scandir(path) as it:
            for e in it:
                try:
                    if e.is_file(follow_symlinks=False):
                        file_count += 1
                        file_names.append(e.name)
                        try:
                            byte_size += e.stat(follow_symlinks=False).st_size
                        except OSError:
                            pass
                except OSError:
                    pass
    except OSError:
        return (study_uid, "failed", 0, 0, None)

    if file_count == 0:
        return (study_uid, "no_dicom", 0, 0, None)

    # 2) 采样文件头判定 series_count
    sample_names = file_names[:_SAMPLE_HEAD]
    if file_count > _SAMPLE_HEAD + _SAMPLE_TAIL:
        sample_names += file_names[-_SAMPLE_TAIL:]
    series_uids: set[str] = set()
    parseable = False
    for name in sample_names:
        srid = _sample_file_is_image(str(path / name))
        if srid is None:
            continue  # 跳过规则命中（SR/RTPLAN/... 或无图像 SOP class）
        if srid == "":
            continue  # 不可解析（坏文件/截断）
        parseable = True
        series_uids.add(srid)
        if len(series_uids) > 1:
            break  # 混入第二个 series → 全量兜底
    if parseable and len(series_uids) == 1:
        return (study_uid, "ok", file_count, byte_size, 1)

    # 3) 回退：register_folder 全量（与 ETL 完全一致的精确口径）
    try:
        reg = indexer.register_folder(path)
        series_count = (
            int(reg["series_count"])
            if reg and reg.get("series_count") is not None else 0
        )
    except Exception:
        return (study_uid, "failed", file_count, byte_size, None)
    finally:
        try:
            indexer.evict_study(study_uid)
        except Exception:
            pass

    return (study_uid, "ok", file_count, byte_size, series_count)


# ---------- 全量 staging（迭代 2） ----------

# staging 根目录放 RAM 盘（/dev/shm，tmpfs）：12 worker × ~195MB = ~2.3GB，
# tmpfs 元数据与带宽均走内存，消除本地 HDD 的元数据 IOPS 争用（实测 12 并发
# 小文件 create/write/unlink 会把 vdc1 打到 242MB/s 上限）。
# tar 全量复制走 NFS 带宽（C→C 无 Python 开销），本地解析用原 register_folder
#（零口径偏差，无截断风险）。


def _tar_copy(src: str, dst: str) -> bool:
    """tar 流式全量复制 NFS→staging（C→C，无 Python 开销）。成功返回 True。
    dst 必须已存在。"""
    try:
        p1 = subprocess.Popen(
            ["tar", "-C", src, "-cf", "-", "."],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        p2 = subprocess.Popen(
            ["tar", "-C", dst, "-xf", "-", "-p"],
            stdin=p1.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        assert p1.stdout is not None
        p1.stdout.close()
        r1 = p1.wait()
        r2 = p2.wait()
        return r1 == 0 and r2 == 0
    except OSError:
        return False


def _worker_staged(study_uid: str, image_path: str, staging_root: str) -> tuple:
    """全量 staging 流水线（staging_root 放 /dev/shm RAM 盘）：
    1. NFS readdir 属性 → file_count/byte_size（不读内容）
    2. tar 全量复制 NFS→tmpfs（走 NFS 带宽，12 worker ≈ GB/s 聚合）
    3. 本地 register_folder（tmpfs 读 + CPU 解析，零口径偏差）
    4. 清理 tmpfs 暂存
    """
    src = image_path
    file_count = 0
    byte_size = 0
    try:
        for p in Path(src).iterdir():
            if p.is_file():
                file_count += 1
                try:
                    byte_size += p.stat().st_size
                except OSError:
                    pass
    except OSError:
        return (study_uid, "failed", 0, 0, None)
    if file_count == 0:
        return (study_uid, "no_dicom", 0, 0, None)

    stage_dir = Path(staging_root) / study_uid
    if stage_dir.exists():
        shutil.rmtree(stage_dir, ignore_errors=True)
    try:
        stage_dir.mkdir(parents=True)
    except OSError:
        return (study_uid, "failed", file_count, byte_size, None)

    ok = _tar_copy(src, str(stage_dir))
    if not ok:
        shutil.rmtree(stage_dir, ignore_errors=True)
        return (study_uid, "failed", file_count, byte_size, None)

    try:
        try:
            reg = indexer.register_folder(stage_dir)
            series_count = (
                int(reg["series_count"])
                if reg and reg.get("series_count") is not None else 0
            )
        except Exception:
            return (study_uid, "failed", file_count, byte_size, None)
        finally:
            try:
                indexer.evict_study(study_uid)
            except Exception:
                pass
        return (study_uid, "ok", file_count, byte_size, series_count)
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)


# ---------- main ----------


def _center_filter_sql(center: str | None) -> str:
    return f"AND s.center_code = '{center}'" if center else ""


def _pick_mount(study_uid: str, mounts: list[str]) -> str:
    """crc32 稳定分片：同一 study 恒走同一挂载点（页缓存局部性）。"""
    if len(mounts) <= 1:
        return mounts[0] if mounts else "/data"
    return mounts[zlib.crc32(study_uid.encode()) % len(mounts)]


def _remap_path(image_path: str, mount_root: str) -> str:
    """/data 是 export /wlx-storage 的挂载点；其他挂载点同 export，
    路径前缀替换即可（/data/wlx/... → /mnt/nfs_b/wlx/...）。"""
    if mount_root == "/data" or not image_path.startswith("/data/"):
        return image_path
    return mount_root + image_path[len("/data"):]


def run_apply(center: str | None, limit: int | None, workers: int,
              mounts: list[str], staging_root: str | None, dry_run: bool) -> None:
    print(
        f"\n[MP-APPLY] 多进程回填 series_count "
        f"（center={center or 'ALL'}, limit={limit or 'NONE'}, workers={workers}, "
        f"mounts={mounts}, staging={staging_root or 'OFF'}"
        f"{', DRY-RUN' if dry_run else ''}）…\n"
    )
    if staging_root:
        sroot = Path(staging_root)
        sroot.mkdir(parents=True, exist_ok=True)
        # 清掉上次崩溃残留的 staging 目录（本目录为专用暂存区，整目录可删）
        for stale in sroot.iterdir():
            if stale.is_dir():
                shutil.rmtree(stale, ignore_errors=True)

    t0 = time.monotonic()
    session = db_session()
    try:
        sql = SQL_PENDING.format(center_filter=_center_filter_sql(center))
        pending = [(r[0], r[1], r[2]) for r in session.execute(text(sql))]
        if limit:
            pending = pending[:limit]
        print(f"  候选 study: {len(pending)} 条（查询耗时 {time.monotonic()-t0:.1f}s）")
        if not pending:
            print("  （无候选 study）")
            return

        batch_id = None
        if not dry_run:
            row = session.execute(text(SQL_GET_ANY_BATCH_ID)).first()
            batch_id = str(row[0]) if row else None
            if not batch_id:
                print("  无可用 ingest_batch，终止")
                return
            print(f"  batch_id={batch_id}")

        # 预筛离线（主进程 is_dir；part07-12 共 ~30k 行离线，提前过滤省 worker 调度）
        online: list[tuple[str, str]] = []
        offline_n = 0
        for uid, _c, p in pending:
            if Path(p).is_dir():
                online.append((uid, _remap_path(p, _pick_mount(uid, mounts))))
            else:
                offline_n += 1
        print(f"  在线目录: {len(online)} / {len(pending)}（离线 {offline_n}，提前过滤）")
        if not online:
            print("  （无在线 study）")
            return

        scanned = 0
        ok = 0
        no_dicom = 0
        failed = 0
        flushed = 0
        pending_flush: list[tuple] = []

        def _commit_flush(force: bool = False) -> None:
            nonlocal pending_flush, flushed
            while len(pending_flush) >= COMMIT_EVERY or (force and pending_flush):
                take = COMMIT_EVERY if len(pending_flush) >= COMMIT_EVERY else len(pending_flush)
                chunk = pending_flush[:take]
                del pending_flush[:take]
                if dry_run:
                    continue
                rows = [
                    {"study_uid": u, "file_count": fc, "byte_size": bs,
                     "series_count": sc, "batch_id": batch_id}
                    for u, _s, fc, bs, sc in chunk
                ]
                session.execute(text(SQL_UPSERT), rows)
                session.commit()
                flushed += len(rows)

        def _drain(res: tuple) -> None:
            nonlocal scanned, ok, no_dicom, failed
            scanned += 1
            _uid, status, _fc, _bs, _sc = res
            if status == "ok":
                ok += 1
                pending_flush.append(res)
            elif status == "no_dicom":
                no_dicom += 1
            elif status == "failed":
                failed += 1
            _commit_flush()
            if scanned % PROGRESS_EVERY == 0:
                el = time.monotonic() - t0
                rate = scanned / el
                eta = (len(online) - scanned) / rate if rate > 0 else 0
                print(
                    f"  进度 {scanned}/{len(online)} ok={ok} no_dicom={no_dicom} "
                    f"failed={failed} flushed={flushed} rate={rate:.2f} study/s "
                    f"eta={eta/60:.1f}min",
                    flush=True,
                )

        if staging_root:
            _wf = _worker_staged
        else:
            _wf = _worker_process
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for i in range(0, len(online), SUBMIT_BATCH):
                chunk = online[i : i + SUBMIT_BATCH]
                futs = [
                    ex.submit(_wf, uid, p) if staging_root is None
                    else ex.submit(_wf, uid, p, staging_root)
                    for uid, p in chunk
                ]
                for f in futs:
                    _drain(f.result())

        _commit_flush(force=True)
    finally:
        session.close()

    el = time.monotonic() - t0
    rate = scanned / el if el > 0 else 0
    print(
        f"\n[MP-APPLY] 完成：scanned={scanned} ok={ok} no_dicom={no_dicom} "
        f"failed={failed} offline_pre={offline_n} flushed={flushed} "
        f"elapsed={el:.0f}s rate={rate:.2f} study/s center={center or 'ALL'}"
    )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="backfill_dicom_series_count_mp")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="只扫描+统计，不写库")
    g.add_argument("--apply", action="store_true", help="实际回填")
    p.add_argument("--center", default=None,
                   choices=["zhujiang", "shengyi", "xinqiao", "hos301"])
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--workers", type=int, default=12,
                   help="进程池大小（默认 12 = 本机核数；I/O bound 可超配）")
    p.add_argument("--mounts", default="/data",
                   help="同 export 的挂载点列表，逗号分隔（默认 /data；"
                        "多挂载点突破 NFS 单连接带宽上限）")
    p.add_argument("--staging", default=None,
                   help="本地暂存盘根目录（如 /data2/series_staging）；"
                        "设置后 worker 走 tar 流式复制到本地再解析，"
                        "突破 NFS 小文件 IOPS 上限（实测 4 mounts ~1GB/s）")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    mounts = [m.strip() for m in args.mounts.split(",") if m.strip()]
    run_apply(args.center, args.limit, args.workers, mounts,
              staging_root=args.staging, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
