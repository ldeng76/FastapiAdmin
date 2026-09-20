"""Issue 6: zhujiang CT exam 灌库 + 回填 imaging_study.anon_exam_id (执行脚本)。

按 docs/etl2/prd/issue-6-ingest-zhujiang-ct-exam-and-backfill-anon-exam-id.md:
1. (可选) 备份 lnrs_anon_imaging_study.anon_exam_id 列与 lnrs_anon_exam 行。
2. 灌库 zhujiang/nodule_imaging.parquet → 写入 lnrs_anon_exam (CT 97,039 行预期)。
3. 跑 backfill_imaging_study_exam_id.py --dry-run --center zhujiang 取 matchable。
4. 跑 --apply 实际回填。
5. 验收断言: 非 NULL 计数 == matchable, 外键完整, 抽样一致。

设计要点:
- 绕过 `import_center` 的 patient spec (避免覆盖现有 67,114 zhujiang 占位患者的
  is_placeholder=TRUE; 否则会触发 issue-9 同类 bug)。
- 直接调用 `_import_exam_text_table` 写 nodule_imaging, 该函数内部会触发
  `_batch_upsert_patients(is_placeholder=True)`, 复用现有占位患者行(只刷新
  last_seen_batch_id, 不覆盖人口学)。

环境: ENVIRONMENT=h196_3。
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from _script_guard import (  # noqa: E402
    EXAM_TEXT_INGEST_TABLES,
    add_target_argument,
    count_parquet_rows,
    gate,
)
from sqlalchemy import text  # noqa: E402

from app.core.database import async_db_session  # noqa: E402
from app.core.logger import log  # noqa: E402


async def backup_imaging_study_state() -> int:
    """备份 zhujiang lnrs_anon_imaging_study.anon_exam_id 列到临时表。"""
    async with async_db_session() as s:
        await s.execute(text("""
            CREATE TABLE IF NOT EXISTS lnrs_tmp_issue6_study_before (
                study_key      bigint PRIMARY KEY,
                anon_exam_id   text
            )
        """))
        await s.execute(text("""
            DELETE FROM lnrs_tmp_issue6_study_before
            USING lnrs.lnrs_anon_imaging_study s
            WHERE lnrs_tmp_issue6_study_before.study_key = s.study_key
              AND s.center_code = 'zhujiang'
        """))
        n = await s.execute(text("""
            INSERT INTO lnrs_tmp_issue6_study_before (study_key, anon_exam_id)
            SELECT study_key, anon_exam_id
            FROM lnrs.lnrs_anon_imaging_study
            WHERE center_code = 'zhujiang'
        """))
        n = n.rowcount if hasattr(n, "rowcount") else 0
        await s.commit()
        log.info(f"[BACKUP] lnrs_tmp_issue6_study_before +{n} 行")
        return n


async def backup_exam_distribution() -> None:
    """备份 zhujiang lnrs_anon_exam 行 (按 exam_type 分布)。"""
    async with async_db_session() as s:
        r = await s.execute(text("""
            SELECT exam_type, COUNT(*) AS n
            FROM lnrs.lnrs_anon_exam
            WHERE center_code = 'zhujiang'
            GROUP BY 1 ORDER BY 1
        """))
        log.info(f"[BACKUP] lnrs_anon_exam 灌库前分布: "
                 f"{[dict(x._mapping) for x in r]}")


async def ingest_nodule_only(data_root: str) -> dict:
    from app.plugin.module_medical.hospital.anon_etl_engine import (
        _import_exam_text_table,
        _resolve_hospital_id,
    )
    from app.plugin.module_medical.hospital.anon_etl_service import (
        _create_batch,
    )
    root = Path(data_root)
    data_dir = root / "zhujiang"
    nodule_pq = data_dir / "nodule_imaging.parquet"
    if not nodule_pq.exists():
        raise FileNotFoundError(nodule_pq)
    async with async_db_session() as batch_sess:
        batch_id = await _create_batch(
            batch_sess, center_code="zhujiang", data_dir=data_dir,
            source_kind="csv_report",
        )
        await batch_sess.commit()
    log.info(f"[ETL-2] batch_id={batch_id}")

    async with async_db_session() as sess:
        await _resolve_hospital_id(sess, "zhujiang")
        n = await _import_exam_text_table(
            sess,
            center_code="zhujiang",
            parquet_path=nodule_pq,
            src_table="nodule_imaging",
            exam_type="CT",
            id_field="exam_id",
            body_fields=["findings", "impression"],
            detail_type="nodule_imaging",
            detail_fields=[
                "nodule_no", "nodule_location", "long_diameter", "density_type",
                "exam_meta", "nodule_morphology", "nodule_quantitative",
                "follow_up_comparison", "raw_text",
            ],
            ordinal_field="nodule_no",
            batch_id=batch_id,
            # issue-23：exam/patient 写 stage 表，promote 命令统一上生产；
            # report_text / exam_detail 不在 4 表 promote 链路内，仍直写
            stage_mode=True,
        )
        await sess.commit()
    log.info(f"[ETL-2] nodule_imaging 导入 {n} 行 exam+report")
    return {"batch_id": batch_id, "nodule_imaging_rows": n}


async def post_ingest_distribution() -> None:
    """灌库后 zhujiang lnrs_anon_exam 分布。"""
    async with async_db_session() as s:
        r = await s.execute(text("""
            SELECT exam_type, COUNT(*) AS n
            FROM lnrs.lnrs_stage_exam
            WHERE center_code = 'zhujiang'
            GROUP BY 1 ORDER BY 1
        """))
        log.info(f"[POST-INGEST] zhujiang lnrs_anon_exam 分布: "
                 f"{[dict(x._mapping) for x in r]}")


async def run_backfill_dry_run(center: str) -> dict | None:
    """跑 backfill dry-run, 返回 matchable。"""
    sys.path.insert(0, str(_BACKEND_ROOT / "etl2"))
    from backfill_imaging_study_exam_id import _center_filter_sql

    log.info(f"[backfill] --dry-run --center {center}")
    async with async_db_session() as s:
        from backfill_imaging_study_exam_id import SQL_COVERAGE_REPORT
        sql = SQL_COVERAGE_REPORT.format(center_filter=_center_filter_sql(center))
        r = await s.execute(text(sql))
        rows = [dict(x._mapping) for x in r]
        for row in rows:
            log.info(f"[backfill dry-run] {row}")
        return rows[0] if rows else None


async def run_backfill_apply(center: str) -> int:
    """跑 backfill apply（issue-23：结果写 stage_imaging_study，不直写生产）。"""
    sys.path.insert(0, str(_BACKEND_ROOT / "etl2"))
    from backfill_imaging_study_exam_id import run_apply
    log.info(f"[backfill] --apply --center {center}（写 stage）")
    await run_apply(center=center, write_target="stage")
    return 0


async def verify_after_apply(center: str, expected_matchable: int) -> None:
    """验收断言（issue-23 stage 口径）: stage 非 NULL 计数 == matchable,
    外键完整（stage.anon_exam_id ↔ 生产 exam）, 抽样一致。
    生产 imaging_study 在 promote 前不变，故验收对象是 stage 表。"""
    async with async_db_session() as s:
        # 1) 非 NULL 计数
        r = await s.execute(text("""
            SELECT COUNT(*) FILTER (WHERE anon_exam_id IS NOT NULL) AS with_exam,
                   COUNT(*) AS total
            FROM lnrs.lnrs_stage_imaging_study
            WHERE center_code = :c
        """), {"c": center})
        row = dict(r.mappings().first())
        log.info(f"[VERIFY] {center} stage_imaging_study: {row}")
        assert row["with_exam"] == expected_matchable, \
            f"期望非 NULL 计数 {expected_matchable}, 实际 {row['with_exam']}"

        # 2) 外键完整性
        r = await s.execute(text("""
            SELECT COUNT(*) FROM lnrs.lnrs_stage_imaging_study s
            WHERE s.center_code = :c
              AND s.anon_exam_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM lnrs.lnrs_anon_exam e
                              WHERE e.anon_exam_id = s.anon_exam_id)
        """), {"c": center})
        n_fk_violate = r.scalar()
        log.info(f"[VERIFY] FK 违例行数: {n_fk_violate}")
        assert n_fk_violate == 0, f"FK 违例 {n_fk_violate} 行"

        # 3) 抽样 3 条一致性: patient_id + exam_type='CT' + exam_date 最近
        r = await s.execute(text("""
            WITH samples AS (
                SELECT study_key
                FROM lnrs.lnrs_stage_imaging_study
                WHERE center_code = :c AND anon_exam_id IS NOT NULL
                ORDER BY random() LIMIT 3
            )
            SELECT s.study_key, s.image_path, s.anon_exam_id,
                   e.patient_id, e.exam_type, e.exam_date,
                   lnrs.path_study_date(s.image_path) AS study_date,
                   abs(e.exam_date - lnrs.path_study_date(s.image_path)) AS diff_days
            FROM lnrs.lnrs_stage_imaging_study s
            JOIN samples USING (study_key)
            JOIN lnrs.lnrs_anon_exam e ON e.anon_exam_id = s.anon_exam_id
            ORDER BY s.study_key
        """), {"c": center})
        log.info("[VERIFY] 抽样 3 条:")
        for row in r:
            d = dict(row._mapping)
            log.info(f"  {d}")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root",
        default="/home/dzy/wk/lnrs/data",
        help="ETL-1 产出物根目录 (默认 /home/dzy/wk/lnrs/data)",
    )
    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="跳过备份步骤 (不推荐)",
    )
    parser.add_argument(
        "--skip-ingest",
        action="store_true",
        help="仅跑 dry-run 统计, 不灌库",
    )
    parser.add_argument(
        "--skip-apply",
        action="store_true",
        help="仅灌库不跑 backfill apply",
    )
    add_target_argument(parser)
    args = parser.parse_args()

    # 安全闸（issue-21）：写生产库必须 --target 显式声明；沙箱库 lnrs_dev 免声明。
    # backup / ingest / backfill-apply 全跳过时本调用只读（action=read，永不拒绝）。
    # 预计影响行数取灌库源 nodule_imaging.parquet 行数（不连库；backfill 部分见下第二次确认）。
    will_write = not (args.skip_backup and args.skip_ingest and args.skip_apply)
    nodule_pq = Path(args.data_root) / "zhujiang" / "nodule_imaging.parquet"
    gate(
        schema="lnrs",
        tables=[
            # issue-23：写入目标只有 stage 表与备份 tmp 表；生产 4 表只读
            "lnrs.lnrs_stage_patient",
            "lnrs.lnrs_stage_exam",
            "lnrs.lnrs_stage_imaging_study",
            "lnrs_tmp_issue6_study_before (backup)",
        ],
        declared=args.target,
        estimated_rows=None if args.skip_ingest else count_parquet_rows(nodule_pq),
        action="write" if will_write else "read",
    )

    if not args.skip_backup:
        await backup_imaging_study_state()
        await backup_exam_distribution()

    if not args.skip_ingest:
        await ingest_nodule_only(args.data_root)
        await post_ingest_distribution()

    matchable_row = await run_backfill_dry_run("zhujiang")
    expected_matchable = matchable_row["matchable"] if matchable_row else 0
    log.info(f"[backfill dry-run] matchable = {expected_matchable}")

    if not args.skip_apply:
        # 第二次确认（issue-21）：backfill apply 的预计行数取自 dry-run 口径
        # （SQL_COVERAGE_REPORT.matchable，上方 run_backfill_dry_run 已算出）
        gate(
            tables=["lnrs.lnrs_stage_imaging_study"],
            declared=args.target,
            estimated_rows=expected_matchable,
            action="write",
        )
        await run_backfill_apply("zhujiang")
        await verify_after_apply("zhujiang", expected_matchable)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
