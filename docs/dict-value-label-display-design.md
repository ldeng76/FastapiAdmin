# 字典 value↔label 前端显示方案

> 通用需求：前端界面显示 `dict_label`，数据库存 `dict_value`。
> 本文给出贴合本项目现状的落地方案，不另起炉灶。

关联：
- 医疗专用映射见 [ADR-0008 dict value mapping](./adr/0008-dict-value-mapping.md)（后端 ETL 阶段归一化，前端不感知）。
- 脱敏落库见 [ETL-2 脱敏流水线](./etl2_anon_pipeline.md)。

---

## 1. 现状盘点（已有，无需重建）

| 层 | 现状 | 位置 |
|---|---|---|
| **DB** | `sys_dict_type` + `sys_dict_data`，存 `dict_value` / `dict_label` / `css_class` / `list_class` | `backend/app/api/v1/module_system/dict/model.py` |
| **后端 API** | `DictAPI.getInitDict(type)` 按类型拉取 | `frontend/web/src/api/module_system/dict.ts` |
| **前端 Store** | `dict.store.ts`：`getDict(types[])` 批量拉取 + localStorage 持久化、`getDictArray(type)`、`getDictLabel(type,value)` 返回完整字典项 | `frontend/web/src/store/modules/dict.store.ts` |
| **现有用法** | `views/module_system/notice/index.vue:198` 用 `dictStore.getDictLabel(...)`，表格列走 `formatter` | — |

**结论**：数据流已打通，缺的不是机制，而是**一层薄封装**让调用处更省事、显示更统一（带颜色 Tag）。

---

## 2. 标准做法（通用模式）

无论技术栈，`value↔label` 套路固定三件事：

1. **存**：DB 只存 `dict_value`（稳定、可索引、国际化无关）。
2. **取**：前端进入页面时按 `dict_type` 一次性拉取并缓存成 `{ value: {label, tagType} }` 的 Map，后续翻译零网络。
3. **显**：三种显示场景统一走同一份缓存——表单下拉、表格列、详情/Tag。

**核心原则**：单一数据源（store）+ 三种消费形态（select / formatter / tag）。

---

## 3. 落地方案（推荐）

在现有 `dict.store.ts` 之上补两个薄封装，改动量小。

### 3.1 架构

```
dict.store.ts (已有：缓存 + getDictLabel / getDictArray)
        │
        ├── useDict.ts        (新增：响应式 hook，声明依赖 + 触发拉取)
        ├── DictTag.vue       (新增：带颜色 Tag，消费 list_class / css_class)
        └── v-dict 指令        (新增，可选：模板里零脚本翻译)
```

### 3.2 `useDict` hook（核心）

解决每页手写 `getDict` + `getDictLabel()?.dict_label` 的啰嗦。

```ts
// frontend/web/src/hooks/useDict.ts
import { useDictStoreHook } from "@/store/modules/dict.store";

/**
 * 声明本组件用到的字典类型，自动按需拉取并缓存。
 * store 内部已去重 + localStorage 持久化，这里只触发。
 */
export function useDict(...types: string[]) {
  const store = useDictStoreHook();
  store.getDict(types).catch(() => {});

  /** value → label（纯文本，找不到回退原值，空值显示 —） */
  const label = (type: string, value: string | null | undefined) => {
    if (value === null || value === undefined || value === "") return "—";
    return store.getDictLabel(type, String(value))?.dict_label ?? value;
  };

  /** value → 完整字典项（给 DictTag 取颜色用） */
  const item = (type: string, value: string) => store.getDictLabel(type, value);

  /** 给 el-select 直接 :options */
  const options = (type: string) => store.getDictArray(type);

  return { label, item, options };
}
```

调用处对比：

```vue
<script setup lang="ts">
// 之前：手写两行，还要自己取 .dict_label
const dictStore = useDictStoreHook();
dictStore.getDict(["sys_notice_type"]);
const text = dictStore.getDictLabel("sys_notice_type", val)?.dict_label ?? val;

// 之后：一行声明，直接用
const { label, options } = useDict("sys_notice_type");
</script>
```

### 3.3 `DictTag.vue`（带颜色，统一显示）

`getDictLabel` 已返回 `list_class`/`css_class`，但无组件消费。补一个：

```vue
<!-- frontend/web/src/components/base/DictTag.vue -->
<template>
  <el-tag v-if="row" :type="row.list_class || undefined" :class="row.css_class">
    {{ row.dict_label }}
  </el-tag>
  <span v-else>{{ value ?? "—" }}</span>
</template>
<script setup lang="ts">
import { computed } from "vue";
import { useDict } from "@/hooks/useDict";
const props = defineProps<{ type: string; value?: string | null }>();
const { item } = useDict(props.type);
const row = computed(() => (props.value ? item(props.type, String(props.value)) : null));
</script>
```

### 3.4 表格列 `formatter`（保持项目现有风格）

项目表格用列配置 + `formatter`（见 `notice/index.vue:468`），沿用：

```ts
{
  label: "性别", prop: "sex",
  formatter: (row) => label("sys_user_sex", row.sex),   // 纯文本
}
// 要彩色 Tag：
{
  label: "状态", prop: "status",
  formatter: (row) => h(DictTag, { type: "sys_normal_disable", value: row.status }),
}
```

### 3.5 表单下拉

```vue
<el-select v-model="form.sex">
  <el-option v-for="d in options('sys_user_sex')" :key="d.dict_value"
             :label="d.dict_label" :value="d.dict_value" />
</el-select>
```

---

## 4. 约定与边界

| 场景 | 约定 |
|---|---|
| **空值** | `null` / `""` 一律显示 `—`，不显示空串或 `undefined` |
| **未匹配** | `value` 在字典里找不到 → 显示原 `value`（调试可见），后端日志 warn |
| **多选值** | DB 存逗号串 `"1,2"` → `label()` 支持 split 后逐个翻译再 join，或用 `DictTag` 数组 |
| **缓存刷新** | 字典管理页增删改后调 `clearDictData()` 再 `getDict(...)`（store 已提供） |
| **登录登出** | 登出时清字典缓存（确认 `user.store.ts` 已挂 `clearDictData`） |
| **字典命名** | `dict_type` 一律 `模块_实体_字段`（如 `sys_user_sex`），全小写下划线 |
| **新增字典项** | 走字典管理页，**禁止**硬编码 options 到组件 |

---

## 5. 与 `med_dict_mapping` 的关系（勿混淆）

本项目特有的、易混点：

- **`sys_dict_data`（通用字典）**：平台标准选项，前端显示翻译用它。← 本方案对象
- **`med_dict_mapping`（医疗映射）**：解决"不同医院上报原始文本 `男/Male/1` → 统一标准 `dict_value`"，是 **ETL 入库阶段** 后端 `normalize_service` 的事。前端只看到归一后的标准 `dict_value`，**不感知**这一层。

→ 前端翻译**永远只查 `sys_dict_data`**，`med_dict_mapping` 对前端透明。

---

## 6. 落地步骤

1. 新增 `frontend/web/src/hooks/useDict.ts`
2. 新增 `frontend/web/src/components/base/DictTag.vue`
3. 挑一个真实页面改造为样板（如 `notice/index.vue` 或某医疗列表页）
4. 补 `label()` 的多值 split 支持 + 空值用例

## 7. 验收

- [ ] 任一列表页字典列显示 `dict_label` 而非 `dict_value`
- [ ] 字典管理页改了选项后，列表刷新即生效（缓存被清）
- [ ] 空值显示 `—`，未匹配显示原值
- [ ] 登出后字典缓存清空，换租户不串字典
