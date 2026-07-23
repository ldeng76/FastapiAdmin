# ETL-2 脱敏落库流水线

> 把 `data/<center>/*.parquet`（ETL-1 产出）脱敏后落入 PostgreSQL 的 `lnrs_anon_*` 匿名窄表。

依据：[ADR-0001 统一确定性脱敏](./adr/0001-linkable-anonymization.md) 与
[ADR-0006 脱敏后落库 Schema](./adr/0006-anonymized-data-schema.md)。

---

## 1. 数据流

```
data/{shengyi,xinqiao,zhujiang}/*.parquet   (ETL-1 产出, 明文)
                │
                │  ETL-2 (anonymize + 批量 upsert)
                ▼
lnrs.lnrs_anon_*  (PostgreSQL, 强脱敏)
  ├─ lnrs_anon_ingest_batch   每中心每次导入 1 行（密钥指纹/schema hash/行数）
  ├─ lnrs_anon_patient        每患者 1 行（PT_xxxxxxxx PK + ANON_<hmac> 反查键）
  ├─ lnrs_anon_exam           每次检查 1 行（CT/Pathology，跨模态桥梁）
  ├─ lnrs_anon_report_text    每检查 1 份报告正文（与 exam 1:1）
  ├─ lnrs_anon_exam_finding   结构化指标（本轮未写入，保留）
  └─ lnrs_anon_phi_audit      每个被脱敏字段 1 行（合规审计回放）
```

## 2. 来源 → 落表映射

| 来源 parquet | 落点 | 说明 |
|---|---|---|
| `*/patient.parquet` | `lnrs_anon_patient` | 每行 1 病人 |
| `*/nodule_imaging.parquet` | `lnrs_anon_exam`(CT) + `lnrs_anon_report_text` | 每次检查 1 行 exam + 报告正文 |
| `*/pathology_specimen.parquet` | `lnrs_anon_exam`(Pathology) + `lnrs_anon_report_text` | 同上 |
| `*/visit_record.parquet` | **跳过** | ADR-0006 visit 桥（patch-visit）本轮未启用 |

> `surgery_record` / `genetic_test` / `ihc_result` / `follow_up` 在 `data/` 中无 parquet，自动跳过。

## 3. 脱敏规则（ADR-0001）

| 字段 | 处理 |
|---|---|
| `patient_id`（明文院内号） | `anon_id = "ANON_" + HMAC-SHA256(secret, center:patient_id)[:12]`；同时分配 `patient_id = "PT_" + LPAD(seq, 8, "0")` |
| `exam_id` / `specimen_id` | `anon_exam_id = "ANON_EXAM_" + HMAC-SHA256(secret, center:exam_no)[:12]` |
| `gender` (男/女/...) | `sex` ENUM('M','F','U') |
| `birth_date` | `birth_date`（精确到日，仅有年份时月日=01，仅有年月时日=01） |
| `exam_date` | 原值保留 |
| 报告正文 | **原样**入 `body_clean`（`clean_method='regex_only'`、`review_status='pending'`，等待后续 regex+LLM 迭代） |

center_code 参与 HMAC 输入，防止跨中心同 patient_id 碰撞。

## 4. 幂等性 / 软删除

- **patient 三态机**（ADR-0006 Rev 2026-07-19）：
  - 活行 → 复用 `patient_id`，仅更新 `last_seen_batch_id` + 人口学
  - 软删行 → 复活（清空 `deleted_*`）
  - 新 → `nextval(lnrs_anon_patient_seq)` 发号 + INSERT
- **exam**：`UNIQUE(center_code, source_exam_hash)` + `ON CONFLICT DO UPDATE`
- **report_text**：PK=`anon_exam_id`，`ON CONFLICT DO UPDATE body_clean`
- 重复运行 ETL-2：patient/exam/report 行数不变，patient_id 不重新发号
  （`phi_audit` 是 append-only 审计日志，每次运行追加新行，符合合规回放需求）

---

## 5. 运行

### 前置
- 本地 PostgreSQL（见 `docker/lnrs-dev.yaml`，user=lnrs/pwd=lnrs_pwd/db=postgres）
- `lnrs` schema 已建表（DDL：`backend/sql/postgres/0006-anonymized-schema-lnrs.sql`）
- `backend/env/.env.dev` 配置 `DATABASE_TYPE=postgres` + `LNRS_ANON_SECRET`

### CLI

```bash
cd backend

# 全量（三中心）
ENVIRONMENT=dev python -m app.plugin.module_medical.hospital.anon_etl --data-root ../data

# 仅某中心
ENVIRONMENT=dev python -m app.plugin.module_medical.hospital.anon_etl \
    --centers zhujiang --data-root ../data

# 预检（不连库）
ENVIRONMENT=dev python -m app.plugin.module_medical.hospital.anon_etl --dry-run
```

### 单测

```bash
cd backend
# 纯函数（无需 DB）
ENVIRONMENT=dev python -m pytest tests/anon_etl/test_anonymize.py -v

# 端到端 smoke（需 PG + data/）
ENVIRONMENT=dev python -m pytest tests/anon_etl/ -v
```

---

## 6. 文件清单

| 文件 | 作用 |
|---|---|
| `backend/app/plugin/module_medical/hospital/anonymize.py` | HMAC 脱敏 + 字段归一化（纯函数） |
| `backend/app/plugin/module_medical/hospital/anon_model.py` | `lnrs_anon_*` ORM 模型 |
| `backend/app/plugin/module_medical/hospital/anon_etl_engine.py` | 批量导入引擎（patient 三态机 + exam/report 幂等 upsert） |
| `backend/app/plugin/module_medical/hospital/anon_etl_service.py` | 多中心编排（每中心一事务、ingest_batch 管理） |
| `backend/app/plugin/module_medical/hospital/anon_etl/__main__.py` | CLI 入口 |
| `backend/sql/postgres/0006-anonymized-schema-lnrs.sql` | 建表 DDL（可执行版） |
| `backend/tests/anon_etl/test_anonymize.py` | 纯函数单测（39 用例） |
| `backend/tests/anon_etl/test_etl_smoke.py` | 端到端 + 幂等性测试 |

---

## 7. 已知边界（本轮不实现）

- **visit_record**（省医 131k 就诊记录）不入库——等 ADR-0006 patch-visit 桥启用
- **自由文本未清洗**——`body_clean` 暂含明文，`review_status='pending'`，待 regex + 私有 LLM 迭代
- **DICOM 表**（`anon_dicom_*`）不建——本轮无 DICOM 源
- **结构化 finding**（`anon_exam_finding`）不写入——自由文本不拆分
- **audit UID map**（`lnrs_anon_dicom_uid_map`）不建——按 ADR 物理隔离不进生产库
