# ADR 0009: 平台租户常量化与字典共享策略

> 状态：已接受
> 日期：2026-07-23
> 关联：ADR 0001（医院即租户）、ADR 0008（医疗字典与值级映射）

## 背景

本项目的多租户架构中，`tenant_id=1` 长期被用作"平台级公共数据"的标识（系统字典、系统配置、平台默认数据等）。这个 magic number 散布在代码各处：

- `base_model.py` — `TenantMixin` 的 `default=1`
- `base_crud.py` — 租户隔离逻辑中 `tid != 1` / `tenant_id == 1` 的比较
- `dict/controller.py` / `params/controller.py` — 前端字典/配置 API 写死 `tenant_id=1`
- `dict/service.py` / `params/service.py` — `get_init_dict_service(tenant_id=1)` 默认值
- 种子 JSON — 所有条目硬编码 `"tenant_id": 1`

这些代码的含义完全依赖隐式约定——没有常量、没有校验、没有文档。OCR 代码审核将其标记为 HIGH 问题。

## 决策

### 1. 引入 `PLATFORM_TENANT_ID` 常量

在 `app/common/constant.py` 定义：

```python
PLATFORM_TENANT_ID: int = 1
```

全局替换所有 hardcoded 的 `1`（共 11 处代码 + 3 处 docstring）。grep `PLATFORM_TENANT_ID` 即可定位所有"平台数据"引用点。

**不修改种子 JSON**：JSON 无法引用 Python 常量，但在 JSON 文件头注释中说明 `"tenant_id": 1` 的含义。

### 2. 启动时校验平台租户存在

在 `init_app.py` 的 `lifespan` 中、`init_db()` 之后加校验：

```python
async with async_db_session() as session:
    platform_tenant = (await session.execute(
        sa_select(TenantModel).where(TenantModel.id == PLATFORM_TENANT_ID)
    )).scalars().first()
    if not platform_tenant:
        raise RuntimeError(
            f"平台租户(id={PLATFORM_TENANT_ID})不存在，"
            "请先初始化 sys_tenant 表。"
        )
```

将"id=1 必须是平台租户"的隐式约定变成**可检测的不变量**。

### 3. 平台字典共享策略

- **医疗字典（`med_sex` / `med_exam_type` / `med_laterality` 等）统一挂载在 `tenant_id=PLATFORM_TENANT_ID` 下**。这是刻意决策：医疗标准字典是全平台统一标准，不应按医院差异化。

- **通过 `__platform_data_shared__` 机制共享读取**。`DictTypeModel` 和 `DictDataModel` 均标注 `__platform_data_shared__ = True`，`base_crud.py` 在读操作时自动放开 `PLATFORM_TENANT_ID` 的过滤，让所有租户都能读到平台字典。

- **写入操作仍按租户隔离**。只有平台管理员（超管）可写 `PLATFORM_TENANT_ID` 的数据。

### 4. 预留租户私有字典复制机制

`TenantService.clone_platform_dict_to_tenant(db, target_tenant_id)` 方法实现了平台字典到目标租户的幂等复制：

- 复制 `sys_dict_type`（按 `(tenant_id, dict_type)` 唯一约束去重）
- 复制 `sys_dict_data`（保留 `dict_type_id` 关联）
- 幂等：已存在的条目跳过
- 调用方负责 commit

这激活了 `UniqueConstraint("tenant_id", "dict_type")` 预留的多租户能力，供"某医院需要私有字典副本"的场景使用。本轮不暴露 controller 端点，仅建服务层骨架。

## 后果

- **正向**：magic number 消除，平台数据引用点可 grep 定位；启动校验防止"清库重建后 id=1 不是平台租户"的隐患；预留了租户私有字典的扩展路径。
- **中性**：种子 JSON 中 `tenant_id: 1` 不变（JSON 无法引用常量），通过文档和注释说明含义。
- **风险**：`clone_platform_dict_to_tenant` 尚无 controller 端点，若需在管理界面使用需后续补 API。
