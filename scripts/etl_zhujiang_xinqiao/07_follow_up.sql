-- 07_follow_up.sql
-- 珠江-新桥 follow_up 表 (Zhujiang-Xinqiao 独有)
-- 无源数据 → schema-only fallback: 0 行
INSTALL spatial; LOAD spatial;

COPY (
  SELECT
    CAST(NULL AS VARCHAR)                                    AS patient_id,
    CAST(NULL AS DATE)                                       AS last_followup_date,
    CAST(NULL AS VARCHAR)                                    AS recurrence,
    CAST(NULL AS VARCHAR)                                    AS survival_status,
    CAST(NULL AS JSON)                                       AS treatment_detail,
    CAST(NULL AS JSON)                                       AS recurrence_detail
  WHERE 1=0
) TO '/data/wlx/DATABASE/0605_small/01disk/zhujiang_xinqiao_parquet/follow_up.parquet'
  (FORMAT PARQUET);
