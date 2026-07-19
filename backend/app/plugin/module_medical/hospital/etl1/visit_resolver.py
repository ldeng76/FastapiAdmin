"""visit_id 反查: 对 visit_recovery=True 的表, 用 (patient_id, m) 反查 visit_record.visit_id。

依据 (unified_table_schema.md "通用约定"):
> 第二列 '当前命中就诊次数/命中就诊总次数' 形如 m/n, 原始表中有多张工作表不携带
> 就诊编号列。新增表统一保留 visit_ordinal 字段, 并通过 ETL 在加载阶段用
> (patient_id, m) 反查 visit_record.visit_id 填充 visit_id; 若患者在 visit_record
> 中无对应记录, visit_id 置 null, 但 visit_ordinal 与 patient_id 仍保留。

实现 (见计划 §5): 全部在 SQL 层做 (LEFT JOIN), Python 不参与行处理。
"""

from __future__ import annotations

from pathlib import Path

from app.core.logger import log

from .config import CenterConfig, SheetSpec, DerivedSpec


def _collect_recovery_tables(center: CenterConfig) -> list[str]:
    """收集所有 visit_recovery=True 的目标表名。"""
    tables: list[str] = []
    for spec in center.universal_tables + center.hospital_tables:
        if isinstance(spec, SheetSpec) and spec.visit_recovery:
            tables.append(spec.target_table)
    for spec in center.derived_tables:
        if isinstance(spec, DerivedSpec) and spec.visit_recovery:
            tables.append(spec.target_table)
    # 去重保序
    seen: list[str] = []
    for t in tables:
        if t not in seen:
            seen.append(t)
    return seen


def resolve_visits(
    con,
    out_dir: Path,
    center: CenterConfig,
    only_tables: list[str] | None = None,
) -> None:
    """对所有 visit_recovery=True 的表, LEFT JOIN visit_record 回填 visit_id。

    流程:
    1. 若 visit_record.parquet 不存在 → 跳过 (visit_record 未生成时无法反查)
    2. 建立 (patient_id, m) → visit_id 的临时表
    3. 对每个需要反查的表, LEFT JOIN 回填 visit_id, 覆盖写 parquet

    安全: 表名已通过 SheetSpec 校验 (_SRC_TABLE_RE), 路径拼接可信。
    """
    visit_parquet = (out_dir / "visit_record.parquet").resolve()
    if not visit_parquet.exists():
        log.warning("ETL1: {}/visit_record.parquet 不存在, 跳过 visit_id 反查", out_dir.name)
        return

    recovery_tables = _collect_recovery_tables(center)
    if only_tables is not None:
        recovery_tables = [t for t in recovery_tables if t in only_tables]
    if not recovery_tables:
        log.info("ETL1: center {} 无需 visit 反查的表", center.code)
        return

    # 建立 visit 字典: (patient_id, m) → visit_id
    # m = visit_ordinal 的 '/' 前部分
    con.execute("""
        CREATE OR REPLACE TEMP TABLE _visit_dict AS
        SELECT
            patient_id,
            TRY_CAST(SPLIT_PART(visit_ordinal, '/', 1) AS BIGINT) AS m,
            visit_id
        FROM read_parquet(?)
        WHERE visit_ordinal IS NOT NULL
          AND visit_id IS NOT NULL
    """, [visit_parquet.as_posix()])
    n_dict = con.execute("SELECT count(*) FROM _visit_dict").fetchone()[0]
    log.info("ETL1: visit 字典 {} 条 (来自 {})", n_dict, visit_parquet.name)

    for tbl in recovery_tables:
        tbl_parquet = (out_dir / f"{tbl}.parquet").resolve()
        if not tbl_parquet.exists():
            log.warning("ETL1: {} 不存在, 跳过 visit 反查", tbl_parquet)
            continue
        _backfill_one(con, tbl_parquet, tbl)


def _backfill_one(con, tbl_parquet: Path, tbl: str) -> None:
    """对单张表 LEFT JOIN _visit_dict, 覆盖写回 parquet。

    策略: 写到一个临时 parquet, 完成后替换原文件 (原子性)。
    """
    tmp_parquet = tbl_parquet.with_suffix(".parquet.tmp")

    # 思路: 读原表, LEFT JOIN _visit_dict, 用 COALESCE 优先保留已有 visit_id
    # 但很多表本来就没有 visit_id 列 (是 visit_recovery=True 的目的就是回填)
    # 所以: SELECT t.*, d.visit_id → 但若 t 已有 visit_id 列会冲突
    # 用 USING(visit_id) 不行 (左表可能没有该列)
    # 安全做法: 先看表里有没有 visit_id 列, 有则 COALESCE, 无则直接补
    cols = con.execute(
        "SELECT column_name FROM (DESCRIBE SELECT * FROM read_parquet(?))",
        [tbl_parquet.as_posix()],
    ).fetchall()
    has_visit_id = any(c[0] == "visit_id" for c in cols)
    all_cols = [c[0] for c in cols]

    if has_visit_id:
        # 已有 visit_id: COALESCE 优先原值, JOIN 用 (patient_id, m) 但要补别名
        select_cols = []
        for c in all_cols:
            if c == "visit_id":
                select_cols.append("COALESCE(t.visit_id, d.visit_id) AS visit_id")
            else:
                select_cols.append(f't."{c}"')
        select_clause = ", ".join(select_cols)
        join_cond = (
            "t.patient_id = d.patient_id "
            "AND TRY_CAST(SPLIT_PART(t.visit_ordinal, '/', 1) AS BIGINT) = d.m"
        )
    else:
        # 无 visit_id 列: 全部原列 + d.visit_id
        select_cols = [f't."{c}"' for c in all_cols]
        select_cols.append("d.visit_id")
        select_clause = ", ".join(select_cols)
        join_cond = (
            "t.patient_id = d.patient_id "
            "AND TRY_CAST(SPLIT_PART(t.visit_ordinal, '/', 1) AS BIGINT) = d.m"
        )

    # 转义单引号
    tmp_path_str = tmp_parquet.as_posix().replace("'", "''")
    src_path_str = tbl_parquet.as_posix().replace("'", "''")

    # 2026-07-19 代码评审修复 (Issue #6):
    # 旧实现: 先 COPY 写 tmp (已含 visit_id), 再对 tmp LEFT JOIN _visit_dict 算统计
    #         —— 这导致"已合并的 visit_id"又被 JOIN 一次, matched 数翻倍/失真。
    # 新实现: 先对**原始 parquet** LEFT JOIN 算统计 (反映反查前的真实命中率),
    #         再 COPY 写 tmp。
    matched, missed = con.execute(f"""
        SELECT count(*) FILTER (WHERE d.visit_id IS NOT NULL) AS matched,
               count(*) FILTER (WHERE d.visit_id IS NULL) AS missed
        FROM read_parquet('{src_path_str}') t
        LEFT JOIN _visit_dict d ON {join_cond}
    """).fetchone()

    sql = f"""
        COPY (
            SELECT {select_clause}
            FROM read_parquet('{src_path_str}') t
            LEFT JOIN _visit_dict d ON {join_cond}
        ) TO '{tmp_path_str}'
        (FORMAT PARQUET, OVERWRITE_OR_IGNORE)
    """
    con.execute(sql)

    # 替换原文件 (原子)
    import os
    os.replace(tmp_parquet, tbl_parquet)
    # matched/missed 反映反查前的真实命中率 (基于原 parquet LEFT JOIN _visit_dict 算)
    log.info("ETL1: {} visit_id 回填完成 (matched={} missed={})",
             tbl, matched, missed)
