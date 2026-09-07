-- =====================================================================
-- 0013 - 301医院(hos301)中心字典驱动 ETL 所需的前置数据
-- 依据: docs/adr/0006-anonymized-data-schema.md / ADR-0009（多中心配置驱动）
-- 目标: PostgreSQL 14+, schema = lnrs（med_* / sys_* 表所在 schema）
-- 内容（幂等 WHERE NOT EXISTS / ON CONFLICT DO NOTHING，可重复执行）:
--   1. 补 sys_dict_data: med_exam_type 新增 'Other'
--      301 exam.parquet 含 14 种 examClass（超声/ＣＴ/心电图/放射/病理/磁共振/
--      核医学/胃肠镜/肺功能/耳鼻喉/气管镜/其他/体检/泌外），其中：
--        ＣＴ  → CT
--        病理 → Pathology
--        超声 → Ultrasound
--        其余 → 'Other'（新增字典值）
--   2. INSERT sys_tenant + med_hospital: 301 中心注册行
--   3. INSERT med_dict_mapping: 301 examClass → med_exam_type 映射规则
-- 说明:
--   - 301 数据无 patient 表，人口学数据由 ETL2 引擎按 anon_id 自动占位生成
--     （sex='0', birth_date=NULL）。无需补 med_sex/med_ethnicity 等枚举映射。
--   - 301 数据无 visit_id 列在 lab.parquet（顶层无 visit_id），lab 表 ETL1 适配脚本
--     会展平嵌套 list 后只挂 patient（visit_id 缺失时引擎退化为只挂 patient，详见
--     anon_etl_engine._import_lab_table）。
-- =====================================================================

BEGIN;

-- 切换目标 schema（lnrs 用户仅有 lnrs schema UC 权限）
SET LOCAL search_path = lnrs;

-- --------------------------------------------------------------------- #
-- 1. 补 sys_dict_data: med_exam_type 新增 'Other'
--    dict_type_id 取 med_exam_type 的 sys_dict_type.id（查询里动态取，不硬编码）
-- --------------------------------------------------------------------- #
INSERT INTO sys_dict_data (uuid, dict_sort, dict_label, dict_value, dict_type, dict_type_id, is_default, description, tenant_id, status, created_time, updated_time, is_deleted)
SELECT
    gen_random_uuid(),
    300,                         -- sort 避开 050/0008/0009 已用 sort
    '其他',
    'Other',
    'med_exam_type',
    (SELECT id FROM sys_dict_type WHERE dict_type = 'med_exam_type'),
    FALSE,
    '医疗检查类型-其他（301 医院 examClass 非 CT/Pathology/Ultrasound 归此）',
    1,
    '0',
    NOW(),
    NOW(),
    FALSE
WHERE NOT EXISTS (
    SELECT 1 FROM sys_dict_data sd
    WHERE sd.dict_type = 'med_exam_type' AND sd.dict_value = 'Other'
);

-- --------------------------------------------------------------------- #
-- 2. INSERT sys_tenant + med_hospital: 301 中心注册行
--    med_hospital 有 UNIQUE(tenant_id) 约束，每 hospital 绑定独立 tenant。
--    珠江已占 tenant_id=1（系统租户），省医占 tenant_id=4。301 需自建独立 tenant。
-- --------------------------------------------------------------------- #
-- 2a. 幂等创建 301 独立 tenant（code='hos301'）
INSERT INTO sys_tenant (
    uuid, name, code, contact_name, contact_phone, contact_email, address,
    domain, logo_url, sort, start_time, end_time, status, description,
    created_time, updated_time, is_deleted
)
SELECT
    gen_random_uuid(), '301医院', 'hos301', NULL, NULL, NULL, NULL,
    NULL, NULL, 0, NULL, NULL, '0', '301 中心租户（0013）',
    NOW(), NOW(), FALSE
WHERE NOT EXISTS (
    SELECT 1 FROM sys_tenant WHERE code = 'hos301'
);

-- 2b. 注册 med_hospital（tenant_id 动态取 301 tenant 的 id）
INSERT INTO med_hospital (
    uuid, code, name, full_name, tenant_id, lifecycle_status,
    contact_name, contact_phone, contact_email, address,
    data_dir, last_import_time, last_import_rows, import_error,
    status, description, created_time, updated_time, is_deleted
)
SELECT
    gen_random_uuid(),
    'hos301',
    '301医院',
    '中国人民解放军总医院',
    (SELECT id FROM sys_tenant WHERE code = 'hos301'),  -- 301 独立 tenant_id
    'mapping_configured',       -- 映射规则已配置就绪
    NULL, NULL, NULL, NULL,
    'data/hos301',
    NULL, 0, NULL,
    '0', '301 中心字典驱动 ETL 注册（0013）', NOW(), NOW(), FALSE
WHERE NOT EXISTS (
    SELECT 1 FROM med_hospital WHERE code = 'hos301'
);

-- --------------------------------------------------------------------- #
-- 3. INSERT med_dict_mapping: 301 examClass → med_exam_type 映射规则
--    raw_label 保留原始大小写（load_all_mappings 会 .strip().lower() 匹配）
--    冲突处理: (hospital_id, dict_type_id, raw_label) ON CONFLICT DO NOTHING
-- --------------------------------------------------------------------- #
-- VALUES 列表中多次 nextval() 在 PG 14+ 下被规划为"按字典序执行一次"，
-- 导致多行得到同一 id（duplicate key）。
-- 修复 = 先 SELECT nextval 一次性锁定起点，再用 ROW_NUMBER() 派生每行 id。
WITH seq_start AS (
    SELECT COALESCE(MAX(id), nextval('med_dict_mapping_id_seq') - 1) AS base
    FROM med_dict_mapping
),
hosp AS (
    SELECT id AS hospital_id FROM med_hospital WHERE code = 'hos301'
),
labels AS (
    -- 301 exam.parquet 的 examClass（14 种） → 引擎可识别的 med_exam_type
    -- 注意 'ＣＴ' 是全角 C（301 数据原始字符）
    SELECT ROW_NUMBER() OVER () AS rn, dict_type_name, raw_label, dict_value, raw_value, note
    FROM (VALUES
        ('med_exam_type', 'ＣＴ',     'CT',        NULL::text, '301 全角 CT → CT'),
        ('med_exam_type', '病理',     'Pathology', NULL,        '301 病理 → Pathology'),
        ('med_exam_type', '超声',     'Ultrasound',NULL,        '301 超声 → Ultrasound'),
        ('med_exam_type', '心电图',   'Other',     NULL,        '301 心电图 → Other'),
        ('med_exam_type', '放射',     'Other',     NULL,        '301 放射 → Other'),
        ('med_exam_type', '磁共振',   'Other',     NULL,        '301 磁共振 → Other'),
        ('med_exam_type', '核医学',   'Other',     NULL,        '301 核医学 → Other'),
        ('med_exam_type', '胃肠镜',   'Other',     NULL,        '301 胃肠镜 → Other'),
        ('med_exam_type', '肺功能',   'Other',     NULL,        '301 肺功能 → Other'),
        ('med_exam_type', '耳鼻喉',   'Other',     NULL,        '301 耳鼻喉 → Other'),
        ('med_exam_type', '气管镜',   'Other',     NULL,        '301 气管镜 → Other'),
        ('med_exam_type', '其他',     'Other',     NULL,        '301 其他 → Other'),
        ('med_exam_type', '体检',     'Other',     NULL,        '301 体检 → Other'),
        ('med_exam_type', '泌外',     'Other',     NULL,        '301 泌外 → Other')
    ) AS m(dict_type_name, raw_label, dict_value, raw_value, note)
)
INSERT INTO med_dict_mapping (
    id, uuid, hospital_id, dict_type_id, dict_data_id, raw_label, raw_value,
    tenant_id, status, description, created_time, updated_time, is_deleted
)
SELECT
    s.base + m.rn,
    gen_random_uuid(),
    h.hospital_id,
    dt.id,
    sd.id,
    m.raw_label,
    m.raw_value,
    1,
    '0',
    m.note,
    NOW(), NOW(), FALSE
FROM hosp h
CROSS JOIN labels m
CROSS JOIN seq_start s
JOIN sys_dict_type dt ON dt.dict_type = m.dict_type_name
JOIN sys_dict_data sd ON sd.dict_type = m.dict_type_name AND sd.dict_value = m.dict_value
ON CONFLICT (hospital_id, dict_type_id, raw_label) DO NOTHING;

COMMIT;