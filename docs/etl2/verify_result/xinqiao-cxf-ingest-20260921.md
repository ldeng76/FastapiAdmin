# Issue 24 执行报告：cxf_archives 7,984 study 入库（ct_mapped 解锁映射）

> 2026-09-21，h196_3（本机）。PRD：[`../prd/issue-24-xinqiao-cxf-ingest-via-ct-mapped.md`](../prd/issue-24-xinqiao-cxf-ingest-via-ct-mapped.md)
> （实现 [Issue 18](../prd/issue-18-xinqiao-cxf-archives-ingest.md) 的目标）。
> 执行脚本：`backend/etl2/_issue24_ingest_xinqiao_cxf.py`；验收 SQL：[`../verify_xinqiao_cxf_ingest.sql`](../verify_xinqiao_cxf_ingest.sql)。

## 1. 结论

7,984 个 `3_cxf_archives` study 全链路入库：**imaging_study +7,984（anon_exam_id 非空率 100%）、
dicom_series +7,984（与 ct_mapped 逐行全等）、patient +4（占位）、exam +4、phi_audit +7,984、
ingest_batch 1（确定性 id）**。zhujiang / shengyi 全表零漂移；既有 xinqiao 33,314 study 未动。
幂等重跑 0 新增 0 更新。验收 SQL V1–V15 全 PASS（V13 复核项 1 行差异，按 PRD 开评注不擅改，见 §5）。

未遍历 1,016 GB 磁盘：study 枚举用 ct_mapped `path[]` 并与 `lists/batch_001..008.txt`
（7,984 行，UTF-8 BOM 需 utf-8-sig 读取）逐 UID 交叉核对一致；唯一磁盘 I/O 是 4 次
DICOM header 单文件读（无日期兜底，见 §3）。

## 2. 端到端写入（--apply 01:15，promote 4 批次审计）

| 表 | 写入路径 | 行数 | 备注 |
|---|---|---:|---|
| lnrs_anon_imaging_study | stage → promote | **+7,984** | source=`xinqiao_3_cxf`，sop_count=len(path[])，study_root=`…/3_cxf_archives/folders/NNN/<StudyUID>` |
| lnrs_anon_dicom_series | stage → promote | **+7,984** | file_count=len(path[])，byte_size=total_size_bytes，series_count=ct_mapped.file_count（PACS series 数，与 20260920 校正口径一致） |
| lnrs_anon_exam | stage → promote | **+4** | 仅「60 个无日期行」中 hash/日期都查不到既有 exam 的 4 行；exam_no=StudyUID，exam_date=DICOM header StudyDate |
| lnrs_anon_patient | stage → promote | **+4** | PT_00567748..51，sex='0'，is_placeholder=TRUE |
| lnrs_anon_phi_audit | 直写 | +7,984 | sha256(patient_id)，strategy=hmac，1 患者 1 行（每患者恰 1 study） |
| lnrs_anon_ingest_batch | 直写 | 1 | `ae059211-ed4d-559b-b873-d0e5f4d7e472`（uuid5 确定性，重跑 0 新增），source_kind=dicom_dir，row_counts 全量记录 |
| lnrs_anon_report_text | — | 0 新增 | cxf 关联的 7,924 个既有 exam 的报告已由 issue-13（ct.parquet 批次）落库（V14：with_report=7,924）；4 个新建 exam 的 ct_mapped raw_text 本为 NULL，无报告可灌 |

备份（apply 前，`*_bak_20260921_011517`，全量快照）：patient 294,183 / exam 1,259,942 /
imaging_study 203,235 / dicom_series 201,574 行。promote 审计批次
（回滚命令见 `/tmp/issue24_promote.log`）：patient `6fe815e6`、exam `a4dfdd1d`、
imaging_study `8bb3a01f`、dicom_series `651bf735`。

## 3. exam 关联口径（ct_mapped 实测解锁的精确路径）

前置调研（`recon_cxf.json` / `recon_cxf_exam.json`，gitignore 目录）推翻了两个直觉假设：

1. **cxf StudyUID 的 `sha256('xinqiao:'+StudyUID)` 与库内 exam 0 命中**——ct.parquet 的
   exam_id 不是 StudyUID（ct_mapped 的 StudyUID 键是 DICOM 侧合并产物）；
2. cxf 行与既有 exam 按 **(patient, exam_date) 精确同日** 可对上（ct_mapped 与 ct.parquet
   同批，对账见 series-counts-fix 报告 §2）。

故 7,984 行的 exam 决策：

| 去向 | 行数 | 说明 |
|---|---:|---|
| 关联既有 exam（同日精确） | 7,924 | exam 内容已在库（issue-13 灌 ct.parquet），**只关联不新建**（issue-25 决策门「不得产生重复 exam」同此约束） |
| └ 其中同日多 exam 平局 | 5 | 取 min(anon_exam_id)，issue-13 残留兜底同款 |
| 关联既有 exam（hash 命中） | 56 | 60 个无日期行中，issue-25 会话已于当日早些时候按 `sha256('xinqiao:'+StudyUID)` 建好 exam——键空间天然幂等，直接关联 |
| 新建 exam（header StudyDate 兜底） | 4 | uid_study_date 为 NULL（非 GE 系 UID）→ 读 1 个 .dcm 的 StudyDate（4 次单文件读）；hash、(patient, 兜底日期) 均查无既有 exam |
| 无法关联 | **0** | anon_exam_id 非空率 100% 达成 |

patient 侧：7,984 个 PID（每患者恰 1 study）中 7,980 个已在库（其中 56 个为 issue-25
当日并发新建），本批仅补 4 个占位。**并发协调**：issue-25（exam 侧）与 issue-26/27
（占位真实化）当日并行写入同一生产库，本单 plan-first（apply 时点按库内现状算计划）+
hash/patient-date 幂等键使两单无重复、无冲突。

## 4. 验收 SQL（V1–V15 全 PASS）

| 断言 | 结果 |
|---|---|
| V1 cxf study = 7,984 | PASS |
| V2 anon_exam_id 非空率 100% | PASS |
| V3 exam FK 违例 = 0 | PASS |
| V4 dicom_series file_count/byte_size/series_count 与 ct_mapped 全等 = 7,984/7,984 | PASS |
| V5 与既有 source 的 StudyUID 交集 = 0 | PASS |
| V6 既有 xinqiao 5-sub = 33,314（不动） | PASS |
| V7 zj/sy imaging_study = 86,927 / 82,994 | PASS |
| V8 zj/sy exam = 98,130 / 1,037,523 | PASS |
| V9 zj/sy patient = 74,450 / 169,820 | PASS |
| V10 本批新建 patient 占位口径 | PASS（0 例外） |
| V11 series.anon_exam_id 与 study 一致 | PASS（0 差异） |
| V12 ingest_batch success + row_counts 全记录 | PASS |
| V13 复核项 | REVIEW（1 行差异，见 §5） |
| V14 报告面：with_report=7,924 / without_report=60 | 符合口径（60 = 新建 exam 无报告行） |
| V15 全局合计（信息性） | xq imaging 41,298 / series 全局 209,558 / xq patient 49,912 |

幂等重跑（promote 后再 --dry-run / --apply）：study/series/exam/patient/phi **全部 0 新增**，
batch 行保持 1。脚本 seam 测试 12 例全绿（`backend/tests/anon_etl/test_issue24_xinqiao_cxf_ingest.py`）。

## 5. 复核项：issue-13 的 33,110 个 anon_exam_id 三方一致性

以 ct_mapped 的 33,314 个 5-sub StudyUID 行为权威，比对链接 exam 的患者与日期：

- **linked_checked=33,110，mismatch=1，null_linked=204**（该 204 个患者确无 CT exam，与
  issue-13 记录一致，非差异）；
- 唯一差异：study_key=206548（`xinqiao_4_tjj`，UID
  `1.2.840.113619.2.55.3.1721121893.187.1703118022.419`）——issue-13 链到同患者
  **2024-10-15** 的 exam，ct_mapped 行的 exam_date 为 **2024-01-02**（该日恰有 1 个 CT exam）。
  根因推断 `[INFERENCE]`：该 study 的 UID 无内嵌日期（`17031180` 非法日期段），issue-13 走了
  残留兜底（文件数/单 exam/平局），在患者多 CT exam 时选错——与 ct_mapped 权威映射相比
  恰好是「同患者不同日」的错链。
- **处置：只列报告开评注，不擅自改**（PRD 原文）。明细：
  [`xinqiao-cxf-exam-link-audit-20260921.csv`](xinqiao-cxf-exam-link-audit-20260921.csv)（anon 键，非 PHI）。
  建议后续单独微工单：将该 study 的 anon_exam_id 改指 2024-01-02 的 exam（`map_candidates=1`，无歧义），
  或等 issue-25 落地后用 ct_mapped 映射做一次 5-sub 全量回填复核。

## 6. 过程缺陷与修复（执行中发现，均已修复）

| # | 缺陷 | 处置 |
|---|---|---|
| D1 | **study_key 序列落后于生产 max**：`lnrs_anon_imaging_study_study_key_seq.last_value=214,261` < 生产 max 239,591（历史批量导入用显式 key 未推进序列）→ 首次 promote 撞 PKEY | `setval` 至 max(study_key)=239,591，stage 7,984 行重新发号（239,592..247,575）后 promote 成功。**遗留**：任何写入方若继续用显式 key 不推进序列，此问题会复发 |
| D2 | promote 审计表 `lnrs_promote_audit(_row)` 被环境清理，promote 护栏无法落审计 | 脚本 `ensure_stage_tables` 幂等重建（DDL 逐字取自迁移 o5p6q7r8s9t0） |
| D3 | stage 表同样被清理，且 asyncpg 事务内 DuplicateObject 后整体 abort，「异常吞掉」式幂等建表不可行 | 改为 `CREATE TABLE IF NOT EXISTS` + 先查 pg_constraint 再 ADD CONSTRAINT |
| D4 | V10 断言首版把既有患者也纳入占位断言 → FAIL | 收窄为本批新建患者（`created_batch_id`=本批）；既有患者已被 issue-26/27 真实化（is_placeholder=FALSE），不属本单断言面 |

## 7. 变更文件

| 文件 | 改动 |
|---|---|
| `backend/etl2/_issue24_ingest_xinqiao_cxf.py` | 新建：plan-first 入库脚本（dry-run/apply/promote/verify/audit，`build_plan` 纯函数 seam） |
| `backend/tests/anon_etl/test_issue24_xinqiao_cxf_ingest.py` | 新建：seam 测试 12 例 |
| `docs/etl2/verify_xinqiao_cxf_ingest.sql` | 新建：V1–V15 验收 SQL |
| `docs/etl2/verify_result/xinqiao-cxf-exam-link-audit-20260921.csv` | 新建：复核差异明细（1 行，非 PHI） |
| `docs/etl2/verify_result/xinqiao-cxf-ingest-20260921.md` | 本报告 |

staging 产物（`recon_*.json`、调研脚本）在 gitignore 目录 `/data_xq0913/xinqiao/`；
ct_mapped 为 PHI 邻接文件，全流程只在内存与临时映射表 `lnrs_tmp_issue24_cxf_map`
（**不含明文 PID**，patient 只落 anon 键）中出现。

## 8. 回退

- promote 回滚：`promote_stage_all.py --rollback <batch_id> --table <name>`（4 个批次 id 见 §2）；
- 表级快照：`lnrs_anon_*_bak_20260921_011517`（4 表全量）；
- phi/batch：按 `batch_id='ae059211-…'` 删除（FK 下 dicom_series.created_batch_id 引用该 batch，
  须先回滚 dicom_series 批次）。
