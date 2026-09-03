"""孤儿研究灌库:orphan_diagnosis_v4.csv → lnrs.lnrs_anon_imaging_orphan。

设计要点(2026-09-03 三轮):
- 输入:docs/孤儿文件研究/2026-09-03珠江医院CT文件/orphan_diagnosis_v4.csv(8,134 行;多中心时可改)
- 输出:INSERT INTO lnrs.lnrs_anon_imaging_orphan + lnrs.lnrs_anon_orphan_audit_batch
- 业务编号 study_orphan_id = 'OR_' + sha256(f'{center_code}:{rel_path_from_dicom_root}')[:8]
  - **rel_path_from_dicom_root** = image_path.removeprefix(dicom_root).lstrip('/')(去掉 dicom 根前缀,保留 dicom 子目录名 + 子路径)
  - 例:image_path='/data/wlx/DATABASE/01_disk/zhujiang_dicom/pn202307/20230715/<basename>',dicom_root='/data/wlx/DATABASE/01_disk/zhujiang_dicom'
    → rel_path='zhujiang_dicom/pn202307/20230715/<basename>'
  - hash 输入 = 'zhujiang:zhujiang_dicom/pn202307/20230715/<basename>'(对齐 source_*_hash 拼接模式)
  - 由 dicom子路径映射生成,**不依赖任何全局序列**;**部署无关**(NFS 挂载点/主机 IP 不进 hash)
- 跨中心指纹 source_orphan_hash = sha256(f'{center_code}:{image_path}')(CHAR(64),含完整 abs_path 便于运维定位)
- 默认只灌真孤儿(in_pg_exact=0 AND in_pg_02d=0);49 双盘副本由 --include-dual-disk 控制
- patient_id 反查:HMAC-SHA256(secret, "zhujiang:{pat_local_id}")[:12] → anon_id → SELECT patient_id
- 6 个 patient_missing 孤儿:patient_id NULL + orphan_kind='patient_missing'
- 幂等:ON CONFLICT (center_code, dicom_study_uid, image_path) DO NOTHING(同磁盘目录不被重复登记)
- audit_batch:一行 lnrs.lnrs_anon_orphan_audit_batch + 关联到所有 orphan.audit_batch_id

用法(venv 内执行):
    /home/dzy/wk/lnrs/backend/.venv/bin/python \\
        /home/dzy/wk/lnrs/scripts/import_orphan_diagnosis.py \\
        [--csv /home/dzy/wk/lnrs/docs/孤儿文件研究/2026-09-03珠江医院CT文件/orphan_diagnosis_v4.csv] \\
        [--center zhujiang] \\
        [--dicom-root /data/wlx/DATABASE/01_disk/zhujiang_dicom] \\
        [--include-dual-disk] [--include-empty-dir] \\
        [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import os
import re
import sys
import time
import uuid
from pathlib import Path

# --------------------------------------------------------------------------- #
# 默认路径与常量
# --------------------------------------------------------------------------- #
DEFAULT_CSV = Path(
    "/home/dzy/wk/lnrs/docs/孤儿文件研究/2026-09-03珠江医院CT文件/orphan_diagnosis_v4.csv"
)
DEFAULT_CENTER = "zhujiang"
DEFAULT_DICOM_ROOT = "/data/wlx/DATABASE/01_disk/zhujiang_dicom"
DEFAULT_SOURCE_TAG = "orphan_audit_2026_09_03"

# 5 类命名风格 → path_date_prefix(与 SQL CHECK 对齐)
PREFIX_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^ymd_\d+"), "ymd_N"),  # ymd_20230715_xxx 形式
    (re.compile(r"^ymd"), "ymd"),          # ymd_20230715 形式
    (re.compile(r"^yd"), "yd"),            # yd_20230715
    (re.compile(r"^new"), "new"),          # new_xxx
    (re.compile(r"^pn"), "pn"),            # pn202307_xxx
]


# --------------------------------------------------------------------------- #
# 核心计算函数(纯函数,无 DB 依赖,易单测)
# --------------------------------------------------------------------------- #
def compute_rel_path(image_path: str, dicom_root: str) -> str:
    """去掉 dicom 根绝对前缀,保留 dicom 子目录名 + 子路径。

    例:image_path='/data/wlx/DATABASE/01_disk/zhujiang_dicom/pn202307/20230715/<basename>',
        dicom_root='/data/wlx/DATABASE/01_disk/zhujiang_dicom'
        → rel_path='zhujiang_dicom/pn202307/20230715/<basename>'
    """
    if image_path.startswith(dicom_root):
        rel = image_path[len(dicom_root):]
        rel = rel.lstrip("/")
        return rel if rel else image_path
    # 不匹配 dicom_root 时,保留原 image_path(运维迁移场景下警告用)
    return image_path


def compute_study_orphan_id(center_code: str, rel_path: str) -> str:
    """业务编号派生:OR_<8hex> = 'OR_' + sha256(f'{center}:{rel_path}')[:8]。

    由 dicom 子路径哈希生成,丢弃绝对部署前缀,部署无关 + 跨中心不撞。
    """
    payload = f"{center_code}:{rel_path}".encode("utf-8")
    return "OR_" + hashlib.sha256(payload).hexdigest()[:8]


def compute_source_orphan_hash(center_code: str, image_path: str) -> str:
    """跨中心唯一指纹(对齐 source_*_hash 模式):sha256(f'{center}:{image_path}')。

    含完整绝对路径,便于磁盘运维定位;CHAR(64) 单列 UNIQUE 防跨中心重复登记。
    """
    payload = f"{center_code}:{image_path}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# 与 backend/app/plugin/module_medical/hospital/anonymize.py:67-101 _secret_bytes/_hmac_hex 同款
# 使用项目全局密钥 LNRS_ANON_SECRET(默认 dev placeholder 与 anon_* 函数一致)
def compute_anon_id(center_code: str, patient_local_id: str) -> str:
    """HMAC-SHA256(secret, "{center}:{patient_local_id}")[:12] → ANON_<12hex>"""
    secret = os.environ.get("LNRS_ANON_SECRET", "change-me-in-production-please")
    mac = hmac.new(
        secret.encode("utf-8"),
        f"{center_code}:{patient_local_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"ANON_{mac[:12]}"


def classify_path_date_prefix(basename: str) -> str:
    """从目录 basename 判定 5 类命名风格:ymd / yd / new / pn / ymd_N。"""
    name = basename.split("/")[-1]
    for pat, label in PREFIX_PATTERNS:
        if pat.match(name):
            return label
    return "pn"  # 兜底(本批 100% 都是 pn/ymd/yd/new,不会触发)


def classify_orphan_kind(row: dict[str, str]) -> str:
    """映射 orphan_kind:
    - patient_in_zhujiang='0' → patient_missing
    - 其余 → csv_uncovered
    """
    if row.get("patient_in_zhujiang") == "0":
        return "patient_missing"
    return "csv_uncovered"


# --------------------------------------------------------------------------- #
# PG DSN
# --------------------------------------------------------------------------- #
def pg_conn_str() -> str:
    return (
        os.environ.get("LNRS_PG_DSN")
        or "host=127.0.0.1 port=5432 user=lnrs password=lnrs_pwd dbname=postgres"
    )


# --------------------------------------------------------------------------- #
# 解析 + 过滤
# --------------------------------------------------------------------------- #
def parse_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader)


def filter_true_orphans(
    rows: list[dict[str, str]],
    *,
    include_dual_disk: bool,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """过滤真孤儿:in_pg_exact='0' AND in_pg_02d='0'。

    返回 (filtered_rows, stats)。
    """
    true_orphans: list[dict[str, str]] = []
    dual_disk: list[dict[str, str]] = []
    in_pg_exact: list[dict[str, str]] = []

    for r in rows:
        if r.get("in_pg_exact") == "1":
            in_pg_exact.append(r)
        elif r.get("in_pg_02d") == "1":
            dual_disk.append(r)
        else:
            true_orphans.append(r)

    stats = {
        "total": len(rows),
        "in_pg_exact": len(in_pg_exact),
        "dual_disk": len(dual_disk),
        "true_orphan": len(true_orphans),
    }

    rows_out = list(true_orphans)
    if include_dual_disk:
        rows_out.extend(dual_disk)
    return rows_out, stats


# --------------------------------------------------------------------------- #
# 患者反查
# --------------------------------------------------------------------------- #
def lookup_patient_ids(
    conn, center_code: str, rows: list[dict[str, str]]
) -> tuple[dict[str, str], dict[str, str]]:
    """对每行的 pat_local_id 计算 anon_id → SELECT patient_id WHERE anon_id=ANY(...)。

    返回 (anon_to_pt, pid_to_anon)。
    """
    pids = sorted({r["pat_local_id"] for r in rows if r.get("pat_local_id")})
    pid_to_anon = {p: compute_anon_id(center_code, p) for p in pids}

    anon_to_pt: dict[str, str] = {}
    with conn.cursor() as cur:
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
                (center_code, chunk),
            )
            for anon, pt in cur.fetchall():
                anon_to_pt[anon] = pt
    return anon_to_pt, pid_to_anon


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description="孤儿研究灌库")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="孤儿审计 CSV 路径")
    parser.add_argument("--center", default=DEFAULT_CENTER, help="center_code")
    parser.add_argument(
        "--dicom-root",
        default=DEFAULT_DICOM_ROOT,
        help="dicom 根绝对路径,用于剥离部署前缀(默认 /data/wlx/DATABASE/01_disk/zhujiang_dicom)",
    )
    parser.add_argument("--include-dual-disk", action="store_true", help="把 49 个双盘副本也灌入(orphan_kind=dual_disk_copy)")
    parser.add_argument("--include-empty-dir", action="store_true", help="占位:本期未实装")
    parser.add_argument("--dry-run", action="store_true", help="只解析不写 PG")
    parser.add_argument("--batch-size", type=int, default=2000, help="INSERT 批大小")
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"ERROR: CSV not found: {args.csv}", file=sys.stderr)
        return 2

    print(f"[*] 输入: {args.csv}")
    print(f"[*] center={args.center}  dicom_root={args.dicom_root}  dry_run={args.dry_run}")
    t0 = time.time()

    # 1. 解析 CSV
    all_rows = parse_csv_rows(args.csv)
    print(f"[*] CSV 解析: {len(all_rows)} 行")

    # 2. 过滤真孤儿
    rows, stats = filter_true_orphans(all_rows, include_dual_disk=args.include_dual_disk)
    print(
        f"[*] 过滤: total={stats['total']}  in_pg_exact={stats['in_pg_exact']}  "
        f"dual_disk={stats['dual_disk']}  true_orphan={stats['true_orphan']}"
    )
    print(f"[*] 待灌入(含 --include-dual-disk): {len(rows)} 行")

    # 3. 连接 PG,反查 patient_id
    import psycopg

    conn = psycopg.connect(pg_conn_str())
    conn.autocommit = False

    anon_to_pt, pid_to_anon = lookup_patient_ids(conn, args.center, rows)
    print(f"[*] patient_id 反查: 命中 {len(anon_to_pt)}/{len(pid_to_anon)} unique PID")

    # 4. 构造 insert rows(每行 14 个字段,顺序对齐 SQL)
    audit_batch_id = str(uuid.uuid4())
    csv_sha256 = hashlib.sha256(args.csv.read_bytes()).hexdigest()
    audit_locator = str(args.csv)

    by_kind_counts: dict[str, int] = {"csv_uncovered": 0, "patient_missing": 0, "dual_disk_copy": 0}
    missing_pids: list[str] = []
    insert_rows: list[tuple] = []
    orphan_status_counts: dict[str, int] = {}

    for r in rows:
        image_path = r["path"]
        dicom_study_uid = r["study_uid"]
        pat_local_id = r.get("pat_local_id") or ""
        basename = image_path.rstrip("/").rsplit("/", 1)[-1]

        rel_path = compute_rel_path(image_path, args.dicom_root)
        study_orphan_id = compute_study_orphan_id(args.center, rel_path)
        source_orphan_hash = compute_source_orphan_hash(args.center, image_path)

        patient_id: str | None = None
        if pat_local_id:
            anon_id = pid_to_anon.get(pat_local_id)
            if anon_id:
                patient_id = anon_to_pt.get(anon_id)
            if not patient_id:
                missing_pids.append(pat_local_id)

        # orphan_kind:49 个双盘副本单独标 dual_disk_copy;真孤儿按 patient_in_zhujiang 分
        if r.get("in_pg_exact") == "0" and r.get("in_pg_02d") == "0":
            kind = classify_orphan_kind(r)
        elif r.get("in_pg_02d") == "1":
            kind = "dual_disk_copy"
        else:
            kind = "csv_uncovered"
        by_kind_counts[kind] = by_kind_counts.get(kind, 0) + 1

        orphan_status = "discovered"
        orphan_status_counts[orphan_status] = orphan_status_counts.get(orphan_status, 0) + 1

        # patient_missing 的 patient_id 必为 NULL(CHECK 约束)
        if kind == "patient_missing":
            patient_id = None

        path_date_prefix = classify_path_date_prefix(basename)

        insert_rows.append((
            study_orphan_id,        # study_orphan_id
            args.center,             # center_code
            patient_id,             # patient_id(nullable)
            dicom_study_uid,         # dicom_study_uid
            image_path,              # image_path
            source_orphan_hash,      # source_orphan_hash
            path_date_prefix,        # path_date_prefix
            "CT",                    # modality
            0,                       # sop_count
            DEFAULT_SOURCE_TAG,      # source
            kind,                    # orphan_kind
            orphan_status,           # orphan_status
            None,                    # review_notes
            audit_batch_id,          # audit_batch_id
        ))

    # 5. 去重(以 (center, dicom_study_uid, image_path) 为 key)
    seen: set[tuple[str, str, str]] = set()
    unique_rows: list[tuple] = []
    for row in insert_rows:
        key = (row[1], row[3], row[4])  # (center_code, dicom_study_uid, image_path)
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)
    print(f"[*] 去重后待插入: {len(unique_rows)} 行（原始 {len(insert_rows)}）")

    if args.dry_run:
        print("[*] dry-run 统计:")
        print(f"    by_kind: {by_kind_counts}")
        print(f"    by_status: {orphan_status_counts}")
        print(f"    missing_pids (前 10): {missing_pids[:10]}")
        for row in unique_rows[:3]:
            print(
                f"    sample: study_orphan_id={row[0]}  center={row[1]}  "
                f"patient_id={row[2]}  path_tail={row[4][-60:]}"
            )
        conn.close()
        return 0

    # 6. 写入 audit_batch
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO lnrs.lnrs_anon_orphan_audit_batch
                (audit_batch_id, center_code, audit_locator, audit_sha256,
                 discovered_count, patient_missing_count, dual_disk_copy_count,
                 empty_dir_count, other_count, ran_by, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                audit_batch_id,
                args.center,
                audit_locator,
                csv_sha256,
                stats["true_orphan"],
                by_kind_counts.get("patient_missing", 0),
                by_kind_counts.get("dual_disk_copy", 0),
                0,  # empty_dir_count 本期未启用
                0,  # other_count 本期未启用
                "script:scripts/import_orphan_diagnosis.py@2026-09-03",
                f"imported {len(unique_rows)} true orphans from {args.csv.name}",
            ),
        )
    print(f"[*] audit_batch 已写入: {audit_batch_id}")

    # 7. 批量 upsert orphans
    upsert_sql = """
        INSERT INTO lnrs.lnrs_anon_imaging_orphan
            (study_orphan_id, center_code, patient_id, dicom_study_uid, image_path,
             source_orphan_hash, path_date_prefix, modality, sop_count, source,
             orphan_kind, orphan_status, review_notes, audit_batch_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (center_code, dicom_study_uid, image_path) DO NOTHING
    """
    inserted = 0
    with conn.cursor() as cur:
        for i in range(0, len(unique_rows), args.batch_size):
            batch = unique_rows[i : i + args.batch_size]
            cur.executemany(upsert_sql, batch)
            inserted += len(batch)
            if (i // args.batch_size) % 10 == 0:
                print(f"  ...batch {i // args.batch_size + 1}: 累计 {inserted}/{len(unique_rows)}")
    conn.commit()
    conn.close()

    elapsed = time.time() - t0
    print(f"[OK] 写入完成: {inserted} 行（耗时 {elapsed:.2f}s）")
    print(f"[OK] by_kind: {by_kind_counts}")
    print(f"[OK] by_status: {orphan_status_counts}")
    if missing_pids:
        miss_path = Path("/tmp/lnrs_audit/orphan_import_missing.txt")
        miss_path.parent.mkdir(parents=True, exist_ok=True)
        miss_path.write_text("\n".join(sorted(set(missing_pids))) + "\n")
        print(f"[!] 缺失 PID({len(missing_pids)}个) → {miss_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
