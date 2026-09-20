# Issue 10: h196_3 → 1.59（h42）三中心影像表同步

## Parent

[plan-disk1-disk2-disk4-zhujiang-import.md](../plan-disk1-disk2-disk4-zhujiang-import.md)（§7-6）

## What to build

把 h196_3（10.12.196.3）上的影像索引表反向同步到 192.168.1.59（h42 库），
让下游环境拿到 **zhujiang / shengyi / xinqiao** 三中心的完整影像索引。

h196_3 行数（PRD 撰写时 2026-09-20 实测；**已过时，现行值以留档 §2 快照与差异表为准**）：

| 表 | 行数 |
|---|---:|
| `lnrs_anon_patient` | 270,247 |
| `lnrs_anon_imaging_study` | 203,235 |
| `lnrs_anon_dicom_series` | 201,574 |
| `lnrs_anon_phi_audit` | 3,873,939 |
| `lnrs_anon_ingest_batch` | 69 |

按中心拆的 `imaging_study`：`shengyi` 82,994 / `zhujiang` 86,927 / `xinqiao` 33,314。

使用 `lnrs-sync-196-to-159` 技能（脚本支持 `--limit N` 每表按主键取前 N 行抽样、
或 `--by-center N` 按医院抽样，衍生表沿 FK 闭包自动跟随；**DROP 前自动备份 1.59 已有目标表到 `/data/lnrs_backup`**）。

**端到端目标**：1.59 上能按中心查到完整影像索引，且外键无孤儿。

## Acceptance criteria

> **2026-09-20 状态**：用户拍板 **1.59 侧不在本次范围**（本机即 h196_3，到
> 192.168.1.59 直连不可达——ssh 22 超时实测，同步须从中转机执行）。源端口径/快照/断言
> 已完成，详见 [`verify_result/issue-10-sync-source-baseline-20260920.md`](../verify_result/issue-10-sync-source-baseline-20260920.md)；
> 标「移交执行」的项在同步执行时按技能执行协议处理。

- [x] 明确同步口径并写进 commit message：**全量**（不抽样），4 表集 =
  `lnrs_anon_patient` + `lnrs_anon_imaging_study` + `lnrs_anon_dicom_series` +
  `lnrs_anon_ingest_batch`（后者为 `dicom_series.created_batch_id` 的 NOT NULL FK 父表）；
  排除 `lnrs_anon_phi_audit` 与其它非影像表。理由与执行命令见留档 §1。
- [ ] 同步前确认 1.59 侧 `/data/lnrs_backup` **可写**（否则脚本会 DROP 现有目标表且无备份）—— 先 `touch` 探测 —— 移交执行时前置检查
- [ ] 同步前记录 1.59 现状：4 表（上条表集）的行数与 `center_code` 分布（用于对比）—— 移交执行时前置检查（源端现状已记录于留档 §2）
- [ ] 1.59 SQL 断言：`SELECT center_code, COUNT(*) FROM lnrs_anon_imaging_study GROUP BY 1;` 覆盖 `shengyi` / `zhujiang` / `xinqiao` 三中心 —— 移交执行时后置检查（源端实测三中心齐全：82,994 / 86,927 / 33,314，全量 COPY 后 1.59 侧必然覆盖）
- [ ] 1.59 SQL 断言：各表行数与 h196_3 对应口径一致（全量则完全相等；抽样则等于抽样预期）—— 移交执行时后置检查（源端基线行数见留档 §2）
- [ ] 外键完整性断言（1.59）：`SELECT COUNT(*) FROM lnrs_anon_imaging_study s WHERE NOT EXISTS (SELECT 1 FROM lnrs_anon_patient p WHERE p.patient_id = s.patient_id);` 返回 0 —— 源端实测 0（2026-09-20 10:43，留档 §3）；1.59 侧执行时复检
- [ ] 外键完整性断言（1.59）：`SELECT COUNT(*) FROM lnrs_anon_dicom_series ds WHERE NOT EXISTS (SELECT 1 FROM lnrs_anon_imaging_study s WHERE s.dicom_study_uid = ds.dicom_study_uid);` 返回 0 —— 源端实测 0；1.59 侧执行时复检
- [ ] 抽样模式断言：衍生表沿 FK 闭包跟随 —— `imaging_study` 的每个 `patient_id` 在 `patient` 表存在（同上）—— N/A（本次为全量同步；若后续改抽样按原口径补验）
- [ ] **单向**：断言 h196_3 侧行数在同步前后**不变** —— 同步通道对源端只读（`pg_dump --schema-only` + `COPY ... TO STDOUT`）；同步前基线行数见留档 §2，执行时同步前后各测一次比对
- [ ] 同步后 1.59 的备份文件路径记入 commit message —— 待执行（本次未跑 1.59 同步，无备份文件；执行侧 commit 补记）

## Blocked by

- [Issue 6](./issue-6-ingest-zhujiang-ct-exam-and-backfill-anon-exam-id.md)
- [Issue 7](./issue-7-fix-etl2-cli-and-backfill-series-count.md)

> 说明：这是**软依赖**。若急于让下游拿到当前状态，可以先同步一次，但 Issue 6/7 跑完还需再同步一次。
> 先跑的前提是明确接受重复同步的成本。

## Notes for implementer

- 同步脚本会 **DROP 1.59 的已有目标表**（备份在 `/data/lnrs_backup`）—— 执行前务必确认 1.59 上没有依赖这些表的
  下游作业/视图，或确认可在窗口内重建。
- h196_3 本机**不要 ssh**（本机即 10.12.196.3）；同步方向是 h196_3 → 1.59。
- 上游背景：珠江导入见 `plan-disk1-disk2-disk4-zhujiang-import.md`；新桥导入见 `plan-xinqiao-disk03-import.md`。
- 若 1.59 上还需要 exam / report / visit 等非影像表，本 issue **不覆盖** —— 那些表的同步口径单独确认。
