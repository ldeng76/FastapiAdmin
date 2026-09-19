#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""珠江三盘 DICOM 统一扫描 → CSV（重建 ct_image_patient_map_v2.csv）。

2026-09-19 新版。覆盖：
  * disk1:  /data/wlx/DATABASE/01_disk/zhujiang_dicom/
  * disk2:  /data/wlx/DATABASE/02_disk_sorted/staging/
  * disk4:  /data/wlx/DATABASE/04_disk/result/（含 *.zip_folder/）

设计要点：
  1. 统一递归匹配 <PID>_<StudyUID>，命中 study 即剪枝（不再仅认 <YYYYMMDD> 顶层 + 1.2. 前缀）
  2. exam_date 沿路径向上找最近 YYYYMMDD 顶层目录；找不到回退 mtime
  3. dry-run 与基线比对（原始目录匹配数），偏差 >1% 报错
  4. PHI 列从既有患者表/历史病历 CSV 取（旧路径失败则留空，不阻断）

输出：
  - /home/dzy/wk/lnrs/docs/sour/ct_image_patient_map_v2.csv
  - /home/dzy/wk/lnrs/docs/sour/scan_skipped_dirs.txt（被 .gitignore 忽略）
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# ---------- 路径与常量 ----------

ROOT = Path("/data/wlx/DATABASE")
OUT_CSV = Path("/home/dzy/wk/lnrs/docs/sour/ct_image_patient_map_v2.csv")
SKIP_LOG = Path("/home/dzy/wk/lnrs/docs/sour/scan_skipped_dirs.txt")

STUDY_RE = re.compile(r"^([A-Za-z]?\d+[A-Za-z0-9]*|\d+)_(.+)$")
DICOM_DATE_RE = re.compile(r"^\d{8}$")

DISK_ROOTS: list[tuple[Path, str]] = [
    (ROOT / "01_disk" / "zhujiang_dicom", "disk1_zhujiang"),
    (ROOT / "02_disk_sorted" / "staging", "disk2_zhujiang_supplement"),
    (ROOT / "04_disk" / "result", "disk4_zhujiang"),
]

# 实测基线（2026-09-19 手工 find 扫描；去重前原始目录数）
BASELINE = {
    "disk1_zhujiang": 27131,
    "disk2_zhujiang_supplement": 19710,
    "disk4_zhujiang": 40416,
    "total": 87594,
}

CSV_FIELDS = [
    "source",
    "exam_date",
    "exam_year_month",
    "exam_date_source",
    "patient_id",
    "study_instance_uid",
    "sop_instance_count",
    "image_path",
    "exam_no",
    "pat_local_id",
    "sick_id",
    "patient_name",
    "patient_sex",
    "patient_age",
    "exam_class",
    "admission_count",
]

MAX_DEPTH = 6


# ---------- 工具函数 ----------


def _is_study_dir(name: str) -> tuple[str, str] | None:
    m = STUDY_RE.match(name)
    if not m:
        return None
    pid, uid = m.group(1), m.group(2)
    if not any(c.isdigit() for c in pid):
        return None
    if "." not in uid:
        return None
    return pid, uid


def _count_files(study_dir: Path) -> int:
    n = 0
    try:
        with os.scandir(study_dir) as it:
            for entry in it:
                if entry.is_file():
                    n += 1
    except OSError:
        pass
    return n


def _find_exam_date(study_dir: Path) -> tuple[str, str]:
    cur = study_dir
    for _ in range(MAX_DEPTH):
        cur = cur.parent
        if cur == cur.parent:
            break
        if DICOM_DATE_RE.match(cur.name):
            return cur.name, "path_date"
    try:
        st = study_dir.stat()
        dt = datetime.fromtimestamp(st.st_mtime)
        return dt.strftime("%Y%m%d"), "mtime"
    except OSError:
        return "", "unknown"


def _source_tag_for(root: Path) -> str:
    for r, tag in DISK_ROOTS:
        if root == r:
            return tag
    return "unknown"


def _iter_studies(root: Path) -> tuple[list[dict], list[Path]]:
    rows: list[dict] = []
    skipped: list[Path] = []
    if not root.exists():
        return rows, skipped
    for dirpath, dirnames, _filenames in os.walk(root, topdown=True, followlinks=False):
        cur = Path(dirpath)
        depth = len(cur.relative_to(root).parts)
        if depth > MAX_DEPTH:
            dirnames[:] = []
            continue
        if depth > 0:
            m = _is_study_dir(cur.name)
            if m is not None:
                pid, uid = m
                file_count = _count_files(cur)
                exam_date, date_source = _find_exam_date(cur)
                rows.append({
                    "source": _source_tag_for(root),
                    "exam_date": exam_date,
                    "exam_year_month": f"{exam_date[:4]}-{exam_date[4:6]}" if exam_date else "",
                    "exam_date_source": date_source,
                    "patient_id": pid,
                    "study_instance_uid": uid,
                    "sop_instance_count": file_count,
                    "image_path": str(cur),
                })
                dirnames[:] = []
                continue
        pruned: list[str] = []
        for d in dirnames:
            if d.startswith("."):
                continue
            pruned.append(d)
        dirnames[:] = pruned
    return rows, skipped


def _dedupe(rows: list[dict]) -> list[dict]:
    seen: set[tuple[str, str, str]] = set()
    out: list[dict] = []
    for r in rows:
        key = (r["patient_id"], r["study_instance_uid"], r["source"])
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _load_phi_columns(rows: list[dict]) -> None:
    try:
        from build_image_patient_map import load_patient_records, load_admission_count  # type: ignore
    except Exception as e:
        print(f"  [phi] 跳过 PHI 列加载：{e}")
        return
    try:
        patient_recs = load_patient_records()
    except Exception as e:
        print(f"  [phi] load_patient_records 失败：{e}")
        patient_recs = {}
    try:
        adm_count = load_admission_count()
    except Exception as e:
        print(f"  [phi] load_admission_count 失败：{e}")
        adm_count = {}
    keys = ["exam_no", "pat_local_id", "sick_id", "patient_name",
            "patient_sex", "patient_age", "exam_class"]
    for r in rows:
        rec = patient_recs.get(r["patient_id"])
        if rec:
            for k in keys:
                r[k] = rec.get(k, "") or ""
        else:
            for k in keys:
                r[k] = ""
        r["admission_count"] = str(adm_count.get(r["patient_id"], "")) if r["patient_id"] in adm_count else ""


def _check_baseline(all_rows: list[dict], deduped: list[dict]) -> bool:
    by_source_raw: dict[str, int] = defaultdict(int)
    for r in all_rows:
        by_source_raw[r["source"]] += 1
    total_raw = sum(by_source_raw.values())
    print(f"\n[基线校验] 与 2026-09-19 实测基线比对（容差 ±1%，口径=原始目录匹配数）:")
    ok = True
    for src, expected in BASELINE.items():
        if src == "total":
            continue
        got = by_source_raw.get(src, 0)
        if expected == 0:
            continue
        delta_pct = (got - expected) / expected * 100
        flag = "OK" if abs(delta_pct) <= 1.0 else "❌"
        if abs(delta_pct) > 1.0:
            ok = False
        print(f"  {src:32s}  实测 {got:6d}  基线 {expected:6d}  Δ {delta_pct:+.2f}%  {flag}")
    exp_total = BASELINE["total"]
    delta_pct = (total_raw - exp_total) / exp_total * 100
    flag = "OK" if abs(delta_pct) <= 1.0 else "❌"
    if abs(delta_pct) > 1.0:
        ok = False
    print(f"  {'TOTAL':32s}  实测 {total_raw:6d}  基线 {exp_total:6d}  Δ {delta_pct:+.2f}%  {flag}")
    print(f"\n  注：去重后写库行数（盘内同 (PID,UID,source) 重复合并）:")
    by_source_w: dict[str, int] = defaultdict(int)
    for r in deduped:
        by_source_w[r["source"]] += 1
    total_w = sum(by_source_w.values())
    for src in sorted(by_source_raw):
        if by_source_raw[src]:
            print(f"    {src:32s}  写库 {by_source_w.get(src,0):6d}  原始 {by_source_raw[src]:6d}  Δ {by_source_raw[src] - by_source_w.get(src,0)}")
    print(f"    {'TOTAL':32s}  写库 {total_w:6d}  原始 {total_raw:6d}")
    return ok


# ---------- 主入口 ----------


def main() -> int:
    parser = argparse.ArgumentParser(description="珠江三盘 DICOM 统一扫描 → CSV")
    parser.add_argument("--dry-run", action="store_true",
                        help="只解析与统计，与基线比对，不写文件")
    parser.add_argument("--out", type=Path, default=OUT_CSV, help="输出 CSV 路径")
    parser.add_argument("--skip-phi", action="store_true", help="跳过 PHI 列加载")
    args = parser.parse_args()

    print(f"[*] 根目录: {ROOT}")
    print(f"[*] 输出: {args.out}")
    print(f"[*] dry-run={args.dry_run}")
    t0 = time.time()

    all_rows: list[dict] = []
    all_skipped: list[Path] = []
    for root, tag in DISK_ROOTS:
        print(f"\n[scan] {tag}  root={root}")
        if not root.exists():
            print(f"  ⚠ 根不存在：{root}，跳过")
            continue
        rows, skipped = _iter_studies(root)
        print(f"  命中 study: {len(rows)}  跳过目录: {len(skipped)}")
        all_rows.extend(rows)
        all_skipped.extend(skipped)

    print(f"\n[汇总] 扫描前总命中: {len(all_rows)}  (含跨盘同 (PID,UID,source) 重复)")
    deduped = _dedupe(all_rows)
    print(f"[去重] (PID, UID, source) 内部去重后: {len(deduped)}  (消 {len(all_rows) - len(deduped)})")

    cross: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in deduped:
        cross[(r["patient_id"], r["study_instance_uid"])].append(r["source"])
    n_cross = sum(1 for v in cross.values() if len(v) > 1)
    print(f"[跨盘重复] 同 (PID, UID) 在多 source: {n_cross} 条 (共占 {sum(len(v) for v in cross.values() if len(v) > 1)} 行，保留多行)")

    if not args.skip_phi:
        print(f"\n[PHI] 从既有 CT/精准医学表加载 patient_name/sex/age/...")
        _load_phi_columns(deduped)
    else:
        for k in ["exam_no", "pat_local_id", "sick_id", "patient_name",
                  "patient_sex", "patient_age", "exam_class", "admission_count"]:
            for r in deduped:
                r[k] = ""

    distinct_uid = len({r["study_instance_uid"] for r in deduped})
    distinct_pid = len({r["patient_id"] for r in deduped})
    print(f"\n[统计]  去重 UID: {distinct_uid}  去重 PID: {distinct_pid}  写库行: {len(deduped)}")

    ok = _check_baseline(all_rows, deduped)
    if not ok:
        print(f"\n[❌] 基线偏差超 ±1%，请检查扫描口径或磁盘变化。中止。")
        return 2

    if args.dry_run:
        print(f"\n[dry-run] 不写 CSV；耗时 {time.time() - t0:.1f}s")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        w.writerows(deduped)
    print(f"\n[OK] 写入: {args.out}  (行数 {len(deduped)})")

    SKIP_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(SKIP_LOG, "w", encoding="utf-8") as f:
        f.write(f"# 扫描跳过目录清单（{len(all_skipped)} 个）\n")
        f.write(f"# 扫描根：{ROOT}\n#\n")
        for p in all_skipped:
            f.write(f"{p}\n")
    print(f"  跳过清单: {SKIP_LOG}  ({len(all_skipped)} 条)")

    print(f"\n总耗时: {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())