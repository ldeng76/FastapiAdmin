-- =====================================================================
-- 0021 - med_modality 字典 seed
-- 依据: docs/all_modalities.json（26 项全院模态定义）
-- 目标: PostgreSQL 14+, schema = lnrs（med_* / sys_* 表所在 schema）
-- 内容（幂等 ON CONFLICT DO NOTHING，可重复执行）:
--   1. INSERT sys_dict_type: 新增字典类型 med_modality
--   2. INSERT sys_dict_data: 从 docs/all_modalities.json 灌入 26 项
-- 说明:
--   - med_modality 与 med_exam_type 并存（dict_value 取自 JSON 原值，
--     snake_case + 少量 PascalCase，与 med_exam_type 的 PascalCase 故意不同，
--     避免跨字典语义重叠；上层业务按 dict_type 选 namespace）。
--   - dict_sort 按 JSON 原始顺序 1..26。
--   - is_default 仅 CT=true（沿用 med_exam_type 惯例）。
--   - description 模板 '医疗-全院模态 - {label}'。
-- =====================================================================

BEGIN;

SET LOCAL search_path = lnrs;

-- --------------------------------------------------------------------- #
-- 1. 新增 sys_dict_type: med_modality
--    uuid 固定值保证幂等；ON CONFLICT DO NOTHING 保证重放不报错。
-- --------------------------------------------------------------------- #
INSERT INTO lnrs.sys_dict_type (
    dict_name, dict_type, status, description,
    created_time, updated_time, is_deleted, tenant_id, uuid
) VALUES (
    '医疗-全院模态',
    'med_modality',
    '0',
    '全院模态字典（docs/all_modalities.json 26 项；与 med_exam_type 并存）',
    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, false,
    1,
    'a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d'
)
ON CONFLICT (tenant_id, dict_type) DO NOTHING;

-- --------------------------------------------------------------------- #
-- 2. 灌入 sys_dict_data: docs/all_modalities.json 26 项
--    dict_value = JSON key（snake_case + PascalCase），与 JSON 字面一致；
--    dict_label = JSON value（中文 label）；
--    dict_sort = 按 VALUES 元组顺序 1..26；
--    is_default 仅 CT=true；
--    uuid 由 DB 通过 gen_random_uuid() 生成（pgcrypto 已可用）；
--    css_class / list_class 设为 NULL（与 med_exam_type 既有行一致）；
--    description = '医疗-全院模态 - {label}'。
-- --------------------------------------------------------------------- #
INSERT INTO lnrs.sys_dict_data (
    dict_sort, dict_label, dict_value, is_default,
    dict_type, dict_type_id, uuid, status, description,
    created_time, updated_time, is_deleted, tenant_id,
    css_class, list_class
)
SELECT
    (row_number() OVER ())::int                AS dict_sort,
    v.label                                    AS dict_label,
    v.key                                      AS dict_value,
    CASE WHEN v.key = 'CT' THEN true ELSE false END AS is_default,
    'med_modality'                             AS dict_type,
    (SELECT id FROM lnrs.sys_dict_type WHERE dict_type='med_modality' AND tenant_id=1) AS dict_type_id,
    gen_random_uuid()::varchar(64)             AS uuid,
    '0'                                        AS status,
    '医疗-全院模态 - ' || v.label              AS description,
    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, false, 1,
    NULL, NULL
FROM (
    VALUES
    ('CT','CT'),
    ('pathology_WSI','病理WSI'),
    ('pathology_text','病理报告'),
    ('gene','基因'),
    ('medical_record','病案首页'),
    ('imaging_report','影像学报告'),
    ('basic_medical_info','就诊基本信息'),
    ('diagnosis','诊断'),
    ('drug_prescription','药物处方'),
    ('medical_orders','医嘱'),
    ('medical_testing','检验'),
    ('radiology','放射'),
    ('ultrasound','超声'),
    ('pulmonary_function','肺功能'),
    ('MRI','磁共振'),
    ('nuclear_medicine','核医学'),
    ('bronchoscope','气管镜'),
    ('ECG','心电图'),
    ('case_history','病历'),
    ('progress_note','病程记录'),
    ('basic_info','基本信息'),
    ('inhospital_record','住院记录'),
    ('IHC_record','免疫组化'),
    ('operation','手术信息'),
    ('anesthesia','麻醉信息'),
    ('nursing','护理记录')
) AS v(key, label)
ON CONFLICT (tenant_id, dict_type, dict_value) DO NOTHING;

COMMIT;