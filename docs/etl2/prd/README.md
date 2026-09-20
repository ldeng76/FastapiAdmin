# 方案 B — PRD 与 Issue 拆分

本目录包含方案 B（让 `/#/medicalFiles` 文件大小显示真实数字）的 PRD 与独立 issue 拆分。

## 文件

| 文件 | 用途 |
|---|---|
| `PRD.md` | 完整 PRD：问题陈述 / 方案 / 用户故事 / 实施决策 / ADR / 测试决策 / 范围外 |
| `issue-1-backfill-imaging-study-exam-id.md` | Issue 1: 回填 imaging_study.anon_exam_id（zhujiang 全量） |
| `issue-2-run-dicom-series-etl.md` | Issue 2: 跑 ETL-2 dicom_series 阶段（zhujiang） |
| `issue-3-switch-files-statistics-to-view.md` | Issue 3: service 切视图 + 清理方案 A 临时改动 |
| `issue-4-investigate-shengyi-exam-gap.md` | Issue 4（独立调研）: shengyi exam 缺口根因调查 |

## 依赖关系

```
Issue 1 ──→ Issue 2 ──→ Issue 3
                ↑
        Issue 4（独立并行；与 1/2/3 无依赖）
```

## 启动方式

每个 issue 在独立会话启动时：

```bash
# 新会话的入口
cat docs/etl2/prd/PRD.md
cat docs/etl2/prd/issue-N-*.md
# 然后调用 /implement
```

issue 已 self-contained：包含 Parent / What to build / Acceptance criteria / Blocked by / Notes for implementer 五段；接手人不需要回看本会话上下文。

## 与既有 commit 的关系

- `722e4f66`（方案 A 止血，已 commit 并 push）：本目录的所有 issue 与之不冲突；Issue 3 撤除方案 A 的临时 null/— 兜底。
- `a9000c56`（方案 B 脚本骨架，已 commit 未 push）：本目录的 Issue 1/2 直接调用该 commit 的脚本；不需要新增代码。

## 后续动作

- 本次 commit：PRD + 4 个 issue 落到 `docs/etl2/prd/`，不 push。
- 用户 review → 选择接下来跑哪个 issue（在哪个新会话用 `/implement` 启动）。

---

## 第二组：影像导入收尾（issue-5 ~ issue-11）

第一组（issue-1~4）是方案 B 的链路。第二组来自珠江三盘导入（86,927 study）与新桥导入（33,314 study）
落地后的收尾盘点，父文档主要是 [`../plan-disk1-disk2-disk4-zhujiang-import.md`](../plan-disk1-disk2-disk4-zhujiang-import.md)。

| 文件 | 用途 | 阻塞 |
|---|---|---|
| `issue-5-extend-path-study-date-zhujiang-prefixes.md` | Issue 5: 扩 `lnrs.path_study_date` 支持 `yd*`/`new*` 前缀（3,710 study 取不到日期） | 无 |
| `issue-6-ingest-zhujiang-ct-exam-and-backfill-anon-exam-id.md` | Issue 6: 补 zhujiang CT exam 入库 + 回填 `imaging_study.anon_exam_id` | Issue 5 |
| `issue-7-fix-etl2-cli-and-backfill-series-count.md` | Issue 7: 修 ETL-2 CLI 三处缺陷 + `dicom_series.series_count` 86,203 行全量回填 | 无 |
| `issue-8-resolve-zhujiang-empty-studies.md` | Issue 8: 415 个零文件 study 处置 + 141 行陈旧 `dicom_series` 计数修复 | 无（落地需拍板） |
| `issue-9-fix-shengyi-placeholder-flag.md` | Issue 9: 修复 shengyi 占位漏标（82,682 个 `is_placeholder` 应为 TRUE） | 无 |
| `issue-10-sync-h196-3-to-h42-imaging-tables.md` | Issue 10: h196_3 → 1.59（h42）三中心影像表同步 | Issue 6, 7 |
| `issue-11-purge-historical-phi-destructive.md` | Issue 11: 清除 git 历史 PHI（**破坏性**） | 无（需批准） |

### 第二组依赖关系

```
Issue 5 ──→ Issue 6 ──┐
                      ├──→ Issue 10
Issue 7 ──────────────┘

Issue 8  （独立；落地需用户拍板 3 套方案）
Issue 9  （独立）
Issue 11 （独立；破坏性，需用户批准 + push 恢复）
```

### 与第一组的关系

- Issue 6 是 `issue-1` 的**前置修正**：issue-1 假设 exam 表有 CT 行，实测 zhujiang 只有 1,091 行 gene exam、
  与影像患者交集仅 23 人 —— 不补 CT exam，issue-1 跑了也接近 0 覆盖。
- Issue 7 与 `issue-2` **有边界重叠**：issue-2 走 ETL-2 main path 会顺带产出 `series_count`（新行），
  但不会回填已存在的 86,203 行；两者都扫同一批目录，跑之前需确认顺序（详见 issue-7 的「与 Issue 2 的边界」）。
- Issue 7 的 `series_count` 是 `issue-3`（service 切视图）的视图字段之一。

---

## 第三组：新桥导入收尾（issue-12 ~ issue-18）

第一/二组围绕珠江三盘与 zhujiang/shengyi 的 ETL-2 收尾；第三组来自新桥 `03_disk/xinqiao`
五 sub 导入（33,314 study / 33,313 PID）落地后的收尾盘点，父文档是
[`../plan-xinqiao-disk03-import.md`](../plan-xinqiao-disk03-import.md)。

| 文件 | 用途 | 阻塞 |
|---|---|---|
| `issue-12-xinqiao-viewer-series-path.md` | Issue 12: 新桥影像查看器适配 — `image_path` 指向 series 目录（布局 A/B/D） | 无 |
| `issue-13-xinqiao-exam-ingest.md` | Issue 13: 新桥 exam 灌库 + 回填 `dicom_series.anon_exam_id` | Issue 6（脚本借鉴）；外部 PACS 映射 |
| `issue-14-zhujiang-study-uid-audit.md` | Issue 14: 珠江 `dicom_study_uid` ≥100 例 header 对账调研 | 无（纯调研） |
| `issue-15-xinqiao-placeholder-realization.md` | Issue 15: 新桥占位真实化（关联 exam 后回填人口学 + `is_placeholder=FALSE`） | Issue 13 |
| `issue-16-resync-xinqiao-to-h42.md` | Issue 16: h196_3 → 1.59（h42）xinqiao 影像表重同步 | Issue 13 |
| `issue-17-purge-xinqiao-historical-phi-destructive.md` | Issue 17: git 历史 PHI 清除扩展（**破坏性**，含新桥 2 个 PHI 文件） | 无（需批准 + push 恢复） |
| `issue-18-xinqiao-cxf-archives-ingest.md` | Issue 18: 新桥 `3_cxf_archives` 入库（阻塞于外部映射） | 无（实际被外部 PACS 映射阻塞） |

### 第三组依赖关系

```
Issue 13 ──┬──→ Issue 15
           └──→ Issue 16

Issue 12  （独立）
Issue 14  （独立；纯调研）
Issue 17  （独立；破坏性，需用户批准 + push 恢复；建议与 issue-11 合并实施）
Issue 18  （被外部 PACS 映射阻塞；与 Issue 13 软联动）
```

### 与第二组的关系

- Issue 13 与 [Issue 6](./issue-6-ingest-zhujiang-ct-exam-and-backfill-anon-exam-id.md) 同模式（CT exam 灌库 + 回填 `anon_exam_id`），
  复用其脚本骨架扩展 `--center xinqiao`。
- Issue 15 与 [Issue 9](./issue-9-fix-shengyi-placeholder-flag.md) 结构对称（占位修复），
  但方向相反：Issue 9 是把漏标的占位补 TRUE，Issue 15 是把已 TRUE 占位 flip FALSE。
- Issue 17 是 [Issue 11](./issue-11-purge-historical-phi-destructive.md) 的扩展（4 个 PHI 文件 vs 2 个），
  落地时建议合并为一次 `git filter-repo` 操作，减少 `--force-with-lease` 次数。
- Issue 14 是 plan-xinqiao §7-6 提出的安全验证：珠江 86,927 study 当前只有 1 例实测目录名 UID == header `StudyInstanceUID`，
  本调研补足抽样证据。

---

## 第四组：「先暂存再上」— stage 表 + 幂等 promote（issue-19 ~ issue-23）

来源：[事故复盘 §10](../findings/incident-20260920-test-cascade-delete.md)。

**先说清楚这一组解决什么、不解决什么**：

- 9-20 那起事故（测试的 `DELETE` 级联删掉 168,260 行）**已由测试沙箱修复**
  （`lnrs_dev` + `tests/anon_etl/_db_guard.py`，commit `bf6564ce`）。本组**不是**它的修复。
- 本组解决的是**另一个风险**：`backend/etl2/` 下的**执行型脚本直写生产库、没有任何闸**。
- 主 ETL 路径**不在**本组范围：它已经是幂等 upsert + 事务内 temp table，收益小、改动大。

| 文件 | 用途 | 阻塞 |
|---|---|---|
| `issue-19-prefactor-share-copy-then-merge.md` | Issue 19: prefactor — 把 `_copy_then_merge` 抽成 promote 可复用的共用函数 | 无 |
| `issue-20-dicom-series-stage-and-promote.md` | Issue 20: `dicom_series` 表级 promote 链路打通（tracer bullet） | Issue 19 |
| `issue-21-adhoc-script-write-guard.md` | Issue 21: ad-hoc 脚本安全闸 — 写生产表必须显式确认 | 无 |
| `issue-22-promote-guardrails.md` | Issue 22: promote 护栏 — 校验闸 + 审计 + 按批次回滚 | Issue 20 |
| `issue-23-remaining-tables-and-scripts.md` | Issue 23: 其余 3 张表接入 + 另两个 ad-hoc 脚本切换 | Issue 20, 22 |

### 第四组依赖关系

```
Issue 19 ──→ Issue 20 ──→ Issue 22 ──→ Issue 23
                 └──────────┘（23 同时依赖 20 与 22）

Issue 21  （独立，与 19/20/22/23 正交）
```

### 选型决策（已决，别再重开）

**同库 stage 表**（`lnrs.lnrs_stage_*`），**不是**独立 stage 数据库。三条理由：

1. **B 是 A 的严格子集**：promote 的 SQL 形状完全相同，只差源引用
   （`lnrs.lnrs_stage_X` vs `fdw.lnrs.lnrs_stage_X`）→ 先做便宜的可逆步骤，
   将来要升 A 时 promote 契约不变。
2. **对「闸」这个目的，B 比 A 更结构化**：B 的 stage 表名**硬编码在代码里**，
   配错也改不了；A 的写入目标取决于连接串 —— **config 错就直写生产且静默**，
   与复盘 §7.1 里「纪律 vs 机制」是同一个坑。
3. **成本**：A 需要装 `postgres_fdw`（要超管，`lnrs` 角色 `rolsuper=false`）、
   手工排 FK 顺序（PG 不支持跨库外键）、且跨库**无法单事务**。

### 与前三组的关系

- Issue 20/23 会改到 [Issue 7](./issue-7-fix-etl2-cli-and-backfill-series-count.md)
  引入的 `backfill_dicom_series_count.py`（写入目标改为 stage）——
  Issue 7 的 CLI 三处修复已完成，本组只改**写入目标**，不改其计算口径。
- Issue 21 是 [Issue 19](./issue-19-prefactor-share-copy-then-merge.md)
  与测试沙箱安全闸的**同思路扩展**：那个面向 pytest，这个面向脚本。

---

## 第五组：新桥数据源收尾（issue-24 ~ issue-26）

来源：`ct_mapped.parquet`（CT 报告+DICOM 合并版，2026-09-20 就位）与 5万例人口学
CSV 的对账调研。对账基线：
[`../verify_result/xinqiao-series-counts-fix-20260920.md`](../verify_result/xinqiao-series-counts-fix-20260920.md)
（含同日已完成的 dicom_series 计数校正，commit `3a48640c`，不另立单）。

| 文件 | 用途 | 阻塞 |
|---|---|---|
| `issue-24-xinqiao-cxf-ingest-via-ct-mapped.md` | Issue 24: cxf_archives 7,984 study 入库（ct_mapped 解除 issue-18 的外部映射阻塞） | 无 |
| `issue-25-xinqiao-exam-report-source-completion.md` | Issue 25: exam 报告源补全 — 83,010 Accession 纯报告 + 262 新检查 | 无 |
| `issue-26-xinqiao-placeholder-realization-v2.md` | Issue 26: 占位真实化 v2（承接 issue-15，源改 5万例 CSV，原 exam 机制作废） | 无 |

### 第五组依赖关系

```
Issue 24 （独立；同源，与 25 可并行，exam 灌库路径可复用）
Issue 25 （独立）
Issue 26 （独立；按 PID 键直填，不依赖 24/25；两个决策门需用户拍板）
```

### 与前三组的关系

- Issue 24 实现 [Issue 18](./issue-18-xinqiao-cxf-archives-ingest.md) 的目标
  （18 原文保持不动），并含「用 ct_mapped 复核 issue-13 的 33,110 个
  `anon_exam_id` 回填」验收项。
- Issue 26 承接 [Issue 15](./issue-15-xinqiao-placeholder-realization.md)
  （15 原文保持不动）：原「exam 行取人口学」机制经实测作废（exam/ct_mapped 均无
  sex/birth_date 列），改用 5万例 CSV 真实源；issue-15 的验收断言 1/2 原样继承。
- 三张单完成后，[Issue 16](./issue-16-resync-xinqiao-to-h42.md)（h196_3 → 1.59
  重同步）建议重跑一次，让 h42 看到完整的新桥数据面。
