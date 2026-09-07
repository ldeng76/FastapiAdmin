-- =====================================================================
-- 0015 - 省医(shengyi) 2026-09 全量批次字典种子
-- 目标: PostgreSQL 14+, schema = lnrs（sys_* / med_* 表所在 schema）
-- 依据: 省医 extracted 批次（26 parquet）画像结果：
--   * 患者基本信息.民族 30 种取值（壮/土家/满/回/瑶/苗/黎/侗/畲/蒙古/布依/彝/
--     朝鲜/藏/仡佬/维吾尔/仫佬/白/锡伯/土/俄罗斯/水/京/达斡尔/傈僳/哈尼/羌/
--     东乡/毛难 + 汉族 + 其他民族或外籍人士/其他/外国血统）
--   * 性别含 '未知的性别'（现有 med_sex 映射只有 男/女/m/f/nan）
--   * 影像 检查类型名称 关键词归一化后出现 MR / ECG 两个 med_exam_type
--     新字典值（现有字典无）
-- 内容（幂等 WHERE NOT EXISTS / ON CONFLICT DO NOTHING，可重复执行）:
--   1. 补 sys_dict_data: med_exam_type 新增 MR / ECG
--   2. INSERT med_dict_mapping: 省医(hospital_id=3) 民族 29 值 +
--      '其他民族或外籍人士/其他/外国血统'→99
--   3. INSERT med_dict_mapping: 省医 性别 '未知的性别'→0
-- 说明:
--   - 民族映射值对齐 HQMS 民族代码（med_ethnicity 字典 01-56/99 已存在，
--     本种子只补 raw_label → dict_value 映射规则）。
--   - 影像 exam_type 由适配层按关键词规则归一化为字典值后落 staging
--     （CT→CT / PET→PETCT / MR→MR / 胸片DR→Radiology / 超声→Ultrasound /
--     其余→Other），引擎行级精确匹配字典值直接返回，无需映射行。
-- =====================================================================

BEGIN;

SET LOCAL search_path = lnrs;

-- --------------------------------------------------------------------- #
-- 1. 补 sys_dict_data: med_exam_type 新增 MR / ECG
-- --------------------------------------------------------------------- #
INSERT INTO sys_dict_data (uuid, dict_sort, dict_label, dict_value, dict_type, dict_type_id, is_default, description, tenant_id, status, created_time, updated_time, is_deleted)
SELECT
    gen_random_uuid(), 301, '磁共振', 'MR', 'med_exam_type',
    (SELECT id FROM sys_dict_type WHERE dict_type = 'med_exam_type'),
    FALSE,
    '医疗检查类型-磁共振（省医影像 检查类型名称 关键词归一化，0015）',
    1, '0', NOW(), NOW(), FALSE
WHERE NOT EXISTS (
    SELECT 1 FROM sys_dict_data sd
    WHERE sd.dict_type = 'med_exam_type' AND sd.dict_value = 'MR'
);

INSERT INTO sys_dict_data (uuid, dict_sort, dict_label, dict_value, dict_type, dict_type_id, is_default, description, tenant_id, status, created_time, updated_time, is_deleted)
SELECT
    gen_random_uuid(), 302, '心电图', 'ECG', 'med_exam_type',
    (SELECT id FROM sys_dict_type WHERE dict_type = 'med_exam_type'),
    FALSE,
    '医疗检查类型-心电图（省医心电图报告，0015）',
    1, '0', NOW(), NOW(), FALSE
WHERE NOT EXISTS (
    SELECT 1 FROM sys_dict_data sd
    WHERE sd.dict_type = 'med_exam_type' AND sd.dict_value = 'ECG'
);

-- --------------------------------------------------------------------- #
-- 2. 省医 民族映射（HQMS 民族代码）
--    同 0013 的 nextval 碰撞修复：先锁定 seq 起点，ROW_NUMBER() 派生 id
-- --------------------------------------------------------------------- #
WITH seq_start AS (
    SELECT COALESCE(MAX(id), nextval('med_dict_mapping_id_seq') - 1) AS base
    FROM med_dict_mapping
),
labels AS (
    SELECT ROW_NUMBER() OVER () AS rn, dict_type_name, raw_label, dict_value, raw_value, note
    FROM (VALUES
        ('med_ethnicity', '壮族',       '08', NULL::text, '壮族 → 08'),
        ('med_ethnicity', '土家族',     '15', NULL,        '土家族 → 15'),
        ('med_ethnicity', '满族',       '11', NULL,        '满族 → 11'),
        ('med_ethnicity', '回族',       '03', NULL,        '回族 → 03'),
        ('med_ethnicity', '瑶族',       '13', NULL,        '瑶族 → 13'),
        ('med_ethnicity', '苗族',       '06', NULL,        '苗族 → 06'),
        ('med_ethnicity', '黎族',       '19', NULL,        '黎族 → 19'),
        ('med_ethnicity', '侗族',       '12', NULL,        '侗族 → 12'),
        ('med_ethnicity', '畲族',       '22', NULL,        '畲族 → 22'),
        ('med_ethnicity', '蒙古族',     '02', NULL,        '蒙古族 → 02'),
        ('med_ethnicity', '布依族',     '09', NULL,        '布依族 → 09'),
        ('med_ethnicity', '彝族',       '07', NULL,        '彝族 → 07'),
        ('med_ethnicity', '朝鲜族',     '10', NULL,        '朝鲜族 → 10'),
        ('med_ethnicity', '藏族',       '04', NULL,        '藏族 → 04'),
        ('med_ethnicity', '仡佬族',     '37', NULL,        '仡佬族 → 37'),
        ('med_ethnicity', '维吾尔族',   '05', NULL,        '维吾尔族 → 05'),
        ('med_ethnicity', '仫佬族',     '32', NULL,        '仫佬族 → 32'),
        ('med_ethnicity', '白族',       '14', NULL,        '白族 → 14'),
        ('med_ethnicity', '锡伯族',     '38', NULL,        '锡伯族 → 38'),
        ('med_ethnicity', '土族',       '30', NULL,        '土族 → 30'),
        ('med_ethnicity', '俄罗斯族',   '44', NULL,        '俄罗斯族 → 44'),
        ('med_ethnicity', '水族',       '25', NULL,        '水族 → 25'),
        ('med_ethnicity', '京族',       '49', NULL,        '京族 → 49'),
        ('med_ethnicity', '达翰尔族',   '31', NULL,        '达翰尔族（源原始值）→ 31'),
        ('med_ethnicity', '傈僳族',     '20', NULL,        '傈僳族 → 20'),
        ('med_ethnicity', '哈尼族',     '16', NULL,        '哈尼族 → 16'),
        ('med_ethnicity', '羌族',       '33', NULL,        '羌族 → 33'),
        ('med_ethnicity', '东乡族',     '26', NULL,        '东乡族 → 26'),
        ('med_ethnicity', '毛难族',     '36', NULL,        '毛难族 → 36'),
        ('med_ethnicity', '达斡尔族',   '31', NULL,        '达斡尔族（规范名）→ 31'),
        ('med_ethnicity', '其他民族或外籍人士', '99', NULL, '其他民族或外籍人士 → 99'),
        ('med_ethnicity', '其他',       '99', NULL,        '其他 → 99'),
        ('med_ethnicity', '外国血统',   '99', NULL,        '外国血统 → 99'),
        -- 3. 性别补充（省医 性别列含 '未知的性别'）
        ('med_sex', '未知的性别', '0', NULL,               '未知的性别 → 0（未知）')
    ) AS m(dict_type_name, raw_label, dict_value, raw_value, note)
)
INSERT INTO med_dict_mapping (
    id, uuid, hospital_id, dict_type_id, dict_data_id, raw_label, raw_value,
    tenant_id, status, description, created_time, updated_time, is_deleted
)
SELECT
    s.base + l.rn,
    gen_random_uuid(),
    (SELECT id FROM med_hospital WHERE code = 'shengyi'),
    dt.id,
    sd.id,
    l.raw_label,
    l.raw_value,
    1,
    '0',
    l.note,
    NOW(), NOW(), FALSE
FROM labels l
CROSS JOIN seq_start s
JOIN sys_dict_type dt ON dt.dict_type = l.dict_type_name
JOIN sys_dict_data sd ON sd.dict_type = l.dict_type_name AND sd.dict_value = l.dict_value
ON CONFLICT (hospital_id, dict_type_id, raw_label) DO NOTHING;

COMMIT;
