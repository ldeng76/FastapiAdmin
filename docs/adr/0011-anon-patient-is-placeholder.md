# ADR 0011: 占位患者标记 is_placeholder 与患者列表默认隐藏

> 状态：已接受
> 日期：2026-09-07
> 实施：`backend/sql/postgres/0018-anon-patient-is-placeholder.sql` + `alembic h8c9d0e1f2a3` + `anon_etl_engine.py` / `anon_medical_query.py` / `patient_controller.py` / 前端 `patient/index.vue`

## 背景

患者档案 → 患者列表中，约 59% 患者性别显示「未知的性别」。根因排查（2026-09-07，dev PG 实测）：

| 中心 | 患者总数 | sex='0' | 占位患者 | 真实档案性别缺失 |
|---|---:|---:|---:|---:|
| zhujiang | 86,301 | 79,577 | 79,577（0719 CT 批次 66,597 + 0825 批次 12,980） | 0 |
| xinqiao | 49,563 | 49,563 | 49,563（无 patient 表） | 0 |
| hos301 | 8,350 | 8,350 | 8,350（无 patient parquet） | 0 |
| shengyi | 87,138 | 1 | 0 | 1（PT_00282376） |
| **合计** | **231,352** | **137,491** | **137,490** | **1** |

**根因**：ETL2 引擎（`_batch_upsert_patients(is_placeholder=True)`）导入 exam/visit/surgery 表时，对无档案患者自动发号创建占位记录（sex 恒 '0'、无人口学）以保证 FK 完整——这是 ADR-0006/导入流水线的**有意设计**。但患者列表 API（`anon_list_patients`）不区分占位与真实档案，全部展示，导致「未知的性别」泛滥。字典映射链路本身无丢失（`med_dict_unmatched` 为空，zhujiang 档案 6,714 人 sex 全部命中）。

## 决策

### 1. 显式列 `is_placeholder`（而非查询期推断）

`lnrs_anon_patient` 加 `is_placeholder BOOLEAN NOT NULL DEFAULT FALSE`。不用查询期推断（"sex='0' 且无人口学"），原因：

- 语义固化在写入路径，查询无需重复推断逻辑；
- 避免误判边缘真实档案（如 shengyi PT_00282376 这类"性别真缺失"的档案）；
- 数据量 23 万行，布尔列过滤成本低。

### 2. 回填规则（0018 SQL，幂等）

```
sex='0' AND 所有人口学字段 IS NULL
AND (patient_meta IS NULL OR = 'null'::jsonb OR = '{}'::jsonb)
```

命中 137,490 行（与逐批次交叉验证一致）。注意 `patient_meta` 存在 **jsonb 字面量 'null'**（0825 批次引擎写入痕迹，非 SQL NULL），规则需覆盖三种空态。

### 3. upsert 翻转语义（`_batch_upsert_patients`）

| 场景 | 行为 |
|---|---|
| 占位路径新建行 | INSERT `is_placeholder=TRUE` |
| 占位路径撞已有行 | 不动（真实行保持 FALSE，占位行保持 TRUE） |
| 完整档案（patient.parquet）新建行 | INSERT `is_placeholder=FALSE` |
| 完整档案撞占位行 | **翻回 FALSE** + 人口学落库（医院后续补交档案表时自动"转正"） |

### 4. API 与前端默认隐藏

- `GET /medical/patients` 新增 `include_placeholders` 查询参数，**默认 false**（隐藏占位）。
- 出参新增 `is_placeholder` 字段；前端搜索栏加「占位患者」开关（默认关），开启后占位行 patient_id 旁显示「占位」标签。
- **范围限定**：仅患者列表。仪表板（`/medical/statistics/*`：KPI 患者总量、性别/年龄分布等维度）仍含占位患者——统计口径是否排除属独立产品决策，未在本次范围内。

## 验证（2026-09-07，dev）

| 检查项 | 结果 |
|---|---|
| 0018 回填 | ✅ 137,490 / 231,352，幂等复跑跳过 |
| 分布 | ✅ shengyi 0 占位 / zhujiang 79,577 / xinqiao 49,563 / hos301 8,350 |
| 真实档案保护 | ✅ PT_00282376（有 birth_date）保持 FALSE |
| `tests/anon_etl/test_anon_patient_placeholder.py` | ✅ 2 passed（upsert 翻转 + 列表过滤契约） |
| API E2E（admin 登录实测） | ✅ 默认 total=93,862（全非占位）；`include_placeholders=true` total=231,352 且带标记 |
| 前端 `vue-tsc --noEmit --skipLibCheck` | ✅ |
| 全量后端测试 | ✅ 91 passed / 2 skipped（3 个既有失败与本次无关：smoking 归一化测试依赖 dev 库种子、module_ticket 模块已移除、test_main 需服务） |

## 已知遗留（follow-up）

1. **仪表板统计口径**：`StatsQuery`（KPI/维度）未过滤占位，患者总量等指标仍含 13.7 万占位。待产品决策后统一处理（`StatsFiltersIn` 加同名参数即可复用本列）。
2. **jsonb 'null' 写入痕迹**：0825 批次 12,980 行 `patient_meta` 为 jsonb 字面量 'null'（当前代码路径写 SQL NULL）。历史行不影响功能，但"空态"判断需持续覆盖该值。
3. **占位患者详情**：占位行仍可进入多模态详情（有检查/就诊/手术数据可看）——符合"检查驱动建档"预期，未做限制。
