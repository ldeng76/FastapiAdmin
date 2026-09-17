-- =====================================================================
-- 0023 - exam_type 值域对齐 all_modalities.json 26 键（+Other = 27 值）
-- 目标: PostgreSQL 14+, schema = lnrs（sys_* / med_* 表所在 schema）
-- 依据: docs/all_modalities.json（平台 modality 权威定义，26 键）
-- 对应 alembic 归档: app/alembic/versions/k1l2m3n4o5p6_exam_type_modalities.py
-- 配套: 0022-add-exam-type-check-manual.sql（CHECK 约束，需 postgres 属主执行）
--
-- 旧值 → 新值改名映射（7 项）:
--   Pathology→pathology_text  Genetic→gene      IHC→IHC_record
--   MR→MRI  Radiology→radiology  Ultrasound→ultrasound  PETCT→nuclear_medicine
--   （CT / ECG / Other 不变）
--
-- 内容（幂等，可重复执行；单事务，末尾守卫越界值）:
--   1. UPDATE lnrs_anon_exam.exam_type 存量改名（7 项全写上，无存量的项 0 行）
--   2. UPDATE sys_dict_data med_exam_type 7 项原地改名 + label 对齐 26 键中文名
--      （原地改名 → med_dict_mapping.dict_data_id 外键自动跟随，
--       zhujiang/shengyi 的 raw_label→dict_value 映射无需更新）
--   3. INSERT sys_dict_data med_exam_type 补齐其余 17 键（sort 400-416）
--   4. UPDATE med_dict_mapping（hos301 examClass，hospital_id=12）6 项
--      dict_data_id 重指向新字典行：
--      心电图→ECG 放射→radiology 磁共振→MRI 核医学→nuclear_medicine
--      肺功能→pulmonary_function 气管镜→bronchoscope
--      （胃肠镜/耳鼻喉/其他/体检/泌外维持 Other）
--   5. 守卫: exam_type 出现 27 值之外的行则 RAISE 回滚整个事务
--
-- 说明:
--   - Lab/Order 两个历史字典项不属于 26 键，保留不动（CHECK 只约束
--     lnrs_anon_exam.exam_type 列，不受字典内容影响）。
--   - CHECK 约束不在本文件：lnrs_anon_exam 属主为 postgres，见 0022。
-- =====================================================================

BEGIN;

SET LOCAL search_path = lnrs;

-- --------------------------------------------------------------------- #
-- 1. 存量改名（每条幂等；无存量的项 0 行跳过）
-- --------------------------------------------------------------------- #
UPDATE lnrs_anon_exam SET exam_type = 'pathology_text'
WHERE exam_type = 'Pathology';

UPDATE lnrs_anon_exam SET exam_type = 'gene'
WHERE exam_type = 'Genetic';

UPDATE lnrs_anon_exam SET exam_type = 'IHC_record'
WHERE exam_type = 'IHC';

UPDATE lnrs_anon_exam SET exam_type = 'MRI'
WHERE exam_type = 'MR';

UPDATE lnrs_anon_exam SET exam_type = 'radiology'
WHERE exam_type = 'Radiology';

UPDATE lnrs_anon_exam SET exam_type = 'ultrasound'
WHERE exam_type = 'Ultrasound';

UPDATE lnrs_anon_exam SET exam_type = 'nuclear_medicine'
WHERE exam_type = 'PETCT';

-- --------------------------------------------------------------------- #
-- 2. sys_dict_data med_exam_type 原地改名 + label 对齐
--    （dict_sort 保留原值；CT/ECG/Other/Lab/Order 不动）
-- --------------------------------------------------------------------- #
UPDATE sys_dict_data
SET dict_label = '病理报告', dict_value = 'pathology_text', updated_time = NOW()
WHERE dict_type = 'med_exam_type' AND dict_value = 'Pathology';

UPDATE sys_dict_data
SET dict_label = '基因', dict_value = 'gene', updated_time = NOW()
WHERE dict_type = 'med_exam_type' AND dict_value = 'Genetic';

UPDATE sys_dict_data
SET dict_label = '免疫组化', dict_value = 'IHC_record', updated_time = NOW()
WHERE dict_type = 'med_exam_type' AND dict_value = 'IHC';

UPDATE sys_dict_data
SET dict_label = '磁共振', dict_value = 'MRI', updated_time = NOW()
WHERE dict_type = 'med_exam_type' AND dict_value = 'MR';

UPDATE sys_dict_data
SET dict_label = '放射', dict_value = 'radiology', updated_time = NOW()
WHERE dict_type = 'med_exam_type' AND dict_value = 'Radiology';

UPDATE sys_dict_data
SET dict_label = '超声', dict_value = 'ultrasound', updated_time = NOW()
WHERE dict_type = 'med_exam_type' AND dict_value = 'Ultrasound';

UPDATE sys_dict_data
SET dict_label = '核医学', dict_value = 'nuclear_medicine', updated_time = NOW()
WHERE dict_type = 'med_exam_type' AND dict_value = 'PETCT';

-- --------------------------------------------------------------------- #
-- 3. 补齐其余 17 键（26 键 - 已有 CT/pathology_text/gene/IHC_record/MRI/
--    radiology/ultrasound/nuclear_medicine/ECG）
-- --------------------------------------------------------------------- #
INSERT INTO sys_dict_data (uuid, dict_sort, dict_label, dict_value, dict_type, dict_type_id, is_default, description, tenant_id, status, created_time, updated_time, is_deleted)
SELECT
    gen_random_uuid(), s.sort, s.label, s.val, 'med_exam_type',
    (SELECT id FROM sys_dict_type WHERE dict_type = 'med_exam_type'),
    FALSE,
    '医疗检查类型-' || s.label || '（all_modalities.json 26 键，0023 补齐）',
    1, '0', NOW(), NOW(), FALSE
FROM (VALUES
    (400, '病理WSI',    'pathology_WSI'),
    (401, '病案首页',   'medical_record'),
    (402, '影像学报告', 'imaging_report'),
    (403, '就诊基本信息', 'basic_medical_info'),
    (404, '诊断',       'diagnosis'),
    (405, '药物处方',   'drug_prescription'),
    (406, '医嘱',       'medical_orders'),
    (407, '检验',       'medical_testing'),
    (408, '肺功能',     'pulmonary_function'),
    (409, '气管镜',     'bronchoscope'),
    (410, '病历',       'case_history'),
    (411, '病程记录',   'progress_note'),
    (412, '基本信息',   'basic_info'),
    (413, '住院记录',   'inhospital_record'),
    (414, '手术信息',   'operation'),
    (415, '麻醉信息',   'anesthesia'),
    (416, '护理记录',   'nursing')
) AS s(sort, label, val)
WHERE NOT EXISTS (
    SELECT 1 FROM sys_dict_data sd
    WHERE sd.dict_type = 'med_exam_type' AND sd.dict_value = s.val
);

-- --------------------------------------------------------------------- #
-- 4. hos301 examClass 映射升级（hospital_id=12 的 med_dict_mapping
--    dict_data_id 重指向新字典行；原指向 Other 的行保持不变）
-- --------------------------------------------------------------------- #
UPDATE med_dict_mapping m
SET dict_data_id = dst.id, updated_time = NOW()
FROM sys_dict_type dt, sys_dict_data src, sys_dict_data dst
WHERE dt.dict_type = 'med_exam_type'
  AND m.dict_type_id = dt.id
  AND m.hospital_id = (SELECT id FROM med_hospital WHERE code = 'hos301')
  AND src.id = m.dict_data_id
  AND (m.raw_label, src.dict_value, dst.dict_value) IN (
    ('心电图',   'Other', 'ECG'),
    ('放射',     'Other', 'radiology'),
    ('磁共振',   'Other', 'MRI'),
    ('核医学',   'Other', 'nuclear_medicine'),
    ('肺功能',   'Other', 'pulmonary_function'),
    ('气管镜',   'Other', 'bronchoscope')
  );

-- --------------------------------------------------------------------- #
-- 5. 守卫: 出现 27 值之外的 exam_type 则回滚整个事务
-- --------------------------------------------------------------------- #
DO $$
DECLARE
    bad_count bigint;
BEGIN
    SELECT count(*) INTO bad_count FROM lnrs_anon_exam
    WHERE exam_type IS NOT NULL
      AND exam_type NOT IN (
        'CT', 'pathology_WSI', 'pathology_text', 'gene', 'medical_record',
        'imaging_report', 'basic_medical_info', 'diagnosis', 'drug_prescription',
        'medical_orders', 'medical_testing', 'radiology', 'ultrasound',
        'pulmonary_function', 'MRI', 'nuclear_medicine', 'bronchoscope', 'ECG',
        'case_history', 'progress_note', 'basic_info', 'inhospital_record',
        'IHC_record', 'operation', 'anesthesia', 'nursing', 'Other'
      );
    IF bad_count > 0 THEN
        RAISE EXCEPTION '0023: % 行 exam_type 越界，回滚', bad_count;
    END IF;
    RAISE NOTICE '0023 OK: exam_type 值域对齐完成，无越界值';
END $$;

COMMIT;
