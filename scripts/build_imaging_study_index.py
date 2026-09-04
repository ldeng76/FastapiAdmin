"""离线灌库脚本：ct_image_patient_map.csv → lnrs.lnrs_anon_imaging_study。

设计要点（2026-08-28）：
- 输入：docs/sour/ct_image_patient_map.csv（10 MB，36,698 行；盘 1 + 盘 2 珠江 DICOM 映射）
- 输出：INSERT INTO lnrs.lnrs_anon_imaging_study
- patient_id (PT_xxx) 通过 compute_anon_id(center, pat_local_id) → SELECT 现有 PG 反查
  不发新号（FK 安全 + 与 ETL-2 幂等）
- 跳过：CSV 中 pat_local_id 在 PG 找不到对应 PT_xxx 的行（典型：少量 demo 范围外 PID）
- 幂等：ON CONFLICT (patient_id, dicom_study_uid, source) DO NOTHING，重跑无副作用
- 默认 center_code='zhujiang'，modality='CT'（本轮只支撑 CT）

用法（venv 内执行）：
    /home/dzy/wk/lnrs/backend/.venv/bin/python \\
        /home/dzy/wk/lnrs/scripts/build_imaging_study_index.py \\
        [--csv /home/dzy/wk/lnrs/docs/sour/ct_image_patient_map.csv] \\
        [--center zhujiang] \\
        [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import os
import sys
import time
from pathlib import Path

# 默认路径
DEFAULT_CSV = Path("/home/dzy/wk/lnrs/docs/sour/ct_image_patient_map.csv")
DEFAULT_CENTER = "zhujiang"

# 与 backend/app/plugin/module_medical/hospital/anonymize.py:92 compute_anon_id 同款
def compute_anon_id(center_code: str, patient_local_id: str) -> str:
    """HMAC-SHA256(secret, "{center}:{patient_id}")[:12] → ANON_<12hex>"""
    secret = (
        os.environ.get("LNRS_ANON_SECRET")
        or "change-me-in-production-please"
    ).encode("utf-8")
    mac = hmac.new(
        secret,
        f"{center_code}:{patient_local_id}".encode("utf-8"),
        hashlib.sha256,
    )
    return f"ANON_{mac.hexdigest()[:12]}"


def pg_conn_str() -> str:
    """从环境变量或硬编码回退拿 PG DSN。"""
    return (
        os.environ.get("LNRS_PG_DSN")
        or "host=127.0.0.1 port=5432 user=lnrs password=lnrs_pwd dbname=postgres"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="CSV → lnrs_anon_imaging_study 灌库")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="DICOM 映射 CSV 路径")
    parser.add_argument("--center", default=DEFAULT_CENTER, help="center_code（默认 zhujiang）")
    parser.add_argument("--dry-run", action="store_true", help="只解析不写 PG")
    parser.add_argument("--batch-size", type=int, default=2000, help="INSERT 批大小")
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"ERROR: CSV not found: {args.csv}", file=sys.stderr)
        return 2

    print(f"[*] 输入: {args.csv}  center={args.center}  dry_run={args.dry_run}")
    t0 = time.time()

    # 1. 解析 CSV
    with open(args.csv, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    print(f"[*] CSV 解析: {len(rows)} 行，列={reader.fieldnames}")

    # 2. 收集唯一 PID，计算 anon_id
    pids = sorted({r["patient_id"] for r in rows})
    print(f"[*] 唯一 PID: {len(pids)}")

    pid_to_anon: dict[str, str] = {}
    for p in pids:
        pid_to_anon[p] = compute_anon_id(args.center, p)
    print(f"[*] HMAC 计算完成（{time.time() - t0:.2f}s）")

    # 3. 连接 PG，反查 anon_id → patient_id
    import psycopg
    conn = psycopg.connect(pg_conn_str())
    conn.autocommit = False

    anon_to_pt: dict[str, str] = {}
    with conn.cursor() as cur:
        # 分块查
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
                (args.center, chunk),
            )
            for anon, pt in cur.fetchall():
                anon_to_pt[anon] = pt

    print(f"[*] PG 反查: 命中 {len(anon_to_pt)}/{len(pids)} unique PID")

    # 4. 构造 insert rows
    missing: list[str] = []
    insert_rows: list[tuple] = []
    for r in rows:
        pid = r["patient_id"]
        anon = pid_to_anon[pid]
        pt_id = anon_to_pt.get(anon)
        if not pt_id:
            missing.append(pid)
            continue
        insert_rows.append((
            pt_id,
            args.center,
            r["study_instance_uid"],
            "CT",
            r["image_path"],
            int(r["sop_instance_count"]) if r.get("sop_instance_count") else 0,
            r.get("source") or "disk_index",
        ))

    # 去重（CSV 自身可能有重复行）
    seen: set[tuple[str, str, str]] = set()
    unique_rows: list[tuple] = []
    for row in insert_rows:
        key = (row[0], row[2], row[6])  # (patient_id, study_uid, source)
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)
    print(f"[*] 去重后待插入: {len(unique_rows)} 行（原始 {len(insert_rows)}）")
    if missing:
        print(f"[!] 跳过 {len(missing)} 个 PID（PG 中无对应 PT_xxx）: {missing[:10]}")

    if args.dry_run:
        print("[*] dry-run，跳过 PG 写入")
        conn.close()
        return 0

    # 5. 批量 upsert
    upsert_sql = """
        INSERT INTO lnrs.lnrs_anon_imaging_study
            (patient_id, center_code, dicom_study_uid, modality, image_path, sop_count, source)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (patient_id, dicom_study_uid, source) DO NOTHING
    """
    inserted = 0
    skipped_dup = 0
    with conn.cursor() as cur:
        for i in range(0, len(unique_rows), args.batch_size):
            batch = unique_rows[i : i + args.batch_size]
            cur.executemany(upsert_sql, batch)
            # executemany 不会返回 rowcount 详情；用单条累计
            inserted += len(batch)
            if (i // args.batch_size) % 10 == 0:
                print(f"  ...batch {i // args.batch_size + 1}: 累计 {inserted}/{len(unique_rows)}")
    conn.commit()
    conn.close()

    elapsed = time.time() - t0
    print(f"[OK] 写入完成: {inserted} 行（耗时 {elapsed:.2f}s）")
    if missing:
        # 写出缺失 PID 供后续人工 review
        miss_path = args.csv.parent / "imaging_study_missing_pids.txt"
        with open(miss_path, "w") as f:
            f.write("\n".join(missing) + "\n")
        print(f"[!] 缺失 PID 列表: {miss_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())