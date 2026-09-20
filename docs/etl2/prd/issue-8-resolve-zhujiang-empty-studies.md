# Issue 8: 415 个零文件 study 的处置 + 141 行陈旧 `dicom_series` 计数修复

## Parent

[plan-disk1-disk2-disk4-zhujiang-import.md](../plan-disk1-disk2-disk4-zhujiang-import.md)（§6 R-空 study / §7-5）

## What to build

zhujiang 有 **415 个 study**（415 个去重 `StudyUID`）`imaging_study.sop_count = 0`，
实测分成**两个性质不同**的子集：

| 子集 | 行数 | `dicom_series.file_count` | 磁盘现状 | 判定 |
|---|---:|---|---|---|
| **A** | 274 | `0`（`byte_size` = 0） | 目录存在且为空 | **一致** —— 真空 study |
| **B** | **141** | **350–578**（`byte_size` 185–297 MB） | **目录存在但已空** | **不一致** —— `dicom_series` 是**陈旧计数** |

> 对照组（证明非零 study 完全一致）：`sop_count > 0` 的 study 随机抽 **40 个**，
> `imaging_study.sop_count == dicom_series.file_count == 磁盘条目数`，**40/40 完全相等**。
> 所以异常**只**集中在 B 子集这 141 行。

B 子集的可疑点：`dicom_series` 的计数是 2026-09-19 的 bypass backfill 写的（当时目录有数据），
现在 `os.listdir` 为 0 —— 需要查清是「数据被清理」还是「NFS 挂载/路径变化」。
注意 `/data` 是 **NFS**（`10.12.180.51:/wlx-storage`，100T / 已用 90%），不是本地盘。

**本 issue 端到端交付**：
1. **调研** B 子集的成因（含与 `lnrs_anon_v_imaging_study_counts` 的相互影响）
2. **决策** A 子集在业务上怎么处置（3 套方案交用户拍板）
3. **落地** 按决策改库 / 改视图

## Acceptance criteria

- [ ] 调研报告 `docs/etl2/verify_result/zhujiang-empty-studies-<date>.md`，含：
  - 415 行的 `source` / 日期目录 / `path_study_date` 分布
  - A（274）与 B（141）的完整清单（`dicom_study_uid` + `image_path`）
  - B 子集的 NFS 现状复核（逐个 `os.listdir` + `stat` 父目录 mtime），并给出「被清理 / 挂载变化 / 其它」的判断与依据
  - 对 PRD 视图 `lnrs_anon_v_imaging_study_counts`（`series_count / instance_count / total_bytes`）的影响评估
- [ ] 给出 A 子集 **3 套处置方案**并各自评估对视图 `total_bytes` 的影响：
      (a) 保留 + 在视图/接口标注 `is_empty`；(b) 软删（`deleted_at` 类字段若存在）；(c) 视图层过滤
- [ ] 用户拍板后落地，SQL 断言：`lnrs_anon_v_imaging_study_counts` 对 A 子集的行为符合所选方案
- [ ] B 子集 141 行修复为与磁盘一致：`dicom_series.file_count = 0 AND byte_size = 0`
      （若调研发现数据其实还在别处，则改为回到磁盘后重跑 backfill 并断言计数恢复）
- [ ] 修复后一致性断言：`SELECT COUNT(*) FROM lnrs_anon_imaging_study s JOIN lnrs_anon_dicom_series ds ON ds.dicom_study_uid=s.dicom_study_uid WHERE s.center_code='zhujiang' AND (s.sop_count=0) <> (ds.file_count=0);` 返回 **0**
- [ ] 不动 `sop_count > 0` 的任何行（`sop_count` 与 `file_count` 已 40/40 一致）
- [ ] 备份：`CREATE TABLE lnrs_anon_dicom_series_bak_empty_<ts> AS SELECT * FROM lnrs.lnrs_anon_dicom_series WHERE dicom_study_uid IN (<141 UIDs>);`

## Blocked by

None - can start immediately（**调研部分**）。
落地部分需用户对 A 子集的 3 套方案拍板。

## Notes for implementer

- **不要擅自删除 A 子集的行** —— 珠江计划已明确「空 study 保留」是既有口径（扫描命中数 vs 基线口径要求保留）。
  本 issue 是**重新审视**这个口径，不是默认推翻它。
- B 子集的修复方向取决于调研结论，别先写死。若确认数据已永久丢失，
  `dicom_series` 的 185-297 MB 计数会让 PRD 视图 `total_bytes` **虚高** —— 这正是需要修的理由。
- 相关背景：`plan-restore-series-count.md` 提到「part 离线 → series_count NULL → 视图/API COALESCE 0」的既有模式，
  本 issue 的 B 子集与它同源（磁盘状态与库内计数漂移）。
- 若发现是**挂载/权限**问题（`drwxr-xr-x+` 带 ACL），先修挂载再复核，不要基于错误前提改库。

## Implementation record (2026-09-20)

实际状态 vs PRD 描述的差异：

| 维度 | PRD 描述（写于 ~2026-09-19） | 当前实测（2026-09-20） |
|---|---|---|
| A 子集（真空 / 一致） | 274 | **415**（磁盘目录全空） |
| B 子集（陈旧计数） | 141 | **0**（后续全量 ETL / DB 重建已移除） |
| zhujiang dicom_series 总行数 | — | **0** |

B 子集当前为 0 → PRD 的「B 子集 141 行修复 + 备份表 + 一致性断言」自然满足（B=0 → 0 行需修）。

用户拍板方案：**方案 (c) 视图层过滤**（最小侵入，零数据修改）。

交付：

| 文件 | 说明 |
|---|---|
| `backend/etl2/investigate_zhujiang_empty_studies.py` | 调研脚本（输出 CSV + Markdown 报告，含 3 方案分析 + shengyi 旁路观察） |
| `backend/sql/postgres/0026-imaging-study-counts-filter-zero-sop.sql` | 视图迁移：`lnrs_anon_v_imaging_study_counts` 加 zero-sop 守卫 |
| `docs/etl2/verify_issue8_zhujiang_empty_studies.sql` | 验收 SQL（A1-A4 断言） |
| `docs/etl2/verify_result/zhujiang_empty_studies_20260920.{csv,md}` | 调研产物（415 行 inventory + 报告） |

验收结果（dev PG 实测）：

- A1 (B-subset consistency): `mismatches = 0` ✓
- A2 (view filter): zhujiang 视图行 86,927 → **86,512**（-415） ✓
- A3 (sop_count>0 不变): 86,512 = 86,512 OK ✓
- A4 (数据未改): imaging_study 行数与 zero-sop 行数与调研基线一致 ✓
