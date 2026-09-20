# Issue 28: medicalFiles 统计口径修复 —— 倒挂、筛选器字典、文件数真实性

## Parent

[事故复盘 §11.7 更正记录 —— 未决问题 1](../findings/incident-20260920-test-cascade-delete.md)

## What to build

medicalFiles 统计页（`/medicalFiles`）当前有三个相互纠缠的口径问题，用户已实际踩中：

1. **患者数倒挂**：同页「患者数」= imaging 口径 82,988，「有检查记录的患者数」=
   exam 口径 66,635 —— "总数"比子集小。根源是 `fa0761bc` 把「总患者数」从
   `lnrs_anon_patient` 切到 `lnrs_anon_exam`，而省医 exam 世界与影像世界几乎不相交
   （exam∩imaging = 219/82,988）—— KPI 计的人群基本不拥有页面列出的文件。
2. **筛选器字典虚胖**：`med_exam_type` 字典 29 值，省医 exam 表实际只有 10 种模态；
   「全选 N 种」与「不选」在 SQL 上语义不同（`IN(...)` vs 无过滤），用户预期两者等价。
3. **文件数失真**：省医 imaging_study 全部 82,994 条 sop_count=0（灌库脚本未数 SOP，
   series 层却有真实字节），`file_count` 公式（record_count + Σ(series_count−1)）
   对省医不成立。

**修法**（总患者数口径依赖 issue-27 的语义决策，故本 issue 排在其后）：

- 「总患者数」回**患者主数据口径**，与 medicalDashboard「患者总量」**同源同值**
  （同一 SQL 写进代码注释；实测省医主数据全集 = 影像∪临床十表并集，无空壳，
  所以主数据口径不虚高）。exam 口径保留为「有检查记录的患者数」并保持标签自描述。
  若 issue-27 决策为身份型且 dashboard 排除占位，则对齐目标改为「排除占位后的全集」，
  两页仍须同源。
- 筛选器下拉裁剪到「该中心 exam 实际存在的 exam_type」（或无数据项禁用 + 计数 0），
  并保证「全选」与「不选」行为等价、有测试钉住。
- 省医 sop_count 回填（= Σ `dicom_series.file_count`，仅动 shengyi），回填后复核
  file_count 公式；真实零文件目录（若有）才允许 sop_count=0。

## Acceptance criteria

**倒挂**

- [ ] 「总患者数」≥「患者数」在**全部中心 × 全部筛选组合**下恒成立（verify SQL 断言）
- [ ] 「总患者数」与 medicalDashboard「患者总量」同源：两处 SQL 逐字相同（或互为引用的同一函数），写进代码注释
- [ ] 页面三个患者数字段（患者数 / 有检查记录的患者数 / 总患者数）标签两两互斥、各自自描述，tooltip 同步更新

**筛选器**

- [ ] 下拉候选与数据中心实际存在的 `exam_type` 一致（裁剪或禁用置灰 + 显示 0）
- [ ] 「全选」与「不选」返回完全相同的 KPI（测试钉住：同 payload 两请求 diff = 0）

**文件数**

- [ ] 省医 sop_count 回填完成：回填后 sop_count=0 的 study 仅剩真实零文件目录（回填前后对照数字写入 commit message）
- [ ] 回填前建备份表（`lnrs_anon_imaging_study_bak_*` 模式），rollback 验证通过
- [ ] `file_count` 公式对省医成立：`file_count ≥ record_count` 且与 series 层实测一致（verify SQL）
- [ ] 本 issue 产生的所有写库走既有 ad-hoc 脚本通道并遵守其安全闸（若 issue-21 已落地）

## Blocked by

- [Issue 27](./issue-27-unify-placeholder-semantics.md)（「总患者数」的对齐目标 —— 排不排除占位 —— 取决于其语义决策）

## Notes for implementer

- **不要**把「总患者数」做成 10 表并集实时查询 —— 主数据口径已足够（并集=全集实测相等）；
  未来若并集 < 全集再引入物化视图。
- exam∩imaging = 219 这个数字在 [issue-1](./issue-1-backfill-imaging-study-exam-id.md) 出现过
  （219/82,988），本 issue 修的是展示口径，**不要**试图用回填 exam 行的方式"修数据"
  —— 那是 [issue-29](./issue-29-shengyi-exam-imaging-linkage.md) 的调研结论决定的事。
- sop_count 回填用一条 SQL（join dicom_series 聚合）即可，但**先在沙箱演练**
  （`cd backend && ENVIRONMENT=test uv run pytest tests/anon_etl/`），真库执行放最后。
- 2026-09-20 的十表探针数据与结构图见复盘 §11.7，写 verify SQL 时直接对照。