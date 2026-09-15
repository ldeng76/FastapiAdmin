-- =====================================================================
-- 迁移: lnrs_anon_v_imaging_study_counts 视图
-- 依据: 2026-09-15 序列数（series_count）落库与展示方案
--       ETL-2 增量阶段解析 lnrs_anon_imaging_study.image_path 目录，
--       把 series 明细 upsert 到 lnrs_anon_dicom_series。
--       前端「患者详情 → 影像列表」需在 study 维度聚合 series_count /
--       instance_count / total_bytes 展示。
-- 日期: 2026-09-15
-- 目标: PostgreSQL 14+, schema = lnrs
--
-- 设计要点：
--   * LEFT JOIN imaging_study → dicom_series：无 series 时 count=0
--     （前端 UI 显示「序列数 0」而不是 NULL）
--   * 聚合键：dicom_study_uid（有 lnrs_anon_ix_imaging_study_uid 索引
--     + lnrs_anon_ix_series_study_uid 双索引，单 patient 路径 ≤ 几十行）
--   * 幂等：CREATE OR REPLACE VIEW
--   * 与既有 lnrs_anon_v_imaging_study / lnrs_anon_v_exam_full 正交：
--     - v_imaging_study：按 study 维度补 study_date / study_description 派生
--     - v_imaging_study_counts：本视图，按 study 维度补 series_count 等聚合
--     - v_exam_full：按 exam 维度汇总
--   * 不动 lnrs_anon_v_imaging_study 与 lnrs_anon_v_exam_full
--
-- 性能：
--   * 单 patient 路径走 lnrs_anon_ix_imaging_patient；本视图再加一次
--     dicom_series 聚合，单 patient 命中 ≤ 几十行，毫秒级。
--
-- 已知缺口：
--   * dicom_series.byte_size 在 ETL-2 改造前为 NULL（DDL 列允许 NULL）；
--     本视图 total_bytes 用 COALESCE(SUM, 0) 兜底，series 未落库时为 0。
--
-- 幂等: CREATE OR REPLACE VIEW 多次执行结果一致
--
-- 回退: DROP VIEW lnrs.lnrs_anon_v_imaging_study_counts
-- =====================================================================

BEGIN;

SET LOCAL search_path = lnrs, public;

-- ---------- 视图: study 维度 series 聚合 ----------

CREATE OR REPLACE VIEW lnrs.lnrs_anon_v_imaging_study_counts AS
SELECT
    ims.study_key,
    ims.dicom_study_uid,
    ims.center_code,
    ims.patient_id,
    ims.anon_exam_id,
    COUNT(s.series_id)::INT                  AS series_count,
    COALESCE(SUM(s.instance_count), 0)::BIGINT AS instance_count,
    COALESCE(SUM(s.byte_size), 0)::BIGINT      AS total_bytes
FROM lnrs.lnrs_anon_imaging_study ims
LEFT JOIN lnrs.lnrs_anon_dicom_series s
       ON s.dicom_study_uid = ims.dicom_study_uid
GROUP BY ims.study_key, ims.dicom_study_uid, ims.center_code,
         ims.patient_id, ims.anon_exam_id;

COMMENT ON VIEW lnrs.lnrs_anon_v_imaging_study_counts IS
    'study 维度 series 聚合（series_count / instance_count / total_bytes）；
     LEFT JOIN 让 series 未落库的 study 也返回 0；与 v_imaging_study 正交。
     引入：2026-09-15 ETL-2 dicom_series 增量阶段';

COMMIT;

-- 验证（事务外，仅输出信息）
DO $$
DECLARE
    total_rows BIGINT;
    with_series BIGINT;
    zero_series BIGINT;
BEGIN
    SELECT count(*),
           count(*) FILTER (WHERE series_count > 0),
           count(*) FILTER (WHERE series_count = 0)
    INTO total_rows, with_series, zero_series
    FROM lnrs.lnrs_anon_v_imaging_study_counts;

    RAISE NOTICE '视图验证: 总 study 行 % / 有 series % / series=0 %',
        total_rows, with_series, zero_series;
END $$;