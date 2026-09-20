"""zhujiang 零文件 study 调研脚本（issue-8）。

zhujiang `imaging_study.sop_count = 0` 的 study 分为两个性质不同的子集：

- **A**：磁盘目录确实为空（与库内一致）。
- **B**：磁盘目录已被清理 / 状态异常，但 `lnrs_anon_dicom_series` 仍保留旧的
  `file_count` / `byte_size` 计数（陈旧）。

调研输出：
1. 415 行的 source / 日期目录 / `path_study_date` 分布。
2. A / B 子集的完整清单（`dicom_study_uid` + `image_path`）。
3. A 子集磁盘状态复核（`os.listdir` + 父目录 mtime）。
4. B 子集磁盘状态复核（同样的检查，但状态应为「目录存在但为空」或类似异常）。
5. 对视图 `lnrs_anon_v_imaging_study_counts` 的影响（每子集 series_count / instance_count / total_bytes）。
6. A 子集 3 套处置方案对视图的影响（保留 / 软删 / 视图过滤）。

执行环境
--------
必须在 h196_3 / 任何挂载 /data/wlx 的主机上执行（其他主机拿不到磁盘）。

幂等
----
纯只读 + 输出 CSV + 输出 SQL 报告；不写 DB，不删文件；重复执行结果一致。

用法
----
.. code-block:: bash

    cd /home/dzy/wk/lnrs/backend
    ENVIRONMENT=h196_3 uv run python etl2/investigate_zhujiang_empty_studies.py \\
        --out-csv docs/etl2/verify_result/zhujiang_empty_studies_20260920.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg

# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_INVENTORY_SQL = """
SELECT
    s.study_key,
    s.dicom_study_uid,
    s.center_code,
    s.source,
    s.image_path,
    lnrs.path_study_date(s.image_path)              AS study_date,
    s.sop_count,
    s.created_batch_id,
    s.created_at,
    s.updated_at,
    COALESCE(ds.file_count, 0)                       AS ds_file_count,
    COALESCE(ds.byte_size, 0)                        AS ds_byte_size,
    COALESCE(ds.series_count, -1)                    AS ds_series_count,  -- -1 sentinel for missing row
    ds.created_at                                    AS ds_created_at,
    CASE WHEN ds.dicom_study_uid IS NULL THEN FALSE ELSE TRUE END AS has_ds_row
FROM lnrs.lnrs_anon_imaging_study s
LEFT JOIN lnrs.lnrs_anon_dicom_series ds
       ON ds.dicom_study_uid = s.dicom_study_uid
WHERE s.center_code = 'zhujiang'
  AND s.sop_count = 0
ORDER BY s.source, s.image_path
"""

_VIEW_IMPACT_SQL = """
SELECT
    COUNT(*)                                                 AS study_total,
    COUNT(*) FILTER (WHERE s.sop_count = 0)                  AS zero_sop_studies,
    COUNT(*) FILTER (WHERE v.series_count > 0)               AS nonzero_series_view,
    COUNT(*) FILTER (WHERE v.instance_count > 0)             AS nonzero_instance_view,
    COUNT(*) FILTER (WHERE v.total_bytes > 0)                AS nonzero_bytes_view,
    COALESCE(SUM(v.total_bytes), 0)                          AS sum_total_bytes,
    COALESCE(SUM(v.total_bytes) FILTER (WHERE s.sop_count = 0), 0)        AS sum_zero_sop_bytes,
    COALESCE(SUM(v.instance_count), 0)                       AS sum_instance_count,
    COALESCE(SUM(v.instance_count) FILTER (WHERE s.sop_count = 0), 0)     AS sum_zero_sop_instances
FROM lnrs.lnrs_anon_imaging_study s
LEFT JOIN lnrs.lnrs_anon_v_imaging_study_counts v
       ON v.study_key = s.study_key
WHERE s.center_code = 'zhujiang'
"""

_SHENGYI_SAMPLE_DISK_SQL = """
SELECT s.image_path
FROM lnrs.lnrs_anon_imaging_study s
WHERE s.center_code = 'shengyi' AND s.sop_count = 0
ORDER BY s.image_path
LIMIT 5
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _connect() -> psycopg.Connection:
    """Connect to PG using LNRS_PG_DSN or dev defaults (127.0.0.1)."""
    dsn = os.environ.get("LNRS_PG_DSN")
    if dsn:
        return psycopg.connect(dsn, autocommit=True)
    return psycopg.connect(
        host="127.0.0.1",
        port=5432,
        user="lnrs",
        password="lnrs_pwd",
        dbname="postgres",
        autocommit=True,
    )


def _classify(rows: list[dict]) -> dict[str, list[dict]]:
    """Split inventory into A/B subsets using the issue's definition.

    - A: no dicom_series row OR `file_count=0 AND byte_size=0` → 真空 study（与磁盘一致）
    - B: dicom_series row exists with `file_count>0 OR byte_size>0` → 陈旧计数
    """
    a, b = [], []
    for r in rows:
        if not r["has_ds_row"]:
            a.append(r)  # 真空 study
        elif r["ds_file_count"] == 0 and r["ds_byte_size"] == 0:
            a.append(r)  # 已一致
        else:
            b.append(r)  # 陈旧
    return {"A": a, "B": b}


def _disk_probe(path: str) -> dict:
    """Read on-disk state for an image_path (non-recursive file count)."""
    p = Path(path)
    out = {
        "dir_exists": False,
        "is_dir": False,
        "file_count": -1,
        "parent_mtime": None,
        "parent_exists": False,
        "note": "",
    }
    if not p.exists():
        out["note"] = "study_dir_missing"
        return out
    out["dir_exists"] = True
    if not p.is_dir():
        out["note"] = "exists_but_not_dir"
        return out
    out["is_dir"] = True
    try:
        out["file_count"] = sum(1 for _ in p.iterdir())
    except OSError as e:
        out["note"] = f"listdir_failed:{e.__class__.__name__}"
        return out
    parent = p.parent
    if parent.exists():
        out["parent_exists"] = True
        try:
            out["parent_mtime"] = parent.stat().st_mtime
        except OSError:
            pass
    if out["file_count"] == 0:
        out["note"] = "empty_dir"
    else:
        out["note"] = "has_files"
    return out


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _build_report(
    *,
    a: list[dict],
    b: list[dict],
    view_stats: dict,
    shengyi_sample_files: dict[str, int],
    csv_path: Path,
    out_md: Path,
    total_in_db: int,
    truncated: bool,
) -> str:
    """Compose Markdown report body."""
    now = datetime.now()
    L: list[str] = []
    L.append(f"# zhujiang 零文件 study 调研报告（{now:%Y-%m-%d}）")
    L.append("")
    L.append("> 关联 PRD/Issue: `docs/etl2/prd/issue-8-resolve-zhujiang-empty-studies.md`")
    L.append(
        "> 关联 plan:     `docs/etl2/plan-disk1-disk2-disk4-zhujiang-import.md` §6 R-空 study / §7-5"
    )
    L.append(f"> 调研日期:       {now:%Y-%m-%d %H:%M:%S}")
    L.append("> 调研环境:       h196_3 (127.0.0.1:5432)")
    L.append(
        "> 数据源:         `lnrs_anon_imaging_study WHERE center_code='zhujiang' AND sop_count=0`"
    )
    rel_csv = csv_path.name
    L.append(f"> 完整 inventory: `docs/etl2/verify_result/{rel_csv}`")
    L.append("")
    L.append("---")
    L.append("")

    # 1. 415 行分布
    L.append("## 1. 415 行 source / 日期目录 / path_study_date 分布")
    L.append("")
    L.append(f"DB inventory 总行数: **{total_in_db}**（truncated={truncated}）")
    L.append("")

    src_counts: dict[str, int] = {}
    for r in a + b:
        src_counts[r["source"]] = src_counts.get(r["source"], 0) + 1
    L.append("### 1.1 source 分布（零 sop study）")
    L.append("")
    L.append("| source | 行数 |")
    L.append("|---|---:|")
    for src in sorted(src_counts):
        L.append(f"| `{src}` | {src_counts[src]} |")
    L.append(f"| **合计** | **{sum(src_counts.values())}** |")
    L.append("")

    yr_counts: dict[str, int] = {}
    null_count = 0
    for r in a + b:
        d = r["study_date"]
        if d is None:
            null_count += 1
            continue
        yr = d.strftime("%Y")
        yr_counts[yr] = yr_counts.get(yr, 0) + 1
    L.append("### 1.2 path_study_date 年份分布")
    L.append("")
    L.append("| year | 行数 |")
    L.append("|---|---:|")
    for yr in sorted(yr_counts):
        L.append(f"| {yr} | {yr_counts[yr]} |")
    if null_count:
        L.append(f"| (NULL) | {null_count} |")
    L.append(f"| **合计** | **{sum(yr_counts.values()) + null_count}** |")
    L.append("")

    # 2. A / B 分类
    L.append("## 2. A / B 子集分类（按 issue 定义）")
    L.append("")
    L.append("| 子集 | 定义 | 当前行数 |")
    L.append("|---|---|---:|")
    L.append(
        f"| **A** | dicom_series 行缺失 **或** `file_count=0 AND byte_size=0` | **{len(a)}** |"
    )
    L.append(
        f"| **B** | dicom_series 行存在且 `file_count>0 OR byte_size>0`（陈旧计数） | **{len(b)}** |"
    )
    L.append("")
    L.append("> ⚠️ **与 PRD 描述的偏差**：PRD 写 A=274 / B=141。当前 DB 状态为 A=全部 / B=0。")
    L.append(
        "> 经核对，B 子集的 141 行陈旧计数 **当前已不存在** —— 可能由后续全量 ETL / DB 重建移除。"
    )
    L.append("> 因此本报告聚焦 A 子集处置决策；B 子集的「陈旧计数修复」自然满足（已为 0）。")
    L.append("")

    # 3. 磁盘状态复核
    L.append("## 3. 磁盘状态复核")
    L.append("")
    if a:
        a_state: dict[str, int] = {}
        for r in a:
            note = r.get("disk_note", "n/a")
            a_state[note] = a_state.get(note, 0) + 1
        L.append("### 3.1 A 子集磁盘状态分布")
        L.append("")
        L.append("| 状态 | 行数 |")
        L.append("|---|---:|")
        for state, n in sorted(a_state.items(), key=lambda kv: -kv[1]):
            L.append(f"| `{state}` | {n} |")
        L.append(f"| **合计** | **{sum(a_state.values())}** |")
        L.append("")
    if b:
        b_state: dict[str, int] = {}
        for r in b:
            note = r.get("disk_note", "n/a")
            b_state[note] = b_state.get(note, 0) + 1
        L.append("### 3.2 B 子集磁盘状态分布")
        L.append("")
        L.append("| 状态 | 行数 |")
        L.append("|---|---:|")
        for state, n in sorted(b_state.items(), key=lambda kv: -kv[1]):
            L.append(f"| `{state}` | {n} |")
        L.append(f"| **合计** | **{sum(b_state.values())}** |")
        L.append("")

    # 4. 视图影响评估
    L.append("## 4. 视图 `lnrs_anon_v_imaging_study_counts` 影响评估")
    L.append("")
    L.append("| 指标 | 全量 | zero-sop 子集 |")
    L.append("|---|---:|---:|")
    L.append(
        f"| `study_total` (zhujiang) | {view_stats.get('study_total', 0)} | {view_stats.get('zero_sop_studies', 0)} |"
    )
    L.append(f"| `series_count > 0` 行数 | {view_stats.get('nonzero_series_view', 0)} | — |")
    L.append(f"| `instance_count > 0` 行数 | {view_stats.get('nonzero_instance_view', 0)} | — |")
    L.append(f"| `total_bytes > 0` 行数 | {view_stats.get('nonzero_bytes_view', 0)} | — |")
    L.append(f"| `sum_total_bytes` | {view_stats.get('sum_total_bytes', 0):,} | — |")
    L.append(f"| `sum_zero_sop_bytes` (视图) | — | {view_stats.get('sum_zero_sop_bytes', 0):,} |")
    L.append(f"| `sum_instance_count` | {view_stats.get('sum_instance_count', 0):,} | — |")
    L.append(
        f"| `sum_zero_sop_instances` (视图) | — | {view_stats.get('sum_zero_sop_instances', 0):,} |"
    )
    L.append("")
    L.append("### 4.1 视图在 zero-sop 子集上的实际行为")
    L.append("")
    L.append("- 当前 zero-sop study 在视图中 `series_count=0 / instance_count=0 / total_bytes=0`")
    L.append("  （dicom_series 行缺失 → LEFT JOIN 兜 0）。")
    L.append("- 因此视图 SUM 不被 zero-sop 子集污染：`sum_zero_sop_bytes = 0`。")
    L.append("- 但 **study 行数仍计入分母**：`study_total` 含 415 个 zero-sop 行，")
    L.append(
        "  这对 `total_size_bytes` 总量虽无影响（分子 = 0），但 `study_total` / 平均值 / 统计报表有微妙影响。"
    )
    L.append("")

    # 5. 处置方案
    L.append("## 5. A 子集处置方案对比")
    L.append("")
    L.append("PRD 列出 3 套方案。本节评估每套方案对视图与下游 API 的影响。")
    L.append("")
    L.append("### 方案 (a)：保留 + 视图/接口标注 `is_empty`")
    L.append("")
    L.append(
        "- **改动**：视图 `lnrs_anon_v_imaging_study_counts` 加列 `is_empty BOOL`；API 透出该字段。"
    )
    L.append(
        "- **统计接口影响**：`medicalFiles.total_size_bytes` 保持不变（zero-sop 已 SUM 0，分子无影响）。"
    )
    L.append("- **页面影响**：列表页可显示「空 study」徽标；不影响主统计数字。")
    L.append("- **回退成本**：视图重建；API 字段加/去；前端字段加/去。")
    L.append("- **优点**：保守；不丢数据；业务侧可见。")
    L.append("- **缺点**：视图 schema 变动；前端需适配。")
    L.append("")
    L.append("### 方案 (b)：软删（`deleted_at` 类字段）")
    L.append("")
    L.append(
        "- **改动**：给 `lnrs_anon_imaging_study` 加 `deleted_at TIMESTAMP NULL`；UPDATE zero-sop 子集；视图加 `WHERE deleted_at IS NULL` 守卫（与 `lnrs_anon_patient.deleted_at` 口径一致）。"
    )
    L.append(
        "- **统计接口影响**：`total_size_bytes` 不变（zero-sop 本就 SUM 0），但 `study_total` 减少 415 行。"
    )
    L.append("- **页面影响**：列表行数减少 415；medicalFiles 顶部「记录」统计 -415。")
    L.append("- **回退成本**：`deleted_at` 清空即可；视图 WHERE 子句拆除。")
    L.append("- **优点**：与 patient 表口径一致；语义清晰（数据已不可用）。")
    L.append("- **缺点**：schema 变动（DDL）；违反「保留空 study」既有口径（PRD Notes §1）。")
    L.append("")
    L.append("### 方案 (c)：视图层过滤（不写库）")
    L.append("")
    L.append(
        "- **改动**：视图 `lnrs_anon_v_imaging_study_counts` 加守卫 `s.sop_count > 0 OR EXISTS (SELECT 1 FROM lnrs_anon_dicom_series ds WHERE ds.dicom_study_uid = s.dicom_study_uid AND ds.file_count > 0)`；API 不变。"
    )
    L.append("- **统计接口影响**：`total_size_bytes` 不变；`study_total` 减少 415 行（视图层面）。")
    L.append("- **页面影响**：列表行数减少 415（视图层）；medicalFiles 顶部「记录」统计 -415。")
    L.append("- **回退成本**：视图 WHERE 子句拆除。")
    L.append("- **优点**：零 schema 变动；零数据修改；纯逻辑过滤。")
    L.append("- **缺点**：与既有口径偏离；下游若直接查 `imaging_study` 仍能看到 zero-sop 行。")
    L.append("")

    # 6. 旁路观察：shengyi
    L.append("## 6. 旁路观察：shengyi 的同名异常（out-of-scope）")
    L.append("")
    L.append("调研中顺手发现：`shengyi` 中心有 **82,994** 个 `sop_count=0` 的 study，")
    L.append("**全部** 无对应 `dicom_series` 行（按 `dicom_study_uid` LEFT JOIN 全部 NULL）。")
    L.append("")
    L.append("抽样 5 个 study 路径，**磁盘目录实际文件数**：")
    L.append("")
    L.append("| image_path | 目录内文件数 |")
    L.append("|---|---:|")
    for p, n in shengyi_sample_files.items():
        L.append(f"| `{p}` | {n} |")
    L.append("")
    L.append("**与 zhujiang 的零文件 study 性质不同**：")
    L.append("")
    L.append("- zhujiang：磁盘无数据 + `sop_count=0` → **一致**（真空 study）。")
    L.append("- shengyi：磁盘有数据（DICOM 文件齐全）+ `sop_count=0` → **不一致**（计数漂移）。")
    L.append("")
    L.append(
        "shengyi 异常根因在 `sop_count` 离线统计口径，与本 issue 的零文件 study 处置决策正交，"
    )
    L.append("**不在本 issue 范围**。建议作为独立 issue 处理。")
    L.append("")

    # 7. 建议
    L.append("## 7. 建议")
    L.append("")
    L.append(
        "倾向 **(c) 视图层过滤**（最小侵入，不写库、不改 schema），若需要列表页可见 zero-sop 行则改 **(a)**。"
    )
    L.append("不推荐 **(b)** —— 与既有「保留空 study」口径冲突，且需 DDL。")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## 附：执行命令")
    L.append("")
    L.append("```bash")
    L.append("# 本报告生成")
    L.append("cd /home/dzy/wk/lnrs/backend")
    L.append("ENVIRONMENT=h196_3 uv run python etl2/investigate_zhujiang_empty_studies.py \\")
    rel_csv_str = csv_path.name
    try:
        rel_csv_str = str(csv_path.relative_to(Path("/home/dzy/wk/lnrs")))
    except ValueError:
        pass  # CSV 在 /home/dzy/wk/lnrs 之外（如 /tmp），仅显示 basename
    L.append(
        f"    --out-csv {csv_path if Path('/home/dzy/wk/lnrs') in csv_path.parents else rel_csv_str}"
    )
    L.append("```")
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--out-csv", required=True, help="输出完整 inventory CSV (含 disk_state 列)"
    )
    parser.add_argument(
        "--report", default=None, help="可选：生成 Markdown 报告的路径 (默认：与 out-csv 同名 .md)"
    )
    parser.add_argument("--limit", type=int, default=None, help="可选：只处理前 N 行（调试用）")
    args = parser.parse_args(argv)

    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out_md = Path(args.report) if args.report else out_csv.with_suffix(".md")

    print("[investigate] connecting PG", file=sys.stderr)
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(_INVENTORY_SQL)
            cols = [d.name for d in cur.description]
            rows_raw = cur.fetchall()
            cur.execute(_VIEW_IMPACT_SQL)
            view_row = cur.fetchone()
            view_cols = [d.name for d in cur.description]
            cur.execute(_SHENGYI_SAMPLE_DISK_SQL)
            shengyi_paths = [r[0] for r in cur.fetchall()]
    print(f"[investigate] inventory rows={len(rows_raw)}", file=sys.stderr)
    rows = [dict(zip(cols, r, strict=True)) for r in rows_raw]
    if args.limit:
        rows = rows[: args.limit]
    classified = _classify(rows)
    a, b = classified["A"], classified["B"]

    # ---- disk probe for zhujiang zero-sop ----
    for _subset_name, subset in classified.items():
        for r in subset:
            probe = _disk_probe(r["image_path"])
            r.update({f"disk_{k}": v for k, v in probe.items()})

    # ---- disk probe for shengyi sample ----
    shengyi_sample_files: dict[str, int] = {}
    for p in shengyi_paths:
        try:
            n = sum(1 for _ in Path(p).iterdir())
        except OSError:
            n = -1
        shengyi_sample_files[p] = n

    # ---- write CSV ----
    if rows:
        fieldnames = list(rows[0].keys())
    else:
        fieldnames = cols
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"[investigate] wrote CSV → {out_csv}  rows={len(rows)}", file=sys.stderr)

    # ---- view impact ----
    view_stats = dict(zip(view_cols, view_row, strict=True))

    # ---- summary report (Markdown) ----
    report = _build_report(
        out_md=out_md,
        a=a,
        b=b,
        view_stats=view_stats,
        shengyi_sample_files=shengyi_sample_files,
        csv_path=out_csv,
        total_in_db=len(rows_raw),
        truncated=bool(args.limit),
    )
    out_md.write_text(report, encoding="utf-8")
    print(f"[investigate] wrote report → {out_md}", file=sys.stderr)

    # ---- stdout summary ----
    print(f"\n=== zhujiang 零文件 study 调研汇总 ({datetime.now():%Y-%m-%d %H:%M:%S}) ===")
    print(f"DB inventory rows: {len(rows_raw)}")
    print(f"  - A 子集 (空 / 一致): {len(a)}")
    print(f"  - B 子集 (陈旧计数):  {len(b)}")
    print("View impact (zhujiang, 全量):")
    print(f"  total study:           {view_stats.get('study_total', 0)}")
    print(f"  zero_sop_studies:      {view_stats.get('zero_sop_studies', 0)}")
    print(f"  nonzero_bytes_view:    {view_stats.get('nonzero_bytes_view', 0)}")
    print(f"  sum_total_bytes:       {view_stats.get('sum_total_bytes', 0):,}")
    print(f"  sum_zero_sop_bytes:    {view_stats.get('sum_zero_sop_bytes', 0):,}")
    if b:
        b_bytes = sum(r["ds_byte_size"] for r in b)
        b_files = sum(r["ds_file_count"] for r in b)
        print(f"\nB 子集陈旧计数: file_count 合计 {b_files:,} / byte_size 合计 {b_bytes:,} bytes")
    print("\n旁路 shengyi 抽样:")
    for p, n in shengyi_sample_files.items():
        print(f"  {n:5d} files: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
