"""ETL-1 适配: ihc.parquet → ETL-2 引擎期望的 ihc_result.parquet 布局。

源文件: /data/wlx/DATABASE/extracted_tables/zhujiang/ihc.parquet
  (6,827 行, 免疫组化检验)
  关键列:
    patient_id, exam_id, pat_local_id, exam_date(VARCHAR),
    ki67_pct(BIGINT), pdl1_tps_pct(BIGINT), pdl1_clone(VARCHAR),
    pdl1_cps(BIGINT), alk_ihc/ttf1/napsina/p40(BOOLEAN), p53(VARCHAR), raw_text

数据特征 (0825 批次实测):
  - 100 个 exam_id 出现 2+ 行 (96 组×2行 + 4 组×3行), 组内结构化字段绝大多数
    仅 raw_text 不同; 2 个 exam 存在结构化字段冲突:
      * 1005300687 (patient 2897920): 行1 完整 (ki67=70, tps=90, 22C3,
        ALK/TTF1/napsina 阳, p40 阴, p53 突变型), 行2 几乎全 NULL 仅 tps=1
      * 1002774152 (patient 2833414): ki67_pct 2 vs 90, 其余列全 NULL

去重策略 (主线 2026-08-25 定, 方案 a): 按 9 个结构化字段的非空数降序取行,
  平手取文件顺序首行 (ROW_NUMBER() OVER () 的扫描序即文件序)。
  1005300687 取完整行, 1002774152 取首行 (ki67=2), 两个 exam 均保留,
  最终 6,723 行 = 唯一 exam_id 数。脚本执行时会对冲突 exam 打印各行非空数
  与实际取舍, 备查。

zhujiang spec (anon_etl_engine.py) 期望的 ihc_result 列:
  id_field = "specimen_id", date_field = "exam_date"
  detail_fields = ["ki67_pct", "pdl1_tps_pct", "pdl1_clone", "pdl1_cps",
                   "alk_ihc", "ttf1", "napsina", "p40", "p53"]
  列名与源文件一致, 无需改名; raw_text 不入引擎。

本适配:
  - exam_id       <- specimen_id
  - exam_date     <- CAST(exam_date AS DATE)  (VARCHAR YYYY-MM-DD -> DATE)
  - 其余 9 个 detail 列原样

用法:
    cd backend
    ./.venv/bin/python etl1_adapt_zhujiang0825_ihc.py
    # 或指定路径:
    ./.venv/bin/python etl1_adapt_zhujiang0825_ihc.py \
        --src /data/wlx/DATABASE/extracted_tables/zhujiang/ihc.parquet \
        --out-dir ../data_zj0825/zhujiang

幂等: COPY OVERWRITE_OR_IGNORE。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

STRUCT_COLS = [
    "ki67_pct", "pdl1_tps_pct", "pdl1_clone", "pdl1_cps",
    "alk_ihc", "ttf1", "napsina", "p40", "p53",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="ihc.parquet → ETL-2 ihc_result.parquet 适配")
    parser.add_argument(
        "--src",
        default=None,
        help="源 parquet (默认 /data/wlx/DATABASE/extracted_tables/zhujiang/ihc.parquet)",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="输出目录 (默认 ../data_zj0825/zhujiang 相对 backend/)",
    )
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parent.parent
    default_src = Path("/data/wlx/DATABASE/extracted_tables/zhujiang/ihc.parquet")
    src = Path(args.src).resolve() if args.src else default_src.resolve()
    out_dir = Path(args.out_dir).resolve() if args.out_dir else (backend_dir.parent / "data_zj0825" / "zhujiang").resolve()

    if not src.exists():
        print(f"[ERR] 源文件不存在: {src}", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / "ihc_result.parquet"

    con = duckdb.connect(":memory:")
    src_posix = src.as_posix()
    dst_posix = dst.as_posix()
    non_null_expr = " + ".join(f"({c} IS NOT NULL)::INT" for c in STRUCT_COLS)

    # 前置一致性检查: 重复 exam_id 组内, 除 raw_text 外各列 distinct 数是否
    # 均为 1 (COUNT(DISTINCT) 忽略 NULL, 组内某列只要有一个非 NULL 值即算一致)。
    # 按主线 2026-08-25 定: 冲突组不阻塞, 按"非空数降序、平手取文件顺序首行"
    # 取舍, 并打印各行明细备查。
    conflicts = con.execute(
        f"""
        SELECT exam_id
        FROM read_parquet('{src_posix}')
        GROUP BY 1
        HAVING COUNT(*) > 1
           AND (COUNT(DISTINCT ki67_pct) > 1 OR COUNT(DISTINCT pdl1_tps_pct) > 1
             OR COUNT(DISTINCT pdl1_clone) > 1 OR COUNT(DISTINCT pdl1_cps) > 1
             OR COUNT(DISTINCT alk_ihc) > 1 OR COUNT(DISTINCT ttf1) > 1
             OR COUNT(DISTINCT napsina) > 1 OR COUNT(DISTINCT p40) > 1
             OR COUNT(DISTINCT p53) > 1)
        """
    ).fetchall()
    print(f"[CHECK] 重复 exam_id 组内结构化字段冲突数: {len(conflicts)}")
    if conflicts:
        for (eid,) in conflicts:
            rows = con.execute(
                f"""
                SELECT {non_null_expr} AS non_null_count,
                       ki67_pct, pdl1_tps_pct, pdl1_clone, pdl1_cps,
                       alk_ihc, ttf1, napsina, p40, p53, src_rn
                FROM (
                    SELECT *, ROW_NUMBER() OVER () AS src_rn
                    FROM read_parquet('{src_posix}')
                )
                WHERE exam_id = ?
                ORDER BY src_rn
                """,
                [eid],
            ).fetchall()
            print(
                f"       冲突 exam_id={eid} 明细 "
                f"(non_null_count, ki67, tps, clone, cps, alk, ttf1, napsina, p40, p53, 文件行号):"
            )
            for r in rows:
                print(f"         {r}")
            print("         取舍: 取非空数最高行, 平手取文件顺序首行")

    sql = f"""
        COPY (
            SELECT
                patient_id,
                exam_id                  AS specimen_id,
                CAST(exam_date AS DATE)  AS exam_date,
                ki67_pct,
                pdl1_tps_pct,
                pdl1_clone,
                pdl1_cps,
                alk_ihc,
                ttf1,
                napsina,
                p40,
                p53,
                raw_text
            FROM (
                SELECT *,
                       ROW_NUMBER() OVER (
                           PARTITION BY exam_id
                           ORDER BY {non_null_expr} DESC, src_rn ASC
                       ) AS pick_rn
                FROM (
                    SELECT *, ROW_NUMBER() OVER () AS src_rn
                    FROM read_parquet('{src_posix}')
                )
            )
            WHERE pick_rn = 1
        ) TO '{dst_posix}' (FORMAT PARQUET, OVERWRITE_OR_IGNORE)
    """
    con.execute(sql)

    n = con.execute("SELECT COUNT(*) FROM read_parquet(?)", [dst.as_posix()]).fetchone()[0]
    n_dup = con.execute(
        "SELECT COUNT(*) - COUNT(DISTINCT specimen_id) FROM read_parquet(?)", [dst.as_posix()]
    ).fetchone()[0]
    n_ki67 = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE ki67_pct IS NOT NULL", [dst.as_posix()]
    ).fetchone()[0]
    n_pdl1 = con.execute(
        "SELECT COUNT(*) FROM read_parquet(?) WHERE pdl1_tps_pct IS NOT NULL OR pdl1_clone IS NOT NULL OR pdl1_cps IS NOT NULL",
        [dst.as_posix()],
    ).fetchone()[0]
    # 冲突 exam 取舍结果回显, 备查
    if conflicts:
        for (eid,) in conflicts:
            r = con.execute(
                "SELECT ki67_pct, pdl1_tps_pct FROM read_parquet(?) WHERE specimen_id = ?",
                [dst.as_posix(), eid],
            ).fetchone()
            print(f"       落库 exam_id={eid}: ki67_pct={r[0]}, pdl1_tps_pct={r[1]}")
    print(
        f"[OK] {dst} 已生成\n"
        f"     总行数: {n}\n"
        f"     重复 specimen_id: {n_dup}\n"
        f"     ki67_pct 非空: {n_ki67}\n"
        f"     pdl1 任一非空: {n_pdl1}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
