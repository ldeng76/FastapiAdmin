# PRD — 让 medicalFiles 页面显示真实文件总大小

> 状态：草稿（draft）
> 创建时间：2026-09-15
> 关联 commit：方案 A 止血 `722e4f66`（已落地）+ 方案 B 脚本骨架 `a9000c56`（已落地，待跑）

## Problem Statement

线上 https://lnrs.nmdi.cn/#/medicalFiles 顶部统计「文件大小」恒显示 `0.00 B`，误导用户以为系统无文件。其它三项统计（患者 / 记录 / 文件）正常。**根因**：`lnrs_anon_dicom_series.byte_size` 在生产库未落库（表里只有手工验证的 4 行），统计接口无法 SUM 出真实字节数。

- 用户视角：运维/医生打开页面看到一个永远为 0 的字节数，不知道是 bug 还是真没有文件。
- 业务影响：医疗数据规模、磁盘占用、备份评估无法从页面直接读出。
- 临时止损（commit 722e4f66）已落地：接口返回 null + 前端显示 `—`，但这只是**症状止血**，根因仍在。

## Solution

把方案 B 完整链路打通：

1. **回填 `imaging_study.anon_exam_id`**：用 exam 表已落库的 CT exam 反查匹配（patient_id + exam_date 距 study_date 最近），UPSERT。
2. **跑 ETL-2 dicom_series 阶段**：扫描 image_path 目录，解析 series 元数据，累加 byte_size，幂等 upsert。
3. **切换 service 到视图**：把统计接口的聚合源从 `lnrs_anon_imaging_study` 切到 `lnrs_anon_v_imaging_study_counts`，还原真实字节展示，并清理方案 A 的临时 `null/—` 兜底。

整条链路跨生产数据库写操作与 ~6-30 小时磁盘 I/O；按 tracer-bullet 切片为 3 个独立 issue（+ 1 个独立调研），每片可在新会话由 `/implement` 启动。

## User Stories

### 核心场景

1. 作为医疗数据运维，我希望 `/#/medicalFiles` 顶部「文件大小」显示真实字节数（如 12.34 GB），从而能快速评估数据规模。
2. 作为医疗数据运维，我希望切筛选条件（模态/中心）后顶部统计仍然正确反映当前筛选下的文件总大小，而不是被 DICOM 体系无 file_type 字段的错误实现误导。
3. 作为医疗数据运维，我希望即使部分 study 因 exam 缺失无法落库 dicom_series，页面也能正常显示（partial backfill ≠ 全 0）。
4. 作为 ETL-2 工程师，我希望 dicom_series 落库脚本是幂等的，重跑同一目录不会破坏既有数据。

### 辅助场景

5. 作为开发，我希望统计接口的 schema 字段类型稳定（int → int|null → int），方便 OpenAPI 自动生成类型准确。
6. 作为运维，我希望 ETL-2 dicom_series 跑库有 dry-run 模式，能先看覆盖范围再决定执行。
7. 作为新会话接手者，我希望 issue 文档自包含，能从 0 开始 `/implement` 而不必先读整个会话上下文。
8. 作为质量把关者，我希望每个 issue 有明确 acceptance criteria，不靠"看着对就行"。

## Implementation Decisions

### 数据流（按方案 B 的三层）

```
imaging_study.image_path  ──┐
                           │
exam.exam_date ──[按 study_date 距离最小]── anon_exam_id  ──UPDATE─→ imaging_study.anon_exam_id
                                                                  │
                                                                  ↓ (image_path 扫描)
                                                          dicom_series.byte_size
                                                                  │
                                                                  ↓ (视图 SUM)
                                            v_imaging_study_counts.total_bytes
                                                                  │
                                                                  ↓ (service 聚合)
                                                statistics.total_size_bytes
                                                                  │
                                                                  ↓ (前端 fileSize)
                                              <strong>X.XX GB</strong>
```

### 关联算法（步骤 1 核心决策）

- 关联键：`(imaging_study.patient_id, exam.patient_id)`
- 模态约束：`exam_type='CT'`（h196_3 上 imaging_study.modality 100%='CT'）
- 时间距离：`|exam.exam_date - lnrs.path_study_date(image_path)|` 最小
- 平局：取 `anon_exam_id` 字典序最小（稳定可复现）
- 不可匹配（patient 不在 exam 表 / exam 表无 CT 行）：保持 NULL，由 dicom_series 阶段跳过

### ETL-2 改造（步骤 2 已有决策，无需新增）

- ETL-2 dicom_series 阶段已在 commit `f8dd292e` 落地：
  - 新增 `kind='dicom_series'` spec；
  - 实现 `_import_dicom_series_for_center` 扫描 `imaging_study.image_path` 列；
  - 通过 `DicomIndexer.register_folder` 拿 series 元数据；
  - `pg_insert ... on_conflict_do_update(dicom_series_uid)` 幂等 upsert；
  - `byte_size` 累加每个 instance 的 `fpath.stat().st_size`；
  - 解析后 `indexer.evict_study` 防单例状态污染。
- 已知降级：`imaging_study.anon_exam_id IS NULL` 时 skip（DDL `dicom_series.anon_exam_id NOT NULL`）。
- 数据规模：119,350 study × 单 study 解析 0.3-1s × 磁盘 stat 6-10 TB = **10-30 小时**（串行，引擎注释明示不可并发）。

### Service 切视图（步骤 3 核心决策）

- 聚合源：`MedFilesModel`（=imaging_study）→ `lnrs_anon_v_imaging_study_counts` 视图。
- 视图字段：`series_count / instance_count / total_bytes / center_code / patient_id / dicom_study_uid`。
- Schema 类型：`total_size_bytes: int = Field(...)`（去除 `int | None` 与 `default=None`）。
- 前端清理：移除 `renderTotalSize()` 的 `—` 兜底、`fileSize()` 直接调用。
- **筛选条件语义**：原 service 在 `imaging_study` 上加 `exam_type / file_type / center_type` in 过滤，但 `imaging_study` 没有 exam_type/file_type 列——当前是**静默 noop**。切视图后需要重新设计筛选语义（视图无 exam_type/file_type；只能按 center_code 过滤，按 modality 需 LEFT JOIN dicom_series）。本 PRD 不展开，由实施 issue 单独决定"筛选行为不变（noop）"还是"重新设计"。

### ADR（已决 / 待决）

#### 已决

- ADR-001：方案 A 作为 UI 止损（已 commit 722e4f66），不撤。
- ADR-002：方案 B 不在本会话执行 dicom_series 跑库——生产数据变更需用户在场拍板。
- ADR-003：脚本骨架放 `backend/etl2/` 下，与既有 `etl1_adapt_*.py` 同目录，便于发现。
- ADR-004：脚本默认 dry-run / 不带 `--apply` 无副作用。

#### 待决（实施时确认）

- ADR-005（步骤 1）：shengyi 0% 覆盖怎么办？本 PRD 主张**不动 shengyi**，等独立调研；先 zhujiang 100% 跑通。
- ADR-006（步骤 3）：service 切视图后筛选条件是否保留（noop）或重新设计？倾向保留 noop + 在文档标记"该筛选在 DICOM 体系无效"。
- ADR-007（步骤 3）：单中心筛选的 service 入口是否要新加 `center_code` 参数？目前 service 不接 center，但影像数据天然按中心分。

## Testing Decisions

### 验证原则

- **只测外部行为**，不测实现细节。
- 数据规模验证以"覆盖报告"代替单元测试：回填率、dicom_series 行数、视图 total_bytes 数值。
- 代码层只保留必要的类型/导入检查（CI 已跑）。

### 各层测试责任

| 层 | 验证手段 |
|---|---|
| 步骤 1 SQL | dry-run 输出覆盖率报告（zhujiang 100% / shengyi 0%）；apply 后用 `SELECT count(*) WHERE anon_exam_id IS NOT NULL` 比对预期 |
| 步骤 2 ETL-2 | 跑库前后 `SELECT count(*), sum(byte_size) FROM lnrs_anon_dicom_series`；与 119,350 × 30.4% = ~36,000 study 估算对比 |
| 步骤 3 service | 启动后端，curl `GET /medical/files/statistics` 断言 `total_size_bytes` 是数字、且 > 0 |
| 步骤 3 前端 | vue-tsc 类型检查 + 浏览器打开页面确认显示非 `—` |

### 回归风险

- 步骤 1 UPDATE 是 idempotent（WHERE anon_exam_id IS NULL 守卫），不会覆盖手工回填的值。
- 步骤 2 ON CONFLICT DO UPDATE 幂等，重跑安全。
- 步骤 3 service 切视图**会移除方案 A 的 null/— 兜底**——若步骤 2 未完成而错误应用步骤 3，页面会显示 85.02 MB（4 行 series）误报。**步骤 3 必须显式断言步骤 2 完成**。

## Out of Scope

- **shengyi exam 入库缺口**（83,000+ study 覆盖率 0%）：根因是 shengyi patient 在 exam 表覆盖率仅 0.26%。这是 ETL-1/ETL-2 shengyi exam 流水线的独立问题，与 dicom_series 回填正交。**列为独立 issue 单独处理**。
- **dicom_instance 落库**：DDL 已声明（0006 §8），ORM 已在 commit f8dd292e 补齐，但本轮不写数据，留作 ETL-3。
- **方案 A 的撤/留**：方案 A 的 null/— 兜底**仅在步骤 3 完成后撤除**；步骤 1+2 期间保持兜底避免误报。
- **生产部署**：本 PRD 不涉及部署；部署窗口由用户在独立会话决定。
- **前端「文件大小」列空值处理**：方案 A 已顺手把 `—` 显示加上（commit 722e4f66）；切视图后该列将真实显示字节数，无须再改。

## Further Notes

### 决策材料

- `local://plan_b_evidence.md`：完整决策材料（h196_3 数据摸底 + 阻断点 + 路径选择）。
- `local://series-count-design-plan.md`：原始 ETL-2 dicom_series 设计（commit f8dd292e 的设计文档）。

### 与既有核验的关系

- `/home/dzy/wk/lnrs/docs/etl2/数据导入核验清单.xlsx`（2026-09-14 收口）覆盖 shengyi 的 23 张 parquet 派生表。本 PRD 对应**核验清单之外的 dicom_series 落库**（数据源是磁盘 DICOM 目录，不在 parquet 体系内）。

### 上下游

- 上游：方案 A 止血（commit 722e4f66）。
- 下游：完成本 PRD 后，`/#/medicalFiles` 顶部「文件大小」从「—」变真实数字；`stats_query.query_series_counts_by_modality` 与 `anon_list_patient_imaging_studies` 已有 series_count 但仍可借助视图 total_bytes 进一步丰富（nice-to-have，独立）。

### 风险

| 风险 | 触发 | 缓解 |
|---|---|---|
| shengyi 覆盖率 0% 让"全量"看起来只跑了一半 | 步骤 2 后 zhujiang 30.4% / shengyi 0% | 文档明示 + 独立 issue 调查 shengyi exam |
| ETL-2 跑库耗时 6-30 小时 | 串行 + 大文件 stat | 备份窗口排期；增量模式 hook 已留 |
| service 切视图后筛选失效 | 视图无 exam_type/file_type 列 | 显式在 service 文档标记 noop；后续按需重构 |
| 步骤 3 在步骤 2 未完成时误应用 | 用户跳步骤 | issue 3 acceptance 显式断言步骤 2 完成 |