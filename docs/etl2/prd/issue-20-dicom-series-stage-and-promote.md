# Issue 20: `dicom_series` 表级 promote 链路打通（tracer bullet）

## Parent

[事故复盘：测试清理按 center_code 级联删除 168,260 行 dicom_series](../findings/incident-20260920-test-cascade-delete.md)（§10 → 「先暂存再上」）

## What to build

**本仓的「先暂存再上」第一片，只打通一张表，但要走完整条路。** 选 `lnrs_anon_dicom_series`
打头阵：只有 **88 MB**、`UNIQUE (dicom_study_uid)` 干净、且 `backfill_dicom_series_count.py`
是三个 ad-hoc 脚本里最简单的一个 —— 用它验证形状最便宜。

**要解决的问题**（不是 9-20 那起事故本身 —— 那起是测试的 DELETE，已由沙箱修复）：
**ad-hoc 执行脚本直写生产库、没有任何闸**。现有三个脚本
（`backfill_dicom_series_count.py` / `_issue13_ingest_xinqiao_ct_exam.py` /
`_issue6_ingest_zhujiang_ct_exam.py`）都是直写 `lnrs.lnrs_anon_*`。

**端到端行为**：脚本把结果写进 `lnrs.lnrs_stage_dicom_series`（结构与生产表一致）→
**真库在 promote 前完全不变** → 跑 promote 命令 → 真库出现这些行 → 再跑一次 promote，
行数不变（幂等）。

**选型（已决）**：**同库 stage 表**，不是独立 stage 数据库。理由见复盘与
本系列决策记录：代码里有 470 处硬编码 `lnrs.` 前缀会绕过 `search_path`，而
**B 方案的 promote SQL 与 A 方案只差源引用**（`lnrs.lnrs_stage_X` vs
`fdw.lnrs.lnrs_stage_X`）→ B 是 A 的严格子集，先做便宜的可逆步骤；
且 B 的 stage 表名**硬编码在代码里**，比 A 的「靠连接串指向」更结构化。

**promote 的机制复用** `_copy_then_merge`（Issue 19）—— 不另写一套 upsert。

## Acceptance criteria

- [ ] `lnrs.lnrs_stage_dicom_series` 存在，且与 `lnrs.lnrs_anon_dicom_series` 列结构一致
      （用 `LIKE ... INCLUDING DEFAULTS` 或等价方式；含 `dicom_study_uid` 上的唯一性以保证 promote 幂等）
- [ ] `backfill_dicom_series_count.py` 的写入目标改为 stage 表；**不再直写生产表**
- [ ] **真库不变断言**：脚本跑完后
      `SELECT COUNT(*) FROM lnrs.lnrs_anon_dicom_series` 与跑前**逐字节相同**，
      且该表的 `pg_stat_user_tables.n_tup_ins/upd/del` 计数不变
- [ ] promote 命令存在，可 dry-run（打印将要 promote 的行数）与 apply
- [ ] **可见性断言**：promote 后 stage 中的 `dicom_study_uid` 在生产表可查到
- [ ] **幂等断言**：连续跑两次 promote，生产表行数与关键字段值不变
- [ ] **幂等断言（重放同一批）**：把 stage 清空后重跑脚本 + promote，生产表行数不变
- [ ] stage 表可安全清空重建（`TRUNCATE lnrs.lnrs_stage_dicom_series`），不影响生产
- [ ] 用 Issue 19 的 `_copy_then_merge` 完成 upsert，**不新增第二套 upsert 实现**
- [ ] 在测试沙箱（`ENVIRONMENT=test`）上跑通全流程；沙箱上 5 个既有失败用例数**不增加**
- [ ] 不在本 issue 内改动另外两个 ad-hoc 脚本（留给 Issue 23）

## Blocked by

- [Issue 19](./issue-19-prefactor-share-copy-then-merge.md)（promote 复用其 upsert 机制）

## Notes for implementer

- **先量再改**：`backfill_dicom_series_count.py` 有 `--dry-run` / `--apply` / `--bypass-exam-fk`，
  先跑 `--dry-run` 确认候选规模，再改写入目标。
- promote 的目标约束是 `UNIQUE (dicom_study_uid)`（实测存在，约束名
  `lnrs_anon_dicom_series_dicom_study_uid_key`）。
- 参考既有回退口径：`backend/etl2/README.md` 的「回退」一节，以及复盘 §3.1
  —— **判断级联范围要查 live `pg_constraint`，不要读 DDL 文件**（两者已分叉）。
- 沙箱：`bash scripts/provision_lnrs_dev_sandbox.sh` 重建；`cd backend && ENVIRONMENT=test uv run pytest tests/anon_etl/`。
- 本片**不解决**「promote 出错怎么办」—— 那是 Issue 22。
