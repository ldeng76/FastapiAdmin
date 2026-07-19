-- ============================================================
-- 隐藏与「肺结节研究系统」业务无关的菜单（幂等，可重复执行）
--
-- 背景：本平台基于通用脚手架（FastapiAdmin）搭建，自带大量与
-- 肺结节研究无关的模块菜单（接口文档、代码生成、插件市场、AI、
-- 案例示例、监控、DB 仪表盘等）。这里仅置 hidden=true，使前端
-- 侧栏不渲染，不删除数据、不破坏权限标识，便于后续按需恢复。
--
-- 匹配方式：按 route_path 前缀（比 id 稳定，跨环境一致）。
-- superuser 走 bypass，隐藏后超管侧栏同样不可见。
-- ============================================================

-- 1) 隐藏整棵子树：接口管理 / 代码管理 / 应用管理 / AI 管理 / 案例管理 / 监控管理
--    （顶级目录及其下所有子菜单/按钮，route_path 均以对应前缀开头）
UPDATE sys_menu
SET hidden = true, updated_time = now()
WHERE route_path LIKE '/common/%'
   OR route_path LIKE '/generator/%'
   OR route_path LIKE '/application/%'
   OR route_path LIKE '/ai/%'
   OR route_path LIKE '/example/%'
   OR route_path LIKE '/monitor/%';

-- 2) 隐藏以上各顶级目录自身（目录行 route_path 不带尾部段）
UPDATE sys_menu
SET hidden = true, updated_time = now()
WHERE route_path IN ('/common', '/generator', '/application', '/ai', '/example', '/monitor');

-- 3) 隐藏 DB 下发的「仪表盘」目录及其子菜单
--    （前端已有静态首页 / 仪表盘壳层，DB 这份重复）
UPDATE sys_menu
SET hidden = true, updated_time = now()
WHERE route_path IN ('/dashboard', '/dashboard/workplace', '/dashboard/analysis', '/dashboard/screen');
