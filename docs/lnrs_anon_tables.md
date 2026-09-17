# `lnrs_anon_*` 匿名 Schema 各表用途说明

> 本文档汇总 PostgreSQL `lnrs` schema 下所有 `lnrs_anon_*` 表/视图的用途、字段语义、行数规模与 ETL 写入路径。
>
> **编写依据：dev_h1963 环境**（`backend/env/.env.dev_h1963` → `lnrs.pg.h1963:5432`/postgres，schema `lnrs`）
> `pg_class` / `pg_attribute` / `pg_constraint` / `pg_indexes` / `pg_sequences` 元数据实拍
> （快照日期 **2026-09-16**，行数为当日精确或 `reltuples` 估计值）+
> [0006](../backend/sql/postgres/0006-anonymized-schema-lnrs.sql) /
> [0010](../backend/sql/postgres/0010-shengyi-anon-tables.sql) /
> [0012](../backend/sql/postgres/0012-imaging-study-bridge.sql) /
> [0014](../backend/sql/postgres/0014-shengyi-anon-extend-2026-09.sql) /
> [0016](../backend/sql/postgres/0016-imaging-orphan-registry.sql) /
> [0018](../backend/sql/postgres/0018-anon-patient-is-placeholder.sql) 等 SQL 迁移 +
> [anon_model.py](../backend/app/plugin/module_medical/hospital/anon_model.py) +
> [anon_etl_engine.py](../backend/app/plugin/module_medical/hospital/anon_etl_engine.py)。

相关 ADR / 文档：
- [ADR-0001 统一确定性脱敏](./adr/0001-linkable-anonymization.md)
- [ADR-0006 脱敏后落库 Schema](./adr/0006-anonymized-data-schema.md)
- [ETL-2 脱敏落库流水线](./etl2_anon_pipeline.md)
- [省医(shengyi)扩展表 schema 设计](./spec-shengyi-anon-etl-design.md)

---

## 1. 整体结构

```
lnrs_anon_ingest_batch            批次锚点（业务表 FK 根，87 批次）
        │
        ├─ lnrs_anon_patient       患者主表（双 ID 体系 PT_xxxxxxxx / ANON_<HMAC>）
        │      │
        │      ├─ lnrs_anon_visit        就诊桥
        │      │      │
        │      │      ├─ lnrs_anon_visit_detail     visit 1:1 富信息（省医/珠江住院/301）
        │      │      ├─ lnrs_anon_surgery          visit 级手术
        │      │      ├─ lnrs_anon_lab_result       visit 级检验（可退化为只挂 patient）
        │      │      ├─ lnrs_anon_order            visit 级医嘱（可退化为只挂 patient）
        │      │      └─ lnrs_anon_vital_observation 生命体征/观察测量 ★（可只挂 patient）
        │      │
        │      ├─ lnrs_anon_exam          检查主表（跨模态桥梁）
        │      │      │
        │      │      ├─ lnrs_anon_report_text     报告原文（1:1）
        │      │      ├─ lnrs_anon_exam_finding    EAV 标量（DDL 就绪，本轮不写入）
        │      │      ├─ lnrs_anon_exam_detail     JSONB 深结构（1:N）
        │      │      └─ lnrs_anon_dicom_series    DICOM study 级元数据（2026-09-15 重构）★
        │      │            └─ lnrs_anon_dicom_instance  关键帧偏移（未启用，留作 ETL-3）
        │      │
        │      ├─ lnrs_anon_diagnosis            患者级诊断 ★（省医 0014）
        │      ├─ lnrs_anon_clinical_document    患者级病程记录文档 ★（省医 0014）
        │      ├─ lnrs_anon_medical_history      患者级就诊病史 ★（省医 0014）
        │      │
        │      └─ lnrs_anon_imaging_study        影像 study 桥（patient ↔ 磁盘路径）★
        │             └─ lnrs_anon_imaging_orphan  影像孤儿登记（patient 可空）★
        │
        └─ lnrs_anon_phi_audit     字段级 PHI 清洗审计（与批次平级）
lnrs_anon_orphan_audit_batch      孤儿审计批次锚点 ★（imaging_orphan 的 FK 根）
lnrs_anon_dicom_uid_map           UID 重映射审计（物理隔离，不进生产库）
```

★ = 上一版文档之后新增/重构的对象。

### 1.1 规模总览（h1963 实测 2026-09-16）

| 表 | 行数 | 体积 | 覆盖中心 |
|---|---:|---:|---|
| `lnrs_anon_patient` | 314,034 | 232 MB | shengyi 169,820 / zhujiang 86,301 / xinqiao 49,563 / hos301 8,350 |
| `lnrs_anon_visit` | 2,408,597 | 1.6 GB | shengyi 2,381,010 / hos301 17,997 / zhujiang 9,590 |
| `lnrs_anon_visit_detail` | 2,408,597（1:1） | 1.6 GB | 同 visit |
| `lnrs_anon_exam` | 1,495,935 | 706 MB | CT 49.8万 / Ultrasound 26.3万 / Pathology 23.8万 / Radiology 17.0万 / ECG 14.9万 / Other 10.8万 / MR 6.2万 / Genetic 7,114 / IHC 25 |
| `lnrs_anon_report_text` | 1,459,159 | 970 MB | 跟随 exam |
| `lnrs_anon_exam_detail` | 1,712,973 | 2.2 GB | imaging_report / nodule_imaging / pathology / exam_extras / ultrasound / ecg / genetic / ihc |
| `lnrs_anon_exam_finding` | 0 | 32 kB | 未启用 |
| `lnrs_anon_lab_result` | ≈44,583,368 | **34 GB** | shengyi（4 分片）+ hos301 |
| `lnrs_anon_order` | ≈21,148,911 | **13 GB** | shengyi（drug/no_drug/outp/anesthesia）+ hos301 |
| `lnrs_anon_surgery` | 342,695 | 255 MB | shengyi + zhujiang |
| `lnrs_anon_diagnosis` | ≈5,546,837 | 4.2 GB | shengyi（诊断流 + 病案首页两来源） |
| `lnrs_anon_clinical_document` | 2,672,861 | 3.5 GB | shengyi（32 种 doc_type） |
| `lnrs_anon_medical_history` | 699,536 | 778 MB | shengyi |
| `lnrs_anon_vital_observation` | ≈16,307,755 | **11 GB** | shengyi（nursing 1166万 / anesthesia 296万 / icu 168万） |
| `lnrs_anon_imaging_study` | 119,350 | 145 MB | shengyi（disk_06/07，83k）+ zhujiang（disk1/disk2，36k） |
| `lnrs_anon_imaging_orphan` | 8,085 | 9.2 MB | zhujiang（csv_uncovered 8,079 / patient_missing 6） |
| `lnrs_anon_orphan_audit_batch` | 1 | 64 kB | zhujiang（2026-09-04 磁盘扫描） |
| `lnrs_anon_dicom_series` | 36,147 | 18 MB | zhujiang（study 级，其余中心待扫） |
| `lnrs_anon_dicom_instance` | 0 | 16 kB | 未启用 |
| `lnrs_anon_dicom_uid_map` | 0 | 24 kB | 未启用 |
| `lnrs_anon_ingest_batch` | 87 | 168 kB | shengyi 58 / hos301 14 / zhujiang 13 / xinqiao 2 |
| `lnrs_anon_phi_audit` | ≈6,275,402 | 1.4 GB | 跟随各导入分支 |
| `lnrs_anon_exam_file` | 3 | 96 kB | 无代码引用的遗留表（见附录） |

设计约定：
- 每张业务表都有 `created_batch_id`（FK → `ingest_batch`，ON DELETE CASCADE）；0014 扩展表与 `imaging_study` / `imaging_orphan` 只带创建批次，**没有** `last_seen_batch_id`（见 §12 差异 6）。
- 幂等键：`(center_code, source_*_hash)` 或全局 `source_*_hash` UNIQUE，重复导入只刷新 `last_seen_batch_id` 与日期（0014 扩展表则整行靠 hash 去重，冲突跳过）。
- 双 ID 体系：`patient_id`（`PT_xxxxxxxx` 对外 PK）/ `anon_id`（`ANON_<HMAC>` 反查键）；visit `ANON_VISIT_<HMAC[:12]>`，exam `ANON_EXAM_<12hex>`。
- 删除语义：FK 全部 `ON DELETE CASCADE`，`patient` 用 `deleted_at` + `deleted_reason` + `deleted_batch_id` 软删除（CHECK `lnrs_anon_ck_deleted_consistency` 保证三列同进退），purge 任务通过部分索引 `lnrs_anon_ix_patient_deleted` 扫描物理清理。
- 枚举权威：`sex` / `laterality` 等字典权威在 **CHECK 约束 + `med_dict_mapping`（医院维度映射表）**；h1963 库中**不存在** `med_sex` / `med_laterality` 独立表（旧文档表述已过时，详见 §12 差异 1）。

---

## 2. 元数据层（批次管理）

### 2.1 `lnrs_anon_ingest_batch`

单次 ETL 导入的批次锚点。当前 87 个批次。

| 关键字段 | 语义 |
|---|---|
| `batch_id` | UUID 主键，所有业务表的 FK 根 |
| `center_code` | 中心代码（CHECK `^[a-z][a-z0-9_]*$`） |
| `source_kind` | enum：`csv_report` / `dicom_dir` / `dicom_zip`（当前 ETL 仅 `csv_report`） |
| `source_locator` | 源定位（路径/对象 key） |
| `source_sha256` | 源 SHA256（来自 ETL-1 的 `conversion_manifest.json`） |
| `secret_version` + `key_fingerprint` | 脱敏密钥版本 + SHA256(secret) 前 16 hex |
| `schema_hash` | 0006 DDL 文件 SHA256，DLT 结构变化时漂移 |
| `row_counts` | JSONB NOT NULL，每张源表本次导入行数 |
| `started_at` / `finished_at` / `status` / `error` | 批次元状态（enum：`running`/`success`/`failed`/`partial`） |

写入方：`anon_etl_service._create_batch` / `_close_batch`，事务外独立 commit，失败回滚后批次记录仍保留。
唯一约束：`lnrs_anon_uq_batch_center_secret (center_code, secret_version, key_fingerprint, schema_hash, started_at)`。
h1963 分布：shengyi 58 / hos301 14 / zhujiang 13 / xinqiao 2（最近批次 2026-09-15）。

---

## 3. 患者主索引层

### 3.1 `lnrs_anon_patient_seq`

全局自增物理序号序列（`INCREMENT 1`，MAXVALUE 99999999，CACHE 50；h1963 当前 `last_value = 434947`）。

ETL 调用路径：`_batch_upsert_patients` → `SELECT nextval('lnrs.lnrs_anon_patient_seq') FROM generate_series(1, n)` 批量发号 → 应用层拼成 `PT_00000001` 格式。

### 3.2 `lnrs_anon_patient`

患者主表，双 ID 体系。314,034 行。

| 字段 | 类型 | 语义 |
|---|---|---|
| `patient_id` | VARCHAR(16) PK | `PT_xxxxxxxx`，对外业务 ID 即 PK（CHECK 格式） |
| `anon_id` | VARCHAR(32) UNIQUE | `ANON_<HMAC>`，内部反查键（CHECK 格式） |
| `center_code` | VARCHAR(32) | 中心代码（CHECK 蛇形小写） |
| `birth_date` | DATE | 出生日期（CHECK 1900-01-01 ~ 2100-12-31） |
| `sex` | VARCHAR(10) NOT NULL | 性别，CHECK 字典值 `'0'/'1'/'2'/'9'` |
| `ethnicity` | VARCHAR(2) | 民族国标码（CHECK `^[0-9]{2}$`） |
| `smoking_status` | VARCHAR(1) | 吸烟状态国标值（CHECK） |
| `abo_blood_type` / `rh_blood_type` | VARCHAR(1) | ABO/RH 血型国标值（CHECK） |
| `native_place` | VARCHAR(100) | 籍贯 |
| `first_nodule_date` | DATE | 首次结节发现日期（CHECK 年份范围） |
| `bmi` | NUMERIC(5,1) | 体质指数 |
| `patient_meta` | JSONB | 兜底终身属性：家族史/既往肿瘤/合并症/发现途径/吸烟包年等（GIN 索引） |
| `is_placeholder` ★ | BOOLEAN NOT NULL DEFAULT FALSE | 占位患者标记：exam/visit/surgery 导入自动发号、无人口学（0018） |
| `created_batch_id` / `last_seen_batch_id` / `deleted_batch_id` | UUID | 批次双 FK + 软删除批 FK |
| `created_at` / `updated_at` / `deleted_at` / `deleted_reason` | 时间戳 | 触发器自动维护 `updated_at` |

索引：PK、`UNIQUE(center_code, anon_id)`、`ix_patient_anon_id` / `ix_patient_center` / `ix_patient_birth`、`ix_patient_meta_gin`（GIN on `patient_meta`）、`ix_patient_deleted`（部分索引 `WHERE deleted_at IS NOT NULL`）。

写入方：
- 主路径 `_batch_upsert_patients`（patient.parquet）。
- 占位路径 `_import_exam_text_table` / `_import_surgery_table` / `_import_visit_detail_table` / `_import_lab_table` / `_import_order_table` / `_import_diagnosis_table` / `_import_document_table` / `_import_history_table` / `_import_observation_table` 以 `is_placeholder=True` 模式预建 FK 行。

三态机：活行 UPDATE `last_seen_batch_id` + 人口学 / 软删复活（清 `deleted_*`） / 新行 INSERT。
h1963 占位比例：hos301 与 xinqiao **100% 占位**（无 patient 档案源文件），zhujiang 92.3%（79,577/86,301），shengyi 0%（有真实档案）。

---

## 4. 就诊层

### 4.1 `lnrs_anon_visit`

就诊桥表（轻量）。`anon_visit_id` 形如 `ANON_VISIT_<HMAC[:12]>`，FK → `patient`。

| 关键字段 | 语义 |
|---|---|
| `anon_visit_id` | VARCHAR(40) 主键 |
| `patient_id` | FK → `lnrs_anon_patient.patient_id`（CASCADE） |
| `visit_ordinal` | VARCHAR(64)，原始 visit_id（如 `153623_1`），保留溯源 |
| `source_visit_hash` | CHAR(64)，(center, visit_id) 裸 SHA256，幂等键 |
| `created_batch_id` / `last_seen_batch_id` | 批次双 FK |

唯一约束：`(center_code, source_visit_hash)` 与 `(patient_id, visit_ordinal)`。

写入方：
- 省医：`_import_visit_detail_table` 自建 visit 桥（不依赖 surgery）。
- 珠江：0825 批次起 `_import_visit_detail_table` 处理 `inpatient.parquet`（`inpatient_id`/`inpatient_date`）建桥——9,590 条住院 visit。
- hos301：`_import_visit_detail_table` 处理 `visit_record.parquet`——17,997 条。
- 珠江/新桥 `surgery_record.visit_id` 反推路径（`_import_surgery_table`）仍保留。

### 4.2 `lnrs_anon_visit_detail`

visit 1:1 富信息（`UNIQUE(anon_visit_id)`）。`visit_detail_json` 忠实保留原始嵌套（病案首页/病史/diagnoses[]/clinical_documents[]），不做语义对齐，date 字段转 ISO。

| 字段 | 类型 | 语义 |
|---|---|---|
| `visit_detail_id` | BIGSERIAL PK | |
| `anon_visit_id` | VARCHAR(40) FK UNIQUE | 1:1 |
| `patient_id` / `center_code` | | 冗余定位列 |
| `visit_category` | VARCHAR(32) | 住院/门诊 |
| `admission_time` / `discharge_date` | DATE | |
| `admission_dept` / `discharge_dept` / `payment_method` | VARCHAR | |
| `length_of_stay` / `visit_age` | INTEGER / NUMERIC(5,1) | |
| `visit_detail_json` | JSONB NOT NULL | 病案首页/病史/诊断数组/临床文档 |
| `source_visit_hash` | CHAR(64) | 复用 visit 桥 hash（1:1 关联） |

写入方：`_import_visit_detail_table`。省医 `visit_record`（`visit_id`/`admission_time`）、珠江 `inpatient`（`inpatient_id`/`inpatient_date`）、hos301 `visit_record`。

---

## 5. 检查（影像/病理/基因）层

### 5.1 `lnrs_anon_exam`

检查主表，跨模态桥梁。`anon_exam_id` = `ANON_EXAM_<12hex>`（HMAC of center+exam_no）。1,495,935 行。

| 字段 | 类型 | 语义 |
|---|---|---|
| `anon_exam_id` | VARCHAR(40) PK | |
| `patient_id` | VARCHAR(16) FK | → `lnrs_anon_patient`（CASCADE） |
| `center_code` | VARCHAR(32) NOT NULL | |
| `exam_type` | VARCHAR(32) | 值域 27 值 = `docs/all_modalities.json` 26 键 + `Other`，由 `lnrs_anon_ck_exam_type` CHECK 锁定（0022 SQL，需 postgres 属主执行）。Rev 2026-09-17 前的旧 10 值词表（Pathology/Genetic/IHC/MR/Radiology/Ultrasound/PETCT）已存量改名对齐：Pathology→pathology_text、Genetic→gene、IHC→IHC_record、MR→MRI、Radiology→radiology、Ultrasound→ultrasound、PETCT→nuclear_medicine（0023 SQL） |
| `exam_date` | DATE NOT NULL | |
| `source_exam_hash` | CHAR(64) | SHA256(center+exam_no)，幂等键 |
| `anon_visit_id` | VARCHAR(40) FK NULL | → `lnrs_anon_visit`（SET NULL） |
| `created_batch_id` / `last_seen_batch_id` | UUID | 批次双 FK |

唯一约束：`(center_code, source_exam_hash)`。

**关键：首次入库锁定 `exam_type` 与 `patient_id` 不再覆盖**（修 IHC 复用 specimen_id 时被覆盖的 bug），但 `exam_date` / `last_seen_batch_id` 仍刷新。DDL 里没有专门的"首次锁定"约束，是 ETL 通过 `ON CONFLICT DO UPDATE` 时把这两列从 SET 子句里剔除实现的。

### 5.2 `lnrs_anon_report_text`

报告原文，1:1 关联 `anon_exam_id`（PK 即 FK，ON DELETE CASCADE）。1,459,159 行。

| 字段 | 语义 |
|---|---|
| `body_clean` | `findings` / `impression` / `pathology_diagnosis` 等用 `\n\n` 拼接后 `truncate_body` 到 10 万字符的结果 |
| `pii_replaced_count` | 替换次数（当前 ETL 恒为 0） |
| `clean_method` | enum `regex_only` / `regex+llm` / `manual_review`（当前恒为 `regex_only`） |
| `llm_model` | 当前恒 NULL |
| `review_status` | enum `pending` / `reviewed` / `flagged`（当前恒为 `pending`） |

写入方：`_import_exam_text_table` → `_batch_upsert_report_text`。

**本轮约定**：`pii_replaced_count=0` / `clean_method='regex_only'` / `review_status='pending'` / `llm_model=NULL`——即先存原文待人工/LLM 抽检，本轮不替换 PHI。

### 5.3 `lnrs_anon_exam_finding`（本轮不写入，行数 0）

EAV 标量表。PK `(finding_id BIGSERIAL)`，UNIQUE `(anon_exam_id, finding_type, raw_value_hash)`，字段 `finding_type` / `value_numeric` NUMERIC(10,3) / `value_text` / `laterality`（CHECK 字典）/ `raw_value_hash`。

**本轮 ETL 不写入**：`anon_model.py` 注释明确"finding 表实际不写入，自由文本不拆分，模型保留"。DDL 与 ORM 都建好但无调用方。预留未来把结节长径 / Ki67 / TPS 等拆成 EAV 标量行（与 JSONB 装的 `exam_detail` 并存互补）。

### 5.4 `lnrs_anon_exam_detail`

exam 级 JSONB 深结构。PK 复合 `(anon_exam_id, detail_type, detail_ordinal)` 实现 1:N。1,712,973 行。

| 字段 | 语义 |
|---|---|
| `detail_type` | 实际取值：`imaging_report` / `nodule_imaging` / `pathology` / `exam_extras`（hos301 检查子结构）/ `ultrasound` / `ecg` / `genetic` / `ihc` |
| `detail_ordinal` | SMALLINT 默认 1；多结节场景（`nodule_no`='n1'/'n2'/…）解析为 1/2/3/4 |
| `detail_json` | 嵌套结构（driver_mutations、staging、腺癌亚型、exam_extras 的 reqDept/examItem/examClass…），date/datetime 走 `_json_safe` 转 ISO 字符串 |
| `created_batch_id` | 批次 FK |

带 GIN 索引 `lnrs_anon_ix_exam_detail_gin` 支持 `detail_json` 检索。

写入方：`_import_exam_text_table` → `_batch_upsert_exam_detail`。

关键设计：同 exam 不同 detail_type 共享 specimen_id 时各成行不互覆盖；多结节 1:N 展开。

---

## 6. 影像层

> 2026-09-15 起 `lnrs_anon_dicom_series` 重构为 **study 级**（一行 = 一个 study 目录，旧 series 级字段全部移除，旧数据备份在 `_migration_old_dicom_series`），由 ETL-2 增量阶段扫描 `lnrs_anon_imaging_study.image_path` 目录 upsert；目前仅 zhujiang 中心完成扫描（36,147 行）。`dicom_instance` ORM 已声明、ETL 不写入，留作 ETL-3。`dicom_uid_map` 仍按 ADR 物理隔离不进生产库。

### 6.1 `lnrs_anon_imaging_study` ★（0012）

影像研究桥接表：`patient_id` (PT_xxx) ↔ 磁盘 Study 根目录绝对路径。119,350 行（shengyi disk_06/07 + zhujiang disk1/disk2；36,342 行已回填 `anon_exam_id`）。

| 字段 | 类型 | 语义 |
|---|---|---|
| `study_key` | BIGSERIAL PK | |
| `patient_id` | VARCHAR(16) FK NOT NULL | → patient（CASCADE），仅存脱敏 ID |
| `center_code` | VARCHAR(32) | CHECK 蛇形小写 |
| `dicom_study_uid` | VARCHAR(64) NOT NULL | StudyInstanceUID 明文（磁盘索引可反查），索引 `ix_imaging_study_uid` |
| `modality` | VARCHAR(16) DEFAULT 'CT' | CHECK：CT/MR/XR/US/PET/NM/Pathology/Genetic/Other |
| `image_path` | TEXT NOT NULL | Study 根目录绝对路径 |
| `sop_count` | INT DEFAULT 0 | 切片数（仅展示/统计） |
| `source` | VARCHAR(64) DEFAULT 'disk_index' | 数据来源盘标识（disk_06_shengyi / disk1_zhujiang / …） |
| `anon_exam_id` | VARCHAR(40) FK NULL | → exam（SET NULL）；ETL-2 回写，离线灌库为空 |
| `created_batch_id` | UUID FK NULL | → ingest_batch（SET NULL） |
| `created_at` / `updated_at` | TIMESTAMP | 触发器 `lnrs_anon_tg_imaging_study_updated` 维护 |

唯一约束：`(patient_id, dicom_study_uid, source)`——同源不重复，跨源（盘 1 + 盘 2）允许重复。
灌库方式：0012/0014 起离线 CSV 直灌（不走 parquet ETL）；另有 ETL-2 回写扩展点。
服务视图：`lnrs_anon_v_imaging_study`（§10.4）。

### 6.2 `lnrs_anon_imaging_orphan` ★（0016）

影像孤儿登记表/中间表：磁盘上找不到患者归属的 study 目录的登记与状态机。8,085 行（`csv_uncovered` 8,079 / `patient_missing` 6）。

| 字段 | 类型 | 语义 |
|---|---|---|
| `orphan_key` | BIGSERIAL PK | |
| `study_orphan_id` | VARCHAR(18) UNIQUE NOT NULL | `OR_<12hex>`，由 `(center_code, rel_path)` SHA256[:12] 派生（CHECK 格式），部署无关 |
| `center_code` | VARCHAR(32) | CHECK 蛇形小写 |
| `patient_id` | VARCHAR(16) FK NULL | → patient（CASCADE）；`patient_missing` 类孤儿强制为 NULL（CHECK） |
| `dicom_study_uid` | VARCHAR(64) NOT NULL | |
| `image_path` | TEXT NOT NULL | |
| `source_orphan_hash` | CHAR(64) UNIQUE NOT NULL | 跨中心唯一锚 |
| `path_date_prefix` | VARCHAR(32) NOT NULL | 路径日期前缀风格：`ymd`/`yd`/`new`/…（CHECK） |
| `modality` | VARCHAR(16) DEFAULT 'CT' | CHECK 枚举 |
| `sop_count` | INT DEFAULT 0 | |
| `source` | VARCHAR(64) DEFAULT 'orphan_audit_2026_09_03' | |
| `orphan_kind` | VARCHAR(16) NOT NULL | `csv_uncovered` / `patient_missing` / `dual_disk_copy` / `empty_dir` / `other`（CHECK） |
| `orphan_status` | VARCHAR(16) DEFAULT 'discovered' | 状态机：`discovered` / `reviewed` / `pending` / …（CHECK） |
| `review_notes` | TEXT | |
| `audit_batch_id` | UUID FK NULL | → `lnrs_anon_orphan_audit_batch`（SET NULL） |
| `created_at` / `updated_at` | TIMESTAMP | 触发器 `lnrs_anon_tg_imaging_orphan_updated` |

唯一约束另有 `(center_code, dicom_study_uid, image_path)`。
`study_orphan_id` 48-bit 空间（2.8e14），≤10^9 行碰撞概率 < 10^-3。
服务视图：`lnrs_anon_v_imaging_orphan`（§10.4）。

### 6.3 `lnrs_anon_orphan_audit_batch` ★（0016）

孤儿审计批次元数据：每次磁盘扫描/反查的批次锚定。当前 1 行（zhujiang，`scripts/import_orphan_diagnosis.py` 2026-09-03 扫描）。

| 字段 | 语义 |
|---|---|
| `audit_batch_id` | UUID PK |
| `center_code` | 中心代码（CHECK） |
| `audit_locator` | 审计源定位（如 orphan_diagnosis_v4.csv 路径） |
| `audit_sha256` | 审计源哈希（可空） |
| `discovered_count` / `patient_missing_count` / `dual_disk_copy_count` / `empty_dir_count` / `other_count` | 各类孤儿计数（均 CHECK ≥ 0） |
| `ran_by` / `ran_at` / `notes` | 执行人 / 时间 / 备注 |

非 ETL 灌库，仅审计锚定（由 `scripts/import_orphan_diagnosis.py` 等脚本写入）。

### 6.4 `lnrs_anon_dicom_series`（2026-09-15 重构为 study 级）★

**一行 = 一个 study**：解析 `lnrs_anon_imaging_study.image_path` 目录后的研究级元数据。36,147 行（全部 zhujiang；其余中心待扫描）。

| 字段 | 类型 | 语义 |
|---|---|---|
| `series_id` | BIGSERIAL PK | 语义已变为 study 行号（历史命名保留） |
| `anon_exam_id` | VARCHAR(40) FK NOT NULL | → exam（CASCADE）；exam 未落库的目录跳过 |
| `dicom_study_uid` | VARCHAR(64) UNIQUE NOT NULL | study 唯一键（v_imaging_study_counts 按它 join） |
| `file_count` | INT NOT NULL CHECK ≥ 0 | study 目录下文件数（不过滤非图像模态，略大于真实 image instance 数） |
| `byte_size` | BIGINT NOT NULL | 累加目录下所有 `.dcm` 的 st_size |
| `created_batch_id` | UUID FK NOT NULL | 批次 FK |
| `created_at` / `updated_at` | TIMESTAMP | 无触发器（由 `_upsert_dicom_byte_size_for_study` 维护） |

旧 series 级字段（`dicom_series_uid` / `modality` / `body_part` / `instance_count` / `file_count_actual` / `file_root` / `series_no`）已全部移除，结构备份在 `_migration_old_dicom_series`（4 行）。
写入方：`_import_dicom_series_for_center` + `_upsert_dicom_byte_size_for_study`（`{"src_table": "dicom_series", "kind": "dicom_series", "scope": "all"}` spec，各中心 2026-09-15 起启用）。

### 6.5 `lnrs_anon_dicom_instance`（未启用，行数 0）

DICOM 关键帧实例。PK 复合 `(series_id, instance_no)`，UNIQUE `sop_instance_uid`，字段 `byte_offset`（文件偏移，配合 study 目录定位）。
设计：仅登记关键帧偏移，不入全量像素。ORM 已声明、ETL 不写入，留作 ETL-3。

### 6.6 `lnrs_anon_dicom_uid_map`（未启用，行数 0）

DICOM UID 重映射审计。PK 复合 `(batch_id, kind, old_uid)`，字段 `anon_exam_id`（NOT NULL）/ `kind`（enum `study`/`series`/`sop`）/ `old_uid` / `new_uid` / `created_at`。
按 ADR 物理隔离不进生产库，仅审计隔离库使用。

---

## 7. 医疗事件层（手术 / 检验 / 医嘱）

### 7.1 `lnrs_anon_surgery`

visit 级手术记录。342,695 行。

| 关键字段 | 语义 |
|---|---|
| `surgery_id` | BIGSERIAL PK |
| `anon_visit_id` | VARCHAR(40) FK → visit（CASCADE）；同 visit 多条不同手术用 `procedure_name` 区分 |
| `patient_id` / `center_code` | 冗余定位列 |
| `surgery_date` | DATE |
| `procedure_name` | VARCHAR(200) NOT NULL，截 200 字 |
| `resection_scope` / `surgical_approach` | 切除范围 / 手术入路 |
| `procedure_detail` | JSONB，icd9cm3_code / 淋巴结清扫 / 时长 / 出血量 |
| `source_surgery_hash` | CHAR(64)，SHA256(center+visit_id+procedure_name)，幂等键 |

唯一约束：`(anon_visit_id, source_surgery_hash)`。
写入方：`_import_surgery_table` → `_batch_upsert_surgeries`（省医 手术信息+病案首页手术合并源；zhujiang `surgery_record`）。

### 7.2 `lnrs_anon_lab_result`

visit 级检验。**≈4,458 万行 / 34 GB，本库第一大表**。`anon_visit_id` 可空（visit 缺失时退化为只挂 patient）。

| 关键字段 | 语义 |
|---|---|
| `lab_result_id` | BIGSERIAL PK |
| `anon_visit_id` | VARCHAR(40) FK NULL → visit |
| `patient_id` / `center_code` | 冗余定位列 |
| `report_id` | VARCHAR(64) |
| `test_name` / `item_name` | 检验组合名 / 单项名 |
| `item_result` | VARCHAR(255)，字符串结果（含定性/比值） |
| `item_result_value` | NUMERIC(12,4)，数值结果（非数值结果时 NULL） |
| `item_unit` / `collection_time` | 单位 / 采集时间（1900-01-01 哨兵过滤为 NULL） |
| `lab_detail_json` | JSONB，`test_detail` 等剩余结构 |
| `source_lab_hash` | CHAR(64)，SHA256(center:report_id:item_name)，全局唯一 |

幂等键：`source_lab_hash` UNIQUE（全局，不依赖 `anon_visit_id`，避免 NULL visit_id 重跑重复插入）。
写入方：`_import_lab_table`（shengyi 44M 行拆 4 片 `lab_result_p1~p4`；hos301 `lab_result`，`test_id` 幂等）。

### 7.3 `lnrs_anon_order`

visit 级医嘱，drug + non_drug 合并。≈2,115 万行 / 13 GB。`anon_visit_id` 可空。

| 关键字段 | 语义 |
|---|---|
| `order_id` | BIGSERIAL PK |
| `anon_visit_id` | VARCHAR(40) FK NULL → visit |
| `patient_id` / `center_code` | 冗余定位列 |
| `order_type` | VARCHAR(16) NOT NULL，`drug` / `non_drug` |
| `order_name` | VARCHAR(200) NOT NULL，截 200 字 |
| `order_time` | DATE |
| `order_source` | VARCHAR(32)，`inpatient` / `outpatient` / 源系统类别（h1963 大多为 NULL，hos301 中文字典值直落） |
| `order_detail_json` | JSONB，剂量/频次/途径等 |
| `source_order_hash` | CHAR(64)，SHA256(center:order_time:order_name:order_type[+patient_id]) |

幂等键：`source_order_hash` UNIQUE（全局）；`order_hash_extra=True` 的源（省医全部医嘱源 + hos301）把 `patient_id` 追加进哈希，吸收跨患者碰撞与同一 (time,name,type) 多行开立。
写入方：`_import_order_table`——shengyi `drug_order`/`no_drug_order`/`outp_order`（门诊处方，就诊号全空只挂 patient）/`anesthesia_order`（术中用药），hos301 `order`（`task_name`，non_drug）。

---

## 8. 患者级扩展层（省医 0014，2026-09 全量批次）

四张表共同模式：BIGSERIAL PK + `patient_id` FK（CASCADE）+ `center_code` + 业务列 + `source_*_hash` UNIQUE（全局幂等键）+ `created_batch_id` FK + `created_at`。**没有** `updated_at` / `last_seen_batch_id` / 触发器——重复导入按 hash 冲突跳过，不做行级刷新。

### 8.1 `lnrs_anon_diagnosis`

患者级诊断事件（两来源 `source` 区分）。≈554.7 万行（`diagnosis` 461.7 万 + `inpatient_front_page` 98.8 万）。

| 字段 | 语义 |
|---|---|
| `diagnosis_id` | BIGSERIAL PK |
| `patient_id` / `center_code` | FK + 定位 |
| `source` | VARCHAR(32) NOT NULL：`diagnosis`（诊疗诊断流）/ `inpatient_front_page`（病案首页） |
| `diagnosis_code` / `diagnosis_name` | VARCHAR(64) / VARCHAR(255) |
| `diagnosis_date` | DATE |
| `is_primary` | VARCHAR(8)，主诊断标记 |
| `diagnosis_category` | VARCHAR(64)，诊断类别（索引） |
| `diagnosis_detail_json` | JSONB，病案首页上下文（`detail`）等 |
| `source_diag_hash` | CHAR(64) UNIQUE |

写入方：`_import_diagnosis_table`（spec kind=`diagnosis`，`source_label` 区分两来源）。

### 8.2 `lnrs_anon_clinical_document`

患者级病程记录文档（自由文本）。267.3 万行（2.48M 空内容行随全量入库），32 种 `doc_type`。

| 字段 | 语义 |
|---|---|
| `document_id` | BIGSERIAL PK |
| `patient_id` / `center_code` | FK + 定位 |
| `doc_type` | VARCHAR(64)，文档类型（索引） |
| `doc_date` | DATE（索引） |
| `doc_content` | TEXT，正文 |
| `source_doc_hash` | CHAR(64) UNIQUE |

写入方：`_import_document_table`（spec kind=`document`）。

### 8.3 `lnrs_anon_medical_history`

患者级就诊病史（主诉/现病史/既往史/个人史/婚育史/家族史六段式）。69.9 万行。

| 字段 | 语义 |
|---|---|
| `history_id` | BIGSERIAL PK |
| `patient_id` / `center_code` | FK + 定位 |
| `chief_complaint` / `present_illness` / `past_history` / `personal_history` / `marriage_history` / `family_history` | TEXT 六段 |
| `record_date` | DATE（索引） |
| `data_source` | VARCHAR(64) |
| `source_hist_hash` | CHAR(64) UNIQUE |

写入方：`_import_history_table`（spec kind=`history`）。

### 8.4 `lnrs_anon_vital_observation`

生命体征/观察测量：护理记录 + ICU 护理 + 麻醉子项合并，`obs_type` 区分。≈1,630.8 万行 / 11 GB（nursing 1,166.6 万 / anesthesia 295.7 万 / icu 168.0 万）。

| 字段 | 语义 |
|---|---|
| `observation_id` | BIGSERIAL PK |
| `anon_visit_id` | VARCHAR(40) FK NULL → visit（CASCADE）；护理报告级就诊号 100% 非空挂 visit，ICU/麻醉无就诊号只挂 patient |
| `patient_id` / `center_code` | FK + 定位 |
| `obs_type` | VARCHAR(16) NOT NULL：`nursing` / `icu` / `anesthesia`（索引） |
| `item_name` / `item_result` | VARCHAR(255)，测量子项名 / 结果 |
| `item_result_value` | NUMERIC(12,4)，数值结果 |
| `item_unit` | VARCHAR(64) |
| `obs_time` | TIMESTAMP，日内多次测量保留时分秒 |
| `obs_detail_json` | JSONB，子项 `detail` 等 |
| `source_obs_hash` | CHAR(64) UNIQUE |

写入方：`_import_observation_table`（spec kind=`observation`，`obs_type` 参数）。

---

## 9. 审计 / 合规层

### 9.1 `lnrs_anon_phi_audit`

字段级 PHI 清洗审计日志（≈627.5 万行）。每条记录对应一次 PHI 处理行为。

| 关键字段 | 语义 |
|---|---|
| `audit_id` | BIGSERIAL PK |
| `batch_id` | FK → `ingest_batch` |
| `source_table` / `source_field` | 被脱敏的来源列 |
| `source_hash` | `hash_for_audit(orig_value)` 的 SHA256（原值不进库只留指纹） |
| `strategy` | enum：`hmac` / `clear` / `partial_keep` / `llm_replace` / `manual_review` |
| `confidence` | NUMERIC(4,3) ∈ [0,1] |

写入方：每个导入分支末尾统一调用 `_write_phi_audit_batch`（仅 INSERT 不去重）。

当前 ETL 写入规则：

| 字段 | strategy | confidence |
|---|---|---|
| `patient_id` / `exam_id` / `specimen_id` / `visit_id` | `hmac` | 1 |
| `birth_date` | `partial_keep` | 1 |
| 正文列（`findings` / `impression` 等） | `llm_replace` | 0（占位，标识本轮实际未替换） |

---

## 10. 跨表对象

### 10.1 触发器与函数

| 函数 / 触发器 | 挂载表 | 作用 |
|---|---|---|
| `lnrs_anon_trg_set_updated_at()` | — | 通用 `updated_at` 自动维护 |
| `lnrs_anon_tg_patient_updated` | `lnrs_anon_patient` | UPDATE 时刷新 `updated_at` |
| `lnrs_anon_tg_exam_updated` | `lnrs_anon_exam` | 同上 |
| `lnrs_anon_tg_report_updated` | `lnrs_anon_report_text` | 同上 |
| `lnrs_anon_tg_visit_updated` | `lnrs_anon_visit` | 同上 |
| `lnrs_anon_tg_imaging_study_updated` ★ | `lnrs_anon_imaging_study` | 同上（函数 `lnrs_anon_trg_imaging_study_set_updated_at`） |
| `lnrs_anon_tg_imaging_orphan_updated` ★ | `lnrs_anon_imaging_orphan` | 同上 |

0014 四张扩展表 / surgery / visit_detail / lab_result / order / exam_detail / exam_finding / phi_audit / ingest_batch / dicom_series / dicom_instance / dicom_uid_map 均无触发器（也不带 `updated_at`，dicom_series 例外但由 ETL 显式写）。

辅助函数 ★：`path_study_date(text)`（从影像路径末两级父目录派生 study 日期）与 `safe_to_date(text, text)`（容错日期解析，供视图用）。另安装了 `pg_trgm` 扩展（模糊检索算子族）。

### 10.2 视图 `lnrs_anon_v_exam_full`（已退化为空壳）★

⚠️ h1963 库中该视图**不再 join 任何业务表**，定义退化为 8 个 `NULL::类型` 占位列（`anon_exam_id` … `finding_count` / `series_count`），恒返回 1 行 NULL。旧文档里的"join patient+exam+report_text+finding+series 聚合"定义已失效。查询侧（`anon_query.py`）勿再依赖；待重建或删除（见 §12 差异 5）。

### 10.3 视图 `lnrs_anon_v_imaging_study_counts`（2026-09-15 引入）

study 维度聚合：给"患者详情 → 影像列表"展示 `series_count` / `instance_count` / `total_bytes`。

```sql
SELECT ims.study_key, ims.dicom_study_uid, ims.center_code,
       ims.patient_id, ims.anon_exam_id,
       0                          AS series_count,        -- 重构后固定 0
       COALESCE(s.file_count, 0)  AS instance_count,      -- ← dicom_series.file_count
       COALESCE(s.byte_size, 0)   AS total_bytes          -- ← dicom_series.byte_size
FROM lnrs.lnrs_anon_imaging_study ims
LEFT JOIN lnrs.lnrs_anon_dicom_series s
       ON s.dicom_study_uid = ims.dicom_study_uid;
```

LEFT JOIN 让 `dicom_series` 未落库的 study 也返回 0（前端显示「序列数 0」而不是 NULL）；单 patient 路径走 `lnrs_anon_ix_imaging_study_uid` + `lnrs_anon_ix_dicom_series_study_uid` 索引，毫秒级。

### 10.4 视图 `lnrs_anon_v_imaging_study` / `lnrs_anon_v_imaging_orphan` ★

- `lnrs_anon_v_imaging_study`：`imaging_study` JOIN patient（带出 `anon_id`），并用 `path_study_date(image_path)` 派生 `study_date` 与 `study_description`（`modality + ' ' + 日期`）——目录名即兜底元数据，与真 DICOM StudyDescription 正交。
- `lnrs_anon_v_imaging_orphan`：`imaging_orphan` LEFT JOIN patient（带 `anon_id`）+ LEFT JOIN `orphan_audit_batch`（带 `audited_at` / `audit_locator`）。

---

## 11. 写入路径速查

```
patient.parquet           → lnrs_anon_patient (主)
visit_record.parquet      → lnrs_anon_visit + lnrs_anon_visit_detail (省医/301)
inpatient.parquet         → lnrs_anon_visit + lnrs_anon_visit_detail (珠江 0825 住院)
surgery_record.parquet    → lnrs_anon_visit(反推桥) + lnrs_anon_surgery (省医/珠江)
nodule_imaging.parquet    → lnrs_anon_exam(CT) + report_text + exam_detail (珠江/新桥)
pathology_specimen.parquet→ lnrs_anon_exam(Pathology) + report_text + exam_detail
imaging_report.parquet    → lnrs_anon_exam(Radiology*) + report_text + exam_detail (省医/珠江)
ultrasound_report.parquet → lnrs_anon_exam(Ultrasound) + report_text + exam_detail (省医)
ecg_report.parquet        → lnrs_anon_exam(ECG) + report_text + exam_detail (省医, 0015 字典)
genetic_report.parquet    → lnrs_anon_exam(Genetic) + exam_detail (省医, SNV/CNV)
genetic_test.parquet      → lnrs_anon_exam(Genetic) + exam_detail (珠江/新桥)
ihc_result.parquet        → lnrs_anon_exam(IHC) + exam_detail (珠江)
exam.parquet              → lnrs_anon_exam(Other/examType 归一) + report_text
                            + exam_detail(exam_extras) (301 nested parquet)
lab_result(_p1~p4).parquet→ lnrs_anon_lab_result (省医 4 分片; 301 直入)
drug_order.parquet        → lnrs_anon_order (order_type='drug', 省医)
no_drug_order.parquet     → lnrs_anon_order (order_type='non_drug', 省医)
outp_order.parquet        → lnrs_anon_order (门诊处方, 只挂 patient, 省医)
anesthesia_order.parquet  → lnrs_anon_order (术中用药, 省医)
order.parquet             → lnrs_anon_order (non_drug/task_name, 301)
diagnosis.parquet         → lnrs_anon_diagnosis (source='diagnosis', 省医)
diagnosis_inpatient.parquet→lnrs_anon_diagnosis (source='inpatient_front_page', 省医)
clinical_document.parquet → lnrs_anon_clinical_document (省医)
medical_history.parquet   → lnrs_anon_medical_history (省医)
nursing_observation.parquet   → lnrs_anon_vital_observation (obs_type='nursing', 省医)
icu_observation.parquet       → lnrs_anon_vital_observation (obs_type='icu', 省医)
anesthesia_observation.parquet→ lnrs_anon_vital_observation (obs_type='anesthesia', 省医)

CSV 离线灌库（非 parquet ETL）:
ct_image_patient_map.csv  → lnrs_anon_imaging_study (0012; shengyi 盘 06/07 + zhujiang 盘 1/2)
orphan_diagnosis_v4.csv   → lnrs_anon_imaging_orphan + lnrs_anon_orphan_audit_batch
                            (scripts/import_orphan_diagnosis.py, 0016)

ETL-2 增量阶段:
lnrs_anon_imaging_study.image_path 目录扫描
                          → lnrs_anon_dicom_series (study 级, 2026-09-15 起;
                            anon_exam_id 为空时跳过; 目前仅 zhujiang 完成)

每个导入分支末尾追加 → lnrs_anon_phi_audit
```

公共依赖顺序：`patient → visit_detail（建 visit 桥 + 富信息）→ exam_text / surgery / lab / order / diagnosis / document / history / observation`。
所有写入共用 `pg_insert(...).on_conflict_do_update(...)` 幂等 upsert（0014 扩展表为 `on_conflict_do_nothing` 语义的 hash 去重）。
ETL 事务内默认 `SET LOCAL synchronous_commit = off` 加速 commit（`LNRS_ETL_FSYNC=1` 恢复；崩溃丢 WAL 段由重跑幂等吸收）。

---

## 12. 与文档 / 设计的差异（h1963 实测）

1. **`lnrs_anon_sex_enum` 与 `lnrs_anon_laterality_enum` 在库内仍存在**（旧值 `M/F/U`、`L/R/Bilateral/N/A`）。0006 注释称"已删除，权威移交字典表"，但 `DROP TYPE` 并未实际执行——这两个 enum 当前是孤儿类型。约束侧已迁移：patient 用 `lnrs_anon_ck_patient_sex` CHECK，finding 用 `lnrs_anon_ck_finding_laterality` CHECK。**建议后续手动 DROP 这两个孤儿 enum**。另外 h1963 库**不存在** `med_sex` / `med_laterality` 表——旧文档"字典权威迁 med_sex/med_laterality"的表述不准确，实际权威是 CHECK 约束 + `med_dict_mapping`（医院维度 raw_label→标准值映射，`dict_type_id` 区分字典类型）。
2. **`lnrs_anon_v_exam_full` 已退化为空壳视图**（SELECT NULL 占位、恒 1 行），`anon_query.py` 等查询侧若仍引用会得到空结果。待重建或删除。
3. **`lnrs_anon_exam_file` 是无主表**：h1963 库内有表（`file_name`/`patient_id`/`exam_type`/`file_type`/`file_size`/`file_path`/`id`，3 行演示数据），但 SQL 迁移与代码均无对应；`module_medical/files` 的 `MedFilesModel` 实际映射的是 `lnrs_anon_imaging_study`。属遗留对象，可评估清理。
4. **`dicom_series` 重构后语义漂移**：表名/主键 `series_id` 仍是 series 时代命名，实际一行 = 一个 study；`v_imaging_study_counts.series_count` 因此恒 0。旧 series 级数据备份在 `_migration_old_dicom_series`（4 行）。除 zhujiang 外其余中心尚未跑 series 扫描阶段。
5. **`exam_finding` / `dicom_instance` / `dicom_uid_map`** 三张表 DDL + ORM 就绪但行数为 0：finding 明确不写入（自由文本不拆分）；dicom 两表等 `dicom_dir`/`dicom_zip` 源接入（ETL-3）。
6. **0014 四张扩展表无 `last_seen_batch_id` / `updated_at` / 触发器**：与老表"重复导入刷新 last_seen"的约定不同，重复导入靠 `source_*_hash` UNIQUE 冲突跳过，行内容永不更新。读者单看 ORM 会误以为有 UPDATE 语义。
7. **`report_text` 写入策略**：现网 ETL 明确把 `pii_replaced_count=0`、`clean_method='regex_only'`、`review_status='pending'`、`llm_model=NULL` 作为本轮约定——是设计而非 bug（先存原文待抽检）。
8. **`exam` 的 `exam_type` / `patient_id` 锁**：DDL 里没有专门的"首次锁定"约束，是 ETL 通过 `ON CONFLICT DO UPDATE` 时把这两列从 SET 子句里剔除实现的。文档读者单看 DDL 会误以为可以任意更新这两列。
9. **visit 桥启用范围**：h1963 中 shengyi（visit_record）、zhujiang（inpatient，9,590 条）、hos301（visit_record，17,997 条）均已建桥；xinqiao 仍无 visit。旧文档"仅省医启用"已过时。
10. **`order_source` 语义漂移**：DDL 注释写 `inpatient`/`outpatient`，h1963 实际大部分为 NULL（省医源无该列），hos301 落的是中文类别（`检验`/`西药`/`治疗`…），非枚举值。

---

## 附录 A：`lnrs_anon_*` 对象清单（h1963，2026-09-16）

```
function:  lnrs_anon_trg_imaging_study_set_updated_at
           lnrs_anon_trg_set_updated_at
           path_study_date(text)            ★ 视图用：路径 → study 日期
           safe_to_date(text, text)         ★ 视图用：容错日期解析

sequence:  lnrs_anon_clinical_document_document_id_seq
           lnrs_anon_diagnosis_diagnosis_id_seq
           lnrs_anon_dicom_series_series_id_seq
           lnrs_anon_exam_finding_finding_id_seq
           lnrs_anon_imaging_orphan_orphan_key_seq
           lnrs_anon_imaging_study_study_key_seq
           lnrs_anon_lab_result_lab_result_id_seq
           lnrs_anon_medical_history_history_id_seq
           lnrs_anon_order_order_id_seq
           lnrs_anon_patient_seq                (MAXVALUE 99999999, last=434947)
           lnrs_anon_phi_audit_audit_id_seq
           lnrs_anon_surgery_surgery_id_seq
           lnrs_anon_visit_detail_visit_detail_id_seq
           lnrs_anon_vital_observation_observation_id_seq

table:     lnrs_anon_clinical_document      ★ 0014
           lnrs_anon_diagnosis              ★ 0014
           lnrs_anon_dicom_instance
           lnrs_anon_dicom_series           ★ 2026-09-15 重构为 study 级
           lnrs_anon_dicom_uid_map
           lnrs_anon_exam
           lnrs_anon_exam_detail
           lnrs_anon_exam_file              ★ 遗留无主表（§12.3）
           lnrs_anon_exam_finding
           lnrs_anon_imaging_orphan         ★ 0016
           lnrs_anon_imaging_study          ★ 0012
           lnrs_anon_ingest_batch
           lnrs_anon_lab_result
           lnrs_anon_medical_history        ★ 0014
           lnrs_anon_order
           lnrs_anon_orphan_audit_batch     ★ 0016
           lnrs_anon_patient                (+ is_placeholder, 0018)
           lnrs_anon_phi_audit
           lnrs_anon_report_text
           lnrs_anon_surgery
           lnrs_anon_visit
           lnrs_anon_visit_detail
           lnrs_anon_vital_observation      ★ 0014

trigger:   lnrs_anon_tg_exam_updated
           lnrs_anon_tg_imaging_orphan_updated  ★
           lnrs_anon_tg_imaging_study_updated   ★
           lnrs_anon_tg_patient_updated
           lnrs_anon_tg_report_updated
           lnrs_anon_tg_visit_updated

type:      lnrs_anon_clean_method_enum
           lnrs_anon_ingest_status_enum
           lnrs_anon_laterality_enum   ← 孤儿（应 DROP）
           lnrs_anon_phi_strategy_enum
           lnrs_anon_review_status_enum
           lnrs_anon_sex_enum          ← 孤儿（应 DROP）
           lnrs_anon_source_kind_enum
           lnrs_anon_uid_kind_enum

view:      lnrs_anon_v_exam_full            ⚠ 空壳（SELECT NULL 占位）
           lnrs_anon_v_imaging_orphan       ★
           lnrs_anon_v_imaging_study        ★
           lnrs_anon_v_imaging_study_counts ★ series_count 恒 0

备份表:    _migration_old_dicom_series      ★ 重构前 series 级结构备份（4 行）
```

## 附录 B：同 schema 内相关非匿名对象

| 对象 | 用途 |
|---|---|
| `med_hospital` | 中心/医院注册表（ETL `_resolve_hospital_id` 依赖；code ↔ center_code） |
| `med_dict_mapping` | 医疗字典值映射（医院原始标签 → 标准字典值；exam_type 归一化的权威） |
| `med_dict_unmatched` | 字典未匹配记录（待人工干预） |
| `med_mapping_rule` | 字段映射规则表 |
| `verify_visit_sample` / `verify_ecg_sample` / `verify_ultrasound_sample` 及对应 `*_staging_hash` | ETL 抽检/校验用中间表（单列 `h` 存哈希） |
| `sys_*` / `gen_*` / `task_*` / `apscheduler_jobs` | 框架表（用户/角色/菜单/租户/代码生成/任务调度），与医学数据无关 |
| `pg_stat_statements`(+`_info`) | 性能扩展视图 |
