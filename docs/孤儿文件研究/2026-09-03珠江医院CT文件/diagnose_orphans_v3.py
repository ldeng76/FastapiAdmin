#!/usr/bin/env python3
"""修正版:用 StudyUID + 完整 image_path 判定孤儿,而非 basename。

问题:01_disk 和 02_disk_sorted 可能有同名目录(<patId>_<studyUid>),basename
相同但 image_path 不同。comm 用 basename 比对 → 错把双盘副本当孤儿。

修正:每个磁盘侧路径,直接查 PG 是否存在 (study_uid, image_path 末段完全匹配)。
如果 (study_uid, image_path) 在 PG 中无记录 → 真孤儿;若 PG 已有同 study_uid
但路径指向 02_disk_sorted → 是双盘副本,不算孤儿。
"""
from __future__ import annotations
import csv
import hashlib
import hmac
import os
import sys
from pathlib import Path

SAMPLE = Path("/tmp/lnrs_audit/orphan_paths_full.txt")
OUT_CSV = Path("/tmp/lnrs_audit/orphan_diagnosis_v3.csv")
CENTER = "zhujiang"
PG_DSN = "host=127.0.0.1 port=5432 user=lnrs password=lnrs_pwd dbname=postgres"
SECRET = os.environ.get("LNRS_ANON_SECRET", "change-me-in-production-please").encode()


def compute_anon_id(pid: str) -> str:
    mac = hmac.new(SECRET, f"{CENTER}:{pid}".encode("utf-8"), hashlib.sha256)
    return f"ANON_{mac.hexdigest()[:12]}"


def parse_path(p: str):
    parts = p.strip().split("/")
    date_prefix = parts[6]
    base = parts[7]
    pid, _, uid = base.partition("_")
    return date_prefix, pid, uid


def main() -> int:
    import psycopg

    paths = [ln.strip() for ln in SAMPLE.read_text().splitlines() if ln.strip()]
    print(f"[*] 全量路径: {len(paths)}", file=sys.stderr)

    parsed = []
    for p in paths:
        d, pid, uid = parse_path(p)
        parsed.append((p, d, pid, uid, compute_anon_id(pid)))
    study_uids = list({r[3] for r in parsed})
    anon_ids = list({r[4] for r in parsed})

    # 1. PG:对每个 (study_uid, 完整路径) 直接查 PG 是否有该 image_path
    # 即:SELECT 1 FROM ... WHERE dicom_study_uid=? AND image_path=?
    # 准备批量 SQL
    print("[*] PG: (study_uid, image_path) 精确匹配", file=sys.stderr)
    # 我们要的是"该 path 是否在 PG 已登记";以及"同 study_uid 在 PG 是否登记过"
    # 由于 8134 行需要 8134 次查,直接用 ANY + LATERAL 太慢;改成:
    # 先查所有 unique study_uid 的 PG 行,然后在 Python 里比对完整路径
    pg_rows: dict[str, list[str]] = {}
    with psycopg.connect(PG_DSN) as conn:
        with conn.cursor() as cur:
            for i in range(0, len(study_uids), 2000):
                chunk = study_uids[i:i + 2000]
                cur.execute(
                    """
                    SELECT dicom_study_uid, image_path
                    FROM lnrs.lnrs_anon_imaging_study
                    WHERE center_code='zhujiang'
                      AND dicom_study_uid = ANY(%s::text[])
                    """,
                    (chunk,),
                )
                for uid, pth in cur.fetchall():
                    pg_rows.setdefault(uid, []).append(pth)

    # 2. PG:anon_id → zhujiang patient
    print("[*] PG: anon_id → zhujiang patient", file=sys.stderr)
    pg_patient: set[str] = set()
    with psycopg.connect(PG_DSN) as conn:
        with conn.cursor() as cur:
            for i in range(0, len(anon_ids), 5000):
                chunk = anon_ids[i:i + 5000]
                cur.execute(
                    """
                    SELECT anon_id
                    FROM lnrs.lnrs_anon_patient
                    WHERE center_code='zhujiang'
                      AND anon_id = ANY(%s::text[])
                      AND deleted_at IS NULL
                    """,
                    (chunk,),
                )
                for (a,) in cur.fetchall():
                    pg_patient.add(a)

    # 3. 写 CSV:精确路径匹配
    print("[*] 写结果", file=sys.stderr)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "path", "date_prefix", "pat_local_id", "study_uid", "anon_id",
            "in_pg_exact_path", "in_pg_same_uid_02d", "patient_in_zhujiang",
        ])
        n_real = n_dup = n_pat_miss = 0
        for p, d, pid, uid, anon in parsed:
            rows = pg_rows.get(uid, [])
            exact = p in rows
            in_02 = any("/02_disk_sorted/" in r for r in rows)
            pe = anon in pg_patient
            in_pg = "1" if exact else "0"
            in_02_mark = "1" if in_02 else "0"
            pe_mark = "1" if pe else "0"
            w.writerow([p, d, pid, uid, anon, in_pg, in_02_mark, pe_mark])
            if exact:
                n_real += 0  # 已被登记,不算孤儿(应从孤儿清单移除)
            elif in_02:
                n_dup += 1  # 双盘副本,不算孤儿
            else:
                n_real += 1  # 真孤儿
            if not pe:
                n_pat_miss += 1
        print(f"[*] 真孤儿(in_pg_exact=0, 无 02d)= {n_real}", file=sys.stderr)
        print(f"[*] 双盘副本(02d 同 study_uid)= {n_dup}", file=sys.stderr)
        print(f"[*] patient_in_zhujiang=0 = {n_pat_miss}", file=sys.stderr)
    print(f"[OK] 写出 {OUT_CSV}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())