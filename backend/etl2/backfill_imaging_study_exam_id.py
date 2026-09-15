"""回填 lnrs_anon_imaging_study.anon_exam_id（2026-09-15 方案 B 步骤 1）。

背景
----
dicom_series 落库依赖 lnrs_anon_imaging_study.anon_exam_id（DDL NOT NULL REFERENCES
lnrs.lnrs_anon_exam）。当前 h196_3 上 119,350 行 imaging_study 100% anon_exam_id=NULL，
导致 ETL-2 dicom_series 阶段（anon_etl_engine._import_dicom_series_for_center:3016）
100% skip。

imaging_study 是离线灌库的（CSV → DB），未走 ETL-2 exam 写入路径，
故 anon_exam_id 一直是 NULL。本脚本用 exam 表已落库的数据反查匹配，为每条
imaging_study 行关联一个最接近的 CT exam。

关联口径
--------
- 关联键：(imaging_study.patient_id, exam.patient_id)
- 模态约束：仅 exam_type='CT'（h196_3 上 imaging_study.modality 100%='CT'）
- 时间距离：|exam.exam_date - lnrs.path_study_date(image_path)| 最小
- 平局：取 anon_exam_id 字典序最小（稳定；可复现）
- 不可匹配（patient 不在 exam 表 / exam 表无 CT 行）：保持 NULL，由 dicom_series 阶段跳过

回填覆盖率（h196_3 实测 2026-09-15）：
  study_total      119,350
  ct_matchable      36,342  (30.4%)
  within_1day       36,337
  within_7day       36,342

用法
----
# dry-run：仅输出统计报告，不连 ETL 引擎，仅 SELECT
uv run python backend/etl2/backfill_imaging_study_exam_id.py --dry-run

# 实际回填（UPSERT 全量；幂等：基于 (study_key) 唯一）
uv run python backend/etl2/backfill_imaging_study_exam_id.py --apply

# 仅回填指定中心（zhujiang/shengyi/xinqiao/hos301）
uv run python backend/etl2/backfill_imaging_study_exam_id.py --apply --center zhujiang

# 仅统计指定中心的覆盖率
uv run python backend/etl2/backfill_imaging_study_exam_id.py --dry-run --center shengyi

前置
----
- ENVIRONMENT=h196_3（或 dev/h42；脚本读取 settings.DATABASE_*）
- anon_etl / 0012 表已落库

幂等
----
- 本脚本输出 SQL 是按 (study_key) 维度的 UPDATE，重复执行结果不变
- 不动 exam / dicom_series 表
- 不动 anon_exam_id 已经非空的行（WHERE anon_exam_id IS NULL 守卫）

回退
----
UPDATE lnrs.lnrs_anon_imaging_study SET anon_exam_id = NULL
WHERE study_key IN (...);  -- 凭 study_key 列表
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 允许直接 `python backend/etl2/backfill_imaging_study_exam_id.py` 跑
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import text  # noqa: E402

from app.core.database import async_db_session  # noqa: E402
from app.core.logger import log  # noqa: E402


# ---------- SQL 块 ----------

# 1) 覆盖率统计（dry-run 用）：不修改任何数据
SQL_COVERAGE_REPORT = """
WITH m AS (
  SELECT
    s.study_key,
    s.center_code,
    s.dicom_study_uid,
    count(e.anon_exam_id) FILTER (WHERE e.exam_type = 'CT')   AS ct_exam_count,
    min(abs(e.exam_date - lnrs.path_study_date(s.image_path)))
      FILTER (WHERE e.exam_type = 'CT')                        AS min_abs_diff_days
  FROM lnrs.lnrs_anon_imaging_study s
  LEFT JOIN lnrs.lnrs_anon_exam e
    ON e.patient_id = s.patient_id
   AND e.exam_type  = 'CT'
   AND lnrs.path_study_date(s.image_path) IS NOT NULL
  WHERE s.image_path IS NOT NULL
    {center_filter}
  GROUP BY s.study_key, s.center_code, s.dicom_study_uid
)
SELECT
  center_code,
  count(*)                                                                AS study_total,
  count(*) FILTER (WHERE ct_exam_count > 0)                              AS matchable,
  count(*) FILTER (WHERE min_abs_diff_days IS NOT NULL AND min_abs_diff_days <= 1)  AS within_1day,
  count(*) FILTER (WHERE min_abs_diff_days IS NOT NULL AND min_abs_diff_days <= 7)  AS within_7day,
  count(*) FILTER (WHERE min_abs_diff_days IS NULL)                       AS no_study_date,
  count(*) FILTER (WHERE ct_exam_count = 0)                               AS no_ct_exam
FROM m
GROUP BY center_code
ORDER BY center_code;
"""

# 2) 实际回填：UPSERT 候选（select_for_update 后批量 UPDATE）
#    平局规则：取 |日期差| 最小；并列取 anon_exam_id 字典序最小
SQL_PICK_CANDIDATE = """
SELECT
  s.study_key,
  (
    SELECT e.anon_exam_id
    FROM lnrs.lnrs_anon_exam e
    WHERE e.patient_id = s.patient_id
      AND e.exam_type  = 'CT'
      AND lnrs.path_study_date(s.image_path) IS NOT NULL
    ORDER BY abs(e.exam_date - lnrs.path_study_date(s.image_path)) ASC,
             e.anon_exam_id ASC
    LIMIT 1
  ) AS picked_exam_id
FROM lnrs.lnrs_anon_imaging_study s
WHERE s.anon_exam_id IS NULL
  AND s.image_path IS NOT NULL
  {center_filter}
  AND EXISTS (
    SELECT 1 FROM lnrs.lnrs_anon_exam e
    WHERE e.patient_id = s.patient_id
      AND e.exam_type  = 'CT'
      AND lnrs.path_study_date(s.image_path) IS NOT NULL
  );
"""


def _center_filter_sql(center: str | None) -> str:
    return f"AND s.center_code = '{center}'" if center else ""


async def run_dry_run(center: str | None) -> None:
    """仅输出覆盖率报告，不修改数据。"""
    sql = SQL_COVERAGE_REPORT.format(center_filter=_center_filter_sql(center))
    print(f"\n[DRY-RUN] 覆盖统计（center={center or 'ALL'}）：\n")
    async with async_db_session() as db:
        rows = (await db.execute(text(sql))).all()
        if not rows:
            print("  （无数据）")
            return
        # 表头
        print(
            f"  {'center':<12} {'total':>8} {'matchable':>10} {'<=1d':>8} "
            f"{'<=7d':>8} {'no_study_date':>14} {'no_ct_exam':>11}"
        )
        print(f"  {'-'*12} {'-'*8} {'-'*10} {'-'*8} {'-'*8} {'-'*14} {'-'*11}")
        for r in rows:
            print(
                f"  {r.center_code:<12} {r.study_total:>8} {r.matchable:>10} "
                f"{r.within_1day:>8} {r.within_7day:>8} {r.no_study_date:>14} "
                f"{r.no_ct_exam:>11}"
            )
        # 汇总
        total_studies = sum(r.study_total for r in rows)
        total_matchable = sum(r.matchable for r in rows)
        ratio = total_matchable / total_studies if total_studies else 0
        print(
            f"\n  合计: {total_matchable}/{total_studies} study 可回填 "
            f"({ratio*100:.1f}%)"
        )


async def run_apply(center: str | None) -> None:
    """实际回填 anon_exam_id。"""
    select_sql = SQL_PICK_CANDIDATE.format(center_filter=_center_filter_sql(center))
    print(f"\n[APPLY] 回填 imaging_study.anon_exam_id（center={center or 'ALL'}）…\n")

    picked = 0
    skipped = 0
    async with async_db_session() as db:
        # 候选选择
        result = await db.execute(text(select_sql))
        candidates = result.all()
        log.info(f"[APPLY] 候选 study 行 {len(candidates)} 条")

        # 批量 UPDATE：每条 study 一行 SQL，保持事务小颗粒
        BATCH = 500
        for i in range(0, len(candidates), BATCH):
            chunk = candidates[i : i + BATCH]
            for row in chunk:
                if not row.picked_exam_id:
                    skipped += 1
                    continue
                await db.execute(
                    text(
                        "UPDATE lnrs.lnrs_anon_imaging_study "
                        "SET anon_exam_id = :exam_id "
                        "WHERE study_key = :study_key "
                        "  AND anon_exam_id IS NULL"
                    ),
                    {"exam_id": row.picked_exam_id, "study_key": row.study_key},
                )
                picked += 1
            await db.commit()
            log.info(
                f"[APPLY] 进度 {min(i + BATCH, len(candidates))}/{len(candidates)} "
                f"committed={picked}"
            )

    print(
        f"\n[APPLY] 完成：updated={picked} skipped_no_candidate={skipped} "
        f"center={center or 'ALL'}"
    )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="backfill_imaging_study_exam_id",
        description="回填 lnrs_anon_imaging_study.anon_exam_id（方案 B 步骤 1）",
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="仅输出覆盖率报告")
    g.add_argument("--apply", action="store_true", help="实际回填")
    p.add_argument(
        "--center",
        default=None,
        choices=["zhujiang", "shengyi", "xinqiao", "hos301"],
        help="限定中心；默认全部",
    )
    return p.parse_args()


async def main() -> int:
    args = _parse_args()
    if args.dry_run:
        await run_dry_run(args.center)
    else:
        await run_apply(args.center)
    return 0


if __name__ == "__main__":
    sys.exit(__import__("asyncio").run(main()))