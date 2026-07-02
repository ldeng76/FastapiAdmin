-- ============================================================
-- 医学数据模块菜单注入（幂等，可重复执行）
-- 新增：医学数据目录 + 患者浏览菜单 + 多模态详情按钮权限
-- superuser 走 bypass，无需 sys_role_menus 关联
-- uuid 用 gen_random_uuid() 去横线生成（对齐 uuid4_str 格式）
-- ============================================================

-- 1) 顶级目录：医学数据
INSERT INTO sys_menu (
    uuid, name, type, icon, "order", permission, route_name, route_path,
    component_path, redirect, status, keep_alive, always_show, hidden, affix,
    title, description, client, tenant_id, created_time, updated_time, is_deleted
)
SELECT
    replace(gen_random_uuid()::text, '-', ''), '医学数据', 1, 'ri:stethoscope-line', 90,
    NULL, 'Medical', '/medical', NULL, '/medical/patient',
    '0', true, false, false, false,
    '医学数据', '医学多模态数据浏览', 'pc', 1, now(), now(), false
WHERE NOT EXISTS (SELECT 1 FROM sys_menu WHERE name = '医学数据' AND parent_id IS NULL);

-- 2) 叶子菜单：患者浏览（挂在「医学数据」下）
INSERT INTO sys_menu (
    uuid, name, type, icon, "order", permission, route_name, route_path,
    component_path, redirect, status, keep_alive, always_show, hidden, affix,
    title, description, client, tenant_id, parent_id, created_time, updated_time, is_deleted
)
SELECT
    replace(gen_random_uuid()::text, '-', ''), '患者浏览', 2, 'ri:search-eye-line', 1,
    'module_medical:patient:query', 'MedicalPatient', '/medical/patient', 'module_medical/patient/index',
    NULL, '0', true, false, false, false,
    '患者浏览', '多模态患者数据钻取', 'pc', 1,
    (SELECT id FROM sys_menu WHERE name = '医学数据' AND parent_id IS NULL),
    now(), now(), false
WHERE NOT EXISTS (
    SELECT 1 FROM sys_menu
    WHERE name = '患者浏览'
      AND parent_id = (SELECT id FROM sys_menu WHERE name = '医学数据' AND parent_id IS NULL)
);

-- 3) 按钮权限：多模态详情（type=3）
INSERT INTO sys_menu (
    uuid, name, type, "order", permission, route_name, route_path, component_path,
    status, keep_alive, always_show, hidden, affix, title, description, client, tenant_id,
    parent_id, created_time, updated_time, is_deleted
)
SELECT
    replace(gen_random_uuid()::text, '-', ''), '多模态详情', 3, 1,
    'module_medical:patient:query', NULL, NULL, NULL,
    '0', true, false, false, false,
    '多模态详情', '查看患者多模态数据', 'pc', 1,
    (SELECT id FROM sys_menu WHERE name = '患者浏览'),
    now(), now(), false
WHERE NOT EXISTS (
    SELECT 1 FROM sys_menu
    WHERE name = '多模态详情'
      AND parent_id = (SELECT id FROM sys_menu WHERE name = '患者浏览')
);

-- 4) 隐藏路由：多模态详情页（type=2, hidden=true；patient_id/center 走 query 参数）
INSERT INTO sys_menu (
    uuid, name, type, icon, "order", permission, route_name, route_path,
    component_path, redirect, status, keep_alive, always_show, hidden, affix,
    title, description, client, tenant_id, parent_id, created_time, updated_time, is_deleted
)
SELECT
    replace(gen_random_uuid()::text, '-', ''), '多模态详情页', 2, NULL, 2,
    'module_medical:patient:query', 'MedicalPatientDetail', '/medical/patient/detail',
    'module_medical/patient/detail', NULL,
    '0', true, false, true, false,
    '多模态详情页', '患者多模态数据详情（隐藏，列表跳转进入）', 'pc', 1,
    (SELECT id FROM sys_menu WHERE name = '医学数据' AND parent_id IS NULL),
    now(), now(), false
WHERE NOT EXISTS (
    SELECT 1 FROM sys_menu
    WHERE route_name = 'MedicalPatientDetail'
);
