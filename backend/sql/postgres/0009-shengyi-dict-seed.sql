-- =====================================================================
-- 0009 - 省医(shengyi)中心字典驱动 ETL 所需的前置数据
-- 依据: docs/adr/0006-anonymized-data-schema.md / ADR-0009（多中心配置驱动）
-- 目标: PostgreSQL 14+, schema = lnrs（med_* / sys_* 表所在 schema）
-- 内容（幂等 WHERE NOT EXISTS / ON CONFLICT DO NOTHING，可重复执行）:
--   1. 补 sys_dict_data: med_exam_type 缺失的 Radiology / Ultrasound / Lab / Order
--      省医数据有影像报告/超声/检验/医嘱，需新增对应 exam_type 字典值
--   2. INSERT med_hospital: 省医中心注册行（ETL _resolve_hospital_id 依赖）
--   3. INSERT med_dict_mapping: 省医中心映射规则
--      - med_sex (2): 男性/女性 → 数字码（省医实际值带"性"字，与珠江"男/女"不同）
--      - med_ethnicity (1): 汉族 → '01'（省医实际值是"汉族"，珠江是"汉"）
--      - med_exam_type (9): 全部 exam_type 自映射
-- 说明:
--   - med_center 字典里 shengyi 已由 050_med_enum_dicts.sql 注册，此处不重复
--   - med_dict_mapping.raw_label 匹配时 load_all_mappings 会 .strip().lower()
--     （dict_mapping/service.py:75），故 raw_label 用原始大小写写入即可
--   - 省医数据内无 center 列，center_code 由数据目录名 shengyi 隐式决定
-- =====================================================================

BEGIN;

-- 切换目标 schema（lnrs 用户仅有 lnrs schema UC 权限）
SET LOCAL search_path = lnrs;

-- --------------------------------------------------------------------- #
-- 1. 补 sys_dict_data: med_exam_type 缺失的 Radiology / Ultrasound / Lab / Order
--    省医数据文件: imaging_report(影像) / ultrasound_report(超声)
--                  lab_result(检验) / drug_order+no_drug_order(医嘱)
--    当前库已有 CT/PETCT/Pathology/Genetic/IHC（由 050 + 0008 提供）。
--    dict_type_id 取 med_exam_type 的 sys_dict_type.id（动态查，不硬编码）
-- --------------------------------------------------------------------- #
INSERT INTO sys_dict_data (uuid, dict_sort, dict_label, dict_value, dict_type, dict_type_id, is_default, description, tenant_id, status, created_time, updated_time, is_deleted)
SELECT
    gen_random_uuid(),
    ROW_NUMBER() OVER () + 200,  -- sort 避开已有（050:1-3 / 0008:101-102）
    CASE d.v
        WHEN 'Radiology'  THEN '影像'
        WHEN 'Ultrasound' THEN '超声'
        WHEN 'Lab'        THEN '检验'
        WHEN 'Order'      THEN '医嘱'
    END,
    d.v,
    'med_exam_type',
    (SELECT id FROM sys_dict_type WHERE dict_type = 'med_exam_type'),
    FALSE,
    '医疗检查类型-' || d.v,
    1,
    '0',
    NOW(),
    NOW(),
    FALSE
FROM (VALUES ('Radiology'), ('Ultrasound'), ('Lab'), ('Order')) AS d(v)
WHERE NOT EXISTS (
    SELECT 1 FROM sys_dict_data sd
    WHERE sd.dict_type = 'med_exam_type' AND sd.dict_value = d.v
);

-- --------------------------------------------------------------------- #
-- 2. INSERT sys_tenant + med_hospital: 省医中心注册行
--    med_hospital 有 UNIQUE(tenant_id) 约束，每 hospital 绑定独立 tenant。
--    珠江已占 tenant_id=1（系统租户），故省医需自建独立 tenant。
-- --------------------------------------------------------------------- #
-- 2a. 幂等创建省医独立 tenant（code='shengyi'）
INSERT INTO sys_tenant (
    uuid, name, code, contact_name, contact_phone, contact_email, address,
    domain, logo_url, sort, start_time, end_time, status, description,
    created_time, updated_time, is_deleted
)
SELECT
    gen_random_uuid(), '省医', 'shengyi', NULL, NULL, NULL, NULL,
    NULL, NULL, 0, NULL, NULL, '0', '省医中心租户（0009）',
    NOW(), NOW(), FALSE
WHERE NOT EXISTS (
    SELECT 1 FROM sys_tenant WHERE code = 'shengyi'
);

-- 2b. 注册 med_hospital（tenant_id 动态取省医 tenant 的 id）
INSERT INTO med_hospital (
    uuid, code, name, full_name, tenant_id, lifecycle_status,
    contact_name, contact_phone, contact_email, address,
    data_dir, last_import_time, last_import_rows, import_error,
    status, description, created_time, updated_time, is_deleted
)
SELECT
    gen_random_uuid(),
    'shengyi',
    '省医',
    '广东省人民医院',
    (SELECT id FROM sys_tenant WHERE code = 'shengyi'),  -- 省医独立 tenant_id
    'mapping_configured',       -- 映射规则已配置就绪
    NULL, NULL, NULL, NULL,
    'data/shengyi',
    NULL, 0, NULL,
    '0', '省医中心字典驱动 ETL 注册（0009）', NOW(), NOW(), FALSE
WHERE NOT EXISTS (
    SELECT 1 FROM med_hospital WHERE code = 'shengyi'
);

-- --------------------------------------------------------------------- #
-- 3. INSERT med_dict_mapping: 省医中心映射规则
--    raw_label → dict_data_id（通过 JOIN sys_dict_data 反查）
--    hospital_id 动态从 med_hospital 取（不依赖固定 id）
--    tenant_id = 1 (PLATFORM_TENANT_ID)
--    冲突处理: (hospital_id, dict_type_id, raw_label) ON CONFLICT DO NOTHING
-- --------------------------------------------------------------------- #
WITH hosp AS (
    SELECT id AS hospital_id FROM med_hospital WHERE code = 'shengyi'
)
INSERT INTO med_dict_mapping (
    uuid, hospital_id, dict_type_id, dict_data_id, raw_label, raw_value,
    tenant_id, status, description, created_time, updated_time, is_deleted
)
SELECT
    gen_random_uuid(),
    h.hospital_id,
    dt.id,
    sd.id,
    m.raw_label,
    m.raw_value,
    1,                          -- tenant_id
    '0',
    m.note,
    NOW(), NOW(), FALSE
FROM hosp h
CROSS JOIN (
    -- raw_label, 目标 dict_type, 目标 dict_value, raw_value(可空), 说明
    -- med_sex (2): 省医实际值 '男性'/'女性'（带"性"字，区别于珠江"男/女"）
    VALUES
        ('med_sex', '男性', '1', 'gender', '省医性别-男性'),
        ('med_sex', '女性', '2', 'gender', '省医性别-女性'),

    -- med_ethnicity (1): 省医实际值 '汉族'（珠江是'汉'，已由 0008 注册）
        ('med_ethnicity', '汉族', '01', 'ethnicity', '省医民族-汉族'),

    -- med_exam_type (9): exam_type 自映射（ETL 不经 normalize_*，保留映射便于一致性校验）
    --   CT/PETCT/Pathology/Genetic/IHC 由 050+0008 提供，Radiology/Ultrasound/Lab/Order 由本文件第 1 段提供
        ('med_exam_type', 'CT',        'CT',        NULL, 'exam_type 自映射'),
        ('med_exam_type', 'PETCT',     'PETCT',     NULL, 'exam_type 自映射'),
        ('med_exam_type', 'Pathology', 'Pathology', NULL, 'exam_type 自映射'),
        ('med_exam_type', 'Genetic',   'Genetic',   NULL, 'exam_type 自映射'),
        ('med_exam_type', 'IHC',       'IHC',       NULL, 'exam_type 自映射'),
        ('med_exam_type', 'Radiology', 'Radiology', NULL, 'exam_type 自映射'),
        ('med_exam_type', 'Ultrasound','Ultrasound',NULL, 'exam_type 自映射'),
        ('med_exam_type', 'Lab',       'Lab',       NULL, 'exam_type 自映射'),
        ('med_exam_type', 'Order',     'Order',     NULL, 'exam_type 自映射')
) AS m(dict_type_name, raw_label, dict_value, raw_value, note)
JOIN sys_dict_type dt ON dt.dict_type = m.dict_type_name
JOIN sys_dict_data sd ON sd.dict_type = m.dict_type_name AND sd.dict_value = m.dict_value
ON CONFLICT (hospital_id, dict_type_id, raw_label) DO NOTHING;

COMMIT;
