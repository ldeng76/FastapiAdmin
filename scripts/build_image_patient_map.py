#!/usr/bin/env python3
"""
构建 CT 影像 ↔ 患者 ID 映射 CSV。

来源：
  盘 1 珠江 DICOM: /data/wlx/DATABASE/01_disk/zhujiang_dicom/<YYYYMMDD>/<PID>_<StudyUID>/<Series>_<Img>_<SOPUID>
  盘 2 珠江补充 : /data/wlx/DATABASE/02_disk_sorted/staging/<压缩包>/<日期>/<PID>_<StudyUID>/<Series>_<Img>_<SOPUID>
  盘 1 字段表   : _字段与原始数据/1珠江/CT与病理数据/0-Select_v_exam_patient_rpt.csv
                  _字段与原始数据/1珠江/精准医学V2_副本/0-Select_v_exam_patient_rpt.csv
                  _字段与原始数据/1珠江/历史病历查询/0-历史病历查询.csv

输出：
  docs/sour/ct_image_patient_map.csv
"""

from __future__ import annotations

import csv
import os
import re
from collections import defaultdict
from pathlib import Path

# ---------- 路径常量 ----------

ROOT = Path("/data/wlx/DATABASE")
OUT_CSV = Path("/home/dzy/wk/lnrs/docs/sour/ct_image_patient_map.csv")

DICOM_DATE_RE = re.compile(r"^\d{8}$")
PID_STUDY_RE = re.compile(r"^([A-Za-z]?\d+[A-Za-z0-9]*|\d+)_(.+)$")

CT_CSV = ROOT / "01_disk/_字段与原始数据/1珠江/CT与病理数据/0-Select_v_exam_patient_rpt.csv"
JZ_CSV = ROOT / "01_disk/_字段与原始数据/1珠江/精准医学V2_副本/0-Select_v_exam_patient_rpt.csv"
HIST_CSV = ROOT / "01_disk/_字段与原始数据/1珠江/历史病历查询/0-历史病历查询.csv"

CSV_FIELDS = [
    "source",            # disk1_zhujiang / disk2_zhujiang_supplement
    "exam_date",         # YYYYMMDD
    "exam_year_month",   # YYYY-MM
    "patient_id",        # 影像目录首段
    "study_instance_uid",
    "sop_instance_count",
    "image_path",        # 该检查单元在磁盘上的根路径
    "exam_no",           # 来自 CT/精准医学 表，按 PID 关联
    "pat_local_id",      # 来自 CT/精准医学 表
    "sick_id",           # 来自 CT/精准医学 表
    "patient_name",
    "patient_sex",
    "patient_age",
    "exam_class",
    "admission_count",   # 历史病历中的住院次数（按 pid 统计）
]


# ---------- DICOM 目录扫描 ----------

def _iter_dicom_studies(root: Path, source_tag: str):
    """遍历根目录，产出 DICOM study 记录。只下钻两层（日期 → study），不递归 study 内部文件。"""
    for date_dir in root.iterdir():
        if not date_dir.is_dir():
            continue
        date_name = date_dir.name
        if not DICOM_DATE_RE.match(date_name):
            continue
        for study_dir in date_dir.iterdir():
            if not study_dir.is_dir() or "_" not in study_dir.name:
                continue
            m = PID_STUDY_RE.match(study_dir.name)
            if not m:
                continue
            pid, study_uid = m.group(1), m.group(2)
            if not study_uid.startswith("1.2."):
                continue
            sop_count = 0
            try:
                with os.scandir(study_dir) as it:
                    for entry in it:
                        if entry.is_file():
                            sop_count += 1
            except OSError:
                pass
            yield {
                "source": source_tag,
                "exam_date": date_name,
                "exam_year_month": f"{date_name[:4]}-{date_name[4:6]}",
                "patient_id": pid,
                "study_instance_uid": study_uid,
                "sop_instance_count": sop_count,
                "image_path": str(study_dir),
            }


def scan_disk1_zhujiang():
    yield from _iter_dicom_studies(
        ROOT / "01_disk/zhujiang_dicom", "disk1_zhujiang"
    )


def scan_disk2_zhujiang_supplement():
    # staging/<pkg>/<日期>/<PID>_<StudyUID>/
    staging = ROOT / "02_disk_sorted/staging"
    if not staging.exists():
        return
    for pkg_dir in staging.iterdir():
        if not pkg_dir.is_dir():
            continue
        for date_dir in pkg_dir.iterdir():
            if not date_dir.is_dir() or not DICOM_DATE_RE.match(date_dir.name):
                continue
            for study_dir in date_dir.iterdir():
                if not study_dir.is_dir() or "_" not in study_dir.name:
                    continue
                m = PID_STUDY_RE.match(study_dir.name)
                if not m:
                    continue
                pid, study_uid = m.group(1), m.group(2)
                if not study_uid.startswith("1.2."):
                    continue
                sop_count = 0
                try:
                    with os.scandir(study_dir) as it:
                        for entry in it:
                            if entry.is_file():
                                sop_count += 1
                except OSError:
                    pass
                yield {
                    "source": "disk2_zhujiang_supplement",
                    "exam_date": date_dir.name,
                    "exam_year_month": f"{date_dir.name[:4]}-{date_dir.name[4:6]}",
                    "patient_id": pid,
                    "study_instance_uid": study_uid,
                    "sop_instance_count": sop_count,
                    "image_path": str(study_dir),
                }


# ---------- 表格数据加载 ----------

def _detect_encoding(path: Path) -> str:
    """探测文件编码。"""
    try:
        import chardet
    except ImportError:
        return "utf-8"
    raw = path.read_bytes()[:200_000]
    enc = chardet.detect(raw).get("encoding") or "utf-8"
    # chardet 把 GB2312/GBK 报成 GB2312，统一为 gbk（超集）
    if enc.lower() in {"gb2312", "gb18030"}:
        enc = "gbk"
    return enc


def _read_csv_auto(path: Path) -> list[dict]:
    """按探测出的编码读取 CSV，去除 BOM。"""
    enc = _detect_encoding(path)
    try:
        text = path.read_text(encoding=enc, errors="replace")
    except (UnicodeDecodeError, LookupError):
        text = path.read_text(encoding="utf-8", errors="replace")
    if text.startswith("\ufeff"):
        text = text[1:]
    return list(csv.DictReader(text.splitlines()))


def _strip_keys(rows: list[dict]) -> list[dict]:
    """去除字段名前后空格。"""
    out = []
    for r in rows:
        out.append({(k.strip() if k else k): v for k, v in r.items()})
    return out


def load_patient_records():
    """加载珠江患者表，按 PAT_LOCAL_ID 聚合。"""
    agg: dict[str, dict] = {}
    for path in (CT_CSV, JZ_CSV):
        for r in _strip_keys(_read_csv_auto(path)):
            pid = (r.get("PAT_LOCAL_ID") or "").strip()
            if not pid:
                continue
            rec = agg.setdefault(pid, {
                "exam_no": "",
                "pat_local_id": pid,
                "sick_id": "",
                "patient_name": "",
                "patient_sex": "",
                "patient_age": "",
                "exam_class": "",
            })
            for src_key, dst_key in [
                ("EXAM_NO", "exam_no"),
                ("SICK_ID", "sick_id"),
                ("NAME", "patient_name"),
                ("SEX", "patient_sex"),
                ("AGE", "patient_age"),
                ("EXAM_CLASS", "exam_class"),
            ]:
                if not rec[dst_key]:
                    v = (r.get(src_key) or "").strip()
                    if v:
                        rec[dst_key] = v
    return agg


def load_admission_count():
    """加载历史病历查询，按 pid 统计住院次数最大值。"""
    cnt: dict[str, int] = defaultdict(int)
    rows = _strip_keys(_read_csv_auto(HIST_CSV))
    for r in rows:
        pid = (r.get("pid") or "").strip()
        if not pid:
            continue
        try:
            n = int((r.get("住院次数") or "0").strip() or 0)
        except ValueError:
            n = 0
        cnt[pid] = max(cnt[pid], n if n > 0 else 1)
    return cnt


# ---------- 主流程 ----------

def main():
    print("扫描盘 1 珠江 DICOM ...", flush=True)
    rows = list(scan_disk1_zhujiang())
    print(f"  盘 1 单元数: {len(rows)}", flush=True)

    print("扫描盘 2 珠江补充（已整理）...", flush=True)
    rows2 = list(scan_disk2_zhujiang_supplement())
    print(f"  盘 2 单元数: {len(rows2)}", flush=True)
    rows.extend(rows2)

    print(f"  合并单元数: {len(rows)}", flush=True)

    print("加载患者表 ...", flush=True)
    pat_records = load_patient_records()
    print(f"  唯一 PAT_LOCAL_ID 数: {len(pat_records)}", flush=True)

    print("加载历史病历统计 ...", flush=True)
    adm = load_admission_count()
    print(f"  历史病历 pid 数: {len(adm)}", flush=True)

    matched = 0
    for r in rows:
        pid = r["patient_id"]
        rec = pat_records.get(pid)
        if rec:
            r["exam_no"] = rec["exam_no"]
            r["pat_local_id"] = rec["pat_local_id"]
            r["sick_id"] = rec["sick_id"]
            r["patient_name"] = rec["patient_name"]
            r["patient_sex"] = rec["patient_sex"]
            r["patient_age"] = rec["patient_age"]
            r["exam_class"] = rec["exam_class"]
            matched += 1
        r["admission_count"] = adm.get(pid, "")

    print(f"  命中 CT/精准医学表的影像检查数: {matched} / {len(rows)}", flush=True)

    rows.sort(key=lambda r: (r["source"], r["exam_date"], r["patient_id"], r["study_instance_uid"]))

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in CSV_FIELDS})
    print(f"已写入: {OUT_CSV}  (行数 {len(rows)})", flush=True)


if __name__ == "__main__":
    main()
