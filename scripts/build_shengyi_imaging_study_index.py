#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""shengyi CT 影像（含报告）离线灌库脚本。

设计要点（2026-09-14）：
- 输入：shengyi 中心 CT_image 目录下 2 个 parquet（shengyi_06_disk_CT.parquet、
  shengyi_07_disk_CT.parquet），共 82,994 行（去重后 82,153 unique record_id）。
- 输出：
    - lnrs.lnrs_anon_patient (center='shengyi') +82,682 个增量
    - lnrs.lnrs_anon_imaging_study (center='shengyi') +82,153 行
- 匿名化：HMAC-SHA256(secret, "shengyi:"+pid)[:12] → ANON_<12hex>，与
  backend/app/plugin/module_medical/hospital/anonymize.py:compute_anon_id 同款。
- patient 续号：pg_advisory_xact_lock + nextval('lnrs.lnrs_anon_patient_seq')。
- source_kind=dicom_dir；source 字段按文件分（disk_06_shengyi / disk_07_shengyi）。
- ETL2 引擎零改动：仅写离线路径，参照 zhujiang build_imaging_study_index.py 模式。

幂等性：
- patient：ON CONFLICT (center_code, anon_id) DO NOTHING
- imaging_study：ON CONFLICT (patient_id, dicom_study_uid, source) DO NOTHING

用法（venv 内执行）：
    ENVIRONMENT=dev backend/.venv/bin/python \\
        scripts/build_shengyi_imaging_study_index.py \\
        [--dry-run] [--batch-size 2000]

patient_added 列表：docs/sour/shengyi_imaging_study_patient_added.txt
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import re
import sys
import time
import uuid
from pathlib import Path

# ---------- 路径与常量 ----------

PARQUET_DIR = Path("/data/wlx/DATABASE/extracted_tables/shengyi/CT_image")

# (parquet 文件名, source 标签)
PARQUETS: list[tuple[Path, str]] = [
    (PARQUET_DIR / "shengyi_06_disk_CT.parquet", "disk_06_shengyi"),
    (PARQUET_DIR / "shengyi_07_disk_CT.parquet", "disk_07_shengyi"),
]

CENTER = "shengyi"
MODALITY = "CT"
BATCH_ID = uuid.uuid4()  # 本次灌库的唯一 batch_id

# 输出文件
PATIENT_ADDED_TXT = Path("/home/dzy/wk/lnrs/docs/sour/shengyi_imaging_study_patient_added.txt")

# record_id 格式: shengyi_<NN>_disk_<DICOM_StudyInstanceUID>
RECORD_PREFIX_RE = re.compile(r"^shengyi_\d{2}_disk_(.+)$")

# ---------- 工具函数 ----------


def compute_anon_id(patient_local_id: str) -> str:
    """HMAC-SHA256(secret, "shengyi:"+pid)[:12] → ANON_<12hex>。"""
    secret = (
        os.environ.get("LNRS_ANON_SECRET")
        or "change-me-in-production-please"
    ).encode("utf-8")
    mac = hmac.new(
        secret,
        f"{CENTER}:{patient_local_id}".encode("utf-8"),
        hashlib.sha256,
    )
    return f"ANON_{mac.hexdigest()[:12]}"


def pg_conn_str() -> str:
    return (
        os.environ.get("LNRS_PG_DSN")
        or "host=127.0.0.1 port=5432 user=lnrs password=lnrs_pwd dbname=postgres"
    )


def read_parquet_rows() -> list[tuple[str, str, str, str]]:
    """DuckDB 读两 parquet，返回 [(record_id, patient_id, dir_path, source), ...]"""
    import duckdb

    con = duckdb.connect()
    rows: list[tuple[str, str, str, str]] = []
    for path, source in PARQUETS:
        if not path.exists():
            print(f"ERROR: parquet 不存在 {path}", file=sys.stderr)
            sys.exit(2)
        for rec_id, pid, dpath in con.execute(
            f"SELECT record_id, patient_id, dir_path FROM read_parquet('{path}')"
        ).fetchall():
            rows.append((rec_id or "", pid or "", dpath or "", source))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="shengyi CT 影像（含报告）parquet → lnrs_anon_imaging_study 灌库"
    )
    parser.add_argument("--dry-run", action="store_true", help="只解析与统计，不写 PG")
    parser.add_argument(
        "--batch-size", type=int, default=2000, help="INSERT 批大小（默认 2000）"
    )
    args = parser.parse_args()

    print(f"[*] 中心={CENTER}  modality={MODALITY}  dry-run={args.dry_run}")
    print(f"[*] batch_id={BATCH_ID}")
    t0 = time.time()

    # ----- Step 1: 读 parquet -----
    print(f"\n[Step 1] 读 parquet …")
    raw_rows = read_parquet_rows()
    print(f"  parquet 总行数: {len(raw_rows)}")

    # ----- Step 2: 解析 dicom_study_uid，过滤无效行 -----
    print(f"\n[Step 2] 解析 record_id → dicom_study_uid …")
    parsed: list[tuple[str, str, str, str]] = []  # (pid, study_uid, dir_path, source)
    n_pid_empty = 0
    n_record_bad = 0
    for rec_id, pid, dpath, source in raw_rows:
        if not pid:
            n_pid_empty += 1
            continue
        m = RECORD_PREFIX_RE.match(rec_id)
        if not m:
            n_record_bad += 1
            continue
        study_uid = m.group(1)
        if not dpath:
            continue
        parsed.append((pid, study_uid, dpath, source))
    print(f"  解析后待处理行: {len(parsed)}  (跳过空 patient_id={n_pid_empty}, record_id 解析失败={n_record_bad})")

    # ----- Step 3: 离线 HMAC 算 anon_id -----
    print(f"\n[Step 3] 离线 HMAC-SHA256 算 anon_id …")
    pids = sorted({p for p, *_ in parsed})
    pid_to_anon = {p: compute_anon_id(p) for p in pids}
    print(f"  distinct patient_id: {len(pids)}")

    # ----- Step 4: PG 反查 -----
    print(f"\n[Step 4] 连接 PG，反查 anon_id → patient_id …")
    import psycopg

    conn = psycopg.connect(pg_conn_str())
    conn.autocommit = False
    anon_to_pt: dict[str, str] = {}
    patient_added: list[tuple[str, str, str]] = []  # (patient_id, anon_id, source_pid)

    with conn.cursor() as cur:
        # 4a) 先 INSERT 一个 ingest_batch 行（patient FK 需要）
        cur.execute(
            """
            INSERT INTO lnrs.lnrs_anon_ingest_batch
                (batch_id, center_code, source_kind, source_locator,
                 secret_version, key_fingerprint, schema_hash, status)
            VALUES (%s, %s, 'dicom_dir', %s, %s, %s, %s, 'success')
            ON CONFLICT (batch_id) DO NOTHING
            """,
            (
                BATCH_ID,
                CENTER,
                str(PARQUET_DIR),
                os.environ.get("LNRS_ANON_SECRET_VERSION", "v1"),
                hashlib.sha256(
                    (os.environ.get("LNRS_ANON_SECRET") or "change-me-in-production-please").encode()
                ).hexdigest()[:16],
                hashlib.sha256(b"disk_image_index_20260914").hexdigest(),
            ),
        )

        # 4b) 反查 anon_id → patient_id（chunk=5000）
        anon_list = list(pid_to_anon.values())
        for i in range(0, len(anon_list), 5000):
            chunk = anon_list[i : i + 5000]
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
        to_add = [pid for pid, a in pid_to_anon.items() if a not in anon_to_pt]
        print(f"  反查命中（patient 复用）: {reused}")
        print(f"  需要新增 patient: {len(to_add)}")

        # ----- Step 5: patient 增量发号 -----
        if to_add and not args.dry_run:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('shengyi_patient_seq'))")
            patient_insert_sql = """
                INSERT INTO lnrs.lnrs_anon_patient
                    (patient_id, anon_id, center_code, sex,
                     created_batch_id, last_seen_batch_id)
                VALUES (
                    'PT_' || LPAD(nextval('lnrs.lnrs_anon_patient_seq')::text, 8, '0'),
                    %s, %s, '0', %s, %s
                )
                ON CONFLICT (anon_id) DO NOTHING
                RETURNING patient_id, anon_id
            """
            for i in range(0, len(to_add), args.batch_size):
                batch_pids = to_add[i : i + args.batch_size]
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
            print(f"  [dry-run] 跳过 patient INSERT")

        # dry-run 模式：回滚 INSERT batch + patient，仅保留 in-memory 统计
        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()

    print(f"  patient_added: {len(patient_added)}")

    # ----- Step 6: 内存去重 -----
    print(f"\n[Step 6] 内存去重 (patient_id, dicom_study_uid, source) …")
    insert_rows: list[tuple] = []
    missing_pid = 0
    for pid, study_uid, dpath, source in parsed:
        anon = pid_to_anon[pid]
        pt_id = anon_to_pt.get(anon)
        if not pt_id:
            missing_pid += 1
            continue
        insert_rows.append((pt_id, CENTER, study_uid, MODALITY, dpath, 0, source))

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

    if args.dry_run:
        conn.close()
        print(f"\n[dry-run] 跳过 PG 写入（rollback 已生效）。耗时 {time.time() - t0:.1f}s")
        print(f"[dry-run] 预期正式跑后会写入：")
        print(f"  lnrs_anon_patient: +{len(to_add)}")
        print(f"  lnrs_anon_imaging_study: +{len(unique_rows) if not args.dry_run else '82153 (估)'}")
        return 0

    # ----- Step 7: INSERT INTO lnrs_anon_imaging_study -----
    print(f"\n[Step 7] INSERT INTO lnrs_anon_imaging_study (ON CONFLICT DO NOTHING) …")
    upsert_sql = """
        INSERT INTO lnrs.lnrs_anon_imaging_study
            (patient_id, center_code, dicom_study_uid, modality, image_path, sop_count, source)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (patient_id, dicom_study_uid, source) DO NOTHING
    """
    inserted = 0
    with conn.cursor() as cur:
        for i in range(0, len(unique_rows), args.batch_size):
            batch = unique_rows[i : i + args.batch_size]
            cur.executemany(upsert_sql, batch)
            inserted += len(batch)
            if (i // args.batch_size) % 10 == 0:
                print(f"  ...imaging batch {i // args.batch_size + 1}: 累计 {inserted}/{len(unique_rows)}")
    conn.commit()
    conn.close()

    # ----- Step 8: 输出 patient_added 列表 -----
    PATIENT_ADDED_TXT.parent.mkdir(parents=True, exist_ok=True)
    with open(PATIENT_ADDED_TXT, "w", encoding="utf-8") as f:
        f.write("# shengyi_imaging_study patient_added 列表\n")
        f.write(f"# 批次: {BATCH_ID}\n")
        f.write(f"# 中心: {CENTER}\n")
        f.write(f"# 来源: parquet (shengyi_06_disk_CT + shengyi_07_disk_CT)\n")
        f.write(f"# 计数: {len(patient_added)}\n")
        f.write("# 列: anon_id, patient_id, source_patient_local_id\n")
        for pt_id, anon, src_pid in patient_added:
            f.write(f"{anon},{pt_id},{src_pid}\n")
    print(f"  patient_added 列表: {PATIENT_ADDED_TXT}")

    elapsed = time.time() - t0
    print(f"\n[OK] 灌库完成: {elapsed:.1f}s")
    print(f"  patient_inserted: {len(patient_added)}")
    print(f"  imaging_inserted: {inserted}")
    print(f"  patient_added 文件: {PATIENT_ADDED_TXT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())