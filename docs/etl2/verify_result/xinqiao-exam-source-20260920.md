# Issue-13 调研：xinqiao exam 输入源与关联可行性（2026-09-20）

> 对应 issue 验收标准 1「明确 xinqiao exam 的输入源」。
> 环境：本机即 h196_3（10.12.196.3），PG `127.0.0.1:5432 postgres/lnrs`（schema `lnrs`）。

## 1. 输入源结论

**xinqiao exam 输入源 = 新桥 PACS/HIS 的 extracted_tables 导出**
`/data/wlx/DATABASE/extracted_tables/xinqiao/`：

| 文件 | 行数 | 用途 |
|---|---:|---|
| `ct.parquet` | 124,045（distinct exam_id） | **本 issue 唯一灌库源**（exam_type='CT'） |
| `ct_dicom_map.parquet` | 186,678 | exam→series 目录映射（无日期残留 study 的关联兜底，见 §4） |
| `ct_dicom_map.json` | — | 同上的 JSON 形式（不用） |
| `pathology.parquet` / `genetics.parquet` | 19,101 / 4,717 行 | **不灌**（issue-13 只处理 CT exam；与 0904 批次一致） |

- 0904 批次（2026-09-05，batch `843e8c43-…`）曾将 ct.parquet 灌入另一环境；
  **当前 h196_3 的 `lnrs_anon_exam` 无 xinqiao 行**（实测 2026-09-20：exam 表只有
  shengyi / zhujiang），故本 issue 需重新灌库。
- ct.parquet 与 zhujiang extracted_tables 同构（12 列同名同型），复用 0904 适配脚本
  `backend/etl2/etl1_adapt_xinqiao_ct.py`（中文标题 检查所见/检查结论 切分，幂等）。
- 适配产物 staging：`data_xq0913/xinqiao/nodule_imaging.parquet`（独立目录，gitignore；
  防引擎连带导入其他表）。
- 灌库走 issue-6 同款直调 `_import_exam_text_table`（不走 ETL2 CLI：CLI 会连带触发
  xinqiao spec 的 `dicom_series` kind 重注册，违背「不动既有 dicom_series」约束）。

## 2. 关联键实测（patient 维度）

- 患者 HMAC 一致：DICOM 灌库用 `ANON_+HMAC(secret,'xinqiao:'+pid)[:12]`，
  引擎 `compute_anon_id` 同式 → 同 PID 必落同一 `PT_` 行（upsert 复用，不覆盖人口学）。
- 影像侧：xinqiao imaging_study **33,314** / patient **33,313**（1 个 PID 有 2 study）。
- exam 侧：ct.parquet distinct patient_id **49,460**，每人 CT exam 数分布
  1:22,869 / 2:10,546 / … / ≥15:47（**多 CT 患者普遍存在，最多 30 例** →
  仅 patient_id 不足以唯一关联，必须用日期距离消歧）。
- **交集：33,313 个影像患者中 33,109（99.4%）在 ct.parquet 有 ≥1 条 CT exam**；
  204 个影像患者无任何 CT exam → 其 study（共 205 条）保持 NULL（合法，断言 3 不受影响）。
- 多 CT 患者中：单 exam 患者 22,869（交集内更多），日期距离仅在「同患者多 CT」时生效。

## 3. study 日期来源（关联算法沿用 issue-1 的前提）

issue-1 关联口径 = `(patient_id) + |exam_date − study_date| 最小`。xinqiao 的
`image_path` 形态（`…/03_disk/xinqiao/<sub>/img_<PID>_<SeriesUID>` 或
`<MD5>/<StudyUID>/<SeriesUID>`）**不含日期**，`lnrs.path_study_date(image_path)`
对 xinqiao 全部返回 NULL（与 issue-5 zhujiang 前缀问题同族）。

实测日期候选：

| 候选 | 覆盖 | 结论 |
|---|---:|---|
| CSV `exam_date`（扫描产物） | 27,028/33,314 | **弃用**：来源是批次目录名里的导出日期（`exam_date_source='batch_name'`），非检查日期（导出 2026，检查多在 2020-2025） |
| **DICOM StudyInstanceUID 内嵌时间戳** | **31,285/33,314（94%）** | **采用**。GE 等厂商 UID 含 `YYYYMMDDHHMMSSmmm`；取 UID 中第一个可解析为 1990–2030 合法日期的 8+ 位数字串 |
| `ct_dicom_map` 批次名日期 | — | 弃用：同为导出日期 |

**UID 日期 = 检查日期（假设验证）**：对 31,097 个「有 UID 日期 且 患者有 CT exam」的
study，取同患者 exam_date 的最小距离分布：

| best \|exam_date − uid_date\| | study 数 |
|---|---:|
| 0 天 | **31,077（99.93%）** |
| ≤1 天 | 19 |
| ≤7 天 | 1 |
| >7 天 | **0** |

→ UID 内嵌日期就是检查日期；issue-1 的「日期最近」算法对 xinqiao 可安全执行。

## 4. 无日期残留（2,012 study）的兜底

33,110 个可匹配 study 中 31,098 有 UID 日期（执行前分析 33,109/31,097，差 1 例）；
**2,012 个无日期**（非 GE 系 UID：
Siemens `1.2.840.113619.2.359.3…` / `1.2.840.113619.2.55.3…` / `1.2.392.200036…`）：

| 残留子类 | 数量 | 处理 |
|---|---:|---|
| 患者恰好 1 条 CT exam | 795 | 直接指派（无歧义） |
| 患者多条 CT exam | 1,217 | `ct_dicom_map` 文件数精确匹配（见下） |

**文件数启发式**：`ct_dicom_map.parquet` 每行 (patient_id, exam_id, dir, filenames[])，
按 (patient_id, exam_id) 聚合 `sum(len(filenames))` = 该 exam 在盘文件数；
与 study 的 `dicom_series.file_count`（= 扫描实测文件数）相等 → 该 exam 即该 study
的 exam（一个 study 一次检查，文件集合唯一）。执行前 duckdb 分析（对全部 2,012 残留）：

- 2,010 恰好 1 个 exam 文件数和匹配（0 歧义）
- 2 个无匹配（exam 文件未全落盘）→ 再兜底：患者仅 1 exam 取之，否则取
  `anon_exam_id` 字典序最小（与 issue-1 平局规则一致，确定性可复现）

实际执行规则分布（灌库后确定性执行，见执行日志）：

| 规则 | 数量 |
|---|---:|
| single（唯一候选） | 795 |
| filecount（文件数精确匹配） | 1,216 |
| tiebreak（字典序） | 1 |

（多候选 1,217 = filecount 1,216 + tiebreak 1；执行前分析的 2,010 恰一匹配中含
795 个唯一候选患者——其无需文件数匹配即已确定。）

## 5. 预期覆盖率

| 口径 | 预期（执行前） | 实际（2026-09-20 执行） |
|---|---:|---:|
| imaging_study 回填 | 33,109 / 33,314（99.39%） | **33,110 / 33,314（99.39%）** |
| dicom_series 回填（1:1 study） | 33,109 / 33,314 | 33,110 / 33,314 |
| 保持 NULL | 205（204 个无 CT exam 的患者 + 1 个双 study 患者中的另一条） | 204（= 204 个无 CT exam 患者；双 study 患者的两条 study 均匹配成功） |
| tier-1 matchable（有日期） | 31,097 | 31,098 |
| 残留（无日期） | 2,012 | 2,012（single 795 / filecount 1,216 / tiebreak 1） |

断言 3 口径说明：PRD 原文子查询 `s.dicom_study_uid IN (SELECT dicom_study_uid FROM
lnrs_anon_exam …)` 不可执行（`lnrs_anon_exam` 无 `dicom_study_uid` 列，疑为笔误）；
按意图改写为「study 为 NULL 且该患者存在 CT exam」：

```sql
SELECT COUNT(*) FROM lnrs.lnrs_anon_imaging_study s
WHERE s.center_code = 'xinqiao' AND s.anon_exam_id IS NULL
  AND EXISTS (SELECT 1 FROM lnrs.lnrs_anon_exam e
              WHERE e.patient_id = s.patient_id AND e.exam_type = 'CT');
```

预期返回 0。

## 6. 变更面

| 变更 | 说明 |
|---|---|
| `lnrs.uid_study_date(text)`（新 PG 函数） | `0027-uid-study-date.sql`；backfill 的 study 日期表达式改为 `COALESCE(path_study_date(image_path), uid_study_date(dicom_study_uid))`。zhujiang/shengyi 的 UID 无内嵌日期（Siemens 系）且路径日期已覆盖 → 行为不变（执行前 dry-run 计数对照验证） |
| `backend/etl2/backfill_imaging_study_exam_id.py` | 仅 study 日期表达式扩展，关联算法（patient + 日期最近 + anon_exam_id 平局）不变 |
| `backend/etl2/_issue13_ingest_xinqiao_ct_exam.py`（新） | 执行脚本：备份 → 适配 → 灌库（直调引擎）→ tier-1 回填（复用 backfill 模块）→ 残留兜底（文件数/单 exam/平局）→ dicom_series 回填 → 验收断言 |
| `lnrs_anon_exam` / `lnrs_anon_patient`（数据） | +124,045 CT exam；患者 33,109 复用 + ~16,351 新增占位（sex='0'，与 issue-6 zhujiang 占位同语义） |
| `lnrs_anon_imaging_study` / `lnrs_anon_dicom_series`（数据） | 仅 `anon_exam_id` 列从 NULL → 回填；其余列零变更（执行前后行级校验） |
