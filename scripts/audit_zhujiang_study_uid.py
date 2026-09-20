#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""issue-14：珠江 lnrs_anon_imaging_study.dicom_study_uid 与 DICOM header (0008,0020) 一致性调研。

端到端：从 lnrs_anon_imaging_study 抽 ≥100 条 zhujiang study，
读每条目录首个 .dcm 的 StudyInstanceUID，比对 dicom_study_uid 列，
生成 docs/etl2/verify_result/zhujiang_study_uid_audit.md 报告。

用法：
    uv run python scripts/audit_zhujiang_study_uid.py            # 抽 100 条
    uv run python scripts/audit_zhujiang_study_uid.py --n 200    # 抽 200 条
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pydicom

# ---------- 数据类 ----------


@dataclass(frozen=True)
class StudySample:
    """PG 抽样的最小三元组。"""

    patient_id: str
    dicom_study_uid: str
    image_path: Path


@dataclass(frozen=True)
class AuditResult:
    """单条 study 的对账结果。

    header_study_uid="N/A" 表示未能读到（路径缺失 / 损坏 / 权限等）。
    """

    patient_id: str
    dicom_study_uid: str
    header_study_uid: str | None
    match: bool
    error: str | None


# ---------- seam 4: PG 抽样 ----------


_SAMPLE_SQL = """
SELECT patient_id, dicom_study_uid, image_path
FROM lnrs.lnrs_anon_imaging_study
WHERE center_code = 'zhujiang'
  AND image_path IS NOT NULL
ORDER BY random()
LIMIT %s
""".strip()


def sample_studies(conn, n: int) -> list[StudySample]:
    """从 PG 随机抽 n 条 zhujiang study。

    conn: psycopg 风格连接，execute(sql, params) → cursor；cursor.fetchall() 返回行。
    """
    cur = conn.execute(_SAMPLE_SQL, (n,))
    rows = cur.fetchall()
    return [
        StudySample(
            patient_id=row[0],
            dicom_study_uid=row[1],
            image_path=Path(row[2]),
        )
        for row in rows
    ]


# ---------- seam 1: DICOM header 读 ----------


def read_study_uid(image_path: Path) -> str:
    """从 study 根目录下首个 DICOM 文件读 (0008,0020) StudyInstanceUID。

    zhujiang 风格的 study 根目录内是「无扩展名 DICOM 文件」（如
    `0001_000001_1.2.156.14702.1.1015.124.2.202501110903457707448`），
    直接用 Path.iterdir() 取首个文件。
    """
    if not image_path.exists():
        raise FileNotFoundError(f"study 目录不存在: {image_path}")
    if not image_path.is_dir():
        raise FileNotFoundError(f"study 路径不是目录: {image_path}")
    files = [p for p in image_path.iterdir() if p.is_file()]
    if not files:
        raise FileNotFoundError(f"study 目录为空: {image_path}")
    first = sorted(files)[0]
    ds = pydicom.dcmread(str(first), stop_before_pixels=True)
    return str(ds.StudyInstanceUID)


# ---------- seam 2: 比对 ----------


def audit_one(sample: StudySample) -> AuditResult:
    """单条对账：dicom_study_uid == header StudyInstanceUID？

    出错时（路径缺失 / 权限 / DICOM 损坏）返回 match=False + 短描述错误，
    不抛 —— 调研类脚本必须保证 100 条抽样不中断。
    """
    try:
        header_uid = read_study_uid(sample.image_path)
    except FileNotFoundError:
        return AuditResult(
            patient_id=sample.patient_id,
            dicom_study_uid=sample.dicom_study_uid,
            header_study_uid="N/A",
            match=False,
            error="路径不可读（缺失或为空）",
        )
    except Exception as exc:  # noqa: BLE001 — 调研类脚本吃异常以保证抽样不中断
        return AuditResult(
            patient_id=sample.patient_id,
            dicom_study_uid=sample.dicom_study_uid,
            header_study_uid="N/A",
            match=False,
            error=f"{type(exc).__name__}",
        )
    return AuditResult(
        patient_id=sample.patient_id,
        dicom_study_uid=sample.dicom_study_uid,
        header_study_uid=header_uid,
        match=(header_uid == sample.dicom_study_uid),
        error=None,
    )


# ---------- 编排 ----------


def audit_many(samples: list[StudySample]) -> list[AuditResult]:
    """批量对账，逐条调用 audit_one。"""
    return [audit_one(s) for s in samples]


# ---------- seam 3: 报告 ----------


def write_report(report_path: Path, results: list[AuditResult], *, sampled_n: int) -> None:
    """生成 markdown 报告：

      1. 头部 metadata（生成时间 / 抽样数 / 数据源）
      2. 汇总（匹配率 / match/mismatch/error 计数）
      3. 完整明细表（每条 4 列：patient_id, dicom_study_uid, header_study_uid, match）
      4. ≤3 个典型 mismatch / error 案例
    """
    total = len(results)
    matched = sum(1 for r in results if r.match)
    mismatched = sum(1 for r in results if not r.match and r.error is None)
    errored = sum(1 for r in results if r.error is not None)
    match_rate = (matched / total * 100) if total else 0.0
    mismatches = [r for r in results if not r.match and r.error is None]
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    lines: list[str] = []
    lines.append("# 珠江 `lnrs_anon_imaging_study.dicom_study_uid` header 对账报告")
    lines.append("")
    lines.append(f"> 生成时间：{now}  ")
    lines.append("> 数据源：`lnrs.lnrs_anon_imaging_study` (center_code='zhujiang')  ")
    lines.append(f"> 抽样数：{sampled_n}（实际返回 {total}）  ")
    lines.append("> 方法：从 `image_path` 目录取首个 `.dcm` 读 (0008,0020) `StudyInstanceUID`，")
    lines.append("> 与 PG `dicom_study_uid` 列比较。")
    lines.append("")

    lines.append("## 1. 汇总")
    lines.append("")
    lines.append(f"- 总样本：{total}")
    lines.append(f"- 匹配（match=True）：{matched}")
    lines.append(f"- 不匹配（mismatch，无 error）：{mismatched}")
    lines.append(f"- 错误（error：路径缺失 / DICOM 损坏 / 权限等）：{errored}")
    lines.append(f"- 匹配率：{match_rate:.2f}%（{matched}/{total}）")
    lines.append("")

    lines.append("## 2. 明细（每条 4 列）")
    lines.append("")
    lines.append("| patient_id | dicom_study_uid | header_study_uid | match |")
    lines.append("|---|---|---|---|")
    for r in results:
        match_cell = "✓" if r.match else "✗"
        if r.error:
            match_cell = f"ERR `{r.error}`"
        lines.append(
            f"| {r.patient_id} | `{r.dicom_study_uid}` | "
            f"`{r.header_study_uid or ''}` | {match_cell} |"
        )
    lines.append("")

    # 典型案例
    if mismatches:
        lines.append("## 3. 典型不匹配案例（最多 3 条）")
        lines.append("")
        lines.append("| patient_id | dicom_study_uid | header_study_uid |")
        lines.append("|---|---|---|")
        for r in mismatches[:3]:
            lines.append(
                f"| {r.patient_id} | `{r.dicom_study_uid}` | `{r.header_study_uid}` |"
            )
        lines.append("")
    elif errored:
        lines.append("## 3. 错误案例（最多 3 条）")
        lines.append("")
        lines.append("| dicom_study_uid | error |")
        lines.append("|---|---|")
        for r in [r for r in results if r.error is not None][:3]:
            lines.append(f"| `{r.dicom_study_uid}` | {r.error} |")
        lines.append("")

    # 决策
    lines.append("## 4. 决策")
    lines.append("")
    if match_rate == 100.0 and errored == 0:
        lines.append(
            "**珠江数据可信**：抽样内 dicom_study_uid 全部等于 DICOM header "
            "StudyInstanceUID，无需重灌。"
        )
    elif match_rate < 100.0 and len(mismatches) >= 3:
        lines.append(
            f"**需修复**：匹配率 {match_rate:.2f}% < 100%，"
            f"且 ≥3 例 mismatch，建议开修复工单重灌 dicom_study_uid。"
        )
    elif errored > 0 and matched == 0:
        lines.append(
            "**抽样全错**：要么 PG 与磁盘完全不对应，要么目录结构已变，需立即排查。"
        )
    else:
        lines.append(
            f"**待人工评估**：匹配率 {match_rate:.2f}%，"
            f"mismatch={len(mismatches)} / error={errored}，"
            f"case-by-case 判断。"
        )
    lines.append("")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


# ---------- main ----------


def _pg_connect():
    """从 env/.env.h196_3 或环境变量读 PG 连接信息，用 psycopg.connect 建立连接。"""
    import psycopg

    env_path = Path("/home/dzy/wk/lnrs/backend/env/.env.h196_3")
    env: dict[str, str] = {}
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip().strip('"').strip("'")
    host = env.get("PG_HOST") or os.environ.get("PG_HOST") or "127.0.0.1"
    port = int(env.get("PG_PORT") or os.environ.get("PG_PORT") or "5432")
    user = env.get("PG_USER") or os.environ.get("PG_USER") or "lnrs"
    password = env.get("PG_PASSWORD") or os.environ.get("PG_PASSWORD") or "lnrs_pwd"
    database = env.get("PG_DATABASE") or os.environ.get("PG_DATABASE") or "postgres"
    return psycopg.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        dbname=database,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="issue-14 zhujiang study UID 对账")
    parser.add_argument("--n", type=int, default=100, help="抽样条数（默认 100）")
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("/home/dzy/wk/lnrs/docs/etl2/verify_result/zhujiang_study_uid_audit.md"),
        help="报告输出路径",
    )
    args = parser.parse_args()

    print(f"[audit] 抽样 {args.n} 条 zhujiang study...", file=sys.stderr)
    with _pg_connect() as conn:
        samples = sample_studies(conn, args.n)
    print(f"[audit] 抽样返回 {len(samples)} 条，开始对账...", file=sys.stderr)
    results = audit_many(samples)
    print(f"[audit] 对账完成，写报告 {args.report}", file=sys.stderr)
    write_report(args.report, results, sampled_n=args.n)

    matched = sum(1 for r in results if r.match)
    total = len(results)
    rate = (matched / total * 100) if total else 0.0
    summary = {
        "sampled_n": args.n,
        "returned_n": total,
        "matched": matched,
        "mismatched": sum(1 for r in results if not r.match and r.error is None),
        "errored": sum(1 for r in results if r.error is not None),
        "match_rate_pct": round(rate, 2),
        "report_path": str(args.report),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())