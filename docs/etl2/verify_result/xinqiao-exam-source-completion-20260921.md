# Issue 25 实施记录：新桥 exam 报告源补全（Accession 纯报告 + 262 新检查）

PRD：[issue-25-xinqiao-exam-report-source-completion.md](../prd/issue-25-xinqiao-exam-report-source-completion.md)
执行脚本：`backend/etl2/_issue25_ingest_xinqiao_report_source.py`
验收 SQL：`docs/etl2/verify_xinqiao_exam_source_completion.sql`
批次：`6bb700b7-a075-4b0c-9e96-d4df4d16af1f`（2026-09-21 00:47）

## 1. 决策门结论

| 决策门 | 结论 |
|---|---|
| 去重口径 | 按 PRD 预置执行：`source_exam_hash`（exam_id 键）+ `(anon_pid, exam_date, md5(拼接正文))` 三键双口径。**关键实测发现**：ct.parquet（已灌 124,045 行）的 exam_id 本就是 Accession 风格编号（如 `24910031`），ct_mapped 将同一批报告**重键**为 `Accession_<编号>` / StudyUID——两文件 raw_text md5 逐行全等。因此 dated 行的去重全部走**内容三键**（124,046 行命中），hash 键两空间天然不相交（skip_ingested=0），与 PRD 决策门 2 的预判一致 |
| 双 ID 空间 | 新行 exam_no 直接用 ct_mapped exam_id，hash/anon_exam_id 引擎派生；重跑后 244 行由 hash 口径 skip_ingested，证明幂等闭环 |
| 262 行 exam_date NULL | `lnrs.uid_study_date(StudyUID)` 兜底成功 **244** 行 → 灌入；失败 **18** 行（清单 `data_xq_issue25/xinqiao/dropped_no_uid_date.csv`，gitignore，含院内 PID）保持不入，对应患者随之不创建 |

## 2. 执行记录

| 步骤 | 结果 |
|---|---|
| 备份 | `lnrs_anon_{exam,report_text,exam_detail,patient}_bak_20260921_004518`（124,045 / 124,045 / 243,241 / 49,664 行） |
| dry-run | ingest=244，skip_duplicate_content=124,046，skip_ingested=0，drop_no_date=18；跳过数与对账预期（有日期行 124,046 与已灌 raw_text 全等）一致 |
| apply | staging 244 行（0904 适配同款变换：中文标题切分 + nodules 展开 + exam_meta struct）；`_import_exam_text_table` 直调，exam 244 / 新占位 patient 244 / exam_detail 244 / phi_audit 244 / report_text 0（262 新检查行 **raw_text 全空**，引擎 `if body:` 守卫不写 report 行——预期行为） |
| 幂等重跑 | ingest=0，全部 skip（skip_ingested=244 / 三键 124,046 / drop 18），0 新增 |
| 验收 | V1–V9 全过（见 §3） |

## 3. 验收结果（V1–V9）

| # | 断言 | 结果 |
|---|---|---|
| V1 | 三键口径重复 exam | **0** ✓ |
| V2 | 新增 244 行 exam_date 非空率 | 100% ✓ |
| V3 | xinqiao CT exam 总数 | 124,289 = 124,045+244 ✓ |
| V4 | 幂等重跑 0 新增 | ✓ |
| V5 | report_text 覆盖 = raw_text 非空数 | 0/0/244 ✓（源正文全空） |
| V6 | FK 孤儿 | 0 ✓ |
| V7 | batch 状态 | success ✓ |
| V8 | 新占位患者 | 244（sex='0'，is_placeholder=TRUE） |
| V9 | zhujiang/shengyi 零漂移 | exam 98,130/1,037,523；rt 97,039/1,031,221 与执行前一致 ✓ |

## 4. 与 PRD 预期的差异说明

PRD 预期「83,010 行 Accession 纯报告未入库」。实测（series-counts-fix 报告 §2 对账 +
本次内容键复核）：**这 83,010 份报告的 raw_text 与已灌 124,045 行内容全等**（ct.parquet
的 exam_id 即无前缀 Accession 编号，issue-13 时已全部入库）。按 PRD 决策门 1「三键幂等
跳过已入库内容、不得产生重复 exam」，dated 行全部跳过是**正确结论而非缺漏**——按
`(patient_id, exam_date, report_text hash)` 口径灌入只会产生纯重复 exam，直接违反验收
断言 V1。端到端目标（报告文本可查、exam 计数反映真实检查量）由 issue-13 已灌数据 +
本次 244 个新检查共同满足。

## 5. 变更文件

| 文件 | 改动 |
|---|---|
| `backend/etl2/_issue25_ingest_xinqiao_report_source.py` | 新建：备份→分类（seam `decide_row`）→staging→灌库→幂等→验收 |
| `backend/tests/anon_etl/test_issue25_report_source.py` | 新建：`decide_row` / 正文口径 seam 测试 8 例 |
| `docs/etl2/verify_xinqiao_exam_source_completion.sql` | 新建：V1–V9 |
| `.gitignore` | 加 `/data_xq_issue25/` |
| `data_xq_issue25/xinqiao/`（gitignore） | staging nodule_imaging.parquet + `dropped_no_uid_date.csv`（18 行） |

## 6. 后续

- 18 个无内嵌日期的 StudyUID 检查（患者随之缺席）待 issue-26 / 后续工单定日期源后处理。
- 占位患者真实化归 issue-26。
