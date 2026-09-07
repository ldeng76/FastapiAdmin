-- =====================================================================
-- 0017 - 新桥中心 (xinqiao) 注册：租户 + med_hospital
-- 依据: anon_etl_engine._resolve_hospital_id 要求 center_code 已注册（0008/0013 先例）
-- 目标: PostgreSQL 14+, schema = lnrs
-- 内容（幂等 WHERE NOT EXISTS / ON CONFLICT，可重复执行）:
--   1. INSERT sys_tenant: 新桥独立租户（code='xinqiao'）
--   2. INSERT med_hospital: 新桥中心注册行
-- 说明:
--   - 2026-09-04 extracted_tables 批次（ct/pathology/genetics 3 表）无 patient 表，
--     人口学由 ETL2 引擎按 anon_id 自动占位生成（sex='0', birth_date=NULL，
--     同 hos301 先例），exam_type 为 spec 静态值（CT/Pathology/Genetic，
--     sys_dict_data 已存在），故无需任何 med_dict_mapping 行。
-- =====================================================================

BEGIN;

-- 切换目标 schema（lnrs 用户仅有 lnrs schema UC 权限）
SET LOCAL search_path = lnrs;

-- --------------------------------------------------------------------- #
-- 1. 幂等创建新桥独立 tenant（code='xinqiao'）
--    已占租户: 1=system(珠江) 4=省医 12=hos301
-- --------------------------------------------------------------------- #
INSERT INTO sys_tenant (
    uuid, name, code, contact_name, contact_phone, contact_email, address,
    domain, logo_url, sort, start_time, end_time, status, description,
    created_time, updated_time, is_deleted
)
SELECT
    gen_random_uuid(), '新桥医院', 'xinqiao', NULL, NULL, NULL, NULL,
    NULL, NULL, 0, NULL, NULL, '0', '新桥中心租户（0017）',
    NOW(), NOW(), FALSE
WHERE NOT EXISTS (
    SELECT 1 FROM sys_tenant WHERE code = 'xinqiao'
);

-- --------------------------------------------------------------------- #
-- 2. 注册 med_hospital（tenant_id 动态取新桥 tenant 的 id）
--    code='xinqiao' 唯一，NOT EXISTS 不覆盖
-- --------------------------------------------------------------------- #
INSERT INTO med_hospital (
    uuid, code, name, full_name, tenant_id, lifecycle_status,
    contact_name, contact_phone, contact_email, address,
    data_dir, last_import_time, last_import_rows, import_error,
    status, description, created_time, updated_time, is_deleted
)
SELECT
    gen_random_uuid(),
    'xinqiao',
    '新桥',
    '陆军军医大学新桥医院',
    (SELECT id FROM sys_tenant WHERE code = 'xinqiao'),  -- 新桥独立 tenant_id
    'mapping_configured',       -- 无枚举映射需求（无 patient 表 + 静态 exam_type）
    NULL, NULL, NULL, NULL,
    'data/xinqiao',
    NULL, 0, NULL,
    '0', '新桥中心字典驱动 ETL 注册（0017）', NOW(), NOW(), FALSE
WHERE NOT EXISTS (
    SELECT 1 FROM med_hospital WHERE code = 'xinqiao'
);

COMMIT;
