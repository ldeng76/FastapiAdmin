-- 06_ihc_result.sql
-- 珠江-新桥 ihc_result 表 (Zhujiang-Xinqiao 独有)
-- Source: 5万例时序影像_带病理_新_1.csv 病理.病理所见-镜下所见
-- Ki-67/PD-L1/TTF-1 等标记在源里都是 free-text,无法直接抽取结构化字段
-- → fallback: 0 行,但保留 schema;原始 free-text 计划下游 NLP 步骤处理
--   (为下游预留接口,在 manifest 中说明)
INSTALL spatial; LOAD spatial;

COPY (
  SELECT
    CAST(NULL AS VARCHAR)                                    AS patient_id,
    CAST(NULL AS VARCHAR)                                    AS specimen_id,
    CAST(NULL AS DOUBLE)                                     AS ki67_pct,
    CAST(NULL AS JSON)                                       AS markers
  WHERE 1=0
) TO '/data/wlx/DATABASE/0605_small/01disk/zhujiang_xinqiao_parquet/ihc_result.parquet'
  (FORMAT PARQUET);
