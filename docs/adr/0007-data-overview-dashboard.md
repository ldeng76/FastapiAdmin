# 数据概览仪表板 · 设计共识

> **文档性质**：需求设计讨论后的共识记录（非技术实现方案）
> **面向对象**：开发团队 / 客户决策层
> **生成日期**：2026-07-21
> **关联背景**：肺结节研究系统的 ETL2 脱敏数据已落库 PostgreSQL（`lnrs_anon_*` 表），需要为医学研究者提供一个"一进来就看到数据量级和丰富维度"的概览仪表板。

---

## 一、核心定位

仪表板的使命是让**医学研究者 / 算法工程师**登录后第一眼就看到：

> "这里有 30 万患者、45 万检查、覆盖 3 个中心、4 种模态 — 数据够丰富，可以做建模。"

这是一个**数据信心入口**，不是数据探索工具（那是后续阶段的工作）。

---

## 二、设计决策

### 决策 1：受众

**结论**：医学研究者 / 算法工程师

**理由**：参照需求文档的阶段 1 MVP 流程 A→B→C→D，研究者在 B（多模态数据选择）阶段要决定"选哪些模态来建模"。仪表板帮他判断数据基础是否充足。

---

### 决策 2：数据源

**结论**：**仅使用 `lnrs_anon_*` 脱敏表**，不使用 `med_*` 统一表。

**理由（合规约束）**：
- `med_*` 表含未脱敏数据（明文 patient_id、病理诊断自由文本等），直接查询展示有数据合规风险
- `lnrs_anon_*` 是 ETL2 脱敏后的产物，字段虽少但可用于聚合统计

**可用字段**：

| 表 | 可用字段 | 可用维度 |
|---|---|---|
| `lnrs_anon_patient` | `birth_date`, `sex`, `center_code` | 年龄分布、性别比、中心分布 |
| `lnrs_anon_exam` | `exam_type`, `exam_date` | 模态检查量、时间趋势 |

### 决策 3：展示维度

**结论**：当前展示 5 个维度，不包含临床特征。

| 维度 | 来源字段 | 图表类型 | 意义 |
|---|---|---|---|
| 年龄分布 | `birth_date` | 柱状图（8 段分桶） | 样本覆盖的年龄段 |
| 性别比 | `sex` | 环形饼图 | 类别均衡性 |
| 中心分布 | `center_code` | 横向柱状图 | 多中心泛化性 |
| 模态检查量 | `exam_type` | 饼图 | 各模态数据丰富度 |
| 检查时间趋势 | `exam_date` | 折线图 | 数据时间跨度 |

**明确不做**：
- ❌ 临床特征覆盖度（结节密度、长径、病理诊断、Ki-67 等）— 需要 `med_*` 表
- ❌ 病理标签分布（金标准标签）— 需要 `med_*` 表
- ❌ 特征交叉组合（"影像+病理"队列）— 需要 `med_*` 表

### 决策 4：扩展性设计

**结论**：同时预留"新维度加入"和"新筛选条件"的扩展能力。

API 返回结构从"固定字段"改为"维度数组 + filters"：

```json
{
  "filters": {
    "center": {"applied": null, "options": ["zhujiang", "xinqiao", "shengyi"]},
    "year_range": {"applied": null, "options": {"min": 2015, "max": 2025}}
  },
  "kpis": [
    {"key": "total_patients", "label": "患者总量", "value": 300000, "format": "number"},
    {"key": "total_exams", "label": "检查总量", "value": 450000, "format": "number"},
    {"key": "center_count", "label": "来源中心", "value": 3, "format": "number"},
    {"key": "modality_count", "label": "检查模态", "value": 5, "format": "number"}
  ],
  "dimensions": [
    {"key": "age_distribution", "label": "年龄分布", "chart_type": "bar", "data": [...]},
    {"key": "gender_ratio", "label": "性别比", "chart_type": "pie", "data": [...]},
    {"key": "center_distribution", "label": "中心分布", "chart_type": "h-bar", "data": [...]},
    {"key": "modality_counts", "label": "模态检查量", "chart_type": "pie", "data": [...]},
    {"key": "exam_trend", "label": "检查时间趋势", "chart_type": "line", "data": [...]}
  ]
}
```

**扩展方式**：
- 新增维度 → 后端在 `dimensions` 数组中加一条，前端按 `chart_type` 自动选组件
- 新增筛选 → 后端在 `filters` 中加一个 option，前端自动生成筛选控件

### 决策 5：前端图表渲染

**结论**：显式映射表（`chart_type → Component`）

```typescript
const chartComponents: Record<string, Component> = {
  bar: BarChart,        // 柱状图（年龄分布）
  pie: PieChart,        // 环形饼图（性别比、模态）
  'h-bar': HBarChart,   // 横向柱状图（中心分布）
  line: LineChart,      // 折线图（时间趋势）
  // 未来扩展: 'heatmap': HeatmapChart, 'boxplot': BoxplotChart
}
```

**理由**：职责清晰 — 后端只负责数据，前端负责渲染。新增图表类型时前端加一个组件 + 映射表加一行。

### 决策 6：筛选交互

**结论**：全局筛选 — 一个筛选器影响全部 KPI + 全部维度。

**理由**：最常见的使用场景是"聚焦单一中心"，简单直观。未来如有高级分析需求再扩展。

### 决策 7：性能策略

**结论**：实时查询，不加缓存。

**理由**：30 万行的 `COUNT + GROUP BY` 在 PostgreSQL 上有索引时 <50ms，不需要缓存层。未来数据到千万级再考虑缓存或物化。

### 决策 8：空状态处理

**结论**：前端统一处理。

| 场景 | 表现 |
|---|---|
| 表完全为空 | 显示"暂无数据，请等待 ETL2 导入" |
| 只有 1 个中心有数据 | 正常展示，筛选器只有一个 option |
| 某维度数据缺失 | 该维度显示"暂无数据"占位 |

---

## 三、技术方案概要

### 后端 API

- 容器前缀：`/medical`（自动发现）
- 路由：`GET /medical/statistics/overview`
- 权限点：`module_medical:stats:query`
- 数据源：仅 `lnrs_anon_patient` + `lnrs_anon_exam`

### 前端页面

- 路径：`views/module_medical/dashboard/index.vue`
- 路由：通过后端菜单动态注册（component_path = `module_medical/dashboard/index`）
- 图表库：ECharts 6（已安装）
- 布局：KPI 卡 + 图表卡片（响应式 grid）

### 文件清单

**后端**：

| 文件 | 说明 |
|---|---|
| `app/plugin/module_medical/hospital/stats_query.py` | 聚合查询层（仅查 lnrs_anon_* 表） |
| `app/plugin/module_medical/hospital/stats_schema.py` | Pydantic 出参 schema |
| `app/plugin/module_medical/hospital/stats_service.py` | Service 层 |
| `app/plugin/module_medical/hospital/stats_controller.py` | API 路由定义 |
| `app/plugin/module_medical/hospital/controller.py` | 更新：include_router(StatsRouter) |
| `app/alembic/versions/d4e5f6a7b8c9_add_medical_stats_menu.py` | 菜单迁移 |

**前端**：

| 文件 | 说明 |
|---|---|
| `src/api/module_medical/statistics.ts` | API 客户端 |
| `src/types/module_medical/hospital.ts` | TS 类型定义 |
| `src/views/module_medical/dashboard/index.vue` | 仪表板主页 |
| `src/views/module_medical/dashboard/components/KpiCard.vue` | KPI 卡片组件 |

---

## 四、风险与限制

1. **数据维度的天花板**：当前仅依赖 `lnrs_anon_*` 脱敏窄表，只能展示 demographics + 检查类型层面的统计，无法展示临床特征分布。若未来需要，需扩展 ETL2 写入逻辑，把临床特征脱敏后写入 `lnrs_anon_exam_finding` 表。

2. **数据实时性**：仪表板反映的是最近一次 ETL2 导入的快照，不是实时数据。ETL2 跑完一次后仪表板才会更新。

3. **筛选条件暂未实现**：API schema 已预留 `filters` 结构，但当前版本不实现筛选控件，只返回可选 options。

---

## 五、下一步

- [ ] 按最终 API 结构重构现有后端代码（固定字段 → 维度数组 + filters）
- [ ] 按维度数组重构前端 dashboard 页面（支持动态渲染）
- [ ] 运行 `alembic upgrade head` 创建菜单项
- [ ] 验证：登录后能看到真实数据渲染的仪表板

---

> **文档维护**：本文件记录设计共识，不随实现细节变更而频繁修改。如设计决策发生变更，应更新本文档并注明变更原因。
