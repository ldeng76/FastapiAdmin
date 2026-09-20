# Issue 27: 统一 `is_placeholder` 语义并收敛三中心方向

## Parent

[事故复盘 §11.7 更正记录 —— 未决问题 2](../findings/incident-20260920-test-cascade-delete.md)

## What to build

**同一个结构，三个中心，三种状态** —— 全部是「影像灌库按目录建的 stub 患者：demographics
全空、但名下有真实 DICOM 数据」：

| 中心 | 患者 | is_placeholder 现状 | 名下数据 | 既有 issue 的方向 |
|---|---:|---|---|---|
| zhujiang | 74,450 | 全 TRUE | 19 TB | （导入脚本显式写 TRUE，无 issue） |
| xinqiao | 49,664 | 全 TRUE | 4 TB | [issue-15](./issue-15-xinqiao-placeholder-realization.md) / [issue-26 v2](./issue-26-xinqiao-placeholder-realization-v2.md) 待翻 FALSE |
| shengyi | 82,682 | 全 FALSE | 15 TB | [issue-9](./issue-9-fix-shengyi-placeholder-flag.md) 待翻 TRUE |

zhujiang 与 xinqiao 同结构却方向相反，shengyi 又是第三方向。**在语义统一前，
issue-9 / issue-15 / issue-26(v2) 都不应执行** —— 否则要么把真实数据患者标成占位
（dashboard 排除占位后他们会"消失"），要么三个中心永远互相矛盾。

**本 issue 做三件事**：

1. **决策**：`is_placeholder` 到底指什么。两个候选：
   - **身份型**（0018 migration 现规则）：`sex='0'` 且 8 个人口学列全 NULL ⇒ 占位。
     后果：三中心影像 stub 全部 TRUE，排除占位的 dashboard 患者数大幅下降
     （shengyi 169,820 → 87,138）。
   - **数据型**（推荐）：名下**无任何业务数据**（影像字节 / 临床行皆无）才 ⇒ 占位。
     后果：shengyi 82,682 维持 FALSE，xinqiao 翻 FALSE（与 issue-15/26v2 同向），
     zhujiang 74,450 需要翻 FALSE —— 这是 zhujiang 方向的反转，影响面必须先评估。
     推荐理由：占位的本意是"这行患者不是真人/没有数据"；名下挂着真实字节的患者
     被标占位，任何排除占位的视图都会制造"数据消失"的事故观感。且第五组
     issue-26 v2（人口学回填 → 翻 FALSE）已经隐含数据型语义，本决策为其前置确认。
2. **消费方审计**：grep 全仓 `is_placeholder` 的全部使用点
   （`build_patient_filters` / `stats_query` / 视图 / API / 前端），逐个标注决策后的
   行为变化，形成清单。已知消费点：`backend/app/plugin/module_medical/hospital/stats_query.py`
   的 `exclude_placeholders`、`_not_deleted_patient`。
3. **落库 + 修订既有 issue**：按决策对三中心执行 backfill（备份表先行、可回滚），
   并把 issue-9 / issue-15 / issue-26(v2) 的 PRD 改写到与决策一致（或显式标注
   「方向由本 issue 修订」）。

## Acceptance criteria

- [ ] 语义决策落成 ADR（`docs/adr/` 已有 0001~0011，新增一篇），含两个候选的取舍论证
- [ ] `is_placeholder` 消费方审计清单：每个使用点 × 决策后的行为变化，写入 ADR 或 findings
- [ ] 三中心 backfill 前有备份表（沿用 `p_shengyi_placeholder_bak` 模式），rollback 验证通过
- [ ] 落库后分布断言：`SELECT center_code, is_placeholder, COUNT(*) FROM lnrs.lnrs_anon_patient GROUP BY 1,2` 符合决策（目标分布写死在测试或 verify SQL 里）
- [ ] **dashboard 患者总量变化预评估**：决策前后各中心「患者总量」对照表（排除/不排除占位两种口径）写入 commit message —— 这是用户可见变化，不能偷袭
- [ ] issue-9 / issue-15 / issue-26(v2) 的 PRD 已按决策更新方向（或在文件头标注「方向由本 issue 修订」）
- [ ] 沙箱（`ENVIRONMENT=test`）上先演练 backfill 全流程，真库执行放最后一步
- [ ] 决策落地前**不修改任何一行的 is_placeholder**

## Blocked by

None - can start immediately.

## Notes for implementer

- **这是产品决策 + 数据迁移的复合 issue**：ADR 没写完之前不许动数据。
- 与第五组 [issue-26 v2](./issue-26-xinqiao-placeholder-realization-v2.md) 的关系：
  它的「数据源 / 范围」两个决策门按其自身流程走用户确认，但**翻 FALSE 这个总方向**
  应在本 ADR 决策后复核一遍 —— 若最终决策是身份型，它要整体重设计。
- zhujiang 的 TRUE 是本仓 zhujiang v2 灌库脚本显式写的（`is_placeholder=TRUE` 显式）——
  若决策为数据型，zhujiang 的翻转量（~74,450 行）是三中心最大，回滚脚本必须先演练。
- issue-9 的脚本（`backfill_shengyi_patient_placeholder.py`）本身可复用，但方向可能要反过来；
  **修订 PRD 而不是删掉**，保留轨迹。
- 0018 migration 的身份型规则若被放弃，需同步注明 0018 的规则归档去向，避免下一个
  新表又按旧规则打标。