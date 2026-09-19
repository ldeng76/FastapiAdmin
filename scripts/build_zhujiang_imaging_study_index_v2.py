#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""珠江 CT 影像三盘（disk1+disk2+disk4）→ lnrs_anon_imaging_study + patient 增量 + phi_audit + ingest_batch 灌库。

输入：/home/dzy/wk/lnrs/docs/sour/ct_image_patient_map_v2.csv
  （由 build_disk1_disk2_disk4_imaging_study_index.py 生成）
落库：
  - lnrs.lnrs_anon_ingest_batch  (source_kind='dicom_dir', center_code='zhujiang')
  - lnrs.lnrs_anon_patient        (增量：HMAC 发号 + is_placeholder=TRUE + 占位字段)
  - lnrs.lnrs_anon_imaging_study  (含 anon_exam_id=NULL + created_batch_id=本次)
  - lnrs.lnrs_anon_phi_audit      (每 imaging_study 一行；strategy='hmac'；source_hash=sha256(patient_id_hex))

设计要点：
  * patient 发号：pg_advisory_xact_lock(hashtext('zhujiang_patient_seq')) + nextval（与 shengyi 模板一致）
  * is_placeholder=TRUE 显式写（0006 §3 默认 FALSE；shengyi 已踩坑）
  * dicom_series 阶段不写 phi_audit（无 PHI）；backfill 推迟到 zhujiang exam 灌库之后（B 方案）
  * dry-run：内存模拟发号（不推进 sequence、不写 PG），让后续 Step 4/5 给出真实规模预期
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import os
import time
import uuid
from pathlib import Path

CENTER = "zhujiang"
MODALITY = "CT"
BATCH_ID = uuid.uuid4()  # 本次灌库的唯一 batch_id

OUT_CSV = Path("/home/dzy/wk/lnrs/docs/sour/ct_image_patient_map_v2.csv")
PATIENT_ADDED_TXT = Path("/home/dzy/wk/lnrs/docs/sour/zhujiang_imaging_study_patient_added.txt")

PHI_SOURCE_TABLE = "lnrs_anon_imaging_study"
PHI_SOURCE_FIELD = "patient_id"
PHI_STRATEGY = "hmac"


# ---------- 工具函数 ----------


def compute_anon_id(pid: str, secret: str) -> str:
    mac = hmac.new(secret.encode("utf-8"), f"zhujiang:{pid}".encode("utf-8"), hashlib.sha256)
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


def filter_valid(rows: list[dict]) -> list[tuple[str, str, str, int, str]]:
    parsed: list[tuple[str, str, str, int, str]] = []
    n_pid_empty = 0
    n_uid_empty = 0
    n_path_empty = 0
    for r in rows:
        pid = (r.get("patient_id") or "").strip()
        uid = (r.get("study_instance_uid") or "").strip()
        path = (r.get("image_path") or "").strip()
        src = (r.get("source") or "").strip()
        if not pid:
            n_pid_empty += 1
            continue
        if not uid or "." not in uid:
            n_uid_empty += 1
            continue
        if not path:
            n_path_empty += 1
            continue
        try:
            sop = int(r.get("sop_instance_count") or 0)
        except ValueError:
            sop = 0
        parsed.append((pid, uid, path, sop, src))
    print(f"  解析后: {len(parsed)}  (跳过: 空 PID={n_pid_empty}, 空 UID={n_uid_empty}, 空路径={n_path_empty})")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description="珠江三盘 imaging_study 灌库")
    parser.add_argument("--csv", type=Path, default=OUT_CSV, help="输入 CSV 路径")
    parser.add_argument("--dry-run", action="store_true", help="只解析与统计，不写 PG")
    parser.add_argument("--batch-size", type=int, default=2000, help="INSERT 批大小")
    args = parser.parse_args()

    print(f"[*] 中心={CENTER}  modality={MODALITY}  dry-run={args.dry_run}")
    print(f"[*] batch_id={BATCH_ID}")
    t0 = time.time()

    secret, secret_version = load_anon_secret()
    print(f"[*] secret_version={secret_version}")

    print(f"\n[Step 1] 读 CSV: {args.csv}")
    if not args.csv.exists():
        print(f"  ❌ CSV 不存在：{args.csv}")
        return 2
    rows = read_csv_rows(args.csv)
    parsed = filter_valid(rows)

    print(f"\n[Step 2] 离线 HMAC-SHA256 算 anon_id …")
    pids = sorted({p for p, *_ in parsed})
    pid_to_anon = {p: compute_anon_id(p, secret) for p in pids}
    distinct_uid = len({u for _, u, *_ in parsed})
    print(f"  distinct patient_id: {len(pids)}")
    print(f"  distinct dicom_study_uid: {distinct_uid}")

    print(f"\n[Step 3] 连接 PG，反查 anon_id → patient_id …")
    import psycopg
    conn = psycopg.connect(pg_conn_str())
    conn.autocommit = False
    anon_to_pt: dict[str, str] = {}
    patient_added: list[tuple[str, str, str]] = []

    try:
        with conn.cursor() as cur:
            # 3a) ingest_batch
            cur.execute(
                """
                INSERT INTO lnrs.lnrs_anon_ingest_batch
                    (batch_id, center_code, source_kind, source_locator,
                     secret_version, key_fingerprint, schema_hash, status)
                VALUES (%s, %s, 'dicom_dir', %s, %s, %s, %s, 'running')
                ON CONFLICT (batch_id) DO NOTHING
                """,
                (
                    BATCH_ID,
                    CENTER,
                    str(args.csv),
                    secret_version,
                    hashlib.sha256(secret.encode("utf-8")).hexdigest()[:16],
                    hashlib.sha256(b"disk_image_index_20260919").hexdigest(),
                ),
            )

            # 3b) 反查 anon_id → patient_id
            anon_list = list(pid_to_anon.values())
            for i in range(0, len(anon_list), 5000):
                chunk = anon_list[i: i + 5000]
                cur.execute(
                    """
                    SELECT anon_id, patient_id
                    FROM lnrs.lnrs_anon_patient
                    WHERE center_code = %s
                      AND anon_id = ANY(%s)
                      AND deleted_at IS NULL
                    """,
                    (CENTER, chunk),
                )
                for anon, pt in cur.fetchall():
                    anon_to_pt[anon] = pt

            reused = len(anon_to_pt)
            to_add = [pid for pid in pids if pid_to_anon[pid] not in anon_to_pt]
            print(f"  反查命中（patient 复用）: {reused}")
            print(f"  需要新增 patient: {len(to_add)}")

            # 3c) patient 增量发号
            if to_add and not args.dry_run:
                cur.execute("SELECT pg_advisory_xact_lock(hashtext('zhujiang_patient_seq'))")
                patient_insert_sql = """
                    INSERT INTO lnrs.lnrs_anon_patient
                        (patient_id, anon_id, center_code, sex,
                         is_placeholder,
                         created_batch_id, last_seen_batch_id)
                    VALUES (
                        'PT_' || LPAD(nextval('lnrs.lnrs_anon_patient_seq')::text, 8, '0'),
                        %s, %s, '0',
                        TRUE,
                        %s, %s
                    )
                    ON CONFLICT (anon_id) DO NOTHING
                    RETURNING patient_id, anon_id
                """
                for i in range(0, len(to_add), args.batch_size):
                    batch_pids = to_add[i: i + args.batch_size]
                    for pid in batch_pids:
                        anon = pid_to_anon[pid]
                        cur.execute(patient_insert_sql, (anon, CENTER, BATCH_ID, BATCH_ID))
                        row = cur.fetchone()
                        if row:
                            new_pt, new_anon = row[0], row[1]
                            anon_to_pt[new_anon] = new_pt
                            patient_added.append((new_pt, new_anon, pid))
                    if (i // args.batch_size) % 10 == 0:
                        print(f"  ...patient batch {i // args.batch_size + 1}: 累计 {len(patient_added)}/{len(to_add)}")
            elif to_add and args.dry_run:
                # dry-run：内存模拟发号（不写 PG、不推进 sequence）
                cur.execute("SELECT last_value FROM lnrs.lnrs_anon_patient_seq")
                row = cur.fetchone()
                if not row:
                    print("  [dry-run] ❌ 读不到 seq last_value")
                    return 2
                seq_cur = int(row[0]) + 1
                for pid in to_add:
                    pt_id = f"PT_{seq_cur:08d}"
                    seq_cur += 1
                    anon = pid_to_anon[pid]
                    anon_to_pt[anon] = pt_id
                    patient_added.append((pt_id, anon, pid))
                print(f"  [dry-run] 模拟发号 +{len(patient_added)} patient（不写 PG）")

        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()
        print(f"  patient_added: {len(patient_added)}")
    except Exception:
        conn.rollback()
        raise

    # ----- Step 4: 内存去重 (patient_id, dicom_study_uid, source) -----
    print(f"\n[Step 4] 内存去重 (patient_id, dicom_study_uid, source) …")
    insert_rows: list[tuple] = []
    phi_audit_rows: list[tuple] = []
    missing_pid = 0
    for pid, study_uid, dpath, sop, source in parsed:
        anon = pid_to_anon[pid]
        pt_id = anon_to_pt.get(anon)
        if not pt_id:
            missing_pid += 1
            continue
        insert_rows.append((pt_id, CENTER, study_uid, MODALITY, dpath, sop, source, BATCH_ID))
        pt_hash = hashlib.sha256(pt_id.encode("utf-8")).hexdigest()
        phi_audit_rows.append((BATCH_ID, PHI_SOURCE_TABLE, PHI_SOURCE_FIELD, pt_hash, PHI_STRATEGY))

    seen: set[tuple[str, str, str]] = set()
    unique_rows: list[tuple] = []
    for row in insert_rows:
        key = (row[0], row[2], row[6])
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)

    print(f"  原始 insert_rows: {len(insert_rows)}  (无对应 patient_id 的行: {missing_pid})")
    print(f"  去重后: {len(unique_rows)}  (消 {len(insert_rows) - len(unique_rows)} 行级重复)")
    print(f"  phi_audit rows: {len(phi_audit_rows)}")

    if args.dry_run:
        conn.close()
        print(f"\n[dry-run] 跳过 PG 写入（rollback 已生效）。耗时 {time.time() - t0:.1f}s")
        print(f"[dry-run] 预期正式跑后会写入：")
        print(f"  lnrs_anon_ingest_batch: +1 ({BATCH_ID})")
        print(f"  lnrs_anon_patient: +{len(to_add)}  (含 is_placeholder=TRUE)")
        print(f"  lnrs_anon_imaging_study: +{len(unique_rows)}")
        print(f"  lnrs_anon_phi_audit: +{len(phi_audit_rows)}")
        return 0

    # ----- Step 5: INSERT -----
    print(f"\n[Step 5] INSERT INTO lnrs_anon_imaging_study (ON CONFLICT DO NOTHING) …")
    upsert_sql = """
        INSERT INTO lnrs.lnrs_anon_imaging_study
            (patient_id, center_code, dicom_study_uid, modality, image_path, sop_count, source,
             created_batch_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (patient_id, dicom_study_uid, source) DO NOTHING
    """
    phi_sql = """
        INSERT INTO lnrs.lnrs_anon_phi_audit
            (batch_id, source_table, source_field, source_hash, strategy)
        VALUES (%s, %s, %s, %s, %s)
    """
    inserted = 0
    phi_inserted = 0
    with conn.cursor() as cur:
        for i in range(0, len(unique_rows), args.batch_size):
            batch = unique_rows[i: i + args.batch_size]
            cur.executemany(upsert_sql, batch)
            inserted += len(batch)
            if (i // args.batch_size) % 10 == 0:
                print(f"  ...imaging batch {i // args.batch_size + 1}: 累计 {inserted}/{len(unique_rows)}")
        print(f"\n[Step 5b] INSERT INTO lnrs_anon_phi_audit …")
        for i in range(0, len(phi_audit_rows), args.batch_size):
            batch = phi_audit_rows[i: i + args.batch_size]
            cur.executemany(phi_sql, batch)
            phi_inserted += len(batch)
            if (i // args.batch_size) % 10 == 0:
                print(f"  ...audit batch {i // args.batch_size + 1}: 累计 {phi_inserted}/{len(phi_audit_rows)}")

        cur.execute(
            """
            UPDATE lnrs.lnrs_anon_ingest_batch
            SET status = 'success',
                finished_at = CURRENT_TIMESTAMP,
                row_counts = %s::jsonb
            WHERE batch_id = %s
            """,
            (
                '{"patient_added": %d, "imaging_study": %d, "phi_audit": %d}' % (
                    len(patient_added), inserted, phi_inserted
                ),
                BATCH_ID,
            ),
        )
    conn.commit()
    conn.close()

    # ----- Step 6: 输出 patient_added 列表 -----
    PATIENT_ADDED_TXT.parent.mkdir(parents=True, exist_ok=True)
    with open(PATIENT_ADDED_TXT, "w", encoding="utf-8") as f:
        f.write("# zhujiang_imaging_study patient_added 列表\n")
        f.write(f"# 批次: {BATCH_ID}\n")
        f.write(f"# 中心: {CENTER}\n")
        f.write(f"# 来源: CSV {args.csv}\n")
        f.write(f"# 计数: {len(patient_added)}\n")
        f.write("# 列: anon_id, patient_id, source_patient_local_id\n")
        for pt_id, anon, src_pid in patient_added:
            f.write(f"{anon},{pt_id},{src_pid}\n")
    print(f"  patient_added 列表: {PATIENT_ADDED_TXT}")

    elapsed = time.time() - t0
    print(f"\n[OK] 灌库完成: {elapsed:.1f}s")
    print(f"  batch_id: {BATCH_ID}")
    print(f"  patient_inserted: {len(patient_added)}")
    print(f"  imaging_inserted: {inserted}")
    print(f"  phi_audit_inserted: {phi_inserted}")
    print(f"  patient_added 文件: {PATIENT_ADDED_TXT}")
    print(f"\n> ⚠ Step 5（dicom_series backfill）尚未跑；B 方案：本批 exam 表无 zhujiang 行，")
    print(f"  留空 dicom_series.anon_exam_id。后续单独批次灌 exam → backfill + UPDATE sync。")
    print(f"> ⚠ 复用 batch_id={BATCH_ID} 跑：")
    print(f"  cd /home/dzy/wk/lnrs/backend && ENVIRONMENT=h196_3 uv run python etl2/backfill_dicom_series_count.py --apply --bypass-exam-fk --center zhujiang")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())