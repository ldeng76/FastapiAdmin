# 医疗宽表直入扩展 — 技术规范

> **日期**: 2026-07-23
> **状态**: 已提交（main 分支，提交 `eb4379c7`）
> **模块**: 医疗模块 — 脱敏数据层（ETL-2）
> **ADR 引用**: ADR-0006（脱敏数据架构）、ADR-0008（医疗字典值级映射）

---

## 1. 概述

### 1.1 功能描述

本功能**废弃中间层 `med_*` 宽表**（ETL-1），实现**Parquet 文件直接入库脱敏表**（ETL-2）的一站式数据管道。

**改造前**（两层 ETL）：
```
Excel ──> med_* 业务宽表 (ETL-1) ──> lnrs_anon_* 脱敏表 (ETL-2)
```

**改造后**（单层 ETL）：
```
医院 Parquet 文件 ──> lnrs_anon_* 脱敏表 (ETL-2)
```

扩展新增 **3 张数据库表**，并对 **patient 表和 exam 表进行列扩展**，以支持病理、基因、免疫组化、手术记录和患者人口学信息——满足产品需求中定义的医疗详情页场景（入院记录、CT 检查、手术记录、基因报告、病理检查）。

### 1.2 设计动机

- **简化管道**：减少一层 ETL，降低转换错误概率，提升可维护性和数据可用速度。
- **保留结构化数据**：复杂嵌套字段（如 `driver_mutations` 含 13 个基因 + VAF，`staging` 含 pT/pN/pM）以 JSONB 存储，而非压平为 EAV 行（单条基因检测会膨胀为 30+ 行且丢失父子关系）。
- **幂等重入**：所有新实体使用 HMAC 确定性 ID 和 SHA256 源哈希，保证重复运行 ETL 不产生重复数据。

---

## 2. 架构变更

### 2.1 实体关系图

```
lnrs_anon_ingest_batch (已有)
├── lnrs_anon_patient (扩展：+7 标量列, +1 JSONB)
│   ├── lnrs_anon_exam (已有，扩展：+anon_visit_id 外键)
│   │   ├── lnrs_anon_report_text (已有)
│   │   └── lnrs_anon_exam_detail (新增 — 与 exam 1:1)
│   └── lnrs_anon_visit (新增)
│       └── lnrs_anon_surgery (新增 — 与 visit 1:N)
└── lnrs_anon_phi_audit (已有)
```

### 2.2 数据流

```
医院 Parquet 文件 ──> anon_etl_engine.py ──> PostgreSQL (lnrs schema)
┌──────────────────────────────────────┐
│ patient.parquet            ──> _import_patient_table()     ──> lnrs_anon_patient
│ nodule_imaging.parquet     ──> _import_exam_text_table()   ──> lnrs_anon_exam + lnrs_anon_report_text + lnrs_anon_exam_detail
│ pathology_specimen.parquet ──> _import_exam_text_table()   ──> lnrs_anon_exam + lnrs_anon_report_text + lnrs_anon_exam_detail
│ genetic_test.parquet       ──> _import_exam_text_table()   ──> lnrs_anon_exam + lnrs_anon_exam_detail
│ ihc_result.parquet         ──> _import_exam_text_table()   ──> lnrs_anon_exam + lnrs_anon_exam_detail
│ surgery_record.parquet     ──> _import_surgery_table()     ──> lnrs_anon_visit + lnrs_anon_surgery
└──────────────────────────────────────┘
```

### 2.3 中心配置

所有 Parquet 表规格在 `anon_etl_engine.py` 的 `_CENTER_PARQUET_SPECS: dict[str, list[dict]]` 中声明。当前已配置 **"zhujiang"** 中心，包含最多表类型。

每条规格声明：

- `src_table`: Parquet 文件名前缀
- `kind`: `"exam_text"` 或 `"surgery"`（路由到对应导入函数）
- `exam_type`: 归一化检查类型码（CT, Pathology, Genetic, IHC）
- `id_field`: 用作检查标识的源列名
- `body_fields`: 拼接为报告文本的列
- `detail_type` / `detail_fields`: 可选的 JSONB 深层结构提取配置

---

## 3. 数据模型变更

### 3.1 `lnrs_anon_patient`（扩展）

**设计理由**：原 patient 表仅含 birth_date + sex。临床 Parquet 数据包含稳定的患者属性，需持久化以供高频查询。

| 列名 | 类型 | 可空 | 来源 | 设计决策 |
|---|---|---|---|---|
| `ethnicity` | VARCHAR(50) | 是 | patient.parquet.ethnicity | 高频过滤维度，标量列 |
| `native_place` | VARCHAR(100) | 是 | patient.parquet.native_place | 人群队列分析 |
| `first_nodule_date` | DATE | 是 | patient.parquet.first_nodule_date | 疾病时间线重建 |
| `smoking_status` | VARCHAR(20) | 是 | patient.parquet.smoking_status | 危险因素分析 |
| `abo_blood_type` | VARCHAR(10) | 是 | patient.parquet.abo_blood_type | 手术规划参考 |
| `rh_blood_type` | VARCHAR(10) | 是 | patient.parquet.rh_blood_type | 手术规划参考 |
| `bmi` | NUMERIC(5,1) | 是 | patient.parquet.demographics.bmi | 从嵌套 struct 提取（见 §4.1） |
| `patient_meta` | JSONB | 是 | patient.parquet.medical_history | 兜底列：家族史、合并症、既往肿瘤、发现途径、吸烟包年等。GIN 索引。 |

**新增约束**：
- `CHECK (first_nodule_date >= '1900-01-01' AND first_nodule_date <= '2100-12-31')`
- `CREATE INDEX lnrs_anon_ix_patient_meta_gin ON lnrs_anon_patient USING gin (patient_meta)`

**Upsert 行为**：ON CONFLICT 在 `lnrs_anon_uq_patient_center` 上，**所有新增列均参与更新**（不仅是 birth_date + sex）。确保上游 Parquet 提供更新后的人口学数据时，患者记录反映最新状态。

### 3.2 `lnrs_anon_exam`（扩展）

| 列名 | 类型 | 可空 | 外键 | 设计决策 |
|---|---|---|---|---|
| `anon_visit_id` | VARCHAR(40) | 是 | `lnrs_anon_visit.anon_visit_id` ON DELETE SET NULL | 将影像学检查关联到就诊。可空——多数检查无就诊关联，不影响既有语义。 |

**索引**：`CREATE INDEX lnrs_anon_ix_exam_visit ON lnrs_anon_exam (anon_visit_id)`

### 3.3 `lnrs_anon_visit`（新增）

**用途**：从 `surgery_record.visit_id` 逆向推导的"就诊桥接"实体。珠江数据源无独立就诊表，故从手术记录合成就诊，作为所有非影像临床数据的挂载点。

| 列名 | 类型 | 可空 | 主键 | 设计决策 |
|---|---|---|---|---|
| `anon_visit_id` | VARCHAR(40) | 否 | 是 | `ANON_VISIT_` + HMAC-SHA256(secret, "{center}:{visit_id}")[:12]。确定性：相同源数据始终生成相同 ID。 |
| `patient_id` | VARCHAR(16) | 否 | — | FK → patient ON DELETE CASCADE。使用 `patient_id`（非 `anon_id`）与表族一致。 |
| `center_code` | VARCHAR(32) | 否 | — | 医院数据中心标识。 |
| `visit_ordinal` | VARCHAR(64) | 否 | — | 原始 visit_id 保留用于追踪（如 "153623_1"）。 |
| `source_visit_hash` | CHAR(64) | 否 | — | SHA256(center, visit_id)——裸哈希用于幂等去重。 |
| `created_batch_id` | UUID | 否 | — | FK → 导入批次。 |
| `last_seen_batch_id` | UUID | 否 | — | 重入时更新。 |

**约束**：
- `UNIQUE (center_code, source_visit_hash)` — 幂等键
- `UNIQUE (patient_id, visit_ordinal)` — 同一患者不能有重复就诊序号
- 无软删除机制（比 patient 生命周期简单）

**索引**：`patient_id` 上、`center_code` 上各建索引。

### 3.4 `lnrs_anon_surgery`（新增）

**用途**：就诊级手术记录。每行代表一次就诊中的一台手术。数据确认单次就诊可有 1~4 台手术。

| 列名 | 类型 | 可空 | 主键 | 设计决策 |
|---|---|---|---|---|
| `surgery_id` | BIGSERIAL | 否 | 是 | 代理键，供内部引用。 |
| `anon_visit_id` | VARCHAR(40) | 否 | — | FK → visit ON DELETE CASCADE。建索引加速就诊→手术查询。 |
| `patient_id` | VARCHAR(16) | 否 | — | 冗余 FK，支持直接患者→手术查询。 |
| `center_code` | VARCHAR(32) | 否 | — | 医院数据中心。 |
| `surgery_date` | DATE | 是 | — | 手术日期。 |
| `procedure_name` | VARCHAR(200) | 否 | — | 截断至 200 字符。 |
| `resection_scope` | VARCHAR(100) | 是 | — | 如"左肺上叶切除术"。 |
| `surgical_approach` | VARCHAR(50) | 是 | — | 如"胸腔镜"。 |
| `procedure_detail` | JSONB | 是 | — | 结构化：icd9cm3_code、淋巴结清扫、时长、出血量等。 |
| `source_surgery_hash` | CHAR(64) | 否 | — | SHA256(center, visit_id, procedure_name)——区分同一就诊的多台手术。 |
| `created_batch_id` | UUID | 否 | — | FK → 导入批次。 |

**约束**：
- `UNIQUE (anon_visit_id, source_surgery_hash)` — 每就诊+每手术幂等键

**索引**：`anon_visit_id`、`patient_id`、`surgery_date` 上各建索引。

### 3.5 `lnrs_anon_exam_detail`（新增）

**用途**：检查的 JSONB 深层结构数据。与扁平的 `lnrs_anon_exam_finding`（EAV 存储标量如结节直径、位置）互补。Detail 表存储压平后会丢失意义的嵌套结构。

| 列名 | 类型 | 可空 | 主键 | 设计决策 |
|---|---|---|---|---|
| `anon_exam_id` | VARCHAR(40) | 否 | 是 | 与 exam 1:1。FK ON DELETE CASCADE。 |
| `detail_type` | VARCHAR(32) | 否 | — | 区分结构语义。建索引支持按类型查询。 |
| `detail_json` | JSONB | 否 | — | Parquet struct 原样保留。GIN 索引。 |
| `created_batch_id` | UUID | 否 | — | FK → 导入批次。 |

**detail_type 目录**：

| detail_type | 来源 Parquet | detail_json 内字段 |
|---|---|---|
| `nodule_imaging` | nodule_imaging.pq | exam_meta, nodule_morphology, nodule_quantitative, follow_up_comparison |
| `pathology` | pathology_specimen.pq | specimen_meta, adenocarcinoma_subtypes, tumor_measurement, high_risk_factors, staging |
| `genetic` | genetic_test.pq | test_meta, variant_result, driver_mutations（13 基因 + VAF）, immune_markers |
| `ihc` | ihc_result.pq | ki67_pct, pdl1_tps_pct, pdl1_clone, pdl1_cps, alk_ihc, ttf1, napsina, p40, p53 |

**为什么选 JSONB 而非 EAV**：基因的 `driver_mutations` 压平为 finding 行，单条检测产生 30+ 行且丢失基因→突变层级关系（如"KRAS G13D 突变"）。JSONB 保留结构；GIN 索引支持高效查询。

---

## 4. API 表面 — 新增函数

### 4.1 脱敏函数（`anonymize.py`）

```python
compute_anon_visit_id(center_code: str, visit_id: str) -> str
```
- **用途**：确定性脱敏就诊 ID。
- **格式**：`ANON_VISIT_` + HMAC-SHA256(secret, "{center}:{visit_id}")[:12]
- **契约**：任意为空则抛 `ValueError`。
- **碰撞抗性**：48 位截断（约 2.8×10^13 值空间）；系统规模（<10^7 患者）下碰撞概率可忽略。

```python
source_visit_hash(center_code: str, visit_id: str) -> str
```
- **用途**：就诊幂等去重哈希。
- **算法**：裸 SHA256(center:visit_id)。

```python
source_surgery_hash(center_code: str, visit_id: str, procedure_name: str) -> str
```
- **用途**：手术记录幂等去重哈希。
- **算法**：裸 SHA256(center:visit_id:procedure_name)。
- **理由**：`procedure_name` 分量必不可少——同一就诊可包含 1~4 台不同手术。

### 4.2 ETL 引擎函数（`anon_etl_engine.py`）

#### 辅助函数

```python
_clean_str(val: Any) -> str | None
```
规范化字符串：`None` → `None`，空串 → `None`，其余 → 去首尾空白。

```python
_extract_bmi(demographics: Any) -> float | None
```
从嵌套 `demographics` struct 提取 BMI。非 dict 或转换失败返回 `None`。

```python
_extract_patient_meta(rd: dict[str, Any]) -> dict[str, Any] | None
```
从 `medical_history` 构建 `patient_meta` JSONB。非空时返回完整 dict；否则 `None`。

```python
_build_detail_json(rd: dict[str, Any], detail_fields: list[str]) -> dict[str, Any]
```
从行字典中提取指定字段，构建精简 JSONB dict。仅包含非 None 字段。

#### 批量 Upsert 函数

```python
async def _batch_upsert_exam_detail(
    db: AsyncSession,
    *,
    detail_rows: list[dict[str, Any]],
) -> None
```
- 检查详情行批量 upsert。
- 冲突键：`anon_exam_id`（主键）。
- 冲突时：更新 `detail_type` 和 `detail_json`。
- 批次大小：`BATCH_SIZE` 常量（5000）。

```python
async def _batch_upsert_visits(
    db: AsyncSession,
    *,
    center_code: str,
    visit_records: list[dict[str, Any]],
    batch_id: str,
) -> dict[str, str]
```
- 就诊记录批量 upsert。
- 返回 `{anon_visit_id: visit_id}` 映射，供下游手术关联使用。
- **去重策略**：先按 `source_visit_hash` 去重（后者胜出），再查已有哈希复用 `anon_visit_id`。
- 冲突键：`(center_code, source_visit_hash)` via `lnrs_anon_uq_visit_source`。
- 冲突时：更新 `last_seen_batch_id` 和 `patient_id`。
- 无软删除机制。

```python
async def _batch_upsert_surgeries(
    db: AsyncSession,
    *,
    surgery_rows: list[dict[str, Any]],
) -> None
```
- 手术记录批量 upsert。
- 冲突键：`(anon_visit_id, source_surgery_hash)` via `lnrs_anon_uq_surgery`。
- 冲突时：更新所有可变列（surgery_date, procedure_name, resection_scope, surgical_approach, procedure_detail）。

#### 导入函数

```python
async def _import_exam_text_table(
    ...,
    detail_type: str | None = None,
    detail_fields: list[str] | None = None,
) -> int
```
- **变更**：新增可选参数 `detail_type` 和 `detail_fields`。
- 两者均提供时，额外提取结构化字段写入 `lnrs_anon_exam_detail`。
- `exam_date` 解析变更：现支持字符串日期（如 "2024-01-30"），通过 `birth_date_from()` 解析。
- 返回导入（去重后）的检查行数。

```python
async def _import_surgery_table(
    db: AsyncSession,
    *,
    center_code: str,
    parquet_path: Path,
    src_table: str,
    batch_id: str,
) -> int
```
- 手术 Parquet 导入新函数。
- **三阶段 upsert**：
  1. 先 upsert 就诊涉及的全部患者（确保外键存在）
  2. 回填 visit 和 surgery 记录中的 `patient_id`（移除临时 `_anon_id`）
  3. Upsert visits → surgeries → PHI audit 记录
- 按 `source_surgery_hash` 在批次内去重。
- 返回导入（去重后）的手术行数。

---

## 5. 字典/枚举变更

### 5.1 `med_exam_type` 医疗检查类型字典

新增两个值：

| dict_label | dict_value | dict_sort | 用途 |
|---|---|---|---|
| 基因检测 | Genetic | 4 | 基因检测检查记录 |
| 免疫组化 | IHC | 5 | 免疫组化结果记录 |

**修改位置**：
- Alembic 迁移：`e5f6a7b8c9d0_add_med_dict_mapping.py`
- 脚本数据：`backend/app/scripts/data/sys_dict_data.json`

**设计决策**：`exam_type` 列仍为 `VARCHAR(32)`，**不设 CHECK 约束**——字典值仅作为 ETL 归一化参考。新增检查类型零 DDL 变更（ADR-0008，决策 3）。

---

## 6. 行为契约

### 6.1 幂等保证

三张新表均保证幂等导入：
- **就诊**：`(center_code, source_visit_hash)` 唯一。相同源数据 → 相同 `anon_visit_id`（确定性 HMAC）→ 无重复。
- **手术**：`(anon_visit_id, source_surgery_hash)` 唯一。相同就诊 + 相同手术 → 同行。
- **检查详情**：主键 = `anon_exam_id`（与 exam 1:1）。重入时更新详情行。

### 6.2 重入语义

- **患者**：ON CONFLICT 更新所有人口学字段 + 复活软删除行。
- **就诊**：ON CONFLICT 仅更新 `last_seen_batch_id` 和 `patient_id`。
- **手术**：ON CONFLICT 更新所有可变列（日期、名称、范围、术式、详情）。
- **检查详情**：ON CONFLICT 更新 `detail_type` 和 `detail_json`。

### 6.3 级联删除

- Patient CASCADE → Visit CASCADE → Surgery CASCADE（FK ON DELETE CASCADE）。
- Patient CASCADE → Exam 的 `anon_visit_id` SET NULL（exam 不依赖 visit 存活）。
- Ingest batch CASCADE → 全部表（FK ON DELETE CASCADE）。

### 6.4 错误处理

- **缺失 ID**：`patient_id`、`visit_id` 或 `procedure_name` 缺失的行跳过并记警告日志。
- **无效 ID**：HMAC 计算抛出 `ValueError` 时捕获、记录、跳过该行。
- **缺失日期**：`exam_date` / `surgery_date` 解析失败变为 `None`（可空）——行仍入库。
- **无效 BMI**：demographics struct 中非数值 BMI 静默转为 `None`。
- **空 Parquet 文件**：记警告日志，函数返回 0——不报错。

---

## 7. Schema 迁移

### 7.1 迁移策略

所有 DDL 变更通过 **`backend/sql/postgres/0006-anonymized-schema-lnrs.sql`** 以幂等 DROP + CREATE 方式应用（非 Alembic）。该文件：
1. 先 DROP 所有依赖视图（CASCADE）
2. 按逆依赖顺序 DROP 所有表（CASCADE）
3. 从头重建

**这是全量重建式迁移**——要求 schema 为空或先 dump/restore 数据。**不适用于零停机生产迁移**。

### 7.2 Schema 哈希

脱敏层从 DDL 文件内容计算 `schema_hash`（ADR-0001）。任何 DDL 变更都会使哈希失效，需重启服务重新计算。此为预期副作用。

---

## 8. 外部引用

### 8.1 HQMS 数据采集接口标准

提交包含 `docs/HQMS住院病案首页数据采集接口标准20130410.pdf`——国家卫健委住院病案首页数据采集标准。需求记录（`docs/sour/需求记录.txt`）注明下拉选项值和显示标签应参考此标准。它提供了规范值域：
- 性别代码（RC001: 0/1/2/9）
- 血型（RC030/RC031: ABO 和 Rh）
- 婚姻状况（RC002）、职业（RC003）、入院途径（RC026）
- 手术分级（RC029: 四级）
- ICD-10 诊断代码（RC020）、ICD-9 操作代码（RC022）

### 8.2 测试数据

`docs/testdats/珠江样例测试数据.xlsx` 作为珠江中心样本的参考数据集。

---

## 9. 测试覆盖

### 9.1 单元测试（`test_anonymize.py`，266 行）

纯函数测试，覆盖：

| 测试类 | 覆盖内容 |
|---|---|
| `TestAnonId` | 确定性输出、格式校验、跨中心碰撞防护、空输入抛 ValueError |
| `TestAnonExamId` | 格式、确定性、前缀与患者级 ID 区分 |
| `TestSourceExamHash` | 64-hex 格式、确定性、中心影响哈希 |
| `TestNormalizeSex` | 11 组参数化用例（男/男性/M/m/male/Male/女/女性/F/female），未知→U，空白裁剪 |
| `TestBirthDate` | 完整日期、整型年份、ISO 字符串、年-月、纯年、None、空串、超范围、乱码 |
| `TestKeyFingerprintAndSchema` | 格式、稳定性、schema_hash 为 64-hex |
| `TestHashForAudit` | 确定性、None→空哈希、64-hex |
| `TestConstants` | CLEAN_METHOD_REGEX_ONLY, MAX_BODY_LEN=100,000 |
| `TestTruncateBody` | None→空串、短正文、恰好上限、超上限截断、多字节字符处理、自定义 max_len |

### 9.2 冒烟测试（`test_etl_smoke.py`，167 行）

端到端测试，需 PostgreSQL：

| 测试类 | 覆盖内容 |
|---|---|
| `TestEtlSmoke` | 导入 shengyi（1016 患者），验证格式、幂等性（重入不新增行或重发 ID）、失败路径（无效 parquet，批次保持 "failed"） |
| `TestCrossCenterNoCollision` | 验证跨中心无共享 anon_id |
| `TestBatchSurvivesImportFailure` | #2.3 回归的文档锚点 |

---

## 10. 变更范围汇总

| 类别 | 数量 | 明细 |
|---|---|---|
| 新增数据库表 | 3 | `lnrs_anon_visit`、`lnrs_anon_surgery`、`lnrs_anon_exam_detail` |
| 扩展数据库表 | 2 | `lnrs_anon_patient`（+8 列）、`lnrs_anon_exam`（+1 列） |
| 新增 Python 模型 | 3 | `AnonVisitModel`、`AnonSurgeryModel`、`AnonExamDetailModel` |
| 新增脱敏函数 | 3 | `compute_anon_visit_id`、`source_visit_hash`、`source_surgery_hash` |
| 新增 ETL 函数 | 8 | `_clean_str`、`_extract_bmi`、`_extract_patient_meta`、`_build_detail_json`、`_batch_upsert_exam_detail`、`_batch_upsert_visits`、`_batch_upsert_surgeries`、`_import_surgery_table` |
| 修改 ETL 函数 | 2 | `_import_patient_table`（+9 字段）、`_import_exam_text_table`（+detail 参数、字符串日期解析） |
| 新增检查类型 | 2 | Genetic、IHC |
| 新增 Parquet 源 | 4 | genetic_test、ihc_result、surgery_record，以及对既有 nodule_imaging 和 pathology_specimen 的 detail 提取 |

---

## 11. 关键设计决策索引

| # | 决策 | 理由 |
|---|---|---|
| D1 | JSONB 替代 EAV 存储嵌套结构 | 保留父子层级关系，避免单条基因检测膨胀为 30+ 行 |
| D2 | HMAC-SHA256 确定性 ID | 相同源数据始终映射相同脱敏 ID，保证幂等重入 |
| D3 | 字典即参考（不设 CHECK 约束） | 新增检查类型零 DDL 变更，符合 ADR-0008 决策 3 |
| D4 | 就诊作为桥接实体 | 源数据无独立就诊表，从手术记录逆向推导，统一挂载非影像临床数据 |
| D5 | 全量重建式 DDL | 简化迁移逻辑，当前阶段 schema 尚为空或可重建 |
| D6 | patient_meta 兜底 JSONB 列 | 避免每次新增患者属性都做 DDL 变更，GIN 索引支持高效查询 |
| D7 | exam.anon_visit_id 可空 + SET NULL | 检查不依赖就诊存活，维持既有 exam 语义不变 |
| D8 | 手术 patient_id 冗余存储 | 支持直接患者→手术查询，避免 JOIN visit 中间表 |
