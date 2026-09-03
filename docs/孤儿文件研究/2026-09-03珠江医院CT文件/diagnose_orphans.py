#!/usr/bin/env python3
"""Orphan imaging study 诊断脚本(只读)。

输入:/tmp/lnrs_audit/orphan_step3_sample.txt(每行一个孤儿完整路径)
输出:/tmp/lnrs_audit/orphan_diagnosis.csv

字段:
  path               — 孤儿完整路径
  date_prefix        — 日期前缀段($7)
  pat_local_id       — 目录名 basename '_' 前
  study_uid          — 目录名 basename '_' 后(完整 DICOM StudyInstanceUID)
  anon_id            — compute_anon_id("zhujiang", pat_local_id) = ANON_<12hex>
  in_pg              — '1' 表示该 StudyUID 在 PG lnrs_anon_imaging_study 中(理论上为 0)
  in_02_disk         — '1' 表示该 StudyUID 在 PG 02_disk_sorted 中(可能有双盘副本)
  patient_exists     — '1' 表示该 anon_id 在 lnrs_anon_patient 命中
  csv_hit            — '1' 表示 (study_uid, patient_id) 同时命中 CSV 一行
  csv_study_uid_hit  — '1' 表示 CSV 中至少有 study_uid 行(但 patient_id 可能不同)
  csv_pat_local_hit  — '1' 表示 CSV 中至少有 pat_local_id 行(用作兜底证据)
  csv_note           — 若 csv_hit=1 但 patient_id 与 pat_local_id 列4不一致,记录差异
"""
from __future__ import annotations
import csv
import hashlib
import hmac
import os
import sys
from pathlib import Path

SAMPLE = Path("/tmp/lnrs_audit/orphan_step3_sample.txt")
OUT_CSV = Path("/tmp/lnrs_audit/orphan_diagnosis.csv")
SRC_CSV = Path("/home/dzy/wk/lnrs/docs/sour/ct_image_patient_map.csv")
CENTER = "zhujiang"
PG_DSN = "host=127.0.0.1 port=5432 user=lnrs password=lnrs_pwd dbname=postgres"

# 与 scripts/build_imaging_study_index.py 一致
SECRET = os.environ.get("LNRS_ANON_SECRET", "change-me-in-production-please").encode()


def compute_anon_id(pid: str) -> str:
    mac = hmac.new(SECRET, f"{CENTER}:{pid}".encode("utf-8"), hashlib.sha256)
    return f"ANON_{mac.hexdigest()[:12]}"


def parse_path(p: str) -> tuple[str, str, str]:
    """(date_prefix, pat_local_id, study_uid)"""
    parts = p.strip().split("/")
    date_prefix = parts[6]
    base = parts[7]
    pid, _, uid = base.partition("_")
    return date_prefix, pid, uid


def main() -> int:
    import psycopg

    # 1. 读抽样路径
    paths = [ln.strip() for ln in SAMPLE.read_text().splitlines() if ln.strip()]
    print(f"[*] 抽样路径数: {len(paths)}", file=sys.stderr)

    # 2. 解析
    rows = []
    for p in paths:
        d, pid, uid = parse_path(p)
        rows.append({"path": p, "date_prefix": d, "pat_local_id": pid, "study_uid": uid})

    # 3. CSV 全量读入(36698 行,可入内存);建立 study_uid 与 patient_id 的索引
    print(f"[*] 读 CSV: {SRC_CSV}", file=sys.stderr)
    with SRC_CSV.open(encoding="utf-8-sig") as f:
        rdr = csv.DictReader(f)
        csv_rows = list(rdr)
    print(f"[*] CSV 行数: {len(csv_rows)};列: {rdr.fieldnames}", file=sys.stderr)

    # 索引:study_uid → [patient_id,...];patient_id → count
    idx_study: dict[str, list[str]] = {}
    idx_pid: dict[str, int] = {}
    for r in csv_rows:
        idx_study.setdefault(r["study_instance_uid"], []).append(r["patient_id"])
        idx_pid[r["patient_id"]] = idx_pid.get(r["patient_id"], 0) + 1

    # 4. PG 反查:批量查 StudyUID 与 anon_id
    print("[*] PG 查询", file=sys.stderr)
    study_uids = [r["study_uid"] for r in rows]
    anon_ids = [compute_anon_id(r["pat_local_id"]) for r in rows]

    pg_study_hit: dict[str, str] = {}  # study_uid → image_path (任意一条)
    pg_02_disk_hit: dict[str, str] = {}
    pg_patient_hit: set[str] = set()

    with psycopg.connect(PG_DSN) as conn:
        with conn.cursor() as cur:
            # StudyUID → image_path(全部命中)
            cur.execute(
                """
                SELECT dicom_study_uid, image_path
                FROM lnrs.lnrs_anon_imaging_study
                WHERE center_code='zhujiang'
                  AND dicom_study_uid = ANY(%s::text[])
                """,
                (study_uids,),
            )
            for uid, pth in cur.fetchall():
                pg_study_hit[uid] = pth
                if pth.startswith("/data/wlx/DATABASE/02_disk_sorted/"):
                    pg_02_disk_hit[uid] = pth

            # anon_id → patient_id
            cur.execute(
                """
                SELECT anon_id
                FROM lnrs.lnrs_anon_patient
                WHERE center_code='zhujiang'
                  AND anon_id = ANY(%s::text[])
                  AND deleted_at IS NULL
                """,
                (anon_ids,),
            )
            for (a,) in cur.fetchall():
                pg_patient_hit.add(a)

    print(f"[*] PG: in_pg={len(pg_study_hit)}, in_02_disk={len(pg_02_disk_hit)}, patient={len(pg_patient_hit)}",
          file=sys.stderr)

    # 5. 写诊断 CSV
    with OUT_CSV.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "path", "date_prefix", "pat_local_id", "study_uid", "anon_id",
            "in_pg", "in_02_disk", "patient_exists",
            "csv_hit", "csv_study_uid_hit", "csv_pat_local_hit", "csv_note",
        ])
        for r, anon in zip(rows, anon_ids):
            uid = r["study_uid"]
            pid = r["pat_local_id"]
            in_pg = "1" if uid in pg_study_hit else "0"
            in_02 = "1" if uid in pg_02_disk_hit else "0"
            pe = "1" if anon in pg_patient_hit else "0"

            csv_pid_list = idx_study.get(uid, [])
            csv_study_hit = "1" if csv_pid_list else "0"
            csv_pid_hit = "1" if pid in idx_pid else "0"
            csv_hit = "1" if (pid in csv_pid_list) else "0"
            note = ""
            if csv_study_hit == "1" and pid not in csv_pid_list:
                # study_uid 命中但 patient_id 不一致
                note = f"study_uid→CSV.patient_id={csv_pid_list[0]}"
            w.writerow([
                r["path"], r["date_prefix"], pid, uid, anon,
                in_pg, in_02, pe,
                csv_hit, csv_study_hit, csv_pid_hit, note,
            ])

    print(f"[OK] 写出 {OUT_CSV}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())