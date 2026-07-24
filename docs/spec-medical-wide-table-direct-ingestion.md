# Medical Wide-Table Direct Ingestion Extension

> **Date**: 2026-07-23
> **Status**: Committed (main branch, commit `eb4379c7`) + uncommitted working changes
> **Component**: Medical Module — Anonymized Data Layer (ETL-2)
> **ADR Reference**: ADR-0006 (Anonymized Data Schema)

---

## 1. Overview

### 1.1 What Was Built

This feature **retires the intermediate `med_*` wide-table layer** (ETL-1) and enables **direct Parquet-to-anonymized-database ingestion** (ETL-2). Previously, data flowed through two stages: Excel → `med_*` wide tables → `lnrs_anon_*` anonymized tables. Now Parquet files from hospital data centers (e.g., the Zhujiang sample in `docs/demodata/0723_珠江sample_pq/`) are the single source of truth, ingested directly into the anonymized schema.

The extension adds **three new database tables** and **expands the patient table** to support pathology, genetics, IHC, surgery records, and enriched patient demographics — enabling the medical detail view described in the product requirements (入院记录, CT检查, 手术记录, 基因报告, 病理检查).

### 1.2 Why This Approach

- **Simplify the pipeline**: One fewer ETL layer means fewer transformation bugs, easier maintenance, and faster data availability.
- **Preserve structural data**: Complex nested fields (e.g., `driver_mutations` with 13 genes + VAF, `staging` with pT/pN/pM) are stored as JSONB rather than flattened into EAV rows, which would explode cardinality (30+ rows per genetic test) and lose parent-child relationships.
- **Deterministic re-ingestion**: All new entities use HMAC-based IDs and SHA256 source hashes, guaranteeing idempotent upserts — re-running ETL on the same source data produces no duplicates.

---

## 2. Architecture Changes

### 2.1 Entity Relationship Diagram (Textual)

```
lnrs_anon_ingest_batch (existing)
├── lnrs_anon_patient (expanded: +7 scalar cols, +1 JSONB)
│   ├── lnrs_anon_exam (existing, expanded: +anon_visit_id FK)
│   │   ├── lnrs_anon_report_text (existing)
│   │   └── lnrs_anon_exam_detail (NEW — 1:1 with exam)
│   └── lnrs_anon_visit (NEW)
│       └── lnrs_anon_surgery (NEW — 1:N with visit)
└── lnrs_anon_phi_audit (existing)
```

### 2.2 Data Flow

```
Hospital Parquet Files ──> anon_etl_engine.py ──> PostgreSQL (lnrs schema)
┌─────────────────────────────┐
│ patient.parquet             │  ──> _import_patient_table()    ──> lnrs_anon_patient
│ nodule_imaging.parquet      │  ──> _import_exam_text_table()  ──> lnrs_anon_exam + lnrs_anon_report_text + lnrs_anon_exam_detail
│ pathology_specimen.parquet  │  ──> _import_exam_text_table()  ──> lnrs_anon_exam + lnrs_anon_report_text + lnrs_anon_exam_detail
│ genetic_test.parquet        │  ──> _import_exam_text_table()  ──> lnrs_anon_exam + lnrs_anon_exam_detail
│ ihc_result.parquet          │  ──> _import_exam_text_table()  ──> lnrs_anon_exam + lnrs_anon_exam_detail
│ surgery_record.parquet      │  ──> _import_surgery_table()    ──> lnrs_anon_visit + lnrs_anon_surgery
└─────────────────────────────┘
```

### 2.3 Center-Specific Configuration

All parquet table specs are declared in `_CENTER_PARQUET_SPECS: dict[str, list[dict]]` in `anon_etl_engine.py`. Currently configured for the **"shengyi"** center. Each spec entry declares:

- `src_table`: parquet filename prefix
- `kind`: `"exam_text"` or `"surgery"` (dispatches to the appropriate import function)
- `exam_type`: normalized exam type code (CT, Pathology, Genetic, IHC)
- `id_field`: source column used as the exam identifier
- `body_fields`: columns to concatenate into report text
- `detail_type` / `detail_fields`: optional JSONB deep-structure extraction config

---

## 3. Data Model Changes

### 3.1 `lnrs_anon_patient` (Expanded)

**Rationale**: The original patient table was minimal (birth_date + sex only). Clinical data from Parquet includes stable patient attributes that are query-frequently and must be persisted.

| Column | Type | Nullable | Source | Design Decision |
|---|---|---|---|---|
| `ethnicity` | VARCHAR(50) | Yes | patient.parquet.ethnicity | High-frequency filter, scalar column |
| `native_place` | VARCHAR(100) | Yes | patient.parquet.native_place | Demographic cohort analysis |
| `first_nodule_date` | DATE | Yes | patient.parquet.first_nodule_date | Disease timeline reconstruction |
| `smoking_status` | VARCHAR(20) | Yes | patient.parquet.smoking_status | Risk factor analysis |
| `abo_blood_type` | VARCHAR(10) | Yes | patient.parquet.abo_blood_type | Surgical planning reference |
| `rh_blood_type` | VARCHAR(10) | Yes | patient.parquet.rh_blood_type | Surgical planning reference |
| `bmi` | NUMERIC(5,1) | Yes | patient.parquet.demographics.bmi | Extracted from nested struct (see §4.1) |
| `patient_meta` | JSONB | Yes | patient.parquet.medical_history | Catch-all for lifetime attributes (family history, comorbidities, prior tumors, discovery pathway, pack-years). GIN-indexed. |

**Constraints added**:
- `CHECK (first_nodule_date >= '1900-01-01' AND first_nodule_date <= '2100-12-31')`
- `CREATE INDEX lnrs_anon_ix_patient_meta_gin ON lnrs_anon_patient USING gin (patient_meta)`

**Upsert behavior**: ON CONFLICT on `lnrs_anon_uq_patient_center`, ALL new columns are updated (not just birth_date + sex). This ensures that if upstream Parquet provides updated demographics, the patient record reflects the latest data.

### 3.2 `lnrs_anon_exam` (Expanded)

| Column | Type | Nullable | FK | Design Decision |
|---|---|---|---|---|
| `anon_visit_id` | VARCHAR(40) | Yes | `lnrs_anon_visit.anon_visit_id` ON DELETE SET NULL | Bridges imaging exams to visits when the reverse lookup succeeds. Nullable to preserve existing exam semantics — most exams have no visit association. |

**Index**: `CREATE INDEX lnrs_anon_ix_exam_visit ON lnrs_anon_exam (anon_visit_id)`

### 3.3 `lnrs_anon_visit` (NEW)

**Purpose**: A "visit bridge" entity reverse-engineered from `surgery_record.visit_id`. Since the Zhujiang data lacks a dedicated visit table, visits are synthesized from surgery records and serve as the attachment point for all non-imaging clinical data.

| Column | Type | Nullable | PK | Design Decision |
|---|---|---|---|---|
| `anon_visit_id` | VARCHAR(40) | No | Yes | `ANON_VISIT_` + HMAC-SHA256(secret, "{center}:{visit_id}")[:12]. Deterministic: same source always produces same ID. |
| `patient_id` | VARCHAR(16) | No | — | FK → `lnrs_anon_patient.patient_id` ON DELETE CASCADE. Uses `patient_id` (not `anon_id`) for consistency with the table family. |
| `center_code` | VARCHAR(32) | No | — | Hospital data center identifier. |
| `visit_ordinal` | VARCHAR(64) | No | — | Raw visit_id preserved for traceability (e.g., "153623_1"). |
| `source_visit_hash` | CHAR(64) | No | — | SHA256(center, visit_id) — bare hash for idempotent deduplication. |
| `created_batch_id` | UUID | No | — | FK → ingest batch. |
| `last_seen_batch_id` | UUID | No | — | Updated on re-ingestion. |

**Constraints**:
- `UNIQUE (center_code, source_visit_hash)` — idempotency key
- `UNIQUE (patient_id, visit_ordinal)` — same patient cannot have duplicate visit ordinals
- No soft-delete mechanism (simpler than patient lifecycle)

**Indexes**: On `patient_id`, on `center_code`.

### 3.4 `lnrs_anon_surgery` (NEW)

**Purpose**: Visit-level surgical records. Each row represents one procedure within a visit. Data confirms 1–4 procedures per visit are possible.

| Column | Type | Nullable | PK | Design Decision |
|---|---|---|---|---|
| `surgery_id` | BIGSERIAL | No | Yes | Surrogate key for internal references. |
| `anon_visit_id` | VARCHAR(40) | No | — | FK → visit ON DELETE CASCADE. Index for visit→surgery lookup. |
| `patient_id` | VARCHAR(16) | No | — | Denormalized FK for direct patient→surgery queries. |
| `center_code` | VARCHAR(32) | No | — | Hospital data center. |
| `surgery_date` | DATE | Yes | — | Surgical procedure date. |
| `procedure_name` | VARCHAR(200) | No | — | Truncated to 200 chars. |
| `resection_scope` | VARCHAR(100) | Yes | — | E.g., "左肺上叶切除术". |
| `surgical_approach` | VARCHAR(50) | Yes | — | E.g., "胸腔镜". |
| `procedure_detail` | JSONB | Yes | — | Structured: icd9cm3_code, lymph node dissection, duration, blood loss, etc. |
| `source_surgery_hash` | CHAR(64) | No | — | SHA256(center, visit_id, procedure_name) — distinguishes multiple procedures in the same visit. |
| `created_batch_id` | UUID | No | — | FK → ingest batch. |

**Constraints**:
- `UNIQUE (anon_visit_id, source_surgery_hash)` — idempotency key per visit+procedure

**Indexes**: On `anon_visit_id`, on `patient_id`, on `surgery_date`.

### 3.5 `lnrs_anon_exam_detail` (NEW)

**Purpose**: JSONB deep-structure data for exams. Complements the flat `lnrs_anon_exam_finding` (EAV for scalars like nodule diameter, position). Detail stores nested structures that would lose meaning if flattened.

| Column | Type | Nullable | PK | Design Decision |
|---|---|---|---|---|
| `anon_exam_id` | VARCHAR(40) | No | Yes | 1:1 with exam. FK ON DELETE CASCADE. |
| `detail_type` | VARCHAR(32) | No | — | Discriminates structure semantics. Index for type-based queries. |
| `detail_json` | JSONB | No | — | Original Parquet struct, preserved verbatim. GIN-indexed. |
| `created_batch_id` | UUID | No | — | FK → ingest batch. |

**Detail type catalog**:

| detail_type | Source Parquet | Fields in detail_json |
|---|---|---|
| `nodule_imaging` | nodule_imaging.pq | exam_meta, nodule_morphology, nodule_quantitative, follow_up_comparison |
| `pathology` | pathology_specimen.pq | specimen_meta, adenocarcinoma_subtypes, tumor_measurement, high_risk_factors, staging |
| `genetic` | genetic_test.pq | test_meta, variant_result, driver_mutations (13 genes + VAF), immune_markers |
| `ihc` | ihc_result.pq | ki67_pct, pdl1_tps_pct, pdl1_clone, pdl1_cps, alk_ihc, ttf1, napsina, p40, p53 |

**Why JSONB over EAV**: Genetic `driver_mutations` flattened into finding rows would produce 30+ rows per test and lose the gene→mutation hierarchy (e.g., "KRAS G13D mutation"). JSONB preserves structure; GIN index enables efficient queries.

---

## 4. API Surface — New Functions

### 4.1 Anonymization Functions (`anonymize.py`)

```python
compute_anon_visit_id(center_code: str, visit_id: str) -> str
```
- **Purpose**: Deterministic anonymized visit ID.
- **Format**: `ANON_VISIT_` + HMAC-SHA256(secret, "{center}:{visit_id}")[:12]
- **Contract**: Raises `ValueError` if either argument is empty.
- **Collision resistance**: 48-bit truncation (~2.8×10^13 values); collision probability negligible at system scale (<10^7 patients).

```python
source_visit_hash(center_code: str, visit_id: str) -> str
```
- **Purpose**: Idempotent deduplication hash for visits.
- **Algorithm**: Bare SHA256(center:visit_id).

```python
source_surgery_hash(center_code: str, visit_id: str, procedure_name: str) -> str
```
- **Purpose**: Idempotent deduplication hash for surgery records.
- **Algorithm**: Bare SHA256(center:visit_id:procedure_name).
- **Rationale**: The procedure_name component is essential — the same visit can have 1–4 different procedures.

### 4.2 ETL Engine Functions (`anon_etl_engine.py`)

#### Helper functions

```python
_clean_str(val: Any) -> str | None
```
Normalizes string values: `None` → `None`, empty string → `None`, others → stripped.

```python
_extract_bmi(demographics: Any) -> float | None
```
Extracts BMI from the nested `demographics` struct. Returns `None` if not a dict or if conversion fails.

```python
_extract_patient_meta(rd: dict[str, Any]) -> dict[str, Any] | None
```
Constructs `patient_meta` JSONB from `medical_history`. Returns the full dict if non-empty; `None` otherwise.

```python
_build_detail_json(rd: dict[str, Any], detail_fields: list[str]) -> dict[str, Any]
```
Extracts specified fields from a row dict into a compact JSONB dict. Only non-None fields are included.

#### Batch upsert functions

```python
async def _batch_upsert_exam_detail(
    db: AsyncSession,
    *,
    detail_rows: list[dict[str, Any]],
) -> None
```
- Batch upsert for exam detail rows.
- Conflict key: `anon_exam_id` (PK).
- On conflict: updates `detail_type` and `detail_json`.
- Batch size: `BATCH_SIZE` constant (inherited, 5000).

```python
async def _batch_upsert_visits(
    db: AsyncSession,
    *,
    center_code: str,
    visit_records: list[dict[str, Any]],
    batch_id: str,
) -> dict[str, str]
```
- Batch upsert for visit records.
- Returns `{anon_visit_id: visit_id}` mapping for downstream surgery linking.
- **Deduplication**: First deduplicates by `source_visit_hash` (last one wins), then queries existing hashes to reuse `anon_visit_id`.
- Conflict key: `(center_code, source_visit_hash)` via `lnrs_anon_uq_visit_source`.
- On conflict: updates `last_seen_batch_id` and `patient_id`.
- No soft-delete mechanism.

```python
async def _batch_upsert_surgeries(
    db: AsyncSession,
    *,
    surgery_rows: list[dict[str, Any]],
) -> None
```
- Batch upsert for surgery records.
- Conflict key: `(anon_visit_id, source_surgery_hash)` via `lnrs_anon_uq_surgery`.
- On conflict: updates all mutable columns (surgery_date, procedure_name, resection_scope, surgical_approach, procedure_detail).

#### Import functions

```python
async def _import_exam_text_table(
    ...,
    detail_type: str | None = None,
    detail_fields: list[str] | None = None,
) -> int
```
- **Changed**: Now accepts optional `detail_type` and `detail_fields` parameters.
- When both are provided, additionally extracts structured fields into `lnrs_anon_exam_detail`.
- `exam_date` parsing changed: now handles string dates (e.g., "2024-01-30") via `birth_date_from()`.
- Returns count of imported (deduplicated) exam rows.

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
- New function for surgery parquet ingestion.
- **Three-phase upsert**:
  1. Upsert all patients involved in visits (ensures FK exists).
  2. Backfill `patient_id` in visit and surgery records (removes temporary `_anon_id`).
  3. Upsert visits → surgeries → PHI audit records.
- Deduplicates by `source_surgery_hash` within the batch.
- Returns count of imported (deduplicated) surgery rows.

---

## 5. Dictionary/Enum Changes

### 5.1 `med_exam_type` Dictionary

Two new values added to the medical exam type dictionary:

| dict_label | dict_value | dict_sort | Purpose |
|---|---|---|---|
| 基因检测 | Genetic | 4 | Genetic test exam records |
| 免疫组化 | IHC | 5 | Immunohistochemistry result records |

**Where updated**:
- Alembic migration: `e5f6a7b8c9d0_add_med_dict_mapping.py`
- Script data: `backend/app/scripts/data/sys_dict_data.json`

**Design decision**: `exam_type` column remains `VARCHAR(32)` with **no CHECK constraint** — dictionary values are used as ETL normalization references only. Adding new exam types requires zero DDL changes (ADR-0008, Decision 3).

---

## 6. Behavioral Contracts

### 6.1 Idempotency Guarantee

All three new tables guarantee idempotent ingestion:
- **Visit**: Unique on `(center_code, source_visit_hash)`. Same source data → same `anon_visit_id` (deterministic HMAC) → no duplicates.
- **Surgery**: Unique on `(anon_visit_id, source_surgery_hash)`. Same visit + same procedure → same row.
- **Exam Detail**: Primary key = `anon_exam_id` (1:1 with exam). Re-ingestion updates the detail row.

### 6.2 Re-ingestion Semantics

- **Patient**: ON CONFLICT updates ALL demographic fields + resurrects soft-deleted rows.
- **Visit**: ON CONFLICT updates `last_seen_batch_id` and `patient_id` only.
- **Surgery**: ON CONFLICT updates all mutable columns (date, name, scope, approach, detail).
- **Exam Detail**: ON CONFLICT updates `detail_type` and `detail_json`.

### 6.3 Cascading Deletes

- Patient CASCADE → Visit CASCADE → Surgery CASCADE (via FK ON DELETE CASCADE).
- Patient CASCADE → Exam SET NULL on `anon_visit_id` (exam survives without visit link).
- Ingest batch CASCADE → all tables (via FK ON DELETE CASCADE).

### 6.4 Error Handling

- **Missing IDs**: Rows with missing `patient_id`, `visit_id`, or `procedure_name` are skipped with a warning log.
- **Invalid IDs**: `ValueError` from HMAC computation is caught, logged, and the row is skipped.
- **Missing dates**: `exam_date` / `surgery_date` that fail parsing become `None` (nullable) — row is still ingested.
- **Invalid BMI**: Non-numeric BMI in demographics struct is silently converted to `None`.
- **Empty Parquet files**: Logged as warning, function returns 0 — no error.

---

## 7. Schema Migration

### 7.1 Migration Strategy

All DDL changes are applied through **`backend/sql/postgres/0006-anonymized-schema-lnrs.sql`** using idempotent DROP + CREATE (not Alembic). This file:
1. Drops all dependent views first (CASCADE).
2. Drops all tables in reverse dependency order (CASCADE).
3. Recreates everything from scratch.

**This is a full-recreate migration** — it requires the schema to be empty or the data to be dumped/restored. It is NOT suitable for zero-downtime production migration.

### 7.2 Schema Hash

The anonymization layer computes a `schema_hash` from the DDL file content (ADR-0001). Any DDL change invalidates the hash, requiring a service restart to recompute. This is documented as an expected side effect.

---

## 8. External References

### 8.1 HQMS Data Interface Standard

The commit includes `docs/HQMS住院病案首页数据采集接口标准20130410.pdf` — the National Health Commission's standard for hospital discharge summary data. The requirements document (`docs/sour/需求记录.txt`) notes that dropdown option values and display labels should reference this standard. This provides the canonical value domains for:
- Sex codes (RC001: 0/1/2/9)
- Blood types (RC030/RC031: ABO and Rh)
- Marriage status (RC002), occupation (RC003), admission route (RC026)
- Surgery classification (RC029: levels 1–4)
- ICD-10 diagnosis codes (RC020), ICD-9 procedure codes (RC022)

### 8.2 Test Data

`docs/testdats/珠江样例测试数据.xlsx` was added as a reference dataset for the Zhujiang center sample.

---

## 9. Uncommitted Changes (Working Directory)

The following files have local modifications not yet committed:

| File | Nature of Change |
|---|---|
| `alembic/versions/e5f6a7b8c9d0_add_med_dict_mapping.py` | Same as committed (Genetic/IHC dict entries) |
| `anon_etl_engine.py` | Same as committed (full ETL extension) |
| `anon_model.py` | Same as committed (3 new models + patient expansion) |
| `anonymize.py` | Same as committed (visit/surgery hash functions) |
| `sys_dict_data.json` | Same as committed (Genetic/IHC entries) |
| `0006-anonymized-schema-lnrs.sql` | Same as committed (DDL extension) |
| `docs/adr/0006-anonymized-data-schema.md` | Same as committed (ADR update) |
| `docs/sour/需求记录.txt` | Same as committed (requirements update) |

These appear to be CRLF→LF line-ending differences that will resolve on next commit.

---

## 10. Summary of Scope

| Category | Count | Details |
|---|---|---|
| New database tables | 3 | `lnrs_anon_visit`, `lnrs_anon_surgery`, `lnrs_anon_exam_detail` |
| Expanded tables | 2 | `lnrs_anon_patient` (+8 cols), `lnrs_anon_exam` (+1 col) |
| New Python models | 3 | `AnonVisitModel`, `AnonSurgeryModel`, `AnonExamDetailModel` |
| New functions (anonymize) | 3 | `compute_anon_visit_id`, `source_visit_hash`, `source_surgery_hash` |
| New functions (ETL) | 7 | `_clean_str`, `_extract_bmi`, `_extract_patient_meta`, `_build_detail_json`, `_batch_upsert_exam_detail`, `_batch_upsert_visits`, `_batch_upsert_surgeries`, `_import_surgery_table` |
| Modified functions | 2 | `_import_patient_table` (+9 fields), `_import_exam_text_table` (+detail params, string date parsing) |
| New exam types | 2 | Genetic, IHC |
| New parquet sources | 4 | genetic_test, ihc_result, surgery_record, + detail extraction on existing nodule_imaging & pathology_specimen |
