# 脱敏后病例数据落库 Schema (Anonymized Data Schema)

## Context

延用 [ADR-0001 统一确定性脱敏](./0001-linkable-anonymization.md) 的方案：

- 病人级 `ANON_ID = "ANON_" + HMAC-SHA256(secret, center + PAT_LOCAL_ID)[:12]`
- 检查级 `ANON_EXAM_ID = "ANON_EXAM_" + HMAC-SHA256(secret, center + EXAM_NO)[:12]`
- DICOM UID 改用"项目根 OID + HMAC 填充"确定性重生成，保证同一病人同一检查每次脱敏都得到相同 UID
- 原始明文 ID、姓名、就诊号、入院号一律**不**进库；DICOM 像素数据落 NAS / OSS，DB 只存路径

本 ADR 决定**脱敏产物的库表结构**，用于：

1. 让研究员/AI 模型按 `ANON_ID` 做病人级纵向追踪（多次检查随访）
2. 让研究员按 `ANON_EXAM_ID` 把"这张 CT 的报告正文/结构化指标"与"这张 CT 的影像"对齐
3. 让数据治理团队可按 `batch_id` 回溯每次导入的密钥版本、文件清单、脱敏规则

## Decision

### 总体布局

```
                     ┌──────────────────┐
                     │  ingest_batch    │  导入批次元数据
                     └────────┬─────────┘
                              │ 1
       ┌──────────────────────┼──────────────────────┐
       │                      │                      │
       ▼ N                    ▼ N                    ▼ N
┌──────────────┐      ┌──────────────┐       ┌──────────────────┐
│ anon_patient │ 1───►│  anon_exam   │ 1───► │ dicom_series     │   DICOM 元数据 + 路径
└──────────────┘  N   └──────┬───────┘   N   └──────────────────┘
                              │ 1
                              ├───► anon_report_text   (检查报告自由文本，已清洗)
                              ├───► anon_exam_finding  (结构化指标：结节长径、位置…)
                              └───► anon_dicom_uid_map (原 UID → 新 UID，调试用)

phi_audit ── 任何含 PHI 的字段被脱敏时写一行 (field, src_hash, strategy, batch_id)
```

### 表设计

#### 1. `lnrs_anon_ingest_batch` — 导入批次

| 列 | 类型 | 说明 |
|---|---|---|
| `batch_id` | UUID PK | 本次导入唯一 ID |
| `center_code` | VARCHAR(32) NOT NULL | 来源中心代号（zhujiang/xinqiao/shengyi …） |
| `source_kind` | ENUM('csv_report','dicom_dir','dicom_zip') | 这次导入的输入形态 |
| `source_locator` | TEXT | 文件路径 / 归档名 / S3 URI |
| `source_sha256` | CHAR(64) | 源文件 SHA-256（拿到原始字节的导入才填） |
| `secret_version` | VARCHAR(32) NOT NULL | 用的 HMAC 密钥版本号（密钥轮换时记录） |
| `key_fingerprint` | CHAR(16) NOT NULL | 密钥指纹（前 8 字节 hex），不泄漏密钥本体 |
| `schema_hash` | CHAR(64) | 脱敏规则 schema 的 hash，便于规则变更后回看"那时怎么洗的" |
| `row_counts` | JSONB | `{"patient":N,"exam":M,"dicom":K}` 落库时统计 |
| `started_at` / `finished_at` | TIMESTAMP | |
| `status` | ENUM('running','success','failed','partial') | |
| `error` | TEXT | 失败原因 |

约束：
- `(secret_version, key_fingerprint, schema_hash)` 上建复合索引——查找"用 V2 密钥 + V3 规则洗出来的全部批次"。

#### 2. `lnrs_anon_patient` — 病人主表（双 ID 体系：百万级对外 PK + 内部反查键）

> **Rev 2026-07-19 改造**：引入百万级对外 ID `patient_id` 并直接当 PK；HMAC `anon_id` 降级为内部反查键。`patient_seq` 已合并入 `patient_id`，不再单独保留 BIGINT 序号列。详见 [ADR-0001 Revision](./0001-linkable-anonymization.md#revision-2026-07-19-引入百万级对外-id-patient_id省去物理-patient_seq)。

| 列 | 类型 | 说明 |
|---|---|---|
| `patient_id` | VARCHAR(16) **PK** | **对外业务 ID + 物理主键**：`PT_` + 8 位 zero-pad（如 `PT_00000001`）；由 SEQUENCE 格式化而来 |
| `anon_id` | VARCHAR(32) UNIQUE NOT NULL | **内部反查键**：`ANON_` + HMAC-SHA256[:12]（保留供密钥持有者反算） |
| `center_code` | VARCHAR(32) NOT NULL | 跨中心碰撞防御 |
| `birth_date` | DATE | 精确到日；源数据只有年份时月日为 01，只有年月时日置 01 |
| `sex` | ENUM('M','F','U') | |
| `created_batch_id` | UUID FK → `lnrs_anon_ingest_batch` | 首次出现批次；后续 update 仅刷新 last_seen |
| `last_seen_batch_id` | UUID FK → `lnrs_anon_ingest_batch` | |
| `created_at` / `updated_at` | TIMESTAMP | |
| `deleted_at` | TIMESTAMP NULL | **软删除标记**：NULL = 活跃；非空 = 已软删。重新导入时复用 |
| `deleted_reason` | VARCHAR(64) NULL | 软删原因（合规/误操作/纠错） |
| `deleted_batch_id` | UUID NULL FK → `lnrs_anon_ingest_batch` | 触发软删的批次 |

约束：
- `PRIMARY KEY (patient_id)` — 对外业务 ID 即 PK
- `UNIQUE (anon_id)` — 内部反查键（**包含已软删行**——保证复活时仍唯一）
- `UNIQUE (center_code, anon_id)` — 同一中心 HMAC 不重
- `CHECK (patient_id ~ '^PT_[0-9]{8}$')` — 格式与 8 位 zero-pad 上限兜底
- `CHECK (anon_id ~ '^ANON_[0-9a-f]{12}$')` — HMAC 格式校验

索引：
- `lnrs_anon_ix_patient_center` ON `(center_code)`
- `lnrs_anon_ix_patient_birth` ON `(birth_date)`
- `lnrs_anon_ix_patient_anon_id` ON `(anon_id)` — 反查路径（**含软删行**）
- `lnrs_anon_ix_patient_deleted` ON `(deleted_at) WHERE deleted_at IS NOT NULL` — 物理清理用部分索引

应用层生成规则：
1. **首次导入**：取 `nextval('lnrs_anon_patient_seq')` 得 seq → 应用层拼 `patient_id = "PT_" || LPAD(seq::text, 8, '0')` → INSERT，`deleted_at = NULL`
2. **同步生成 `anon_id = "ANON_" + HMAC-SHA256(secret, center + PAT_LOCAL_ID)[:12]`**
3. **重复导入（活）**：先按 `(anon_id, deleted_at IS NULL)` 查得原 `patient_id` → 复用，不重新发号
4. **重新导入（软删）**：按 `(anon_id, deleted_at IS NOT NULL)` 查得原 `patient_id` → **复活**：`UPDATE deleted_at = NULL, deleted_reason = NULL, deleted_batch_id = NULL`，复用
5. **物理清理（PURGE）**：`DELETE WHERE deleted_at < NOW() - INTERVAL '90 days'` —— 由治理团队手动触发，触发子表 CASCADE
6. **反查**：持密钥者重算 `anon_id` → JOIN 查到 `patient_id`（不限 `deleted_at`，可查历史）

#### 3. `lnrs_anon_exam` — 检查主表（跨模态桥梁）

| 列 | 类型 | 说明 |
|---|---|---|
| `anon_exam_id` | VARCHAR(40) PK | `ANON_EXAM_<12位hex>` |
| `anon_id` | VARCHAR(32) FK → `lnrs_anon_patient` | 该检查所属病人 |
| `center_code` | VARCHAR(32) NOT NULL | |
| `exam_type` | VARCHAR(32) | `CT` / `PETCT` / `Pathology` / …（归一化后） |
| `exam_date` | DATE | 原值保留（DICOM StudyDate / CSV EXAM_DATE） |
| `source_exam_hash` | CHAR(64) | `(center, EXAM_NO)` 的 SHA-256（仅用于"同检查被重复导入"幂等） |
| `created_batch_id` | UUID FK | |
| `last_seen_batch_id` | UUID FK | |
| `created_at` / `updated_at` | TIMESTAMP | |

约束：
- `UNIQUE (center_code, source_exam_hash)` — 重复导入同一检查只 update、insert
- `INDEX (anon_id)` — 病人级纵向检索

#### 4. `lnrs_anon_report_text` — 报告自由文本（已清洗）

| 列 | 类型 | 说明 |
|---|---|---|
| `anon_exam_id` | VARCHAR(40) PK FK → `lnrs_anon_exam` | 一对一 |
| `body_clean` | TEXT NOT NULL | 规则 + LLM 清洗后正文 |
| `pii_replaced_count` | INT | 替换了几处 PHI（用于审计抽检） |
| `clean_method` | VARCHAR(32) | `regex+llm` / `regex_only` / `manual_review` |
| `llm_model` | VARCHAR(64) | 私有化部署的模型名（`qwen3-9b-int4` 等） |
| `review_status` | ENUM('pending','reviewed','flagged') | 人工抽检标记 |

#### 5. `lnrs_anon_exam_finding` — 结构化指标（按检查一查多）

| 列 | 类型 | 说明 |
|---|---|---|
| `finding_id` | BIGINT PK AUTO_INCREMENT | |
| `anon_exam_id` | VARCHAR(40) FK → `lnrs_anon_exam` | |
| `finding_type` | VARCHAR(32) | `nodule_size` / `nodule_location` / `pathology_stage` … |
| `value_numeric` | NUMERIC(10,3) | 数值类（结节长径 mm） |
| `value_text` | VARCHAR(255) | 文本类（位置 "RUL"） |
| `laterality` | ENUM('L','R','Bilateral','N/A') | |
| `raw_value_hash` | CHAR(64) | 原值的 SHA-256，溯源用，但原文不存 |

约束：
- `INDEX (anon_exam_id)`
- `INDEX (finding_type, value_numeric)` — 影像组学 / 统计常用

#### 6. `lnrs_anon_dicom_series` — DICOM 序列元数据 + 文件路径

| 列 | 类型 | 说明 |
|---|---|---|
| `series_id` | BIGINT PK AUTO_INCREMENT | 内部代理主键，对外用 `dicom_series_uid` |
| `anon_exam_id` | VARCHAR(40) FK → `lnrs_anon_exam` | 检查级桥梁 |
| `dicom_series_uid` | VARCHAR(64) UNIQUE NOT NULL | **脱敏重生成** 后的 SeriesInstanceUID（合法 OID） |
| `dicom_study_uid` | VARCHAR(64) | 脱敏重生成后的 StudyInstanceUID |
| `modality` | VARCHAR(8) | `CT`/`PT`/`MR`/… |
| `body_part` | VARCHAR(32) | `CHEST` |
| `instance_count` | INT | 序列内实例数 |
| `file_root` | TEXT NOT NULL | 脱敏 DICOM 文件根目录/NAS 路径 |
| `file_count_actual` | INT | 实际落盘的 .dcm 文件数（重生成后校验用） |
| `byte_size` | BIGINT | |
| `series_no` | INT | SeriesNumber |
| `created_batch_id` | UUID FK | |

约束：
- `UNIQUE (dicom_series_uid)` — 重复系列走 ON CONFLICT DO NOTHING
- `INDEX (anon_exam_id)`

> DICOM 实例级（每张 .dcm）一般不入库元数据——实例数可能上千/系列，靠 walker 实时扫盘重建 viewer 索引。仅对**稀疏关键序列**（如结构化报告里点名的病灶序列）才建 `lnrs_anon_dicom_instance` 表，存 `instance_no + sop_instance_uid + offset_in_bytes`。

#### 7. `lnrs_anon_dicom_instance` — 关键实例表（按需建）

| 列 | 类型 | 说明 |
|---|---|---|
| `series_id` | BIGINT FK → `lnrs_anon_dicom_series` | |
| `sop_instance_uid` | VARCHAR(64) NOT NULL | 脱敏后的 SOPInstanceUID |
| `instance_no` | INT | InstanceNumber |
| `byte_offset` | BIGINT | 在 file_root 内偏移（若多个 instance 合一个 .dcm） |
| PRIMARY KEY | `(series_id, instance_no)` | |

#### 8. `lnrs_anon_dicom_uid_map` — 原 UID ↔ 新 UID（仅调试/审计）

| 列 | 类型 | 说明 |
|---|---|---|
| `batch_id` | UUID FK | |
| `anon_exam_id` | VARCHAR(40) FK | |
| `kind` | ENUM('study','series','sop') | |
| `old_uid` | VARCHAR(64) | 原 UID（**不上线、留内网审计盘**） |
| `new_uid` | VARCHAR(64) | 新 UID |
| PRIMARY KEY | `(batch_id, kind, old_uid)` | |

约束：
- 此表**不进生产库**——攻击者拿到 `new_uid` 在此表能找到 `old_uid`，等于削弱脱敏强度
- 仅保存在独立的"审计归档数据库"（物理隔离，单独读权限）

#### 9. `lnrs_anon_phi_audit` — 字段级清洗审计

| 列 | 类型 | 说明 |
|---|---|---|
| `audit_id` | BIGINT PK AUTO_INCREMENT | |
| `batch_id` | UUID FK → `lnrs_anon_ingest_batch` | |
| `source_table` | VARCHAR(64) | `dicom`/`csv_report`/`llm_input` |
| `source_field` | VARCHAR(64) | DICOM tag 名 / CSV 列名 |
| `source_hash` | CHAR(64) | 原值的 SHA-256（值本身不存） |
| `strategy` | VARCHAR(32) | `hmac` / `clear` / `partial_keep` / `llm_replace` / `manual_review` |
| `confidence` | NUMERIC(4,3) | LLM 清洗时的置信度；规则策略为 1.0 |
| `created_at` | TIMESTAMP | |

约束：
- `INDEX (batch_id, source_table, source_field)`

### 字段名约定

| 来源 | 原字段 | 入库字段 | 备注 |
|---|---|---|---|
| CSV | `PAT_LOCAL_ID` | `anon_id`（FK） | 病人级 |
| CSV | `EXAM_NO` | `anon_exam_id`（FK） | 检查级 |
| CSV | `SICK_ID` | — | **不入库**，决策 3 |
| CSV | `NAME` | — | 不入库 |
| CSV | `SEX` | `sex` | 标准化为 M/F/U |
| CSV | `BIRTH_DATE` | `birth_date` | 精确到日，精度不足时补齐 |
| CSV | `EXAM_DATE` | `exam_date` | 原值 |
| CSV | `AGE` | — | 可由 birth_date + exam_date 精确计算，不再存原值 |
| DICOM | `(0010,0010) PatientName` | — | 不入库 |
| DICOM | `(0010,0020) PatientID` | 推导为 `anon_id`（FK） | |
| DICOM | `(0008,0050) AccessionNumber` | 推导为 `anon_exam_id`（FK），原值不入库 | |
| DICOM | `(0020,000D) StudyInstanceUID` | `dicom_study_uid`（重生成后） | |
| DICOM | `(0020,000E) SeriesInstanceUID` | `dicom_series_uid`（重生成后） | |
| DICOM | `(0008,0020) StudyDate` | `exam_date` | |
| DICOM | `(0010,0030) PatientBirthDate` | `birth_date` | 精确到日 |

### 反范式取舍

- `anon_patient.center_code` 与 `anon_exam.center_code` 冗余一份。理由：跨中心统计查询`WHERE center_code=?` 频繁；省一次 JOIN。
- `anon_exam.exam_type` 在两处源（CSV 自由文本列 vs DICOM Modality）会归一化到同一枚举。

### Visit 层扩展（2026-07-19 补丁）

主文档 `0006-anonymized-schema.sql` 只覆盖"一次影像检查 + 一次报告 + DICOM"的语义。多中心业务宽表（`docs/unified_table_schema.md`）后续追加了 6 张**就诊级**表：诊断、病史、病程、护理测量、ICU、麻醉。它们与影像检查无关，挂到 `anon_exam` 上会丢"非影像就诊"的数据，因此引入**第二条桥 `anon_visit`**。详见 `0006-anonymized-schema-patch-visit.sql` 与 `0006-anonymized-schema-vs-unified-tables.md` §7。

关键取舍：

- **anon_visit 桥的语义** —— `anon_visit_id = 'ANON_VIS_' + HMAC(secret, center + PAT_LOCAL_ID + ':' + VISIT_ORDINAL)[:12]`，遵循本 ADR 的统一确定性脱敏约定。`(anon_id, visit_ordinal)` 复合唯一，`visit_ordinal` 保留原始 `m/n` 文本以便溯源。
- **anon_exam 加可空 anon_visit_id** —— 仅 `ALTER TABLE` 加列，不修改原约束。ETL 反查 `visit_record` 成功则回填，失败置 null（保持现有 exam 语义完全不变）。
- **幂等 UNIQUE** —— 每张业务表都带 `(anon_visit_id, 原始字段哈希)` 形态的 UNIQUE，让重复导入只 UPDATE 不 INSERT（与 `anon_exam.source_exam_hash` 同等模式）。
- **PHI 处理** —— 沿用本 ADR 的铁律：原始 `patient_id` / `visit_id` / 护士签名 / 医生姓名一律不落库；长文本（主诉、现病史、病程正文）经 regex+LLM 清洗后落 `body_clean`，写入 `phi_audit`；结构化字段（如 ICD-10 编码、护理测量数值、ASA 分级）直接入库，不视为 PHI。
- **长文本表的 clean_method / review_status** —— 与 `anon_report_text` 同等字段，便于复用同一套 LLM 清洗流水线与人工抽检流程。
- **anesthesia_event 双事件类型** —— medication 与 observation 共享一张表，靠 `event_kind` 枚举区分；会话级字段（asa_level / surgery_name / 手术时间等）按 session 冗余，便于单行查询。
- **不加新审计表** —— 所有 visit 层表的 `created_batch_id` 都指向已有 `lnrs_anon_ingest_batch`，PHI 清洗记录写入已有 `lnrs_anon_phi_audit`（`source_table` 取 `'visit_csv'` / `'medical_history_text'` 等）。

## Consequences

- ✅ **跨模态可关联**：`anon_exam_id` 是 CSV 报告 ↔ DICOM 序列的唯一连接键。
- ✅ **跨批次幂等**：`source_exam_hash` + `dicom_series_uid` UNIQUE 让重复导入只更新不重复。
- ✅ **审计可回放**：`lnrs_anon_phi_audit` + `lnrs_anon_ingest_batch` 给出"用什么密钥、什么规则、清洗了什么字段"的完整记录。
- ⚠️ **原 UID 映射表**是双刃剑：研究价值高，但**必须物理隔离**——泄漏即破解关联。落地产线应默认不开。
- ⚠️ **DICOM 文件不入 DB**——`file_root` 必须指向稳定的 NAS / OSS，研究员访问受与 DB 等同的权限控制。
- ⚠️ **`anon_id` 不可反推**：研究员不能"通过病人姓名查 anon_id"，只能拿 `(center, PAT_LOCAL_ID)` 找治理团队用密钥重算。这与 ADR-0001 的不可逆约束一致。
- ⚠️ **批次回滚**：删除 `lnrs_anon_ingest_batch` 时级联删除 `lnrs_anon_patient/lnrs_anon_exam/lnrs_anon_dicom_series`（运行级），但 `lnrs_anon_phi_audit` 永保留——满足合规"清洗记录"。

## Considered Options

- **NoSQL（Mongo / ES）**：被否。`anon_id`↔`anon_exam_id`↔`lnrs_anon_dicom_series` 是强关系型结构；统计查询与 JOIN 频繁；ES 只做搜索索引层（可选附加）。
- **把所有元数据塞 Parquet**：被否。Parquet 不支持行级 UPDATE，跨模态关联查询须读全表，不适合运行期业务。
- **不分 `lnrs_anon_report_text` 与 `lnrs_anon_exam_finding` 合在一张 `lnrs_anon_exam`**：被否。一份报告可能 0/1/N 条结构化指标，独立建表更清晰，且 `finding` 是影像组学的核心查询对象，需要独立索引。
- **DICOM 实例全入库**：被否。一个胸部 CT 一千多张 .dcm，全部入库膨胀过大；运行时按需 lazy-scan 即可。
- **保存原始 PAT_LOCAL_ID 进库（仅 hash 比对）**：被否。`source_exam_hash` 已经哈希过；明文 ID 一律不进库（铁律）。
