"""ETL-1 适配: pathology.parquet → ETL-2 引擎期望的 pathology_specimen.parquet 布局。

源文件: /data/wlx/DATABASE/extracted_tables/zhujiang/pathology.parquet
  (15,542 行, exam 级 + specimens[] 数组)
  关键列:
    patient_id, exam_id, pat_local_id, exam_date(VARCHAR),
    frozen(BOOLEAN), multi_nodules(BOOLEAN),
    specimens (LIST of 32 字段 STRUCT, 部分行为 NULL 或空数组),
    raw_text

数据特征 (0825 批次实测):
  - 152 个 exam 跨多行 (2/3 行), 15,382 个唯一 exam_id
  - 75 行 specimens 为空数组, 49 行为 NULL
  - 同一 exam 跨行/行内的 specimens 存在完全重复 (struct 全字段相同), 需去重

zhujiang spec (anon_etl_engine.py) 期望的 pathology_specimen 列:
  id_field = "specimen_id", body_fields = ["histology_class"]
  detail_fields = ["specimen_meta", "adenocarcinoma_subtypes", "tumor_measurement",
                   "high_risk_factors", "staging", "specimen_type", "sampling_site",
                   "specimens"]

本适配 (1 exam 1 行):
  - patient_id/exam_date/frozen/multi_nodules/raw_text
      <- 按 exam_id GROUP BY 取 FIRST (执行前断言: 跨行 exam 的 patient_id/
         exam_date 必须一致, 否则停止)
  - specimen_id <- exam_id
  - exam_date   <- CAST(FIRST(exam_date) AS DATE)
  - specimens   <- 跨行 unnest 后按 (exam_id, specimen) 去重再 list 合并
                   (LIST of STRUCT, 原生类型; 空 exam 为 [])
  - histology_class/specimen_type/sampling_site
      <- 合并后 specimens 中首个非空对应字段 (list_filter + list_extract)

用法:
    cd backend
    ./.venv/bin/python etl1_adapt_zhujiang0825_pathology.py
    # 或指定路径:
    ./.venv/bin/python etl1_adapt_zhujiang0825_pathology.py \
        --src /data/wlx/DATABASE/extracted_tables/zhujiang/pathology.parquet \
        --out-dir ../data_zj0825/zhujiang

幂等: COPY OVERWRITE_OR_IGNORE。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb


def main() -> int:
    parser = argparse.ArgumentParser(description="pathology.parquet → ETL-2 pathology_specimen.parquet 适配")
    parser.add_argument(
        "--src",
        default=None,
        help="源 parquet (默认 /data/wlx/DATABASE/extracted_tables/zhujiang/pathology.parquet)",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="输出目录 (默认 ../data_zj0825/zhujiang 相对 backend/)",
    )
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parent.parent
    default_src = Path("/data/wlx/DATABASE/extracted_tables/zhujiang/pathology.parquet")
    src = Path(args.src).resolve() if args.src else default_src.resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else (backend_dir.parent / "data_zj0825" / "zhujiang").resolve()

    if not src.exists():
        print(f"[ERR] 源文件不存在: {src}", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / "pathology_specimen.parquet"

    con = duckdb.connect(":memory:")
    src_posix = src.as_posix()
    dst_posix = dst.as_posix()

    # 前置一致性断言: 跨行 exam 的 patient_id/exam_date 必须一致, 否则 FIRST()
    # 取值无意义, 停止并报告。
    n_conflict = con.execute(
        f"""
        SELECT COUNT(*) FROM (
            SELECT exam_id,
                   COUNT(DISTINCT patient_id)                    AS c,
                   COUNT(DISTINCT CAST(exam_date AS VARCHAR))    AS d
            FROM read_parquet('{src_posix}')
            GROUP BY exam_id
            HAVING c > 1 OR d > 1
        )
        """
    ).fetchone()[0]
    print(f"[CHECK] 跨行 exam 的 patient_id/exam_date 不一致组数: {n_conflict}")
    if n_conflict > 0:
        print(
            "[ERR] 存在跨行不一致的 exam_id, 无法安全合并, 已停止。"
            "请先核查源数据。",
            file=sys.stderr,
        )
        return 1

    # CROSS JOIN LATERAL 的等价改写: histology_class 等三列直接从
    # COALESCE(sm.specimens, []) 表达式计算, 语义一致且兼容性更好。
    # 注意: DuckDB 的 CTE 必须写在 COPY (...) 括号内部。
    #
    # 确定性 (2026-08-26 修复): 多行 exam 的取值原先依赖 FIRST()/扫描顺序,
    # 同一源文件每次运行产出不同 staging (152 个跨行 exam 的 histology_class/
    # raw_text 与 specimens 数组顺序漂移), 重导会静默改写已落库值。
    # 现改为: src_rn = 行内容 md5 哈希的确定性序号; 可变列取"稳定序首个非空"
    # (arg_min + FILTER); specimens 数组按"首现行 src_rn, 行内位置"排序。
    sql = f"""
        COPY (
            WITH src AS (
                SELECT *,
                       ROW_NUMBER() OVER (
                           ORDER BY md5(to_json(struct_pack(
                               patient_id, exam_id, pat_local_id, exam_date,
                               frozen, multi_nodules, specimens, raw_text
                           )))
                       ) AS src_rn
                FROM read_parquet('{src_posix}')
            ),
            base AS (
                SELECT s.exam_id,
                       s.specimens[i]  AS specimen,
                       s.src_rn,
                       i               AS spec_pos
                FROM src s,
                     unnest(range(1, COALESCE(len(s.specimens), 0) + 1)) u(i)
            ),
            exam_attr AS (
                SELECT exam_id,
                       arg_min(patient_id, src_rn)    AS patient_id,
                       arg_min(pat_local_id, src_rn) FILTER (WHERE pat_local_id IS NOT NULL)  AS pat_local_id,
                       CAST(arg_min(exam_date, src_rn) AS DATE)  AS exam_date,
                       arg_min(frozen, src_rn)       FILTER (WHERE frozen IS NOT NULL)        AS frozen,
                       arg_min(multi_nodules, src_rn) FILTER (WHERE multi_nodules IS NOT NULL) AS multi_nodules,
                       arg_min(raw_text, src_rn)     FILTER (WHERE raw_text IS NOT NULL)      AS raw_text
                FROM src
                GROUP BY exam_id
            ),
            spec_merged AS (
                SELECT exam_id, list(specimen ORDER BY first_key) AS specimens
                FROM (
                    SELECT exam_id, MIN(src_rn * 1000000 + spec_pos) AS first_key, specimen
                    FROM base
                    GROUP BY exam_id, specimen
                ) g
                GROUP BY exam_id
            )
            SELECT
                ea.patient_id,
                ea.exam_id                              AS specimen_id,
                ea.exam_date,
                ea.frozen,
                ea.multi_nodules,
                ea.raw_text,
                COALESCE(sm.specimens, [])              AS specimens,
                list_extract(
                    list_filter(COALESCE(sm.specimens, []), x -> x.histology_class IS NOT NULL), 1
                ).histology_class                       AS histology_class,
                list_extract(
                    list_filter(COALESCE(sm.specimens, []), x -> x.specimen_type IS NOT NULL), 1
                ).specimen_type                         AS specimen_type,
                list_extract(
                    list_filter(COALESCE(sm.specimens, []), x -> x.sampling_site IS NOT NULL), 1
                ).sampling_site                         AS sampling_site
            FROM exam_attr ea
            LEFT JOIN spec_merged sm ON sm.exam_id = ea.exam_id
        ) TO '{dst_posix}' (FORMAT PARQUET, OVERWRITE_OR_IGNORE)
    """
    con.execute(sql)

    n = con.execute("SELECT COUNT(*) FROM read_parquet(?)", [dst.as_posix()]).fetchone()[0]
    n_uniq = con.execute(
        "SELECT COUNT(DISTINCT specimen_id) FROM read_parquet(?)", [dst.as_posix()]
    ).fetchone()[0]
    n_specimens = con.execute(
        "SELECT COALESCE(SUM(len(specimens)), 0) FROM read_parquet(?)", [dst.as_posix()]
    ).fetchone()[0]
    n_hist = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE histology_class IS NOT NULL", [dst.as_posix()]
    ).fetchone()[0]
    n_empty = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE len(specimens) = 0", [dst.as_posix()]
    ).fetchone()[0]
    print(
        f"[OK] {dst} 已生成\n"
        f"     总行数: {n}\n"
        f"     唯一 specimen_id: {n_uniq}\n"
        f"     specimens 总数 (合并去重后): {n_specimens}\n"
        f"     histology_class 非空: {n_hist}\n"
        f"     specimens 空数组行数: {n_empty}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
