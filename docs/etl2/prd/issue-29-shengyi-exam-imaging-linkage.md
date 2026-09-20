# Issue 29: 省医 exam 世界 × 影像世界关联调研（PACS/RIS 脱节根因）

## Parent

[事故复盘 §11.7 更正记录 —— 未决问题 3](../findings/incident-20260920-test-cascade-delete.md)；[issue-4](./issue-4-investigate-shengyi-exam-gap.md) 的延伸

## What to build

省医的 exam 数据源与 DICOM 归档**几乎是两个人群**：exam∩imaging = **219 / 82,988**。
纯影像人群 82,682 人（15 TB 真实字节）没有任何临床文书行；临床人群的影像需求
在这套归档里基本找不到。**为什么脱节、能不能关联 —— 目前是未知**，本 issue 把它变成
确定答案。

**调研三步**（全部只读，不改任何业务表）：

1. **解剖 219 个交集患者**（最重要的线索）：他们是怎么同时出现在两个世界的 ——
   靠什么键匹配上（patient_id？匿名化前的人工映射？同一患者的两种 ID 恰好同值？）。
   这 219 人是"关联可行性"的活样本。
2. **header ID 审计**：抽样 ≥100 个纯影像患者的 DICOM header（PatientID / 住院号 /
   门诊号等替代键），与 exam 人群的 ID 空间比对匹配率 —— 方法论复用
   [issue-14](./issue-14-zhujiang-study-uid-audit.md) 的 zhujiang 100/100 对账
   （含其 PHI 纪律：header 只进内存，输出只留统计数）。
3. **结论分流**：
   - **可关联**（header ID 命中或存在外部映射表）→ 产出回填 PRD：为纯影像人群补
     exam 行或补 `anon_exam_id` 桥，**走 issue-20/22/23 的 stage+promote 体系**，
     不直写生产；
   - **不可关联**（header 空 / ID 空间正交 / 无映射）→ 根因文档化 +
     UI 标注方案落地（省医影像人群在页面上明确标注"无临床关联数据"类提示）。

## Acceptance criteria

- [ ] 219 个交集患者的关联机制说清楚（匹配键、谁灌的、哪个 batch），写入 findings 文档
- [ ] header ID 抽样 ≥100，匹配率表格（issue-14 同款：匹配/不匹配/header 空三类计数）
- [ ] 根因结论落在 `docs/etl2/findings/` 新文档，链回复盘 §11.7 与 issue-4
- [ ] 按结论分流：回填 PRD（含 stage+promote 路径与回滚）**或** UI/文档标注方案落地
- [ ] 调研过程 `write=0`（pg_stat 断言 exam/patient/imaging_study 十表零写入）
- [ ] header 抽样输出的中间文件不含 PHI（姓名/生日落盘前剔除）

## Blocked by

None - can start immediately.

## Notes for implementer

- **调研独立于 issue-27/28**，可并行；但其结论决定 issue-28 的长期形态 ——
  若关联成功，exam 口径人群会扩大，页面 KPI 标签的措辞要跟着复查一遍。
- 新桥侧的"补全临床面"由第五组平行推进（[issue-25 报告源补全](./issue-25-xinqiao-exam-report-source-completion.md)）；
  本 issue 只管省医，两中心方法论可互参，范围不要混。
- 先查省医灌库脚本（`build_shengyi_imaging_study_index.py`）当年用目录名还是
  header 建 patient_id —— 若是目录名，219 的交集本身就是"目录名撞上 ID 空间"的样本，
  结论可能直接从这批人的匹配方式推出来。
- 省医 DICOM header 的 PHI 风险与 zhujiang issue-14 相同：对比逻辑放内存，
  落盘只留 `matched/unmatched/empty` 计数与匿名 ID 前缀。
- 若结论是"需要外部映射"（如 xinqiao `3_cxf_archives` 的情况，现为
  [issue-24](./issue-24-xinqiao-cxf-ingest-via-ct-mapped.md) 的 ct_mapped 路线），
  对照其处理模式，别发明新流程。