# Issue-10 源端留档：h196_3 三中心影像表同步口径与现状快照（2026-09-20）

> 对应 issue-10 验收标准「明确同步口径」「记录现状」「外键完整性断言」「单向」。
> **范围声明（2026-09-20 用户拍板）**：1.59（192.168.1.59）侧不在本次范围内；且本机即
> h196_3（10.12.196.3），到 192.168.1.59 的 ssh 22 端口直连超时（实测 2026-09-20 10:30），
> 同步必须从能同时连通两端的中转机按 `lnrs-sync-196-to-159` 技能执行。本文档完成
> **源端（h196_3）全部可验证项**：口径、现状快照、完整性断言、单向基线；1.59 侧项
> （备份目录探测、现状记录、同步执行、备份路径）移交执行时处理（§4）。

环境：本机 PG `127.0.0.1:5432 postgres/lnrs`（schema `lnrs`，PG 18）。
快照时间：**2026-09-20 10:43 CST**（断言全部同一时点执行）。

## 1. 同步口径（验收标准 1）

**全量，不抽样**（不用 `--limit` / `--by-center`）。理由：

- PRD 端到端目标是「1.59 上能按中心查到**完整**影像索引」，验收标准 5 的口径是
  「全量则完全相等」；抽样模式无法满足"完整"。
- 体量可行：4 表合计 ≈ 514k 行，表实际存储 ~541 MB（`pg_total_relation_size`
  合计，2026-09-20 10:56 实测），与 `lnrs-sync-196-to-159` 技能「真实场景验证
  记录（2026-09-07）」（23 表 / 620 万行 / 14 分钟）同一量级。

**表集（4 表）**：

| 表 | 角色 |
|---|---|
| `lnrs_anon_patient` | imaging_study 的 FK 父表（验收标准 6/8 断言依赖） |
| `lnrs_anon_imaging_study` | 影像索引主表（三中心） |
| `lnrs_anon_dicom_series` | 影像 series 索引（xinqiao，见 §2 差异说明） |
| `lnrs_anon_ingest_batch` | `dicom_series.created_batch_id` 的 **NOT NULL** FK 父表——不同步它，1.59 端 5 个 xinqiao batch 键成孤儿，脚本会 DETACH 该 FK 并告警 |

**排除**：

- `lnrs_anon_phi_audit`（4,165,056 行）：PHI 审计日志，非影像索引，PRD 范围是
  「影像表」；体量也最大（09-07 记录占 7 分钟）。
- exam / visit / lab_result 等非影像表：PRD 明示「那些表的同步口径单独确认」，本 issue 不覆盖。

**执行命令**（中转机上，按 `lnrs-sync-196-to-159` 技能；本机不可执行，见 §4）：

```bash
bash ~/.claude/skills/lnrs-sync-196-to-159/scripts/sync_anon_tables.sh \
  lnrs_anon_patient lnrs_anon_imaging_study lnrs_anon_dicom_series lnrs_anon_ingest_batch
```

## 2. 源库现状快照（2026-09-20 10:43 CST）

| 表 | 行数 | 分布 / 备注 |
|---|---:|---|
| `lnrs_anon_patient` | 277,588 | shengyi 169,820 / zhujiang 74,450 / xinqiao 33,313 / **ph_bak_358c2985 5**（§5 风险 3） |
| `lnrs_anon_imaging_study` | 203,235 | shengyi 82,994 / zhujiang 86,927 / xinqiao 33,314；modality 100% CT；`anon_exam_id` 非空 85,483 |
| `lnrs_anon_dicom_series` | 33,314 | **全部 xinqiao**（join study 归属实测）；`anon_exam_id` 100% NULL；file_count 18,664,932；byte_size 4,358,671,594,046（≈4.36 TB——这是**盘上 DICOM 文件**的 `byte_size` 列合计，非表存储体积，与同步传输量无关） |
| `lnrs_anon_ingest_batch` | 8 | 5 个 xinqiao `dicom_dir` success（row_counts 合计 33,314，与 series 行数闭环）+ 3 个 stale `running`（§5 风险 3）。**快照后 10:56 复测已 9 行**：新增 1 行 `xinqiao csv_report running`（started_at 02:46:30，晚于快照插入）——issue-13 流水线并行在跑，同步前须复测基线（§5 风险 3） |
| `lnrs_anon_phi_audit` | 4,165,056 | 不同步，仅参考 |

`imaging_study.source` 分布（溯源用）：shengyi `disk_06` 52,991 + `disk_07` 30,003；
zhujiang `disk4` 40,570 + `disk1` 26,940 + `disk2_supplement` 19,417；
xinqiao `xinqiao_6_zjj` 9,108 / `xinqiao_7_hsy` 8,600 / `xinqiao_5_yxl` 8,291 /
`xinqiao_8_hy` 6,903 / `xinqiao_4_tjj` 412。

### 与 PRD 记录（2026-09-20 实测）的差异

| 表 | PRD | 实测 | 原因 |
|---|---:|---:|---|
| patient | 270,247 | 277,588 | 今日 00:20–01:56 xinqiao DICOM 重导入（5 个 dicom_dir batch）新增占位患者 + 5 行 ph_bak 残留 |
| imaging_study | 203,235 | 203,235 | **一致**（三中心分布逐中心一致） |
| dicom_series | 201,574 | 33,314 | 今日 xinqiao `dicom_dir` ETL **重建**该表，仅留 xinqiao 33,314 行；zhujiang/shengyi 的 series 行在 h196_3 上已不存在（**同步前**的源库现状，非同步造成）。zhujiang series 重跑属于 issue-1/issue-2 线（工作区有未提交改动），跑完需再同步一次（同 issue-16 的重同步口径） |
| phi_audit | 3,873,939 | 4,165,056 | 新导入写入新审计行 |
| ingest_batch | 69 | 8 | 今日重建（8 行 `started_at` 全部 2026-09-20 00:20 之后），旧 69 个历史批次元数据被清——zhujiang/shengyi series 重灌时 batch 元数据会重新生成 |

## 3. 源端完整性断言（全部通过，2026-09-20 10:43 CST）

| # | 断言 | SQL | 结果 |
|---|---|---|---:|
| 1 | study→patient 无孤儿（PRD 验收 6 同源） | `SELECT COUNT(*) FROM lnrs_anon_imaging_study s WHERE NOT EXISTS (SELECT 1 FROM lnrs_anon_patient p WHERE p.patient_id = s.patient_id);` | **0** |
| 2 | series→study 无孤儿（PRD 验收 7 同源） | `SELECT COUNT(*) FROM lnrs_anon_dicom_series ds WHERE NOT EXISTS (SELECT 1 FROM lnrs_anon_imaging_study s WHERE s.dicom_study_uid = ds.dicom_study_uid);` | **0** |
| 3 | series→exam 无孤儿 | `SELECT COUNT(*) FROM lnrs_anon_dicom_series ds WHERE ds.anon_exam_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM lnrs_anon_exam e WHERE e.anon_exam_id = ds.anon_exam_id);` | **0**（全 NULL，无引用） |
| 4 | series→batch 无孤儿 | `SELECT COUNT(*) FROM lnrs_anon_dicom_series ds WHERE NOT EXISTS (SELECT 1 FROM lnrs_anon_ingest_batch b WHERE b.batch_id = ds.created_batch_id);` | **0** |
| 5 | series 经 study 间接 patient 覆盖 | `SELECT count(*) FROM lnrs_anon_dicom_series ds JOIN lnrs_anon_imaging_study s USING (dicom_study_uid) WHERE NOT EXISTS (SELECT 1 FROM lnrs_anon_patient p WHERE p.patient_id = s.patient_id);` | **0** |
| 6 | xinqiao batch row_counts 闭环 | 5 个 success batch 的 `row_counts->>'dicom_series'` 求和 = 6,903+8,291+9,108+8,600+412 | **33,314** = series 行数 |

**单向（PRD 验收 9）**：同步通道对源端只读（`pg_dump --schema-only` + `COPY ... TO
STDOUT`，技能已固定该通道），源端无任何写操作。§2 行数即同步前基线；执行时同步前后
各测一次比对相等即可（源端在同步窗口内若有 ETL 写入会破坏比对，执行前先确认无
ETL 在跑——2026-09-20 10:43 实测 `pg_stat_activity` 无活跃 ETL 查询）。

## 4. 1.59 侧移交项（本次不做；执行时按技能执行协议）

本机（h196_3）到 192.168.1.59 直连不可达（ssh 22 超时实测），以下各项在**中转机**
执行时处理：

1. `touch /data/lnrs_backup/.probe` 探测备份目录可写（技能已内置 DROP 前自动备份，
   备份失败即中止）。
2. 同步前记录 1.59 现状：4 表行数 + `imaging_study`/`patient` 的 `center_code`
   分布（与 §2 对比用）。
3. 确认 1.59 上无依赖这 4 张表的下游作业/视图（h42 应用 DROP 期间秒级不可用）。
4. 执行 §1 命令；把脚本 `[4/7]` 备份文件路径与 `[7/7] 校验通过` 块（每表
   行数|md5）记入执行侧 commit message。
5. 同步后在 1.59 重跑 PRD 验收 4/5/6/7 断言 + §3 同源 SQL。

## 5. 已知风险 / 后续

1. **三中心影像索引不完整**：当前源库 `dicom_series` 只有 xinqiao（zhujiang/shengyi
   series 已被今日重建清掉）。按现状同步后，1.59 上 zhujiang/shengyi 的 series 部分
   缺失；issue-1/issue-2（zhujiang series 重跑）完成后需再同步一次。
2. **`dicom_series.anon_exam_id` 当前 100% NULL**（33,314 xinqiao 行）：issue-13
   （xinqiao exam 回填）在工作区进行中（`backend/tests/anon_etl/test_issue13_xinqiao_exam_backfill.py`
   未提交）。issue-13 跑完后按 issue-16 口径重同步 xinqiao。
3. **源库残留与并行变更（本 issue 不清理，属导入/issue-13 侧）**：`lnrs_anon_ingest_batch`
   4 行 stale `running`（xinqiao csv_report @ started_at 02:46:30——该行**晚于快照插入**，
   10:56 复测为 9 行；zhujiang csv_report ×2 @01:40/01:47；center_code='src_kind_48a6cfd6'
   dicom_dir ×1 @00:20；row_counts 全空，pg_stat_activity 无对应进程）；
   `lnrs_anon_patient` 5 行 `center_code='ph_bak_358c2985'`（PT_00535648–52，
   created_at 2026-09-20 01:08:24，疑似今日导入残留）。
   会话期间工作区新增 `_issue13_ingest_xinqiao_ct_exam.py` / `verify_xinqiao_exam.sql`
   → issue-13 流水线并行在跑：**同步执行前必须确认无 ETL 在跑，并复测 §2 基线行数**
   （单向断言的前提；ingest_batch 在 4 表集内，其行数变化会破坏比对）。
4. 软依赖状态：issue-6 / issue-7 已落地（commit 757ac2ce / 296eb602）；但 issue-13
   进行中意味着**本次同步不是终态**，后续至少还需一次重同步（issue-16 覆盖 xinqiao
   部分；zhujiang/shengyi series 重跑后还需全量再同步一次）。
