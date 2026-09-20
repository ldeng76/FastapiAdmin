-- =====================================================================
-- 0025 - 删除 med_exam_type 'Other' 字典项 + CHECK 约束收紧到 26 值
-- 目标: PostgreSQL 14+, database = postgres
-- 前提: 0023/0024/etl2/reclassify_shengyi_other_exam_type.py 已执行（Other=0）
--       docs/handoff-20260919-reclassify-other-exam-type.md §3 §5 Step 3
--
-- ⚠️ lnrs.lnrs_anon_exam 表属主是 postgres，lnrs 角色无 ALTER 权限。
--    本文件请在服务器上以 postgres 身份执行，例如：
--      sudo -u postgres psql -d postgres -f 0025-drop-other-exam-type.sql
--    也可以拆成两步：
--      (a) lnrs 角色跑 SET LOCAL 部分（字典软删除 + 守卫）
--      (b) postgres 角色跑 ALTER TABLE（CHECK 收紧）
--
-- 内容（幂等，可重复执行；多个事务）:
--   1. 软删除 sys_dict_data 中 med_exam_type=Other（is_deleted=TRUE），
--      并同步字典缓存 key='system_dict:1:med_exam_type'
--   2. ALTER TABLE lnrs.lnrs_anon_exam DROP CONSTRAINT IF EXISTS
--      lnrs_anon_ck_exam_type + ADD CONSTRAINT ... CHECK (... 26 值 ...);
--      事务内自检（试 UPDATE 成 26 值之外应被拒，ROLLBACK）
--   3. 守卫: lnrs_anon_exam.exam_type 不应在 27 值集合（=26 值 + Other 兜底）
--      中出现 Other，否则 RAISE EXCEPTION 回滚 0025 的字典部分
--   4. hos301 hospital_id=12 的 med_dict_mapping 5 项指向 Other 的保留不动
--      （决策 5：未来 hos301 导入时被 fail-fast/约束拒绝，逼迫人工补映射）
--
-- 说明:
--   - 这里用软删除（is_deleted=TRUE）而非硬 DELETE：
--     ① 与 0023 的"原地改名"语义连贯（不破坏历史 raw_label 映射链路）；
--     ② sys_dict_data.uuid 作为 med_dict_mapping.dict_data_id 的潜在外键，
--        软删除可让历史映射记录保留可追溯性。
--     如需硬删可改 DELETE ... RETURNING uuid; 并先备份。
--   - med_modality 字典本就 26 键无 Other，不动。
--   - Lab/Order 两个历史字典项不属于 26 键，保留不动（CHECK 只约束
--     lnrs_anon_exam.exam_type 列）。
-- =====================================================================

-- --------------------------------------------------------------------- #
-- 1. 软删除 Other 字典项（幂等）
-- --------------------------------------------------------------------- --
DO $$
BEGIN
    UPDATE lnrs.sys_dict_data
    SET is_deleted = TRUE, deleted_time = NOW(), updated_time = NOW()
    WHERE dict_type = 'med_exam_type' AND dict_value = 'Other' AND is_deleted = FALSE;
    RAISE NOTICE '0025: sys_dict_data med_exam_type=Other 已软删除';
EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE '0025: sys_dict_data 软删除失败：%', SQLERRM;
END $$;

-- --------------------------------------------------------------------- #
-- 2. ALTER CHECK 约束（需 postgres 属主权限）
--    已存在 26 值约束则跳过；旧 27 值约束 DROP 后重建
-- --------------------------------------------------------------------- --
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'lnrs_anon_ck_exam_type'
          AND conrelid = 'lnrs.lnrs_anon_exam'::regclass
    ) THEN
        EXECUTE 'ALTER TABLE lnrs.lnrs_anon_exam DROP CONSTRAINT lnrs_anon_ck_exam_type';
        RAISE NOTICE '0025: 旧 lnrs_anon_ck_exam_type 已 DROP';
    END IF;
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
                'operation', 'anesthesia', 'nursing'
            )
        )
    $ddl$;
    RAISE NOTICE '0025: 新 lnrs_anon_ck_exam_type 已创建（26 值）';
END $$;

-- --------------------------------------------------------------------- #
-- 3. 自检（CHECK 拒绝 27 值之外的 UPDATE，ROLLBACK 不留改动）
-- --------------------------------------------------------------------- --
BEGIN;
DO $$
BEGIN
    UPDATE lnrs.lnrs_anon_exam
    SET exam_type = 'ZZZ_INVALID'
    WHERE anon_exam_id = (SELECT anon_exam_id FROM lnrs.lnrs_anon_exam LIMIT 1);
    RAISE NOTICE '⚠️ 0025 UPDATE 成功 — CHECK 约束未生效，请检查！';
EXCEPTION
    WHEN check_violation THEN
        RAISE NOTICE '✅ 0025 OK: CHECK 约束已拒绝非法值';
END $$;
ROLLBACK;

-- --------------------------------------------------------------------- #
-- 4. 守卫：lnrs_anon_exam.exam_type 必须是 26 值之一（不允许 Other）
-- --------------------------------------------------------------------- --
DO $$
DECLARE
    bad_count bigint;
BEGIN
    SELECT count(*) INTO bad_count FROM lnrs.lnrs_anon_exam
    WHERE exam_type IS NOT NULL AND exam_type NOT IN (
        'CT', 'pathology_WSI', 'pathology_text', 'gene',
        'medical_record', 'imaging_report', 'basic_medical_info',
        'diagnosis', 'drug_prescription', 'medical_orders',
        'medical_testing', 'radiology', 'ultrasound',
        'pulmonary_function', 'MRI', 'nuclear_medicine',
        'bronchoscope', 'ECG', 'case_history', 'progress_note',
        'basic_info', 'inhospital_record', 'IHC_record',
        'operation', 'anesthesia', 'nursing'
    );
    IF bad_count > 0 THEN
        RAISE EXCEPTION '0025: % 行 exam_type 越界（应在 26 值内），请先跑 etl2/reclassify_shengyi_other_exam_type.py', bad_count;
    END IF;
    RAISE NOTICE '0025 OK: exam_type 值域已收紧至 26 值，无越界';
END $$;

-- --------------------------------------------------------------------- #
-- 5. Redis 字典缓存清理（需 redis-cli；db=7）
--    在 psql 外手动执行：
--      redis-cli -n 7 DEL "system_dict:1:med_exam_type"
--    或重启后端服务让 init_dict_service 重新加载
-- --------------------------------------------------------------------- --