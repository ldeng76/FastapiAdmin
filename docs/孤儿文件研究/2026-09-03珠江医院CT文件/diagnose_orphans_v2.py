#!/usr/bin/env python3
"""基于 lnrs_anon_patient 重做孤儿诊断。

输入:/tmp/lnrs_audit/orphan_paths_full.txt (8134 行)
输出:/tmp/lnrs_audit/orphan_diagnosis_v2.csv (全量 8134 行)
列:
  path, date_prefix, pat_local_id, study_uid, anon_id
  in_pg_any            -- StudyUID 在 lnrs_anon_imaging_study(任意 source) - 真孤儿判断
  in_pg_zhujiang_01d   -- 在 zhujiang 01_disk(应该都 0)
  in_pg_zhujiang_02d   -- 在 zhujiang 02_disk_sorted(双盘副本排查)
  patient_in_zhujiang  -- anon_id 在 lnrs_anon_patient center=zhujiang
  modality             -- 从磁盘 DICOM 头部 (0008,0060) 读出
"""
from __future__ import annotations
import csv
import hashlib
import hmac
import os
import sys
from pathlib import Path

SAMPLE = Path("/tmp/lnrs_audit/orphan_paths_full.txt")
OUT_CSV = Path("/tmp/lnrs_audit/orphan_diagnosis_v2.csv")
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


def parse_dicom_modality(filepath: Path) -> str:
    """裸解析:128 preamble + 4 DICM + explicit VR little endian → (0008,0060) Modality。"""
    with open(filepath, "rb") as f:
        f.read(128)
        magic = f.read(4)
        if magic != b"DICM":
            return ""
        for _ in range(50):
            hdr = f.read(4)
            if len(hdr) < 4:
                return ""
            group = int.from_bytes(hdr[0:2], "little")
            elem = int.from_bytes(hdr[2:4], "little")
            vr = f.read(2)
            if vr in (b"OB", b"OW", b"OF", b"SQ", b"UT", b"UN"):
                f.read(2)
                length = int.from_bytes(f.read(4), "little")
            else:
                length = int.from_bytes(f.read(2), "little")
            if group == 0x0008 and elem == 0x0060:
                return f.read(length).decode("ascii", errors="replace").strip("\x00 ").strip()
            f.seek(length, 1)
            if group > 0x0008:
                return ""
    return ""


def first_file(d: Path):
    if not d.is_dir():
        return None
    try:
        with os.scandir(d) as it:
            for ent in it:
                if ent.is_file():
                    return Path(ent.path)
    except Exception:
        return None
    return None


def main() -> int:
    import psycopg

    paths = [ln.strip() for ln in SAMPLE.read_text().splitlines() if ln.strip()]
    print(f"[*] 全量孤儿路径: {len(paths)}", file=sys.stderr)

    # 解析 + 算 anon_id
    parsed = []
    for p in paths:
        d, pid, uid = parse_path(p)
        parsed.append((p, d, pid, uid, compute_anon_id(pid)))
    study_uids = list({r[3] for r in parsed})
    anon_ids = list({r[4] for r in parsed})
    print(f"[*] unique study_uid={len(study_uids)}, anon_id={len(anon_ids)}", file=sys.stderr)

    # 1. PG:StudyUID → image_path / source
    print("[*] PG: StudyUID 全量反查", file=sys.stderr)
    pg_study: dict[str, list[tuple[str, str]]] = {}  # uid → [(image_path, source)]
    with psycopg.connect(PG_DSN) as conn:
        with conn.cursor() as cur:
            # 分块查,8134 个 study_uid
            for i in range(0, len(study_uids), 2000):
                chunk = study_uids[i:i + 2000]
                cur.execute(
                    """
                    SELECT dicom_study_uid, image_path, source
                    FROM lnrs.lnrs_anon_imaging_study
                    WHERE dicom_study_uid = ANY(%s::text[])
                    """,
                    (chunk,),
                )
                for uid, pth, src in cur.fetchall():
                    pg_study.setdefault(uid, []).append((pth, src))
    print(f"[*] PG: StudyUID 命中条数 = {sum(len(v) for v in pg_study.values())}", file=sys.stderr)

    # 2. PG:anon_id → patient_id(zhujiang, 未删除)
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
    print(f"[*] PG: anon_id 在 zhujiang 命中 = {len(pg_patient)}/{len(anon_ids)}", file=sys.stderr)

    # 3. 写 CSV(modality 先空,后面读到再回填)
    print("[*] 写中间 CSV(modality 字段待回填)", file=sys.stderr)
    with OUT_CSV.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "path", "date_prefix", "pat_local_id", "study_uid", "anon_id",
            "in_pg_any", "in_pg_01d", "in_pg_02d",
            "patient_in_zhujiang", "modality",
        ])
        for p, d, pid, uid, anon in parsed:
            rows = pg_study.get(uid, [])
            in_pg_any = "1" if rows else "0"
            in_01 = "1" if any("/01_disk/" in r[0] for r in rows) else "0"
            in_02 = "1" if any("/02_disk_sorted/" in r[0] for r in rows) else "0"
            pe = "1" if anon in pg_patient else "0"
            w.writerow([p, d, pid, uid, anon, in_pg_any, in_01, in_02, pe, ""])
    print(f"[OK] 写出中间 {OUT_CSV}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())