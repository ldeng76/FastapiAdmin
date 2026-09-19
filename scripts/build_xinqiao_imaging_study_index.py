#!/usr/bin/env python3
"""新桥 CT 影像（/data/wlx/DATABASE/03_disk/xinqiao）→ CSV 索引。

与珠江的关键差异（2026-09-20 实测）：
  1. 珠江布局 `<PID>_<StudyUID>/<扁平 DICOM 文件>`：目录名 UID == DICOM StudyInstanceUID，
     目录内直接放 DICOM 文件 → image_path 即 study 根。
  2. 新桥布局 `img_<PID>_<SeriesUID>/*.dcm`：目录名 UID == DICOM **SeriesInstanceUID**，
     study 根目录**不存在**；一个 study 的多个 series 是同层兄弟目录。
     因此必须读 DICOM header 拿到真实 StudyInstanceUID，按 (PID, StudyInstanceUID) 聚合。
  3. 新桥存在**第二种布局** `<MD5>/<StudyUID>/<SeriesUID>/*.dcm`（5_yxl/8_hy/7_hsy 部分批次），
     该布局**有** study 根目录（第 2 层），且目录名不含 PID → PID 同样来自 header。
  4. 新桥存在**第三种布局** `img_<PID>_<16hex>/*.dcm`（5_yxl，1,175 个）：目录名 PID 可用，
     UID 是不透明 16 位 hex → StudyInstanceUID 来自 header。
  5. `3_cxf_archives` 本批**排除**：实测 DICOM 的 PatientID/PatientName 全空，且其 7,984 个
     StudyInstanceUID 与其余 5 个 sub 及 PG 现有数据交集均为 0 → 无任何患者身份线索，
     需外部映射（新桥 PACS/HIS）后才能入库。见 plan-xinqiao-3disk-import.md §1.7。

本脚本只读磁盘、只写 CSV，不碰 PG。
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time
import warnings
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed

import pydicom

# 新桥部分批次把不透明 16 位 hex 当作 SeriesInstanceUID 写入（VR UI 非法）；
# 本脚本只用 StudyInstanceUID 作聚合键，故静音该告警。
warnings.filterwarnings("ignore", message="Invalid value for VR UI")

ROOT = "/data/wlx/DATABASE/03_disk/xinqiao"

# sub 目录 → source 标签
SUBS: dict[str, str] = {
    "4_tjj": "xinqiao_4_tjj",
    "5_yxl": "xinqiao_5_yxl",
    "6_zjj": "xinqiao_6_zjj",
    "7_hsy": "xinqiao_7_hsy",
    "8_hy": "xinqiao_8_hy",
}

MAX_DEPTH = 6

# `img_<PID>_<uid>`：UID 可能是 SeriesUID（含点）或不透明 16 位 hex。
# PID 形态实测有 3 种：纯数字（60,612）、字母前缀（`T04774748`，8 个）、
# 带尾点（`03009286.`，6 个）——故字符集放宽到 [A-Za-z0-9.]。
RE_IMG = re.compile(r"^img_([A-Za-z0-9.]{1,16})_(.+)$")
# MD5 布局的批次目录名
RE_MD5 = re.compile(r"^[0-9A-Fa-f]{32}$")
# 裸 UID（MD5 布局下 study 根 / series 目录名）
RE_UID = re.compile(r"^\d+(?:\.\d+)+$")
# 路径中的日期目录（YYYYMMDD），新桥批次名里是 YYYY-MM-DD
RE_DATE_DIR = re.compile(r"^(\d{8})$")
RE_DATE_IN_NAME = re.compile(r"(\d{4})-(\d{2})-(\d{2})")

DICOM_TAGS = ["StudyInstanceUID", "SeriesInstanceUID", "PatientID", "Modality"]

CSV_HEADER = [
    "patient_id", "center_code", "dicom_study_uid", "modality", "image_path",
    "sop_count", "series_count", "file_count", "byte_size", "source",
    "exam_date", "exam_date_source", "study_root_kind",
]


# --------------------------------------------------------------------------- #
# 发现阶段：单进程 walk，产出候选目录
# --------------------------------------------------------------------------- #
def _date_from_path(path: str, root: str) -> tuple[str, str]:
    """沿路径向上找最近 YYYYMMDD 目录；否则从批次目录名里的 YYYY-MM-DD 取；再否则空。"""
    rel = os.path.relpath(path, root)
    for part in reversed(rel.split(os.sep)):
        m = RE_DATE_DIR.match(part)
        if m:
            d = m.group(1)
            return f"{d[:4]}-{d[4:6]}-{d[6:]}", "path_dir"
    for part in reversed(rel.split(os.sep)):
        m = RE_DATE_IN_NAME.search(part)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}", "batch_name"
    return "", ""


def discover(sub: str) -> list[tuple[str, str, str, bool]]:
    """返回候选 [(dir_path, pid_from_name, source, is_study_root)]。"""
    src = SUBS[sub]
    base = os.path.join(ROOT, sub)
    out: list[tuple[str, str, str, bool]] = []

    for dirpath, dirnames, _files in os.walk(base, topdown=True):
        rel = os.path.relpath(dirpath, base)
        depth = 0 if rel == "." else len(rel.split(os.sep))
        if depth > MAX_DEPTH:
            dirnames[:] = []
            continue

        # 布局 A/B：img_<PID>_<uid> —— series 级叶目录
        m = RE_IMG.match(os.path.basename(dirpath))
        if m and depth > 0:
            out.append((dirpath, m.group(1), src, False))
            dirnames[:] = []
            continue

        # 布局 C：<MD5>/<StudyUID>/<SeriesUID> —— 第 2 层是 study 根
        if RE_MD5.match(os.path.basename(dirpath)):
            for child in dirnames:
                if RE_UID.match(child):
                    out.append((os.path.join(dirpath, child), "", src, True))
            dirnames[:] = []
            continue

        dirnames[:] = [d for d in dirnames if not d.startswith(".")]

    return out


# --------------------------------------------------------------------------- #
# 解析阶段：worker 内读一个 DICOM + 递归统计文件数/字节
# --------------------------------------------------------------------------- #
def resolve_one(job: tuple[str, str, str, bool]) -> dict:
    dir_path, pid_name, src, is_root = job
    try:
        files = []
        for entry in os.scandir(dir_path):
            if entry.is_file():
                files.append(entry)
        if not files and is_root:
            # 布局 C：study 根目录下是 series 子目录，DICOM 在孙层
            for sub in os.scandir(dir_path):
                if not sub.is_dir():
                    continue
                files = [e for e in os.scandir(sub.path) if e.is_file()]
                if files:
                    break
        if not files:
            return {"ok": False, "path": dir_path, "err": "no_file"}
        # 取一个可解析的 DICOM（优先 .dcm）
        files.sort(key=lambda e: (not e.name.endswith(".dcm"), e.name))
        ds = None
        last = ""
        for e in files[:5]:
            try:
                ds = pydicom.dcmread(
                    e.path, stop_before_pixels=True, specific_tags=DICOM_TAGS, force=True
                )
                break
            except Exception as exc:  # noqa: BLE001
                last = str(exc)
        if ds is None:
            return {"ok": False, "path": dir_path, "err": f"unreadable: {last}"}

        study = str(ds.get("StudyInstanceUID", "") or "")
        series = str(ds.get("SeriesInstanceUID", "") or "")
        # DICOM header 的 PatientID 是权威值（目录名 PID 可能带尾点/字母前缀），
        # 仅当 header 为空时回退到目录名。
        pid = str(ds.get("PatientID", "") or "") or pid_name
        modality = str(ds.get("Modality", "") or "")
        if not study or not pid:
            return {"ok": False, "path": dir_path, "err": f"empty study/pid (study={study!r} pid={pid!r})"}

        # study 根：递归统计；series 叶：直接统计
        n_files = 0
        n_bytes = 0
        if is_root:
            for dp, _dns, fns in os.walk(dir_path):
                for fn in fns:
                    n_files += 1
                    try:
                        n_bytes += os.stat(os.path.join(dp, fn)).st_size
                    except OSError:
                        pass
        else:
            for e in files:
                n_files += 1
                try:
                    n_bytes += e.stat().st_size
                except OSError:
                    pass

        return {
            "ok": True, "path": dir_path, "pid": pid, "study": study, "series": series,
            "modality": modality, "n_files": n_files, "n_bytes": n_bytes,
            "is_root": is_root, "src": src,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "path": dir_path, "err": repr(exc)}


def main() -> int:
    ap = argparse.ArgumentParser(description="新桥 CT 影像 → CSV 索引")
    ap.add_argument("--out", default="/home/dzy/wk/lnrs/docs/sour/ct_image_patient_map_xinqiao.csv")
    ap.add_argument("--skipped", default="/home/dzy/wk/lnrs/docs/sour/scan_skipped_dirs_xinqiao.txt")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--subs", default=",".join(SUBS))
    ap.add_argument("--dry-run", action="store_true", help="只统计不写 CSV")
    args = ap.parse_args()

    subs = [s.strip() for s in args.subs.split(",") if s.strip()]
    bad = [s for s in subs if s not in SUBS]
    if bad:
        print(f"[!] 未知 sub: {bad}", file=sys.stderr)
        return 2

    t0 = time.monotonic()
    jobs: list[tuple[str, str, str, bool]] = []
    per_sub: dict[str, int] = {}
    for sub in subs:
        t = time.monotonic()
        got = discover(sub)
        per_sub[sub] = len(got)
        jobs += got
        print(f"[scan] {SUBS[sub]:20s} 候选目录 {len(got):7d}  ({time.monotonic()-t:.1f}s)", flush=True)

    print(f"[scan] 候选合计 {len(jobs)}  ({time.monotonic()-t0:.1f}s)，开始读 DICOM header…", flush=True)

    results: list[dict] = []
    skipped: list[tuple[str, str]] = []
    done = 0
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(resolve_one, j) for j in jobs]
        for fut in as_completed(futs):
            r = fut.result()
            done += 1
            if r["ok"]:
                results.append(r)
            else:
                skipped.append((r["path"], r["err"]))
            if done % 2000 == 0:
                print(f"  ...已解析 {done}/{len(jobs)}  成功 {len(results)}  跳过 {len(skipped)}"
                      f"  ({time.monotonic()-t0:.0f}s)", flush=True)

    print(f"[resolve] 完成 {done}  成功 {len(results)}  跳过 {len(skipped)}"
          f"  ({time.monotonic()-t0:.0f}s)", flush=True)

    # 聚合：(patient_id, dicom_study_uid, source) → study 行
    agg: dict[tuple[str, str, str], dict] = {}
    for r in results:
        key = (r["pid"], r["study"], r["src"])
        a = agg.get(key)
        if a is None:
            a = {
                "pid": r["pid"], "study": r["study"], "src": r["src"],
                "modality": r["modality"], "series": set(),
                "file_count": 0, "byte_size": 0,
                "root": None, "leaves": [],
            }
            agg[key] = a
        a["series"].add(r["series"])
        a["file_count"] += r["n_files"]
        a["byte_size"] += r["n_bytes"]
        if r["is_root"]:
            a["root"] = r["path"]
        else:
            a["leaves"].append(r["path"])
        if not a["modality"]:
            a["modality"] = r["modality"]

    rows = []
    for a in agg.values():
        if a["root"]:
            image_path, kind = a["root"], "md5_layout_study_root"
        else:
            image_path, kind = min(a["leaves"]), "series_leaf"
        exam_date, exam_src = _date_from_path(image_path, ROOT)
        rows.append({
            "patient_id": a["pid"],
            "center_code": "xinqiao",
            "dicom_study_uid": a["study"],
            "modality": a["modality"] or "CT",
            "image_path": image_path,
            "sop_count": a["file_count"],
            "series_count": len(a["series"]),
            "file_count": a["file_count"],
            "byte_size": a["byte_size"],
            "source": a["src"],
            "exam_date": exam_date,
            "exam_date_source": exam_src,
            "study_root_kind": kind,
        })
    rows.sort(key=lambda r: (r["source"], r["patient_id"], r["dicom_study_uid"]))

    by_src: dict[str, int] = defaultdict(int)
    for r in rows:
        by_src[r["source"]] += 1
    pids = {r["patient_id"] for r in rows}

    print("\n[统计]")
    for s in sorted(by_src):
        print(f"  {s:20s} study {by_src[s]:7d}")
    print(f"  {'合计':20s} study {len(rows):7d}   去重 PID {len(pids)}   去重 StudyUID {len({r['dicom_study_uid'] for r in rows})}")
    print(f"  文件合计 {sum(r['file_count'] for r in rows):,}   字节合计 {sum(r['byte_size'] for r in rows)/2**40:.2f} TiB")

    if args.dry_run:
        print("\n[dry-run] 未写 CSV")
        return 0

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADER)
        w.writeheader()
        w.writerows(rows)
    print(f"\n[写出] {args.out}  ({len(rows)} 行)")

    with open(args.skipped, "w", encoding="utf-8") as f:
        for p, err in skipped:
            f.write(f"{p}\t{err}\n")
    print(f"[写出] {args.skipped}  ({len(skipped)} 条)")
    print(f"[总计] {time.monotonic()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
