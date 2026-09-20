# Issue 22: promote 护栏 —— 前置校验闸 + 审计记录 + 按批次回滚

## Parent

[事故复盘：测试清理按 center_code 级联删除 168,260 行 dicom_series](../findings/incident-20260920-test-cascade-delete.md)（§10 → 「先暂存再上」）

## What to build

Issue 20 打通了「写 stage → promote」，但**promote 自己出错怎么办**没解决 ——
本 issue 补上 promote 的三道护栏，让「先暂存再上」真的成为一个**闸**而不是一次搬运。

**端到端行为**：

1. **前置校验闸**：promote 之前先校验 stage 与生产的不变量，**不过则拒绝 promote、生产库零变化**。
2. **审计记录**：每次 promote 留下可追溯记录（谁、何时、哪个批次、promote 了多少行、校验结果）。
3. **按批次回滚**：一次 promote 能被回滚，生产库回到 promote 前的状态。

**为什么先于「其余表」**（Issue 23）：表一多，promote 的失败面就大 —— 护栏应先到位。

## Acceptance criteria

**校验闸**

- [ ] promote 前校验 stage 数据的不变量，至少覆盖：
      **行数**（stage 与「本次预计 promote」是否一致）、
      **外键完整性**（stage 行引用的父行在生产或本次 promote 集合内存在）、
      **非空约束**（stage 行不违反目标表的 NOT NULL / CHECK）
- [ ] 校验不通过 → **拒绝 promote、退出码非 0、错误信息指出哪条不变量破了**，
      且生产表行数与 `pg_stat_user_tables` 计数**零变化**
- [ ] 有测试：故意往 stage 塞一条违反不变量的行 → promote 被拒 + 生产零变化

**审计**

- [ ] 每次 promote（含 dry-run）写入审计记录：`batch_id` / 目标表 / 行数 / 校验结果 / 触发者 / 时间戳
- [ ] 审计记录可查询：给定一次 promote，能回答「它动了哪些表、多少行」
- [ ] 审计表本身**不放在会被 promote 覆盖的表里**

**回滚**

- [ ] 一次 promote 可按批次回滚，回滚后目标表的行数与 promote 前**一致**
- [ ] 回滚**只撤销该批次的影响**，不碰其它批次写入的行
- [ ] 有测试：promote → 回滚 → 断言行数复原；再 promote 一次 → 断言可重放

## Blocked by

- [Issue 20](./issue-20-dicom-series-stage-and-promote.md)（护栏是 promote 的属性，promote 得先存在）

## Notes for implementer

- **回滚的实现形态先想清楚再写**。可选：(a) 审计表记下「本批次插入/更新的主键集合」，
  回滚时按集合撤销；(b) promote 前对受影响行做快照。二者成本不同，先估算行数量级再选 ——
  本系列涉及的表体量：`dicom_series` 88 MB / `patient` 193 MB / `imaging_study` 264 MB / `exam` 750 MB。
- **别把校验闸做成只查行数** —— 9-20 事故的教训之一是「空集会让任何一致性检查通过」
  （复盘 §4.4 放大 4：issue-13 的 `verify_no_drift` 报「跨中心零漂移」，因为跨中心集合当时是空的）。
  校验要在**集合非空**的前提下才有意义，空集要单独判定为「异常」而不是「通过」。
- 与 Issue 21 的分工：21 管「脚本直写生产」，22 管「promote 自身出错」。两者都做才闭环。