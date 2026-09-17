-- =====================================================================
-- 0022 - lnrs_anon_exam.exam_type CHECK 约束（手动执行，需表属主权限）
-- 目标: PostgreSQL 14+, database = postgres
-- 前提: 0023-exam-type-modalities-dict.sql 已执行（数据已对齐 27 值）
--
-- ⚠️ lnrs_anon_exam 属主是 postgres，lnrs 角色无 ALTER 权限，
--    本文件请在服务器上以 postgres 身份执行，例如：
--      sudo -u postgres psql -d postgres -f 0022-add-exam-type-check-manual.sql
--
-- 内容（幂等，可重复执行）:
--   1. ADD CONSTRAINT lnrs_anon_ck_exam_type CHECK（27 值 = 26 键 + Other），
--      已存在则跳过
--   2. 自检: 事务内尝试把一行 exam_type 改为非法值，期望被 CHECK 拒绝，
--      最终 ROLLBACK 不留任何改动
-- =====================================================================

-- --------------------------------------------------------------------- #
-- 1. 加 CHECK 约束（已存在则跳过）
-- --------------------------------------------------------------------- #
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'lnrs_anon_ck_exam_type'
          AND conrelid = 'lnrs.lnrs_anon_exam'::regclass
    ) THEN
        RAISE NOTICE 'lnrs_anon_ck_exam_type 已存在，跳过';
    ELSE
        EXECUTE $ddl$
            ALTER TABLE lnrs.lnrs_anon_exam
            ADD CONSTRAINT lnrs_anon_ck_exam_type CHECK (
                exam_type IS NULL OR exam_type IN (
                    'CT', 'pathology_WSI', 'pathology_text', 'gene',
                    'medical_record', 'imaging_report', 'basic_medical_info',
                    'diagnosis', 'drug_prescription', 'medical_orders',
                    'medical_testing', 'radiology', 'ultrasound',
                    'pulmonary_function', 'MRI', 'nuclear_medicine',
                    'bronchoscope', 'ECG', 'case_history', 'progress_note',
                    'basic_info', 'inhospital_record', 'IHC_record',
                    'operation', 'anesthesia', 'nursing', 'Other'
                )
            )
        $ddl$;
        RAISE NOTICE 'lnrs_anon_ck_exam_type 已创建';
    END IF;
END $$;

-- --------------------------------------------------------------------- #
-- 2. 自检（成功路径 UPDATE 会被 ROLLBACK，两种结果都不留改动）
-- --------------------------------------------------------------------- #
BEGIN;

DO $$
BEGIN
    UPDATE lnrs.lnrs_anon_exam
    SET exam_type = 'ZZZ_INVALID'
    WHERE anon_exam_id = (SELECT anon_exam_id FROM lnrs.lnrs_anon_exam LIMIT 1);
    RAISE NOTICE '⚠️ UPDATE 成功 — CHECK 约束未生效，请检查！';
EXCEPTION
    WHEN check_violation THEN
        RAISE NOTICE '✅ OK: CHECK 约束已拒绝非法值';
END $$;

ROLLBACK;
