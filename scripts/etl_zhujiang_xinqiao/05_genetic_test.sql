-- 05_genetic_test.sql
-- 珠江-新桥 genetic_test 表 (unified, Zhujiang side)
-- Source: 精准医学V2_副本.xls (经 libreoffice 预转 xlsx)
-- 此源文件是叙述性报告模板,非结构化表格,无法拆出 patient_id/test_id
-- → schema-only fallback: 0 行,但保留完整 schema
INSTALL spatial; LOAD spatial;

COPY (
  SELECT
    CAST(NULL AS VARCHAR)                                    AS patient_id,
    CAST(NULL AS VARCHAR)                                    AS visit_id,
    CAST(NULL AS VARCHAR)                                    AS test_id,
    CAST(NULL AS DATE)                                       AS test_date,
    CAST(NULL AS VARCHAR)                                    AS variant_type,
    CAST(NULL AS VARCHAR)                                    AS test_method,
    CAST(NULL AS JSON)                                       AS test_meta,
    CAST(NULL AS JSON)                                       AS driver_mutations,
    CAST(NULL AS JSON)                                       AS immune_markers
  WHERE 1=0
) TO '/data/wlx/DATABASE/0605_small/01disk/zhujiang_xinqiao_parquet/genetic_test.parquet'
  (FORMAT PARQUET);
