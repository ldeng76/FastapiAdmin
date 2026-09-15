# `lnrs_anon_*` 匿名 Schema 各表用途说明

> 本文档汇总 PostgreSQL `lnrs` schema 下所有 `lnrs_anon_*` 表的用途、字段语义与 ETL 写入路径。
> 编写依据：dev 库（`127.0.0.1:5432`/postgres）`pg_class`/`pg_type`/`pg_constraint` 元数据快照 +
> [0006-anonymized-schema-lnrs.sql](../backend/sql/postgres/0006-anonymized-schema-lnrs.sql) +
> [0010-shengyi-anon-tables.sql](../backend/sql/postgres/0010-shengyi-anon-tables.sql) +
> [anon_etl_engine.py](../backend/app/plugin/module_medical/hospital/anon_etl_engine.py) +
> [anonymize.py](../backend/app/plugin/module_medical/hospital/anonymize.py)。

相关 ADR / 文档：
- [ADR-0001 统一确定性脱敏](./adr/0001-linkable-anonymization.md)
- [ADR-0006 脱敏后落库 Schema](./adr/0006-anonymized-data-schema.md)
- [ETL-2 脱敏落库流水线](./etl2_anon_pipeline.md)
- [省医(shengyi)扩展表 schema 设计](./spec-shengyi-anon-etl-design.md)

---

## 1. 整体结构

```
lnrs_anon_ingest_batch            批次锚点（其它表 FK 根）
        │
        ├─ lnrs_anon_patient       患者主表（双 ID 体系 PT_xxxxxxxx / ANON_<HMAC>）
        │      │
        │      ├─ lnrs_anon_visit        就诊桥（轻量）
        │      │      │
        │      │      ├─ lnrs_anon_visit_detail   visit 1:1 富信息（仅省医）
        │      │      ├─ lnrs_anon_surgery        visit 级手术
        │      │      ├─ lnrs_anon_lab_result     visit 级检验（仅省医）
        │      │      └─ lnrs_anon_order          visit 级医嘱（仅省医）
        │      │
        │      └─ lnrs_anon_exam          检查主表（跨模态桥梁）
        │             │
        │             ├─ lnrs_anon_report_text     报告原文（1:1）
        │             ├─ lnrs_anon_exam_finding    EAV 标量（本轮不写入）
        │             ├─ lnrs_anon_exam_detail     JSONB 深结构（pathology/genetic/ihc/结节）
        │             ├─ lnrs_anon_dicom_series    DICOM 序列（ETL-2 增量 2026-09-15）
        │             │     └─ lnrs_anon_dicom_instance  关键帧偏移（ORM 已声明，留作 ETL-3）
        │             └─ lnrs_anon_dicom_uid_map   UID 重映射审计（不进生产库）
        │
        └─ lnrs_anon_phi_audit     字段级 PHI 清洗审计（与批次平级）
```

设计约定：
- 每张业务表都有 `created_batch_id`（FK → `ingest_batch`，ON DELETE CASCADE），`patient` / `exam` / `visit` 三张主表还多带 `last_seen_batch_id`，`patient` 多带 `deleted_batch_id`。
- 幂等键：`(center_code, source_*_hash)` 或全局 `source_*_hash` UNIQUE，重复导入只刷新 `last_seen_batch_id` 与日期。
- 双 ID 体系：`patient_id`（`PT_xxxxxxxx` 对外 PK）/ `anon_id`（`ANON_<HMAC>` 反查键）；visit `ANON_VISIT_<HMAC[:12]>`，exam `ANON_EXAM_<12hex>`。
- 删除语义：FK 全部 `ON DELETE CASCADE`，`patient` 用 `deleted_at` + `deleted_reason` + `deleted_batch_id` 软删除，purge 任务通过 `lnrs_anon_ix_patient_deleted` 部分索引扫描物理清理。
- 枚举权威外移：`sex`/`laterality` 字典权威已迁 `med_sex` / `med_laterality`，约束改为 `CHECK`（详见 [§6 与文档的差异](#6-与文档的差异)）。

---

## 2. 元数据层（批次管理）

### 2.1 `lnrs_anon_ingest_batch`

单次 ETL 导入的批次锚点。

| 关键字段 | 语义 |
|---|---|
| `batch_id` | UUID 主键，所有业务表的 FK 根 |
| `center_code` | 中心代码（小写蛇形命名） |
| `source_kind` | `csv_report` / `dicom_dir` / `dicom_zip`（当前 ETL 仅 `csv_report`） |
| `source_locator` | 源定位（路径/对象 key） |
| `source_sha256` | 源 SHA256（来自 ETL-1 的 `conversion_manifest.json`） |
| `secret_version` + `key_fingerprint` | 脱敏密钥版本 + SHA256(secret) 前 16 hex |
| `schema_hash` | 0006 DDL 文件 SHA256，DLT 结构变化时漂移 |
| `row_counts` | JSONB，每张源表本次导入行数 |
| `started_at` / `finished_at` / `status` / `error` | 批次元状态（`running` / `success` / `failed` / `partial`） |

写入方：`anon_etl_service._create_batch` / `_close_batch`，事务外独立 commit，失败回滚后批次记录仍保留。
唯一约束：`(center_code, secret_version, key_fingerprint, schema_hash, started_at)`。

---

## 3. 患者主索引层

### 3.1 `lnrs_anon_patient_seq`

全局自增物理序号序列（`INCREMENT 1`，MAXVALUE 99999999，CACHE 50）。

ETL 调用路径：`_batch_upsert_patients` → `SELECT nextval('lnrs.lnrs_anon_patient_seq') FROM generate_series(1, n)` 批量发号 → 应用层拼成 `PT_00000001` 格式。

### 3.2 `lnrs_anon_patient`

患者主表，双 ID 体系。

| 字段 | 类型 | 语义 |
|---|---|---|
| `patient_id` | VARCHAR(16) PK | `PT_xxxxxxxx`，对外业务 ID 即 PK |
| `anon_id` | VARCHAR(32) UNIQUE | `ANON_<HMAC>`，内部反查键 |
| `center_code` | VARCHAR(32) | 中心代码 |
| `birth_date` | DATE | 出生日期 |
| `sex` | VARCHAR(10) | 性别（CHECK 字典值 `'0'/'1'/'2'/'9'`） |
| `ethnicity` / `smoking_status` / `abo_blood_type` / `rh_blood_type` | VARCHAR | 国标字典值 |
| `native_place` / `first_nodule_date` / `bmi` | 各类型 | 稳定属性（从 patient.parquet 直接承载） |
| `patient_meta` | JSONB | 兜底终身属性：家族史/既往肿瘤/合并症/发现途径/吸烟包年等 |
| `created_batch_id` / `last_seen_batch_id` / `deleted_batch_id` | UUID | 批次双 FK + 软删除批 FK |
| `created_at` / `updated_at` / `deleted_at` / `deleted_reason` | 时间戳 | 含触发器自动维护 `updated_at` |

写入方：
- 主路径 `_batch_upsert_patients`（patient.parquet）。
- 占位路径 `_import_exam_text_table` / `_import_surgery_table` / `_import_visit_detail_table` / `_import_lab_table` / `_import_order_table` 以 `is_placeholder=True` 模式预建 FK 行。

三态机：活行 UPDATE `last_seen_batch_id` + 人口学 / 软删复活（清 `deleted_*`） / 新行 INSERT。
唯一约束：`(center_code, anon_id)` 与 `patient_id` PK 双重去重。
格式约束：`patient_id` 匹配 `^PT_[0-9]{8}$`，`anon_id` 匹配 `^ANON_[0-9a-f]{12}$`。

---

## 4. 就诊 / 事件层

### 4.1 `lnrs_anon_visit`

就诊桥表（轻量）。`anon_visit_id` 形如 `ANON_VISIT_<HMAC[:12]>`，FK → `patient`。

| 关键字段 | 语义 |
|---|---|
| `anon_visit_id` | 主键 |
| `patient_id` | FK → `lnrs_anon_patient.patient_id` |
| `visit_ordinal` | 原始 visit_id（如 `153623_1`），保留溯源 |
| `source_visit_hash` | (center, visit_id) 裸 SHA256，幂等键 |
| `created_batch_id` / `last_seen_batch_id` | 批次双 FK |

唯一约束：`(center_code, source_visit_hash)` 与 `(patient_id, visit_ordinal)`。

写入方：
- 珠江/新桥：`_import_surgery_table` 从 `surgery_record.visit_id` 反推。
- 省医：`_import_visit_detail_table` 自建 visit 桥（不依赖 surgery）。

注意：珠江/新桥本轮显式跳过 `visit_record`（"ADR-0006 visit 桥未启用"），仅省医启用。

### 4.2 `lnrs_anon_visit_detail`（仅省医，0010）

visit 1:1 富信息。`visit_detail_json` 忠实保留原始嵌套（病案首页/病史/diagnoses[]/clinical_documents[]），不做语义对齐，date 字段转 ISO。

| 字段 | 类型 | 语义 |
|---|---|---|
| `visit_detail_id` | BIGSERIAL PK | |
| `anon_visit_id` | VARCHAR(40) FK UNIQUE | 1:1（由本函数自建 visit 桥） |
| `visit_category` | VARCHAR(32) | 住院/门诊 |
| `admission_time` / `discharge_date` | DATE | |
| `admission_dept` / `discharge_dept` / `payment_method` | VARCHAR | |
| `length_of_stay` / `visit_age` | INTEGER / NUMERIC | |
| `visit_detail_json` | JSONB NOT NULL | 病案首页/病史/诊断数组/临床文档 |
| `source_visit_hash` | CHAR(64) | 复用 visit 桥 hash（1:1 关联） |

写入方：`_import_visit_detail_table`（仅 shengyi 中心启用）。

---

## 5. 检查（影像/病理/基因）层

### 5.1 `lnrs_anon_exam`

检查主表，跨模态桥梁。`anon_exam_id` = `ANON_EXAM_<12hex>`（HMAC of center+exam_no）。

| 字段 | 类型 | 语义 |
|---|---|---|
| `anon_exam_id` | VARCHAR(40) PK | |
| `patient_id` | VARCHAR(16) FK | → `lnrs_anon_patient` |
| `exam_type` | VARCHAR(32) | CT/Pathology/Genetic/IHC/Radiology/Ultrasound |
| `exam_date` | DATE NOT NULL | |
| `source_exam_hash` | CHAR(64) | SHA256(center+exam_no)，幂等键 |
| `anon_visit_id` | VARCHAR(40) FK NULL | → `lnrs_anon_visit`（ON DELETE SET NULL） |
| `created_batch_id` / `last_seen_batch_id` | UUID | 批次双 FK |

唯一约束：`(center_code, source_exam_hash)`。

**关键：首次入库锁定 `exam_type` 与 `patient_id` 不再覆盖**（修 IHC 复用 specimen_id 时被覆盖的 bug），但 `exam_date` / `last_seen_batch_id` 仍刷新。DDL 里没有专门的"首次锁定"约束，是 ETL 通过 `ON CONFLICT DO UPDATE` 时把这两列从 SET 子句里剔除实现的。

### 5.2 `lnrs_anon_report_text`

报告原文，1:1 关联 `anon_exam_id`（PK 即 FK，ON DELETE CASCADE）。

| 字段 | 语义 |
|---|---|
| `body_clean` | `findings` / `impression` / `pathology_diagnosis` 等用 `\n\n` 拼接后 `truncate_body` 到 10 万字符的结果 |
| `pii_replaced_count` | 替换次数（当前 ETL 恒为 0） |
| `clean_method` | `regex_only` / `regex+llm` / `manual_review`（当前恒为 `regex_only`） |
| `llm_model` | 当前恒 NULL |
| `review_status` | `pending` / `reviewed` / `flagged`（当前恒为 `pending`） |

写入方：`_import_exam_text_table` → `_batch_upsert_report_text`。

**本轮约定**：`pii_replaced_count=0` / `clean_method='regex_only'` / `review_status='pending'` / `llm_model=NULL`——即先存原文待人工/LLM 抽检，本轮不替换 PHI。

### 5.3 `lnrs_anon_exam_finding`（本轮不写入）

EAV 标量表。PK `(finding_id BIGSERIAL)`，UNIQUE `(anon_exam_id, finding_type, raw_value_hash)`，字段 `finding_type` / `value_numeric` / `value_text` / `laterality` / `raw_value_hash`。

**本轮 ETL 不写入**：`anon_model.py` 注释明确"finding 表实际不写入，自由文本不拆分，模型保留"。DDL 与 ORM 都建好但无调用方。预留未来把结节长径 / Ki67 / TPS 等拆成 EAV 标量行（与 JSONB 装的 `exam_detail` 并存互补）。

### 5.4 `lnrs_anon_exam_detail`

exam 级 JSONB 深结构。PK 复合 `(anon_exam_id, detail_type, detail_ordinal)` 实现 1:N。

| 字段 | 语义 |
|---|---|
| `detail_type` | `nodule_imaging` / `pathology` / `genetic` / `ihc` / `imaging_report` / `ultrasound` |
| `detail_ordinal` | 默认 1；多结节场景（zhujiang `nodule_no`='n1'/'n2'）解析为 1/2/3/4 |
| `detail_json` | 嵌套结构（driver_mutations、staging、腺癌亚型等），date/datetime 走 `_json_safe` 转 ISO 字符串 |
| `created_batch_id` | 批次 FK |

带 GIN 索引 `lnrs_anon_ix_exam_detail_gin` 支持 `detail_json` 全文检索。

写入方：`_import_exam_text_table` → `_batch_upsert_exam_detail`。

关键设计：同 exam 不同 detail_type 共享 specimen_id 时各成行不互覆盖；多结节 1:N 展开。

---

## 6. 影像（DICOM）层

> 2026-09-15 起 `lnrs_anon_dicom_series` 已被 ETL-2 增量阶段写入（解析 `lnrs_anon_imaging_study.image_path` 目录 → series 明细 upsert）；`dicom_instance` ORM 已声明、ETL 不写入，留作 ETL-3。`dicom_uid_map` 仍按 ADR 物理隔离不进生产库。

### 6.1 `lnrs_anon_dicom_series`

DICOM 序列级元数据。`series_id BIGSERIAL`，UNIQUE `dicom_series_uid`。

| 关键字段 | 语义 |
|---|---|
| `anon_exam_id` | FK → `lnrs_anon_exam` |
| `dicom_series_uid` / `dicom_study_uid` | 新匿名 UID + 关联 study |
| `modality` / `body_part` | |
| `instance_count` / `file_count_actual` / `byte_size` | 计数与字节数 |
| `file_root` | NAS/OSS 路径 |
| `series_no` | 默认 1 |

带 `updated_at` 触发器 `lnrs_anon_tg_series_updated`。

### 6.2 `lnrs_anon_dicom_instance`

DICOM 关键帧实例。PK 复合 `(series_id, instance_no)`，UNIQUE `sop_instance_uid`。

| 关键字段 | 语义 |
|---|---|
| `series_id` | FK → `dicom_series` |
| `sop_instance_uid` | UNIQUE |
| `instance_no` | > 0 |
| `byte_offset` | 文件偏移，配合 `file_root` 定位 |

设计：仅登记关键帧偏移，不入全量像素。

### 6.3 `lnrs_anon_dicom_uid_map`

DICOM UID 重映射审计。PK 复合 `(batch_id, kind, old_uid)`。

| 字段 | 语义 |
|---|---|
| `batch_id` | FK → `ingest_batch` |
| `kind` | `study` / `series` / `sop` |
| `old_uid` / `new_uid` | 旧→新匿名 UID 映射 |

按 ADR 物理隔离不进生产库，仅审计隔离库使用。

---

## 7. 手术 / 医嘱层（医疗事件）

### 7.1 `lnrs_anon_surgery`

visit 级手术记录。FK → visit + patient。

| 关键字段 | 语义 |
|---|---|
| `anon_visit_id` | FK → `lnrs_anon_visit`（同 visit 多条不同手术用 `procedure_name` 区分） |
| `surgery_date` | DATE |
| `procedure_name` | VARCHAR(200)，截 200 字 |
| `resection_scope` / `surgical_approach` | 切除范围 / 手术入路 |
| `procedure_detail` | JSONB，icd9cm3_code / 淋巴结清扫 / 时长 / 出血量 |
| `source_surgery_hash` | CHAR(64)，SHA256(center+visit_id+procedure_name)，幂等键 |

唯一约束：`(anon_visit_id, source_surgery_hash)`。

写入方：`_import_surgery_table` → `_batch_upsert_surgeries`。

### 7.2 `lnrs_anon_lab_result`（仅省医，0010）

visit 级检验。`anon_visit_id` 可空（visit 缺失时退化为只挂 patient）。

| 关键字段 | 语义 |
|---|---|
| `report_id` | VARCHAR(64) |
| `test_name` / `item_name` | 检验组合名 / 单项名 |
| `item_result` | VARCHAR(255)，字符串结果（含定性/比值） |
| `item_result_value` | NUMERIC(12,4)，数值结果（非数值结果时 NULL） |
| `item_unit` / `collection_time` | 单位 / 采集时间（1900-01-01 哨兵过滤为 NULL） |
| `lab_detail_json` | JSONB，`test_detail` 等剩余结构 |
| `source_lab_hash` | CHAR(64)，SHA256(center:report_id:item_name)，全局唯一 |

幂等键：`source_lab_hash` UNIQUE（全局，不依赖 `anon_visit_id`，避免 NULL visit_id 重跑重复插入）。

写入方：`_import_lab_table`（仅 shengyi）。

### 7.3 `lnrs_anon_order`（仅省医，0010）

visit 级医嘱，drug + non_drug 合并。`anon_visit_id` 可空。

| 关键字段 | 语义 |
|---|---|
| `order_type` | VARCHAR(16)，`drug` / `non_drug`（`drug` 取 `drug_generic_name`，`non_drug` 取 `order_name`） |
| `order_name` | VARCHAR(200)，截 200 字 |
| `order_time` / `order_source` | 开立时间 / `inpatient` / `outpatient` |
| `order_detail_json` | JSONB，`order_detail` struct（剂量/频次/途径...） |
| `source_order_hash` | CHAR(64)，SHA256(center:order_time:order_name:order_type) |

幂等键：`source_order_hash` UNIQUE（全局，不依赖 `anon_visit_id`），用 `order_time` + `order_type` 区分同名医嘱的多次开立。

写入方：`_import_order_table`（drug_order + no_drug_order 两源合一，仅 shengyi）。

---

## 8. 审计 / 合规层

### 8.1 `lnrs_anon_phi_audit`

字段级 PHI 清洗审计日志。每条记录对应一次 PHI 处理行为。

| 关键字段 | 语义 |
|---|---|
| `batch_id` | FK → `ingest_batch` |
| `source_table` / `source_field` | 被脱敏的来源列 |
| `source_hash` | `hash_for_audit(orig_value)` 的 SHA256（原值不进库只留指纹） |
| `strategy` | `hmac` / `clear` / `partial_keep` / `llm_replace` / `manual_review` |
| `confidence` | NUMERIC(4,3) ∈ [0,1] |

写入方：每个导入分支末尾统一调用 `_write_phi_audit_batch`（仅 INSERT 不去重）。

当前 ETL 写入规则：

| 字段 | strategy | confidence |
|---|---|---|
| `patient_id` / `exam_id` / `specimen_id` / `visit_id` | `hmac` | 1 |
| `birth_date` | `partial_keep` | 1 |
| 正文列（`findings` / `impression` 等） | `llm_replace` | 0（占位，标识本轮实际未替换） |

---

## 9. 跨表对象

### 9.1 触发器与函数

| 函数 / 触发器 | 挂载表 | 作用 |
|---|---|---|
| `lnrs_anon_trg_set_updated_at()` | — | 通用 `updated_at` 自动维护 |
| `lnrs_anon_tg_patient_updated` | `lnrs_anon_patient` | UPDATE 时刷新 `updated_at` |
| `lnrs_anon_tg_exam_updated` | `lnrs_anon_exam` | 同上 |
| `lnrs_anon_tg_report_updated` | `lnrs_anon_report_text` | 同上 |
| `lnrs_anon_tg_series_updated` | `lnrs_anon_dicom_series` | 同上 |
| `lnrs_anon_tg_visit_updated` | `lnrs_anon_visit` | 同上 |

未挂触发器的：`dicom_instance` / `dicom_uid_map` / `exam_detail` / `exam_finding` / `phi_audit` / `ingest_batch` / `surgery` / `visit_detail` / `lab_result` / `order`——这些表也不带 `updated_at` 列。

### 9.2 视图 `lnrs_anon_v_exam_full`

检查跨模态汇总视图：join patient + exam + report_text + finding + dicom_series，按 exam 聚合得到 `finding_count`、`series_count` 与 `body_clean` / `review_status`。

```sql
SELECT e.anon_exam_id, p.patient_id, p.anon_id, e.center_code,
       e.exam_type, e.exam_date, rt.body_clean, rt.review_status,
       COUNT(DISTINCT f.finding_id) AS finding_count,
       COUNT(DISTINCT s.series_id)  AS series_count
FROM lnrs_anon_exam e
JOIN lnrs_anon_patient       p  ON p.patient_id   = e.patient_id
LEFT JOIN lnrs_anon_report_text  rt ON rt.anon_exam_id = e.anon_exam_id
LEFT JOIN lnrs_anon_exam_finding f  ON f.anon_exam_id  = e.anon_exam_id
LEFT JOIN lnrs_anon_dicom_series s  ON s.anon_exam_id  = e.anon_exam_id
GROUP BY e.anon_exam_id, p.patient_id, p.anon_id, rt.body_clean, rt.review_status;

### 9.3 视图 `lnrs_anon_v_imaging_study_counts`（2026-09-15 引入）

study 维度 series 聚合：给"患者详情 → 影像列表"展示 `series_count` /
`instance_count` / `total_bytes`。LEFT JOIN 让 series 未落库的 study 也
返回 0（前端 UI 显示「序列数 0」而不是 NULL）；不引入表达式索引（单 patient
路径 ≤ 几十行 + `lnrs_anon_ix_imaging_study_uid` + `lnrs_anon_ix_series_study_uid`
双索引，毫秒级）。定义见 `backend/sql/postgres/0020-imaging-study-counts-view.sql`：

```sql
SELECT ims.study_key, ims.dicom_study_uid, ims.center_code,
       ims.patient_id, ims.anon_exam_id,
       COUNT(s.series_id)::INT                  AS series_count,
       COALESCE(SUM(s.instance_count), 0)::BIGINT AS instance_count,
       COALESCE(SUM(s.byte_size), 0)::BIGINT      AS total_bytes
FROM lnrs.lnrs_anon_imaging_study ims
LEFT JOIN lnrs.lnrs_anon_dicom_series s
       ON s.dicom_study_uid = ims.dicom_study_uid
GROUP BY ims.study_key, ims.dicom_study_uid, ims.center_code,
         ims.patient_id, ims.anon_exam_id;
```

与 §9.2 `v_exam_full` 正交：前者按 exam 聚合、后者按 study 聚合。

---

## 10. 写入路径速查

```
patient.parquet           → lnrs_anon_patient (主)
visit_record.parquet      → lnrs_anon_visit (省医自建桥) + lnrs_anon_visit_detail (仅省医)
surgery_record.parquet    → lnrs_anon_visit (珠江/新桥反推桥) + lnrs_anon_surgery
nodule_imaging.parquet    → lnrs_anon_exam(CT) + lnrs_anon_report_text + lnrs_anon_exam_detail
pathology_specimen.parquet→ lnrs_anon_exam(Pathology) + lnrs_anon_report_text + lnrs_anon_exam_detail
genetic_test.parquet      → lnrs_anon_exam(Genetic) + lnrs_anon_exam_detail
ihc_result.parquet        → lnrs_anon_exam(IHC) + lnrs_anon_exam_detail
imaging_report.parquet    → lnrs_anon_exam + lnrs_anon_report_text + lnrs_anon_exam_detail
ultrasound_report.parquet → lnrs_anon_exam + lnrs_anon_report_text + lnrs_anon_exam_detail
drug_order.parquet        → lnrs_anon_order (order_type='drug', 仅省医)
no_drug_order.parquet     → lnrs_anon_order (order_type='non_drug', 仅省医)
lab_result.parquet        → lnrs_anon_lab_result (仅省医)
lnrs_anon_imaging_study (0012 CSV 灌库)
   image_path 目录扫描   → lnrs_anon_dicom_series (ETL-2 增量；2026-09-15 启用，
                          解析 .dcm → series 明细；anon_exam_id 为空时跳过)

每个导入分支末尾追加 → lnrs_anon_phi_audit
```

公共依赖顺序：`patient → visit_detail（建 visit 桥 + 富信息）→ exam_text / surgery / lab / order`。
所有写入共用 `pg_insert(...).on_conflict_do_update(...)` 幂等 upsert。

---

## 11. 与文档的差异

dev 库 `pg_class` / `pg_type` / `pg_constraint` 元数据与 DDL 注释不完全一致：

1. **`lnrs_anon_sex_enum` 与 `lnrs_anon_laterality_enum` 在库内仍存在**（旧值 `M/F/U`、`L/R/Bilateral/N/A`）。0006 注释称"已删除，权威移交 med_sex/med_laterality 字典表"，但 `DROP TYPE IF EXISTS lnrs.lnrs_anon_sex_enum CASCADE` / `..._laterality_enum CASCADE` 在库内并未实际执行——这两个 enum 当前是孤儿类型。约束侧已迁移：patient 用 `lnrs_anon_ck_patient_sex` CHECK，finding 用 `lnrs_anon_ck_finding_laterality` CHECK。**建议后续手动 DROP 这两个孤儿 enum**，否则 ALTER 维护路径会被它们干扰。
2. **DICOM 三张表（`dicom_series` / `dicom_instance` / `dicom_uid_map`）+ `exam_finding`** 已建 DDL，但本轮 ETL 实际不写入；DDL/触发器占位、ORM 未建模，等 `dicom_dir`/`dicom_zip` 源接入再用。
3. **`report_text` 写入策略**：现网 ETL 明确把 `pii_replaced_count=0`、`clean_method='regex_only'`、`review_status='pending'`、`llm_model=NULL` 作为本轮约定——是设计而非 bug（先存原文待抽检）。
4. **`exam` 的 `exam_type` / `patient_id` 锁**：DDL 里没有专门的"首次锁定"约束，是 ETL 通过 `ON CONFLICT DO UPDATE` 时把这两列从 SET 子句里剔除实现的。文档读者单看 DDL 会误以为可以任意更新这两列。
5. **珠江/新桥中心的 visit 桥状态**：库内 `visit` 表已建好，但当前 ETL 在这两中心**显式跳过 visit_record**（仅省医启用 visit_detail + lab + order 三张表）——文档若只说"visit 从 surgery_record.visit_id 反推"会与现状不一致。

---

## 附录：库内对象清单（dev）

```
function: lnrs_anon_trg_set_updated_at

sequence: lnrs_anon_dicom_series_series_id_seq
          lnrs_anon_exam_finding_finding_id_seq
          lnrs_anon_lab_result_lab_result_id_seq
          lnrs_anon_order_order_id_seq
          lnrs_anon_patient_seq
          lnrs_anon_phi_audit_audit_id_seq
          lnrs_anon_surgery_surgery_id_seq
          lnrs_anon_visit_detail_visit_detail_id_seq

table:    lnrs_anon_dicom_instance
          lnrs_anon_dicom_series
          lnrs_anon_dicom_uid_map
          lnrs_anon_exam
          lnrs_anon_exam_detail
          lnrs_anon_exam_finding
          lnrs_anon_ingest_batch
          lnrs_anon_lab_result
          lnrs_anon_order
          lnrs_anon_patient
          lnrs_anon_phi_audit
          lnrs_anon_report_text
          lnrs_anon_surgery
          lnrs_anon_visit
          lnrs_anon_visit_detail

trigger:  lnrs_anon_tg_exam_updated
          lnrs_anon_tg_patient_updated
          lnrs_anon_tg_report_updated
          lnrs_anon_tg_series_updated
          lnrs_anon_tg_visit_updated

type:     lnrs_anon_clean_method_enum
          lnrs_anon_ingest_status_enum
          lnrs_anon_laterality_enum   ← 孤儿（应 DROP）
          lnrs_anon_phi_strategy_enum
          lnrs_anon_review_status_enum
          lnrs_anon_sex_enum          ← 孤儿（应 DROP）
          lnrs_anon_source_kind_enum
          lnrs_anon_uid_kind_enum

view:     lnrs_anon_v_exam_full
```