#!/usr/bin/env python3
"""修正路径解析:
- 标准 2 层:zhujiang_dicom/<date>/<patId>_<studyUid>  → pat_local_id 在 $7
- pn* 3 层:  zhujiang_dicom/pn*/<date>/<patId>_<studyUid>  → pat_local_id 在 $8
"""
from __future__ import annotations
import csv
import hashlib
import hmac
import os
import sys
from pathlib import Path

SAMPLE = Path("/tmp/lnrs_audit/orphan_paths_full.txt")
OUT_CSV = Path("/tmp/lnrs_audit/orphan_diagnosis_v4.csv")
CENTER = "zhujiang"
PG_DSN = "host=127.0.0.1 port=5432 user=lnrs password=lnrs_pwd dbname=postgres"
SECRET = os.environ.get("LNRS_ANON_SECRET", "change-me-in-production-please").encode()


def compute_anon_id(pid: str) -> str:
    mac = hmac.new(SECRET, f"{CENTER}:{pid}".encode("utf-8"), hashlib.sha256)
    return f"ANON_{mac.hexdigest()[:12]}"


def parse_path(p: str):
    """返回 (date_prefix, pat_local_id, study_uid, depth_marker)"""
    parts = p.strip().split("/")
    date_seg = parts[6]  # 总是"pn*/new*/yd*/YYYYMMDD*"形式
    if date_seg.startswith("pn"):
        # 3 层:pn*/<YYYYMMDD>/<patId>_<studyUid>
        actual_date = parts[7]
        base = parts[8]
    else:
        # 2 层
        actual_date = date_seg
        base = parts[7]
    pid, _, uid = base.partition("_")
    return actual_date, pid, uid, "pn" if date_seg.startswith("pn") else "std"


def main() -> int:
    import psycopg

    paths = [ln.strip() for ln in SAMPLE.read_text().splitlines() if ln.strip()]
    print(f"[*] 全量路径: {len(paths)}", file=sys.stderr)

    parsed = []
    for p in paths:
        actual_date, pid, uid, dep = parse_path(p)
        anon = compute_anon_id(pid) if pid else ""
        parsed.append((p, actual_date, pid, uid, anon, dep))

    study_uids = list({r[3] for r in parsed if r[3]})
    anon_ids = list({r[4] for r in parsed if r[4]})
    print(f"[*] unique study_uid={len(study_uids)}, anon_id={len(anon_ids)}", file=sys.stderr)

    # PG: study_uid → image_paths (任意源)
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

    # PG: anon_id → zhujiang patient
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
    print(f"[*] anon_id 在 zhujiang 患者表命中: {len(pg_patient)}/{len(anon_ids)}", file=sys.stderr)

    with OUT_CSV.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "path", "actual_date", "depth", "pat_local_id", "study_uid", "anon_id",
            "in_pg_exact", "in_pg_02d", "patient_in_zhujiang",
        ])
        for p, ad, pid, uid, anon, dep in parsed:
            rows = pg_rows.get(uid, [])
            exact = p in rows
            in_02 = any("/02_disk_sorted/" in r for r in rows)
            pe = anon in pg_patient if anon else False
            w.writerow([
                p, ad, dep, pid, uid, anon,
                "1" if exact else "0",
                "1" if in_02 else "0",
                "1" if pe else "0",
            ])
    print(f"[OK] 写出 {OUT_CSV}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())