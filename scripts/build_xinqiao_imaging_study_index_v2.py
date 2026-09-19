#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新桥 CT 影像（03_disk/xinqiao 的 5 个 sub）→ PG 灌库。

写入：
  - lnrs.lnrs_anon_ingest_batch  (source_kind='dicom_dir', center_code='xinqiao', 每个 source 一个 batch)
  - lnrs.lnrs_anon_patient       (增量发号, is_placeholder=TRUE)
  - lnrs.lnrs_anon_imaging_study (anon_exam_id=NULL)
  - lnrs.lnrs_anon_dicom_series  (file_count/byte_size/series_count 由扫描阶段算好，**不再跑 backfill**)
  - lnrs.lnrs_anon_phi_audit     (每 imaging_study 一条 hmac)

与珠江 v2 的差异：
  1. 一个 source 一个 batch（5 个），便于按 sub 单独回退；
  2. dicom_series 在此一并写入 —— 新桥的 study 由多个同层 series 目录聚合而成，
     `backfill_dicom_series_count.py` 的非递归 `iterdir()` 对这类目录会算出 0，
     且其 NFS 扫描成本极高；扫描阶段已有准确的 file_count/byte_size/series_count。
  3. modality 来自 DICOM header（非硬编码）。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import os
import re
import time
import uuid
from pathlib import Path

CENTER = "xinqiao"
SALT_PREFIX = "xinqiao:"

OUT_CSV = Path("/home/dzy/wk/lnrs/docs/sour/ct_image_patient_map_xinqiao.csv")
PATIENT_ADDED_TXT = Path("/home/dzy/wk/lnrs/docs/sour/xinqiao_imaging_study_patient_added.txt")

PHI_SOURCE_TABLE = "lnrs_anon_imaging_study"
PHI_SOURCE_FIELD = "patient_id"
PHI_STRATEGY = "hmac"

# PID 形态：纯数字 / 字母前缀（T04774748）/ 带尾点（03009286.）——以 DICOM header 为权威值
RE_PID = re.compile(r"^[A-Za-z0-9.]{1,16}$")


def compute_anon_id(pid: str, secret: str) -> str:
    mac = hmac.new(secret.encode("utf-8"), f"{SALT_PREFIX}{pid}".encode("utf-8"), hashlib.sha256)
    return f"ANON_{mac.hexdigest()[:12]}"


def pg_conn_str() -> str:
    return (
        f"host={os.environ.get('DATABASE_HOST', '127.0.0.1')} "
        f"port={int(os.environ.get('DATABASE_PORT', '5432'))} "
        f"user={os.environ.get('DATABASE_USER', 'lnrs')} "
        f"password={os.environ.get('DATABASE_PASSWORD', 'lnrs_pwd')} "
        f"dbname={os.environ.get('DATABASE_NAME', 'postgres')}"
    )


def load_anon_secret() -> tuple[str, str]:
    return (
        os.environ.get("LNRS_ANON_SECRET", "change-me-in-production-please"),
        os.environ.get("LNRS_ANON_SECRET_VERSION", "v1"),
    )


def read_csv_rows(csv_path: Path) -> list[dict]:
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    print(f"  CSV rows: {len(rows)}")
    return rows


def filter_valid(rows: list[dict]) -> tuple[list[dict], int]:
    good: list[dict] = []
    bad = 0
    for r in rows:
        pid = (r.get("patient_id") or "").strip()
        uid = (r.get("dicom_study_uid") or "").strip()
        src = (r.get("source") or "").strip()
        path = (r.get("image_path") or "").strip()
        if not RE_PID.match(pid) or not uid or not src or not path:
            bad += 1
            continue
        good.append({
            "pid": pid, "uid": uid, "src": src, "path": path,
            "modality": (r.get("modality") or "CT").strip() or "CT",
            "sop_count": int(r.get("sop_count") or 0),
            "series_count": int(r.get("series_count") or 0),
            "file_count": int(r.get("file_count") or 0),
            "byte_size": int(r.get("byte_size") or 0),
        })
    return good, bad


def main() -> int:
    parser = argparse.ArgumentParser(description="新桥 5 sub imaging_study 灌库")
    parser.add_argument("--csv", type=Path, default=OUT_CSV)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=2000)
    args = parser.parse_args()

    print(f"[*] 中心={CENTER}  dry-run={args.dry_run}")
    t0 = time.time()

    secret, secret_version = load_anon_secret()
    print(f"[*] secret_version={secret_version}")

    print(f"\n[Step 1] 读 CSV: {args.csv}")
    if not args.csv.exists():
        print(f"  ❌ CSV 不存在：{args.csv}")
        return 2
    rows = read_csv_rows(args.csv)
    parsed, bad = filter_valid(rows)
    print(f"  有效行 {len(parsed)}  丢弃（PID/UID/路径不合法）{bad}")

    pids = sorted({r["pid"] for r in parsed})
    sources = sorted({r["src"] for r in parsed})
    pid_to_anon = {p: compute_anon_id(p, secret) for p in pids}
    print(f"  distinct patient_id: {len(pids)}")
    print(f"  distinct dicom_study_uid: {len({r['uid'] for r in parsed})}")
    print(f"  sources: {sources}")

    # 每个 source 一个 batch
    src_to_batch = {s: uuid.uuid4() for s in sources}
    print(f"\n[Step 2] 本次 batch（每 source 一个）:")
    for s in sources:
        print(f"  {s:20s} {src_to_batch[s]}")

    import psycopg

    conn = psycopg.connect(pg_conn_str())
    conn.autocommit = False
    anon_to_pt: dict[str, str] = {}
    patient_added: list[tuple[str, str, str]] = []
    to_add: list[str] = []

    try:
        with conn.cursor() as cur:
            # 2a) ingest_batch × N
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('xinqiao_patient_seq'))")
            for s in sources:
                cur.execute(
                    """
                    INSERT INTO lnrs.lnrs_anon_ingest_batch
                        (batch_id, center_code, source_kind, source_locator,
                         secret_version, key_fingerprint, schema_hash, status)
                    VALUES (%s, %s, 'dicom_dir', %s, %s, %s, %s, 'running')
                    ON CONFLICT (batch_id) DO NOTHING
                    """,
                    (
                        src_to_batch[s], CENTER,
                        f"{args.csv}#{s}",
                        secret_version,
                        hashlib.sha256(secret.encode("utf-8")).hexdigest()[:16],
                        # schema_hash 必须逐 source 不同：ingest_batch 有
                        # UNIQUE(center_code, secret_version, key_fingerprint, schema_hash, started_at)，
                        # 而同一事务内 CURRENT_TIMESTAMP 相同 → 5 个 batch 会撞唯一键。
                        hashlib.sha256(f"xinqiao_disk_image_index_20260920:{s}".encode("utf-8")).hexdigest(),
                    ),
                )

            # 2b) 反查 anon_id → patient_id
            anon_list = list(pid_to_anon.values())
            for i in range(0, len(anon_list), 5000):
                chunk = anon_list[i: i + 5000]
                cur.execute(
                    """
                    SELECT anon_id, patient_id FROM lnrs.lnrs_anon_patient
                    WHERE center_code = %s AND anon_id = ANY(%s) AND deleted_at IS NULL
                    """,
                    (CENTER, chunk),
                )
                for anon, pt in cur.fetchall():
                    anon_to_pt[anon] = pt

            print(f"\n[Step 3] 反查命中（patient 复用）: {len(anon_to_pt)}")
            to_add = [pid for pid in pids if pid_to_anon[pid] not in anon_to_pt]
            print(f"  需要新增 patient: {len(to_add)}")

            # 首现 source → 该 patient 的 created_batch_id
            pid_first_src: dict[str, str] = {}
            for r in parsed:
                pid_first_src.setdefault(r["pid"], r["src"])

            if to_add and not args.dry_run:
                ins = """
                    INSERT INTO lnrs.lnrs_anon_patient
                        (patient_id, anon_id, center_code, sex, is_placeholder,
                         created_batch_id, last_seen_batch_id)
                    VALUES ('PT_' || LPAD(nextval('lnrs.lnrs_anon_patient_seq')::text, 8, '0'),
                            %s, %s, '0', TRUE, %s, %s)
                    ON CONFLICT (anon_id) DO NOTHING
                    RETURNING patient_id, anon_id
                """
                for i, pid in enumerate(to_add):
                    bid = src_to_batch[pid_first_src[pid]]
                    cur.execute(ins, (pid_to_anon[pid], CENTER, bid, bid))
                    row = cur.fetchone()
                    if row:
                        anon_to_pt[row[1]] = row[0]
                        patient_added.append((row[0], row[1], pid))
                    if i and i % 5000 == 0:
                        print(f"  ...patient {i}/{len(to_add)}")
            elif to_add and args.dry_run:
                cur.execute("SELECT last_value FROM lnrs.lnrs_anon_patient_seq")
                seq_cur = int(cur.fetchone()[0]) + 1
                for pid in to_add:
                    pt_id = f"PT_{seq_cur:08d}"
                    seq_cur += 1
                    anon_to_pt[pid_to_anon[pid]] = pt_id
                    patient_added.append((pt_id, pid_to_anon[pid], pid))
                print(f"  [dry-run] 模拟发号 +{len(patient_added)} patient")

        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()
    except Exception:
        conn.rollback()
        raise

    # ----- Step 4: 内存去重 (patient_id, dicom_study_uid, source) -----
    print(f"\n[Step 4] 去重 (patient_id, dicom_study_uid, source) …")
    seen: set[tuple[str, str, str]] = set()
    imaging_rows: list[tuple] = []
    series_rows: list[tuple] = []
    phi_rows: list[tuple] = []
    phi_seen: set[tuple] = set()
    missing = 0
    for r in parsed:
        pt_id = anon_to_pt.get(pid_to_anon[r["pid"]])
        if not pt_id:
            missing += 1
            continue
        bid = src_to_batch[r["src"]]
        key = (pt_id, r["uid"], r["src"])
        if key in seen:
            continue
        seen.add(key)
        imaging_rows.append((pt_id, CENTER, r["uid"], r["modality"], r["path"],
                             r["sop_count"], r["src"], bid))
        series_rows.append((r["uid"], r["file_count"], r["byte_size"],
                            r["series_count"], bid))
        ph = hashlib.sha256(pt_id.encode("utf-8")).hexdigest()
        pk = (bid, PHI_SOURCE_TABLE, PHI_SOURCE_FIELD, ph)
        if pk not in phi_seen:
            phi_seen.add(pk)
            phi_rows.append((bid, PHI_SOURCE_TABLE, PHI_SOURCE_FIELD, ph, PHI_STRATEGY))

    print(f"  imaging_study: {len(imaging_rows)}  (无 patient 的行 {missing})")
    print(f"  dicom_series : {len(series_rows)}")
    print(f"  phi_audit    : {len(phi_rows)}")

    if args.dry_run:
        conn.close()
        print(f"\n[dry-run] 跳过 PG 写入。耗时 {time.time()-t0:.1f}s")
        print("[dry-run] 预期写入：")
        print(f"  lnrs_anon_ingest_batch : +{len(sources)}")
        print(f"  lnrs_anon_patient      : +{len(to_add)}")
        print(f"  lnrs_anon_imaging_study: +{len(imaging_rows)}")
        print(f"  lnrs_anon_dicom_series : +{len(series_rows)}")
        print(f"  lnrs_anon_phi_audit    : +{len(phi_rows)}")
        return 0

    # ----- Step 5: INSERT -----
    imaging_sql = """
        INSERT INTO lnrs.lnrs_anon_imaging_study
            (patient_id, center_code, dicom_study_uid, modality, image_path, sop_count,
             source, created_batch_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (patient_id, dicom_study_uid, source) DO NOTHING
    """
    series_sql = """
        INSERT INTO lnrs.lnrs_anon_dicom_series
            (anon_exam_id, dicom_study_uid, file_count, byte_size, series_count, created_batch_id)
        VALUES (NULL, %s, %s, %s, %s, %s)
        ON CONFLICT (dicom_study_uid) DO UPDATE SET
            file_count   = EXCLUDED.file_count,
            byte_size    = EXCLUDED.byte_size,
            series_count = EXCLUDED.series_count,
            updated_at   = CURRENT_TIMESTAMP
    """
    phi_sql = """
        INSERT INTO lnrs.lnrs_anon_phi_audit
            (batch_id, source_table, source_field, source_hash, strategy)
        VALUES (%s, %s, %s, %s, %s)
    """
    print(f"\n[Step 5] INSERT imaging_study / dicom_series / phi_audit …")
    with conn.cursor() as cur:
        for i in range(0, len(imaging_rows), args.batch_size):
            cur.executemany(imaging_sql, imaging_rows[i: i + args.batch_size])
            if (i // args.batch_size) % 10 == 0:
                print(f"  ...imaging {min(i+args.batch_size, len(imaging_rows))}/{len(imaging_rows)}")
        for i in range(0, len(series_rows), args.batch_size):
            cur.executemany(series_sql, series_rows[i: i + args.batch_size])
            if (i // args.batch_size) % 10 == 0:
                print(f"  ...series {min(i+args.batch_size, len(series_rows))}/{len(series_rows)}")
        for i in range(0, len(phi_rows), args.batch_size):
            cur.executemany(phi_sql, phi_rows[i: i + args.batch_size])

        for s in sources:
            n_img = sum(1 for r in imaging_rows if r[6] == s)
            n_ser = sum(1 for r in series_rows if r[4] == src_to_batch[s])
            cur.execute(
                """
                UPDATE lnrs.lnrs_anon_ingest_batch
                SET status='success', finished_at=CURRENT_TIMESTAMP, row_counts=%s::jsonb
                WHERE batch_id=%s
                """,
                ('{"imaging_study": %d, "dicom_series": %d}' % (n_img, n_ser), src_to_batch[s]),
            )
    conn.commit()
    conn.close()

    PATIENT_ADDED_TXT.parent.mkdir(parents=True, exist_ok=True)
    with open(PATIENT_ADDED_TXT, "w", encoding="utf-8") as f:
        f.write("# xinqiao_imaging_study patient_added\n")
        f.write(f"# 中心: {CENTER}\n# 来源: {args.csv}\n# 计数: {len(patient_added)}\n")
        f.write("# 列: anon_id, patient_id, source_patient_local_id\n")
        for pt_id, anon, src_pid in patient_added:
            f.write(f"{anon},{pt_id},{src_pid}\n")

    print(f"\n[OK] 灌库完成 {time.time()-t0:.1f}s")
    print(f"  patient_inserted: {len(patient_added)}")
    print(f"  imaging_inserted: {len(imaging_rows)}")
    print(f"  series_inserted : {len(series_rows)}")
    print(f"  phi_inserted    : {len(phi_rows)}")
    print(f"  patient_added   : {PATIENT_ADDED_TXT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
