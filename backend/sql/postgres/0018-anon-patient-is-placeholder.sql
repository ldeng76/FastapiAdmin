-- =====================================================================
-- 迁移: lnrs_anon_patient 增加 is_placeholder 占位标记列
-- 依据: 2026-09-07 患者列表「未知的性别」根因修复
--       ETL2 导入 exam/visit/surgery 表时为无档案患者自动发号的占位记录
--       （sex 恒 '0'、无人口学）在患者列表占 59.4%
--       （dev 实测 137,490 / 231,352）；本列供列表默认过滤 + 行内标记。
-- 日期: 2026-09-07
-- 目标: PostgreSQL 14+, schema = lnrs
--
-- 幂等: 可重复执行（列已存在时跳过）
--
-- 回填规则: sex='0' 且所有人口学字段均为空 → 占位。
--   patient_meta 需同时覆盖 SQL NULL / jsonb 'null'（0825 批次写入痕迹）/ '{}'。
--   已知边界: shengyi PT_00282376（真实档案、有 birth_date、源数据性别缺失）
--   有 birth_date 故不会被误标。
-- =====================================================================
-- =====================================================================
-- ⚠ 归档注记（ADR 0012，2026-09-20）：下方「回填规则」（sex='0' 且人口学
-- 全 NULL ⇒ 占位）的身份型语义已被数据型语义取代（无业务数据才为占位），
-- 本回填 UPDATE **废弃、禁止复跑**。存量修正见
-- backend/etl2/backfill_placeholder_data_semantics.py。列本身保留。
-- =====================================================================

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'lnrs'
          AND table_name = 'lnrs_anon_patient'
          AND column_name = 'is_placeholder'
    ) THEN
        RAISE NOTICE 'is_placeholder 列已存在，跳过';
        RETURN;
    END IF;

    -- 1. 加列（server_default 兜底引擎之外的手工 INSERT）
    ALTER TABLE lnrs.lnrs_anon_patient
    ADD COLUMN is_placeholder BOOLEAN NOT NULL DEFAULT FALSE;

    COMMENT ON COLUMN lnrs.lnrs_anon_patient.is_placeholder IS
        '占位患者标记：exam/visit/surgery 导入自动发号、无人口学';

    -- 2. 回填：无任何人口学字段的 sex='0' 行标记为占位
    UPDATE lnrs.lnrs_anon_patient
    SET is_placeholder = TRUE
    WHERE sex = '0'
      AND birth_date IS NULL
      AND ethnicity IS NULL
      AND smoking_status IS NULL
      AND abo_blood_type IS NULL
      AND rh_blood_type IS NULL
      AND native_place IS NULL
      AND first_nodule_date IS NULL
      AND bmi IS NULL
      AND (
            patient_meta IS NULL
            OR patient_meta = 'null'::jsonb
            OR patient_meta = '{}'::jsonb
      );

    RAISE NOTICE 'is_placeholder 列已创建并回填';
END $$;

COMMIT;

-- 3. 验证（事务外，仅输出信息）
DO $$
DECLARE
    ph_count BIGINT;
    total BIGINT;
BEGIN
    SELECT count(*) FILTER (WHERE is_placeholder), count(*)
    INTO ph_count, total
    FROM lnrs.lnrs_anon_patient;

    RAISE NOTICE '验证结果: 占位患者 % / 总患者 %', ph_count, total;
END $$;
