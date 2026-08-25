# 珠江批次 0825（/data/wlx/DATABASE/extracted_tables/zhujiang）→ h196_3 PG 导入计划

状态：**待批准**（2026-08-25）

## 0. 结论先行

- **h196_3 与 dev 是同一物理库**（127.0.0.1:5432/postgres，schema=lnrs，同密钥）。
  导入用 `ENVIRONMENT=h196_3` 的 ETL2 CLI 直连即可，无额外推送环节。
- 7 个文件：1 个与库内 100% 重复（patient）、1 个库内全量已有但文本有更新（ct，
  去空白后 42,063/97,039 条正文有实质差异，属重新抽取版本）、5 个以新增为主。
- 需 2 处小代码改动：
  1. 引擎一行修复——**空正文不写 report_text 行**（否则 IHC 导入会以空 body 覆盖
     6,698 条病理报告正文，见 §3.1）；
  2. zhujiang spec 追加 inpatient（visit_detail）条目 + IHC 日期字段改用文件自带列。
- 需 5 个 ETL1 适配（patient/ct 直接复用现有脚本 `--src` 换路径，genetics/pathology/
  operation 新写，inpatient 无需适配）；独立 staging 目录 `data_zj0825/`。
- CT 重导会覆盖 97k 条 report_text/exam_detail → **导入前备份**（4 表，含回滚脚本）。

## 1. 目标库现状（已实测，h196_3 = dev 同库）

| 项 | 值 |
|---|---|
| zhujiang patient | 73,321（0814 批次 6,714 真实 + CT 批次占位 ~66,607） |
| zhujiang exam | CT 97,039（ct0820 全量，2026-08-18 最后一次重跑）/ Pathology 39（0723 sample）/ Genetic 12（0723 sample）/ IHC 0 |
| zhujiang visit / surgery | 17 / 47（均为 0723 sample） |
| 字典映射 | zhujiang(hospital_id=1) 6 类齐全：med_sex 7 / med_ethnicity 24 / med_smoking_status 4 / med_blood_type_abo 6 / med_blood_type_rh 6 / med_exam_type 5 |
| 新 patient 值域 | 男/女；22 个民族；从不/现在/既往(+71 空)；O/A/B/AB/未查/不详；阳/阴/未查/不详 —— 与 0814 一致，**无需补种子 SQL**（导入时核对 unmatched=0 兜底） |

## 2. 逐文件分析（DuckDB 实测 + 库内 ID 比对）

| 文件 | 行数 | 库内重叠 | 判定 | 处理方式 |
|---|---|---|---|---|
| patient.parquet | 6,714 | **6,714/6,714（100%）** | 与 0814 同 6,714 人（重抽取版） | 复用 `etl1_adapt_zhujiang0814.py --src`；upsert 原位刷新，0 新增 |
| ct.parquet | 97,039 | **97,039/97,039（100%）** | 与库内 CT 全量同 exam 集；去空白归一化后正文相同 54,976、**实质不同 42,063**（重新抽取，报告文本有更新；旧库正文带 U+3000 全角空格前缀） | 复用 `etl1_adapt_zhujiang_ct0820.py --src`；导入 = 97k report_text + exam_detail 全量刷新，**导入前必须备份** |
| genetics.parquet | 1,091 | 15/1,091 | 新数据（0723 sample 仅 12 条 Genetic） | 新适配脚本：`exam_id→test_id`、`exam_date→test_date`、25 个平铺列按引擎 detail_fields 组装为 4 个 struct 组：`test_meta`(sample_source/test_method/panel_size/pat_local_id/raw_text)、`driver_mutations`(kras±vaf/alk/ros1/ret/ntrk/braf/her2/met/tp53/egfr±vaf/other_variants)、`variant_result`(tmb_per_mb/tmb_level)、`immune_markers`(msi/mmr) |
| ihc.parquet | 6,827 行 / 6,723 唯一 exam_id（100 个 id×2 行，结构化字段相同、仅 raw_text 不同） | 14/6,723 | 新数据；**6,698 个 id 与 pathology 共享**（IHC 与病理同标本） | 适配 `exam_id→specimen_id`；引擎空正文修复为前置；104 个重复行取首行（结构化字段一致，无损）；日期改用文件自带 `exam_date`（见 §3.2） |
| pathology.parquet | 15,542 行 / 15,382 唯一 exam（152 个 exam 跨多行，各行 specimens 为**独立标本**，合计 348 个、完全重复 48 个；specimens/行 分布 0~15，75 行空数组 + 49 行 NULL） | 35/15,382（0723 sample 39 条中的 35 条 id 命中） | 新数据 + sample 原位刷新 | 新适配：按 exam 合并跨行 specimens[] 并去重（348→300），**1 exam 1 行**（`specimen_id := exam_id`，与 IHC id 对齐）、`histology_class` 取合并后首非空、detail 保留完整 specimens 数组（ct0820 nodule_morphology 模式）+ 按 spec detail_fields 分组（specimen_meta/adenocarcinoma_subtypes/tumor_measurement/high_risk_factors/staging） |
| operation.parquet | 18,326 行 / 18,058 唯一 (visit,name)（268 条同 visit 同术名重复） | 47/18,058（0723 sample） | 新数据 | 适配：`visit_id := inpatient_id`、`procedure_name := operation_name`、`surgery_date := operation_date`、`procedure_detail := struct(icd9cm3_code, asa_score, los_days)`；resection_scope/surgical_approach 原名直传；268 条重复由引擎按 (visit,name) hash 去重（设计内行为） |
| inpatient.parquet | 9,590（23 行 inpatient_date 空 → 以 admission_time=NULL 入库不丢弃；14 个 patient_id 不在 patient 表 → 占位发号） | 0 | 全新数据；**引擎 zhujiang 无对应 spec** | 追加 spec 条目 `kind=visit_detail, id_field=inpatient_id, date_field=inpatient_date`（引擎通用逻辑：其余列 chief_complaint/present_illness/diagnoses[]/raw_text 原样进 visit_detail_json，**无需适配脚本**）；operation 的 7,341 个 inpatient_id 全部 ⊆ 本表 9,590 个 → 手术 visit 与住院 visit 同桥关联 |

patient_id 覆盖（占位发号预期）：ct 57,589 个新占位、pathology 2,267、ihc 1,540、
genetics 229、inpatient 14、operation 0。

## 3. 代码改动（2 处，最小化）

### 3.1 引擎一行修复：空正文不写 report_text（**IHC 导入前置**）

- 现状：`lnrs_anon_report_text` PK = `anon_exam_id`（单列，跨 exam_type 唯一）；
  `_import_exam_text_table` 对**每行**无条件追加 report 行（`body=""` 也写），
  upsert `ON CONFLICT DO UPDATE body_clean`。
- 后果：IHC（spec `body_fields=[]`，id 与 pathology 共享 6,698 个）按 spec 顺序在
  pathology 之后导入 → 6,698 条病理 `body_clean` 被覆写为 `""`（静默丢正文）。
  （2026-07-24 修过同类 exam_type 覆盖 bug，report_text 这条路径漏了。）
- 修复：`_import_exam_text_table` 中 `if body:` 非空才 append report 行（1 行改动）。
  影响面：Genetic/IHC（本就无正文）不再产生空 report 行；库内既有 12 条 Genetic
  空正文行不受影响（无害保留）。

### 3.2 zhujiang spec 微调（`_CENTER_PARQUET_SPECS["zhujiang"]`）

- 追加：`{"src_table": "inpatient", "kind": "visit_detail", "id_field": "inpatient_id", "date_field": "inpatient_date"}`（置于 patient 之后、surgery 之前）。
- `ihc_result`：`date_field: ""`（反查同 specimen 的 pathology 日期）→ `"exam_date"`
  （本文件自带日期列；反查方案会丢弃 25 条无 pathology 匹配的 IHC 行）。

## 4. 执行步骤

| 步 | 内容 | 产物/核对 |
|---|---|---|
| S0 | 应用 §3 两处代码改动 | 引擎逻辑单测/干跑确认（dry-run 不连库） |
| S1 | 5 个适配生成 staging：`data_zj0825/zhujiang/{patient,nodule_imaging,genetic_test,ihc_result,pathology_specimen,surgery_record}.parquet` + `inpatient.parquet` 直拷；`.gitignore` 追加 `/data_zj0825/` | 各文件行数/去重统计打印；specimen 合并后 15,382 行、ihc 6,723 行、surgery 18,326 行 |
| S2 | dry-run：`PYTHONPATH="" ENVIRONMENT=h196_3 .venv/bin/python -m app.plugin.module_medical.hospital.anon_etl --dry-run --centers zhujiang --data-root ../data_zj0825` | "将处理 7 个源表"且只含本批目标表 |
| S3 | 导入前备份（Linux 适配 `scripts/backup_dev_zhujiang_ct.sh`：PSQL=psql、无 cygpath、/tmp 路径）：report_text+exam_detail（zhujiang CT exam 集过滤）/ phi_audit（zhujiang 全部 batch）/ patient（zhujiang 全量） | 4 CSV + md5 + 行数核对；记录 BACKUP_DIR |
| S4 | 正式导入：`PYTHONPATH="" ENVIRONMENT=h196_3 .venv/bin/python -m app.plugin.module_medical.hospital.anon_etl --centers zhujiang --data-root ../data_zj0825 > /tmp/zhujiang_0825_run.log 2>&1` | EXIT=0、汇总 success、"未匹配标签 0 条"；预计 3~5 分钟（CT 97k 刷新 + 新增 ~5.5 万 exam/visit） |
| S5 | 验证：分表增量（patient 0 新增/6,714 刷新；CT 0 新增/97,039 刷新；genetics ~1,076；ihc exam 0 新增（合并入 Pathology）+ detail 6,723 条；pathology ~15,347 新增；surgery ~18,011 新增；visit 9,590 新增）；V1-V10（PGCLIENTENCODING=SQL_ASCII）；`med_dict_unmatched` 为空；抽样核对枚举码/bmi/patient_meta/visit_detail_json | 全部通过 |
| S6 | （可选，另行确认）同步 h59：定向增量脚本（仿 `migrate_dev_to_h59_zhujiang_ct0820.sh`，Linux 适配，BATCH_IDS=本批） | 两端 count + md5 对比 |

## 5. 风险与缓解

| 风险 | 缓解 |
|---|---|
| CT 刷新覆盖 97k report_text/exam_detail | S3 备份 + 回滚脚本（Linux 适配 `rollback_dev_ct0820.sh`）；V1-V10 任一失败即回滚 |
| IHC 空正文覆盖病理 body | §3.1 引擎修复（导入前完成并验证） |
| 病理 152 个跨行 exam 若未合并会丢标本 | 适配脚本合并+去重，S1 打印核对 300 标本 |
| raw_text/自由文本含 PHI 入 patient_meta / detail_json / visit_detail_json（无 review_status） | 已知风险（同 0814/ct0820 先例），后续清洗计划覆盖 |
| LNRS_ANON_SECRET 为开发占位密钥 | dev 可用；换密钥=全量重导（不在本批范围） |
| 同库特性：dev 与 h196_3 数据合一 | 无需处理，仅记录 |

## 6. 待人工决策项

1. **CT 是否重导**（推荐执行：42k 条文本为真实更新；不执行则库内 CT 保持 8/18 版本）
2. **inpatient 是否导入**（推荐执行：需 §3.2 spec 追加，无新表、通用 JSONB 落库）
3. **是否同步 h59**（默认不执行）
