-- =====================================================================
-- 0008 - 珠江中心字典驱动 ETL 所需的前置数据
-- 依据: docs/adr/0006-anonymized-data-schema.md §343 / ADR-0009（待写）
-- 目标: PostgreSQL 14+, schema = lnrs（med_* / sys_* 表所在 schema）
-- 内容（幂等 ON CONFLICT DO NOTHING / WHERE NOT EXISTS，可重复执行）:
--   1. 补 sys_dict_data: med_exam_type 缺失的 Genetic / IHC（ADR-0006 §343 已约定）
--   2. INSERT med_hospital: 珠江中心注册行（全新 hospital_id）
--   3. INSERT med_dict_mapping: 珠江中心 28 行映射规则
--      - med_sex       (7): 男/女/M/F/1/2/0 → 数字码
--      - med_smoking_status (4): 从不/既往/现在/未知 → 数字码
--      - med_blood_type_abo (4): A/B/O/AB（珠江数据中未出现但补常见值便于未来扩展）
--      - med_blood_type_rh (2): 阴性/阳性
--      - med_ethnicity (1): 汉 → '01'（珠江实际值是 '汉' 不是 '汉族'）
--      - med_exam_type (5): CT/PETCT/Pathology/Genetic/IHC 各自映射自身
-- 说明: med_dict_mapping 没有 dict_value 列，必须 JOIN sys_dict_data
--       反查 dict_data_id（见下文 USING 子句）。
-- 注: med_dict_unmatched 表已存在（由 initialize.py metadata.create_all 创建），
--     本 SQL 不重建。
-- =====================================================================

BEGIN;

-- 切换目标 schema（lnrs 用户仅有 lnrs schema UC 权限）
SET LOCAL search_path = lnrs;

-- --------------------------------------------------------------------- #
-- 1. 补 sys_dict_data: med_exam_type 缺失的 Genetic / IHC
--    ADR-0006 §343 已约定：med_exam_type 字典新增 Genetic / IHC
--    当前库只有 CT/PETCT/Pathology 3 行。
--    dict_type_id 取 med_exam_type 的 sys_dict_type.id（查询里动态取，不硬编码）
-- --------------------------------------------------------------------- #
INSERT INTO sys_dict_data (uuid, dict_sort, dict_label, dict_value, dict_type, dict_type_id, is_default, description, tenant_id, status, created_time, updated_time, is_deleted)
SELECT
    gen_random_uuid(),
    ROW_NUMBER() OVER () + 100,  -- sort 避开已有 1/2/3
    CASE d.v
        WHEN 'Genetic' THEN '基因检测'
        WHEN 'IHC'     THEN '免疫组化'
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
FROM (VALUES ('Genetic'), ('IHC')) AS d(v)
WHERE NOT EXISTS (
    SELECT 1 FROM sys_dict_data sd
    WHERE sd.dict_type = 'med_exam_type' AND sd.dict_value = d.v
);

-- --------------------------------------------------------------------- #
-- 2. INSERT med_hospital: 珠江中心注册行
--    code='zhujiang' 唯一，ON CONFLICT 不覆盖
-- --------------------------------------------------------------------- #
INSERT INTO med_hospital (
    uuid, code, name, full_name, tenant_id, lifecycle_status,
    contact_name, contact_phone, contact_email, address,
    data_dir, last_import_time, last_import_rows, import_error,
    status, description, created_time, updated_time, is_deleted
)
SELECT
    gen_random_uuid(),
    'zhujiang',
    '珠江医院',
    '南方医科大学珠江医院',
    1,                          -- tenant_id = PLATFORM_TENANT_ID
    'mapping_configured',       -- 映射规则已配置就绪
    NULL, NULL, NULL, NULL,
    'data/0723_sample/zhujiang',
    NULL, 0, NULL,
    '0', '珠江中心字典驱动 ETL 注册（0008）', NOW(), NOW(), FALSE
WHERE NOT EXISTS (
    SELECT 1 FROM med_hospital WHERE code = 'zhujiang'
);

-- --------------------------------------------------------------------- #
-- 3. INSERT med_dict_mapping: 珠江中心映射规则
--    raw_label → dict_data_id（通过 JOIN sys_dict_data 反查）
--    hospital_id 动态从 med_hospital 取（不依赖固定 id）
--    tenant_id = 1 (PLATFORM_TENANT_ID)
--    冲突处理: (hospital_id, dict_type_id, raw_label) ON CONFLICT DO NOTHING
-- --------------------------------------------------------------------- #
WITH hosp AS (
    SELECT id AS hospital_id FROM med_hospital WHERE code = 'zhujiang'
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
    -- med_sex (7): 珠江实际值 '男'/'女' + 兼容英文/数字（共 7 行）
    VALUES
        ('med_sex', '男',   '1', 'gender',   '珠江性别-男'),
        ('med_sex', '女',   '2', 'gender',   '珠江性别-女'),
        ('med_sex', 'M',    '1', NULL,       '兼容-男'),
        ('med_sex', 'F',    '2', NULL,       '兼容-女'),
        ('med_sex', '1',    '1', NULL,       'HQMS 码-男'),
        ('med_sex', '2',    '2', NULL,       'HQMS 码-女'),
        ('med_sex', '0',    '0', NULL,       'HQMS 码-未知'),

    -- med_smoking_status (4): 珠江实际值 '从不'/'既往'/'现在'
        ('med_smoking_status', '从不', '1', 'smoking_status', '珠江吸烟-从不'),
        ('med_smoking_status', '既往', '2', 'smoking_status', '珠江吸烟-既往'),
        ('med_smoking_status', '现在', '3', 'smoking_status', '珠江吸烟-现在'),
        ('med_smoking_status', '未知', '9', NULL,             '兼容-未知'),

    -- med_blood_type_abo (4): 珠江数据全 NULL，补常见字母值便于未来扩展
        ('med_blood_type_abo', 'A',  '1', NULL, '兼容-A型'),
        ('med_blood_type_abo', 'B',  '2', NULL, '兼容-B型'),
        ('med_blood_type_abo', 'O',  '3', NULL, '兼容-O型'),
        ('med_blood_type_abo', 'AB', '4', NULL, '兼容-AB型'),

    -- med_blood_type_rh (2): 珠江数据全 NULL，补常见值
        ('med_blood_type_rh', '阴性', '1', NULL, '兼容-Rh阴性'),
        ('med_blood_type_rh', '阳性', '2', NULL, '兼容-Rh阳性'),

    -- med_ethnicity (1): 珠江实际值是 '汉'（不是 '汉族'）
        ('med_ethnicity', '汉', '01', 'ethnicity', '珠江民族-汉'),

    -- med_exam_type (5): exam_type 自身映射自身（ETL 不经 normalize_*，但保留映射便于一致性校验）
        ('med_exam_type', 'CT',        'CT',        NULL, 'exam_type 自映射'),
        ('med_exam_type', 'PETCT',     'PETCT',     NULL, 'exam_type 自映射'),
        ('med_exam_type', 'Pathology', 'Pathology', NULL, 'exam_type 自映射'),
        ('med_exam_type', 'Genetic',   'Genetic',   NULL, 'exam_type 自映射'),
        ('med_exam_type', 'IHC',       'IHC',       NULL, 'exam_type 自映射')
) AS m(dict_type_name, raw_label, dict_value, raw_value, note)
JOIN sys_dict_type dt ON dt.dict_type = m.dict_type_name
JOIN sys_dict_data sd ON sd.dict_type = m.dict_type_name AND sd.dict_value = m.dict_value
ON CONFLICT (hospital_id, dict_type_id, raw_label) DO NOTHING;

COMMIT;
