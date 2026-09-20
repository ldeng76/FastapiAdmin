# ADR 0012: `is_placeholder` 采用数据型语义（无业务数据才为占位）

> 状态：已接受
> 日期：2026-09-20
> 关联：[ADR 0011](./0011-anon-patient-is-placeholder.md)（部分修订，见 §6）、
> [issue-27](../etl2/prd/issue-27-unify-placeholder-semantics.md)、
> [事故复盘 §11.7](../etl2/findings/incident-20260920-test-cascade-delete.md)
> 实施：`backend/etl2/backfill_placeholder_data_semantics.py`（三中心 backfill）+
> `anon_etl_engine.py` 写入语义更新

## 1. 背景

同一个结构，三个中心，三种 `is_placeholder` 状态 —— 全部是「影像灌库按目录建的
stub 患者：demographics 全空、但名下有真实 DICOM 数据」：

| 中心 | 患者 | is_placeholder 现状（2026-09-20 dev 实测） | 名下数据 |
|---|---:|---|---|
| zhujiang | 74,450 | 全 TRUE | 19 TB |
| xinqiao | 49,664 | 全 TRUE | 4 TB |
| shengyi | 169,820 | 全 FALSE | 15 TB |

ADR 0011 / migration 0018 的规则是**身份型**：`sex='0'` 且 8 个人口学列全 NULL
⇒ 占位。该规则下 zhujiang/xinqiao 的影像 stub 全部是「占位」，而 shengyi 同结构
stub 全部不是 —— 语义互相矛盾；issue-9 / issue-15 / issue-26(v2) 各自按不同方向
翻标志，会在矛盾上叠加矛盾。

## 2. 两个候选

### 候选 A：身份型（0018 现规则）

`sex='0'` 且人口学全空 ⇒ 占位。

- 优点：与 ADR 0011 的原始动机（患者列表「未知的性别」泛滥）直接对齐；
  判定不依赖业务表 JOIN。
- 后果：三中心影像 stub 全部 TRUE；排除占位的 dashboard 患者数大幅下降
  （shengyi 当时 169,820 全部翻 TRUE，排除后只剩有档案的极少数）。
  **名下挂着 19 TB / 4 TB / 15 TB 真实字节的患者被标占位**，任何排除占位的视图
  都会制造「数据消失」的事故观感 —— 正是 2026-09-20 事故的同款观感。

### 候选 B：数据型（本 ADR 采用）

名下**无任何业务数据**（影像字节 / 临床行皆无）才 ⇒ 占位。
判定：患者行在 12 张业务子表（exam / visit / visit_detail / surgery / lab_result /
order / diagnosis / clinical_document / medical_history / vital_observation /
exam_file / imaging_study）中**均无引用行** ⇒ TRUE。

- 后果（2026-09-20 实测）：
  - shengyi 169,820 全部有业务数据 → 维持 FALSE（0 行翻转）；
  - xinqiao 49,664 全部有影像数据 → TRUE 翻 FALSE；
  - zhujiang 74,450 全部有影像数据 → TRUE 翻 FALSE；
  - 合成中心 ph_bak_*（测试残留）5 行无数据 → 维持 TRUE。
- 与 issue-26 v2（人口学回填 → 翻 FALSE）同向；该单「翻 FALSE」总方向由本 ADR
  确认成立，其自身两个决策门（数据源 / 范围）仍按其流程走用户确认。

## 3. 决策

**采用候选 B（数据型）**。理由：

1. 占位的本意是「这行患者不是真人 / 没有数据」。挂真实字节的患者被标占位，
   排除占位的视图必然少计大量真实数据 —— 语义性错误，不是口径偏好。
2. 用户的检索入口是数据（检查、影像）；人口学是否齐全属于数据质量维度，
   应由「人口学待补」之类的独立口径表达，而不是劫持「占位」标志。
3. issue-26 v2 的回填→翻 FALSE 已隐含数据型语义，本决策是其前置确认。

**身份型规则的归档去向**：0018 migration（`backend/sql/postgres/
0018-anon-patient-is-placeholder.sql`）与 alembic `h8c9d0e1f2a3` 的回填 UPDATE
**就此废弃、不再复跑**（历史环境已应用过，列本身保留）。两文件头部已加注记
指向本 ADR。下一个新表/新脚本**禁止**再按「sex='0' 且人口学全 NULL」打标。
「人口学是否齐全」如需口径，另立列或另立查询（不在本 ADR 范围）。

**写入路径语义**（`_batch_upsert_patients`）：

- exam/visit/lab/order 等导入路径的自动发号建档：患者**必然有引用行**
  （正是这些行触发了建档）⇒ 落库 `is_placeholder = FALSE`（原为 TRUE）。
  「不覆盖已有人口学」的 ON CONFLICT 行为保持不变 —— 该行为保护的是
  patient.parquet 先写入的真实档案，与占位标志解耦。
- 完整档案（patient.parquet）路径：本来就写 FALSE，不变。
- 结论：**正常导入路径今后不再产生任何 TRUE 行**；TRUE 只会出现在
  真正的孤立患者行上（如手工误建、测试残留）。

## 4. 消费方审计清单

全仓 grep `is_placeholder`（排除 etl1 脚本里同名不同义的 nodule 占位行标志，
见 §7），逐点标注决策后的行为变化：

| # | 消费点 | 现行为 | 决策后变化 |
|---|---|---|---|
| 1 | `stats_query.py::_build_patient_filters`（患者列表默认过滤） | 默认排除占位（`is_placeholder=FALSE`），按 patient_id 搜索时放行 | zhujiang/xinqiao 的 12.4 万 stub 患者进入默认列表（此前被隐藏）。前端本就传 `is_placeholders:true`，实际列表无感 |
| 2 | `stats_query.py::StatsQuery._conditions`（`exclude_placeholders` 子查询） | KPI/维度统计默认排除占位 | **患者总量等 KPI 大幅上升**（见 §5 预评估表）—— 用户可见，已预评估 |
| 3 | `anon_medical_query.py::PATIENT_LIST_COLS` | 出参携带 `is_placeholder` 字段 | 不变；行内「占位」标签今后只标真正孤立行 |
| 4 | `stats_schema.py::StatsFiltersIn.is_placeholders` | 查询参数，默认 False | 不变 |
| 5 | `patient_controller.py` 文档串 | 列出可过滤字段 | 不变 |
| 6 | 前端 `patient/index.vue` / `dashboard/index.vue` | 检索显式传 `is_placeholders: true`（包含占位） | 不变（两中心 stub 由「仅在包含模式可见」变为「默认可见」） |
| 7 | 前端 `patient.ts` / `patient/detail.vue` | 行内标记字段 | 不变 |
| 8 | `anon_etl_engine.py::_batch_upsert_patients`（`is_placeholder=True` 调用 ×9） | 自动建档写 TRUE | **改为写 FALSE**（§3）；冲突时不覆盖人口学的行为不变 |
| 9 | `stage_promote.py` patient promote | DO UPDATE 不触碰 `is_placeholder`；INSERT 沿用 stage 行值 | 不变；stage 行来自 prod 拷贝，回填后即 FALSE |
| 10 | migration 0018 / alembic `h8c9d0e1f2a3` 回填 UPDATE | 身份型回填 | **废弃归档**（§3），头部加注记，禁止复跑 |
| 11 | `backfill_shengyi_patient_placeholder.py`（issue-9 脚本） | 身份型方向翻 TRUE | 方向作废；保留文件作轨迹，由 `backfill_placeholder_data_semantics.py` 取代 |
| 12 | `tests/anon_etl/test_anon_patient_placeholder.py` | 锁定「占位 upsert 写 TRUE」契约 | 契约更新为「自动建档写 FALSE + 不覆盖人口学」 |
| 13 | `etl1_adapt_zhujiang_ct_2025.py` / `etl1_adapt_xinqiao_ct.py` 的 `is_placeholder` | **同名不同义**：nodule 占位行标志（DataFram 维表内） | 无关，不改 |

## 5. dashboard 患者总量预评估（dev 实测 2026-09-20）

口径：`deleted_at IS NULL`。排除占位 = 现有 `exclude_placeholders` 默认行为。

| 中心 | 总行数 | 排除占位（前） | 排除占位（后） |
|---|---:|---:|---:|
| zhujiang | 74,450 | **0** | 74,450 |
| xinqiao | 49,664 | **0** | 49,664 |
| shengyi | 169,820 | 169,820 | 169,820 |
| **合计** | 293,934 | **169,820** | **293,934** |

- 后变化：dashboard 患者总量 **169,820 → 293,934（+124,114，+73%）**。
  这不是数据新增，是此前被排除的 zhujiang/xinqiao 影像 stub 回归统计口径。
- 不排除占位口径：前 293,934 → 后 293,934，**不变**。
- zhujiang/xinqiao 名下影像字节数（19 TB / 4 TB）本就不受占位过滤影响
  （字节口径走 imaging_study/dicom_series），前后不变。

## 6. 对 ADR 0011 的修订

- §2「回填规则」与 §3 upsert 翻转语义中的**身份型判据**由本 ADR 取代；
  0011 的其余部分（显式列而非查询期推断、API/前端默认隐藏机制）继续有效。
- 0011 中「占位 = exam/visit/surgery 导入自动发号」的表述在本 ADR 下不再成立：
  自动发号建档的患者有名下数据，不是占位。列表默认隐藏机制保留，
  但今后实际被隐藏的只有真正孤立的行（预计接近 0）。

## 7. 命名撞车说明

`etl1_adapt_*` 脚本里的 `is_placeholder` 指 **nodule 占位行**（肺结节列表里
`nodules` 为空时生成的 n0 行），与本 ADR 的患者占位完全无关，仅名字相同。

## 8. 回滚

backfill 脚本按「备份表先行、可回滚」实现（沿用 `p_shengyi_placeholder_bak`
模式）：apply 前建 `lnrs.lnrs_anon_patient_bak_ph_<ts>`（patient_id, is_placeholder），
rollback 按备份表原值还原。真库执行前先在沙箱库（`ENVIRONMENT=test`，
`lnrs_dev`）全流程演练含 rollback。
