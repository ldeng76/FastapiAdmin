-- =====================================================================
-- 迁移: lnrs_anon_patient.birth_year (smallint) → birth_date (date)
-- 依据: ADR-0006 精度优先原则，年份补齐为 YYYY-01-01
-- 日期: 2026-07-23
-- 目标: PostgreSQL 14+, schema = lnrs
--
-- 幂等: 可重复执行（已迁移过的库不会报错）
-- =====================================================================

BEGIN;

-- 1. 仅当 birth_year 列存在时才执行迁移
DO $$
DECLARE
    col_type TEXT;
BEGIN
    SELECT data_type INTO col_type
    FROM information_schema.columns
    WHERE table_schema = 'lnrs'
      AND table_name = 'lnrs_anon_patient'
      AND column_name = 'birth_year';

    IF col_type IS NULL THEN
        RAISE NOTICE 'birth_year 列不存在，可能已迁移为 birth_date，跳过';
        RETURN;
    END IF;

    IF col_type <> 'smallint' THEN
        RAISE NOTICE 'birth_year 类型不是 smallint（实际: %），跳过', col_type;
        RETURN;
    END IF;

    -- 删除旧 CHECK 约束（如果存在）
    ALTER TABLE lnrs.lnrs_anon_patient
    DROP CONSTRAINT IF EXISTS lnrs_anon_patient_birth_year_check;

    -- 列重命名
    ALTER TABLE lnrs.lnrs_anon_patient
    RENAME COLUMN birth_year TO birth_date;

    -- 类型转换: smallint → date（年份 → YYYY-01-01）
    ALTER TABLE lnrs.lnrs_anon_patient
    ALTER COLUMN birth_date TYPE DATE
    USING make_date(birth_date::int, 1, 1);

    RAISE NOTICE '列已迁移: birth_year (smallint) → birth_date (date)';
END $$;

-- 2. 添加新 CHECK 约束（幂等）
ALTER TABLE lnrs.lnrs_anon_patient
DROP CONSTRAINT IF EXISTS lnrs_anon_ck_patient_birth;

ALTER TABLE lnrs.lnrs_anon_patient
ADD CONSTRAINT lnrs_anon_ck_patient_birth
CHECK (birth_date >= '1900-01-01' AND birth_date <= '2100-12-31');

-- 3. 重建索引（自动更新列引用）
REINDEX INDEX lnrs.lnrs_anon_ix_patient_birth;

COMMIT;

-- 4. 验证（事务外，仅输出信息）
DO $$
DECLARE
    col_name TEXT;
    col_type TEXT;
    row_count BIGINT;
    null_count BIGINT;
BEGIN
    SELECT column_name, data_type
    INTO col_name, col_type
    FROM information_schema.columns
    WHERE table_schema = 'lnrs'
      AND table_name = 'lnrs_anon_patient'
      AND column_name = 'birth_date';

    SELECT count(*), count(*) FILTER (WHERE birth_date IS NULL)
    INTO row_count, null_count
    FROM lnrs.lnrs_anon_patient;

    RAISE NOTICE '验证结果: birth_date % (类型: %)', col_name, col_type;
    RAISE NOTICE '总行数: %, birth_date 非空: %', row_count, row_count - null_count;
END $$;
