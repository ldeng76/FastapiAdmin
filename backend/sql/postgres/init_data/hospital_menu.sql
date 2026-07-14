-- ============================================================
-- 医院管理模块菜单注入（幂等，可重复执行）
-- 新增：医院管理菜单 + 注册/映射/导入/上下线按钮权限
-- superuser 走 bypass，无需 sys_role_menus 关联
-- uuid 用 gen_random_uuid() 去横线生成（对齐 uuid4_str 格式）
-- ============================================================

-- 1) 叶子菜单：医院管理（挂在「医学数据」下）
INSERT INTO sys_menu (
    uuid, name, type, icon, "order", permission, route_name, route_path,
    component_path, redirect, status, keep_alive, always_show, hidden, affix,
    title, description, client, tenant_id, parent_id, created_time, updated_time, is_deleted
)
SELECT
    replace(gen_random_uuid()::text, '-', ''), '医院管理', 2, 'ri:hospital-line', 2,
    'module_medical:hospital:query', 'MedicalHospital', '/medical/hospital',
    'module_medical/hospital/index', NULL,
    '0', true, false, false, false,
    '医院管理', '多中心数据注册、Schema 映射、ETL 导入、上下线', 'pc', 1,
    (SELECT id FROM sys_menu WHERE name = '医学数据' AND parent_id IS NULL),
    now(), now(), false
WHERE NOT EXISTS (
    SELECT 1 FROM sys_menu
    WHERE name = '医院管理'
      AND parent_id = (SELECT id FROM sys_menu WHERE name = '医学数据' AND parent_id IS NULL)
);

-- 2) 按钮权限：注册医院（type=3）
INSERT INTO sys_menu (
    uuid, name, type, "order", permission, route_name, route_path, component_path,
    status, keep_alive, always_show, hidden, affix, title, description, client, tenant_id,
    parent_id, created_time, updated_time, is_deleted
)
SELECT
    replace(gen_random_uuid()::text, '-', ''), '注册医院', 3, 1,
    'module_medical:hospital:create', NULL, NULL, NULL,
    '0', true, false, false, false,
    '注册医院', '注册新医院并创建对应租户', 'pc', 1,
    (SELECT id FROM sys_menu WHERE name = '医院管理'),
    now(), now(), false
WHERE NOT EXISTS (
    SELECT 1 FROM sys_menu
    WHERE name = '注册医院'
      AND parent_id = (SELECT id FROM sys_menu WHERE name = '医院管理')
);

-- 3) 按钮权限：编辑映射（type=3）
INSERT INTO sys_menu (
    uuid, name, type, "order", permission, route_name, route_path, component_path,
    status, keep_alive, always_show, hidden, affix, title, description, client, tenant_id,
    parent_id, created_time, updated_time, is_deleted
)
SELECT
    replace(gen_random_uuid()::text, '-', ''), '编辑映射', 3, 2,
    'module_medical:hospital:mapping:edit', NULL, NULL, NULL,
    '0', true, false, false, false,
    '编辑映射', '编辑医院字段映射规则', 'pc', 1,
    (SELECT id FROM sys_menu WHERE name = '医院管理'),
    now(), now(), false
WHERE NOT EXISTS (
    SELECT 1 FROM sys_menu
    WHERE name = '编辑映射'
      AND parent_id = (SELECT id FROM sys_menu WHERE name = '医院管理')
);

-- 4) 按钮权限：触发导入（type=3）
INSERT INTO sys_menu (
    uuid, name, type, "order", permission, route_name, route_path, component_path,
    status, keep_alive, always_show, hidden, affix, title, description, client, tenant_id,
    parent_id, created_time, updated_time, is_deleted
)
SELECT
    replace(gen_random_uuid()::text, '-', ''), '触发导入', 3, 3,
    'module_medical:hospital:import', NULL, NULL, NULL,
    '0', true, false, false, false,
    '触发导入', '触发 ETL 数据导入', 'pc', 1,
    (SELECT id FROM sys_menu WHERE name = '医院管理'),
    now(), now(), false
WHERE NOT EXISTS (
    SELECT 1 FROM sys_menu
    WHERE name = '触发导入'
      AND parent_id = (SELECT id FROM sys_menu WHERE name = '医院管理')
);

-- 5) 按钮权限：上线（type=3）
INSERT INTO sys_menu (
    uuid, name, type, "order", permission, route_name, route_path, component_path,
    status, keep_alive, always_show, hidden, affix, title, description, client, tenant_id,
    parent_id, created_time, updated_time, is_deleted
)
SELECT
    replace(gen_random_uuid()::text, '-', ''), '上线', 3, 4,
    'module_medical:hospital:online', NULL, NULL, NULL,
    '0', true, false, false, false,
    '上线', '医院上线发布（data_imported → live）', 'pc', 1,
    (SELECT id FROM sys_menu WHERE name = '医院管理'),
    now(), now(), false
WHERE NOT EXISTS (
    SELECT 1 FROM sys_menu
    WHERE name = '上线'
      AND parent_id = (SELECT id FROM sys_menu WHERE name = '医院管理')
);

-- 6) 按钮权限：下线（type=3）
INSERT INTO sys_menu (
    uuid, name, type, "order", permission, route_name, route_path, component_path,
    status, keep_alive, always_show, hidden, affix, title, description, client, tenant_id,
    parent_id, created_time, updated_time, is_deleted
)
SELECT
    replace(gen_random_uuid()::text, '-', ''), '下线', 3, 5,
    'module_medical:hospital:offline', NULL, NULL, NULL,
    '0', true, false, false, false,
    '下线', '医院下线（live → data_imported）', 'pc', 1,
    (SELECT id FROM sys_menu WHERE name = '医院管理'),
    now(), now(), false
WHERE NOT EXISTS (
    SELECT 1 FROM sys_menu
    WHERE name = '下线'
      AND parent_id = (SELECT id FROM sys_menu WHERE name = '医院管理')
);
