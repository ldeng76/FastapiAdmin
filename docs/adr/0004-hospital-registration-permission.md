# ADR 0004: 医院注册权限与 UI 归属

> 状态：已接受
> 日期：2026-07-07

## 背景

医院注册 = 创建租户 = 独立数据域，需要决定操作权限和 UI 模块归属。

## 决策

### 权限：仅平台超级管理员可注册医院

- `is_superuser=1` 的用户才能执行注册操作
- 不在通用租户管理的权限范围内（通用租户管理是 `tenant:create` 权限）
- 医院注册 API 使用独立的权限点 `hospital:create`

### UI：新建独立医院管理模块

- 模块路径：`module_medical/hospital/`
- 后端：独立 `model + schema + service + controller`
- 内部复用租户服务（调用 `TenantService.create()` 创建对应租户）
- 不包含在通用 `module_system/tenant` 中

**理由：**
- 租户是平台基础设施，医院是业务实体，生命周期不同
- 医院注册流程比通用租户 CRUD 重（模板选择、映射配置、就绪状态）
- 避免非医院类租户被医院语义"污染"
- 医院管理未来持续增长（映射、导入历史、质量报告），独立模块更易维护

## 后果

- 超管在医院管理模块中注册医院 → 系统内部创建对应租户 → 返回 hospital_id + tenant_id
- 租户管理模块（`module_system/tenant`）保持不变，仍是纯平台基础管理
- 切换上下文逻辑：前端在已注册的医院列表中选择当前激活医院 → 后续请求携带 `X-Tenant-Id` header 或 JWT 中的 active_tenant_id 字段
