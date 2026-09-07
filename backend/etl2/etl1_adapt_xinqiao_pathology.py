"""ETL-1 适配: xinqiao pathology.parquet → ETL-2 引擎期望的 pathology_specimen.parquet 布局。

源文件: /data/wlx/DATABASE/extracted_tables/xinqiao/pathology.parquet (19,101 行, 8 列)
  关键列:
    patient_id, pat_local_id, 病理.送检部位(组织病理/冰冻切片),
    exam_date(VARCHAR 时间戳 'YYYY-MM-DD HH:MM:SS'),
    frozen(BOOLEAN), multi_nodules(BOOLEAN),
    specimens (LIST of 25 字段 STRUCT, 117 行 NULL),
    raw_text

与珠江 0825 pathology 的差异:
  - **无 exam_id 列** → 本脚本合成确定性 specimen_id:
      'XQP' || substr(md5(patient_id || '|' || exam_date || '|' || 送检部位), 1, 16)
    组键用完整时间戳（秒级）：(patient_id, exam_date, 送检部位) 组内 = 同一 exam
    跨多行（实测 12 组 × 2 行），跨行标本合并去重，同珠江 0825 模式。
  - 多一列 病理.送检部位（组织病理 9,788 / 冰冻切片 9,313，100% 非空）
    → 改名 submit_site 落 detail（珠江源文件没有此列）。

数据特征 (2026-09-04 实测):
  - 19,101 行 / 19,089 组（(patient,date,site)），12 组 2 行, max 2 行/组
  - 0 行完全重复; specimens 117 行 NULL / 0 行空数组
  - exam_date 全部可 CAST 为 DATE（含时间戳前缀）

xinqiao spec (anon_etl_engine.py) 期望的 pathology_specimen 列:
  id_field = "specimen_id", body_fields = ["histology_class"]
  detail_fields = ["submit_site", "frozen", "multi_nodules", "specimen_type",
                   "sampling_site", "specimens", "raw_text"]

本适配 (1 exam 1 行):
  - patient_id/exam_date/submit_site  <- 组键（组内常量）
  - frozen/multi_nodules/raw_text     <- 组内"稳定序首个非空" (arg_min + FILTER)
  - specimens                         <- 跨行 unnest 后按 (组, specimen) 去重再
                                         list 合并（LIST of STRUCT 原生类型;
                                         空组为 []）
  - histology_class/specimen_type/sampling_site
      <- 合并后 specimens 中首个非空对应字段 (list_filter + list_extract)

确定性 (同 2026-08-26 珠江病理修复): src_rn = 行内容 md5 哈希的确定性序号;
可变列取"稳定序首个非空"; specimens 数组按"首现行 src_rn, 行内位置"排序。

用法:
    cd backend
    ./.venv/bin/python etl2/etl1_adapt_xinqiao_pathology.py
    # 或指定路径:
    ./.venv/bin/python etl2/etl1_adapt_xinqiao_pathology.py \
        --src /data/wlx/DATABASE/extracted_tables/xinqiao/pathology.parquet \
        --out-dir ../data_xq0904/xinqiao

幂等: COPY OVERWRITE_OR_IGNORE。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb


def main() -> int:
    parser = argparse.ArgumentParser(description="xinqiao pathology.parquet → ETL-2 pathology_specimen.parquet 适配")
    parser.add_argument(
        "--src",
        default=None,
        help="源 parquet (默认 /data/wlx/DATABASE/extracted_tables/xinqiao/pathology.parquet)",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="输出目录 (默认 ../data_xq0904/xinqiao 相对 backend/)",
    )
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parent.parent
    default_src = Path("/data/wlx/DATABASE/extracted_tables/xinqiao/pathology.parquet")
    src = Path(args.src).resolve() if args.src else default_src.resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else (backend_dir.parent / "data_xq0904" / "xinqiao").resolve()

    if not src.exists():
        print(f"[ERR] 源文件不存在: {src}", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / "pathology_specimen.parquet"

    con = duckdb.connect(":memory:")
    src_posix = src.as_posix()
    dst_posix = dst.as_posix()

    # 组键 (patient_id, exam_date, 送检部位) 自带 patient_id/exam_date/submit_site
    # 一致性（珠江脚本的跨行一致性断言在此天然成立，无需单独检查）。
    # 注意: DuckDB 的 CTE 必须写在 COPY (...) 括号内部。
    sql = f"""
        COPY (
            WITH src AS (
                SELECT
                    patient_id,
                    "病理.送检部位"                  AS submit_site,
                    exam_date,
                    frozen,
                    multi_nodules,
                    specimens,
                    raw_text,
                    -- 合成确定性 exam id（组键 md5 前 16 hex = 64 bit,
                    -- 19k 组碰撞概率 ~1e-11）
                    'XQP' || substr(md5(
                        patient_id || '|' || exam_date || '|' || "病理.送检部位"
                    ), 1, 16)                        AS specimen_id,
                    ROW_NUMBER() OVER (
                        ORDER BY md5(to_json(struct_pack(
                            patient_id, "病理.送检部位", exam_date,
                            frozen, multi_nodules, specimens, raw_text
                        )))
                    )                                 AS src_rn
                FROM read_parquet('{src_posix}')
            ),
            base AS (
                SELECT s.specimen_id,
                       s.specimens[i]  AS specimen,
                       s.src_rn,
                       i               AS spec_pos
                FROM src s,
                     unnest(range(1, COALESCE(len(s.specimens), 0) + 1)) u(i)
            ),
            exam_attr AS (
                SELECT specimen_id,
                       arg_min(patient_id, src_rn)    AS patient_id,
                       arg_min(submit_site, src_rn)   AS submit_site,
                       CAST(arg_min(exam_date, src_rn) AS DATE)  AS exam_date,
                       arg_min(frozen, src_rn)       FILTER (WHERE frozen IS NOT NULL)        AS frozen,
                       arg_min(multi_nodules, src_rn) FILTER (WHERE multi_nodules IS NOT NULL) AS multi_nodules,
                       arg_min(raw_text, src_rn)     FILTER (WHERE raw_text IS NOT NULL)      AS raw_text
                FROM src
                GROUP BY specimen_id
            ),
            spec_merged AS (
                SELECT specimen_id, list(specimen ORDER BY first_key) AS specimens
                FROM (
                    SELECT specimen_id, MIN(src_rn * 1000000 + spec_pos) AS first_key, specimen
                    FROM base
                    GROUP BY specimen_id, specimen
                ) g
                GROUP BY specimen_id
            )
            SELECT
                ea.patient_id,
                ea.specimen_id,
                ea.exam_date,
                ea.submit_site,
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
            LEFT JOIN spec_merged sm ON sm.specimen_id = ea.specimen_id
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
    n_src_specimens = con.execute(
        f"SELECT COALESCE(SUM(len(specimens)), 0) FROM read_parquet('{src_posix}')",
    ).fetchone()[0]
    n_hist = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE histology_class IS NOT NULL", [dst.as_posix()]
    ).fetchone()[0]
    n_empty = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE len(specimens) = 0", [dst.as_posix()]
    ).fetchone()[0]
    n_no_date = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE exam_date IS NULL", [dst.as_posix()]
    ).fetchone()[0]
    print(
        f"[OK] {dst} 已生成\n"
        f"     总行数: {n} (源: 19,101; 12 组跨行合并)\n"
        f"     唯一 specimen_id: {n_uniq}\n"
        f"     specimens 总数 (合并去重后): {n_specimens} (源: {n_src_specimens}, 差=组内重复)\n"
        f"     histology_class 非空: {n_hist}\n"
        f"     specimens 空数组行数: {n_empty}\n"
        f"     exam_date 空: {n_no_date}"
    )
    if n_uniq != n:
        print("[ERR] specimen_id 存在重复, 引擎将静默去重丢行!", file=sys.stderr)
        return 1
    if n_no_date > 0:
        print("[WARN] 存在 exam_date 空行, 引擎将跳过这些行!", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
