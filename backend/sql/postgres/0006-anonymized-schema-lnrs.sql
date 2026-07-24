-- =====================================================================
-- 脱敏后病例数据 schema (执行版) - Rev 2026-07-24 宽表直入扩展嫁接
-- 依据: docs/adr/0006-anonymized-data-schema.md
-- 目标: PostgreSQL 14+, schema = lnrs
-- 变更要点:
--   * lnrs_anon_patient 双 ID 体系
--     - patient_id VARCHAR(16) PRIMARY KEY (PT_xxxxxxxx, 对外业务 ID 即 PK)
--       由 lnrs_anon_patient_seq 生成：应用层 "PT_" || LPAD(nextval, 8, '0')
--     - anon_id VARCHAR(32) UNIQUE NOT NULL (ANON_<HMAC>[:12], 内部反查键)
--   * 跨表 FK 指向 patient_id (不再指向 anon_id)
--   * 软删除字段 (deleted_at/deleted_reason/deleted_batch_id) + 复活语义
--   * 2026-07-23 枚举权威移交（ADR-0008）:
--     - sex / laterality 由 ENUM 改为 VARCHAR(10) + CHECK
--     - 枚举标准来源 = 新建 med_* 字典类型（字典为唯一事实源）
--     - ENUM 类型 lnrs_anon_sex_enum / lnrs_anon_laterality_enum 已删除
--   * 2026-07-24 医疗宽表直入扩展嫁接（med_* 中间层退役）:
--     - lnrs_anon_patient 扩展 4 个非枚举列 + patient_meta JSONB
--       (native_place/first_nodule_date/bmi + 病史兜底 JSONB)
--       注: 枚举列 (ethnicity/smoking_status/abo/rh_blood_type) 保持国标码紧凑存储
--     - 新增 lnrs_anon_visit (就诊桥, 从 surgery_record.visit_id 反推)
--     - 新增 lnrs_anon_surgery (visit 级手术记录)
--     - 新增 lnrs_anon_exam_detail (exam 级 JSONB 深结构: 病理/基因/IHC/结节)
--     - lnrs_anon_exam 加 anon_visit_id 可空桥列
-- =====================================================================

BEGIN;

-- 切换目标 schema
SET LOCAL search_path = lnrs, public;
-- 注意: 索引/触发器名只属于当前 schema, 不能带 lnrs. 前缀

-- ---------- 0. 幂等清理 ----------

DROP VIEW IF EXISTS lnrs.lnrs_anon_v_exam_full;
-- exam_detail 依赖 exam, 必须在 exam 之前删
DROP TABLE IF EXISTS lnrs.lnrs_anon_exam_detail            CASCADE;
DROP TABLE IF EXISTS lnrs.lnrs_anon_phi_audit               CASCADE;
DROP TABLE IF EXISTS lnrs.lnrs_anon_dicom_uid_map          CASCADE;
DROP TABLE IF EXISTS lnrs.lnrs_anon_dicom_instance         CASCADE;
DROP TABLE IF EXISTS lnrs.lnrs_anon_dicom_series           CASCADE;
DROP TABLE IF EXISTS lnrs.lnrs_anon_exam_finding           CASCADE;
DROP TABLE IF EXISTS lnrs.lnrs_anon_report_text            CASCADE;
DROP TABLE IF EXISTS lnrs.lnrs_anon_exam                   CASCADE;
-- surgery 依赖 visit, visit 依赖 patient, 都在 exam 之后 patient 之前删
DROP TABLE IF EXISTS lnrs.lnrs_anon_surgery                CASCADE;
DROP TABLE IF EXISTS lnrs.lnrs_anon_visit                  CASCADE;
DROP TABLE IF EXISTS lnrs.lnrs_anon_patient                CASCADE;
DROP TABLE IF EXISTS lnrs.lnrs_anon_ingest_batch           CASCADE;

DROP SEQUENCE IF EXISTS lnrs.lnrs_anon_patient_seq CASCADE;

DROP TYPE IF EXISTS lnrs.lnrs_anon_phi_strategy_enum CASCADE;
DROP TYPE IF EXISTS lnrs.lnrs_anon_clean_method_enum CASCADE;
DROP TYPE IF EXISTS lnrs.lnrs_anon_uid_kind_enum     CASCADE;
DROP TYPE IF EXISTS lnrs.lnrs_anon_review_status_enum CASCADE;
DROP TYPE IF EXISTS lnrs.lnrs_anon_source_kind_enum  CASCADE;
DROP TYPE IF EXISTS lnrs.lnrs_anon_ingest_status_enum CASCADE;

DROP FUNCTION IF EXISTS lnrs.lnrs_anon_trg_set_updated_at() CASCADE;

-- ---------- 1. ENUM ----------

-- lnrs_anon_sex_enum 已移除：枚举权威移交至 med_sex 字典（ADR-0008）
CREATE TYPE lnrs.lnrs_anon_ingest_status_enum  AS ENUM ('running','success','failed','partial');
CREATE TYPE lnrs.lnrs_anon_source_kind_enum    AS ENUM ('csv_report','dicom_dir','dicom_zip');
CREATE TYPE lnrs.lnrs_anon_review_status_enum  AS ENUM ('pending','reviewed','flagged');
-- lnrs_anon_laterality_enum 已移除：枚举权威移交至 med_laterality 字典（ADR-0008）
CREATE TYPE lnrs.lnrs_anon_uid_kind_enum       AS ENUM ('study','series','sop');
CREATE TYPE lnrs.lnrs_anon_clean_method_enum   AS ENUM ('regex_only','regex+llm','manual_review');
CREATE TYPE lnrs.lnrs_anon_phi_strategy_enum   AS ENUM ('hmac','clear','partial_keep','llm_replace','manual_review');

-- ---------- 2. lnrs_anon_ingest_batch ----------

CREATE TABLE lnrs.lnrs_anon_ingest_batch (
    batch_id           UUID         PRIMARY KEY,
    center_code        VARCHAR(32)  NOT NULL,
    source_kind        lnrs.lnrs_anon_source_kind_enum    NOT NULL,
    source_locator     TEXT         NOT NULL,
    source_sha256      CHAR(64),
    secret_version     VARCHAR(32)  NOT NULL,
    key_fingerprint    CHAR(16)     NOT NULL,
    schema_hash        CHAR(64)     NOT NULL,
    row_counts         JSONB        NOT NULL DEFAULT '{}'::jsonb,
    started_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at        TIMESTAMP,
    status             lnrs.lnrs_anon_ingest_status_enum NOT NULL DEFAULT 'running',
    error              TEXT,
    CONSTRAINT lnrs_anon_uq_batch_center_secret UNIQUE (center_code, secret_version, key_fingerprint, schema_hash, started_at)
);

CREATE INDEX lnrs_anon_ix_batch_status       ON lnrs.lnrs_anon_ingest_batch (status);
CREATE INDEX lnrs_anon_ix_batch_secret_ver   ON lnrs.lnrs_anon_ingest_batch (secret_version, key_fingerprint, schema_hash);

-- ---------- 3. lnrs_anon_patient (Rev 2026-07-19: 双 ID 体系, patient_id 直接当 PK) ----------

-- 全局自增物理序号 (百万级起步, 8 位 zero-pad, BIGINT 预留到亿级)
-- 应用层: patient_id = "PT_" || LPAD(nextval(...), 8, '0')
CREATE SEQUENCE lnrs.lnrs_anon_patient_seq
    INCREMENT BY 1
    START WITH 1
    MINVALUE 1
    MAXVALUE 99999999
    CACHE 50;

CREATE TABLE lnrs.lnrs_anon_patient (
    patient_id         VARCHAR(16)  PRIMARY KEY,        -- PT_xxxxxxxx, 对外 ID 即 PK
    anon_id            VARCHAR(32)  NOT NULL UNIQUE,   -- ANON_<HMAC>, 内部反查键
    center_code        VARCHAR(32)  NOT NULL,
    birth_date         DATE         CHECK (birth_date >= '1900-01-01' AND birth_date <= '2100-12-31'),
    sex                VARCHAR(10)  NOT NULL DEFAULT '0',
    ethnicity          VARCHAR(2),
    smoking_status     VARCHAR(1),
    abo_blood_type     VARCHAR(1),
    rh_blood_type      VARCHAR(1),
    -- 患者稳定属性（医疗宽表直入扩展，从 patient.parquet 直接承载）
    native_place       VARCHAR(100),
    first_nodule_date  DATE         CHECK (first_nodule_date >= '1900-01-01' AND first_nodule_date <= '2100-12-31'),
    bmi                NUMERIC(5,1),
    -- 兜底 JSONB：家族史/既往肿瘤/合并症/发现途径/吸烟包年等终身属性
    patient_meta       JSONB,
    created_batch_id   UUID         NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
    last_seen_batch_id UUID         NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
    created_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- 软删除字段: NULL = 活跃, 非空 = 软删 (但 patient_id 仍保留, 可被重新导入复活)
    deleted_at         TIMESTAMP,
    deleted_reason     VARCHAR(64),
    deleted_batch_id   UUID         REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id),
    CONSTRAINT lnrs_anon_uq_patient_center   UNIQUE (center_code, anon_id),
    CONSTRAINT lnrs_anon_ck_patient_id_fmt   CHECK (patient_id ~ '^PT_[0-9]{8}$'),
    CONSTRAINT lnrs_anon_ck_anon_id_fmt      CHECK (anon_id ~ '^ANON_[0-9a-f]{12}$'),
    CONSTRAINT lnrs_anon_ck_deleted_consistency CHECK (
        (deleted_at IS NULL  AND deleted_reason IS NULL  AND deleted_batch_id IS NULL) OR
        (deleted_at IS NOT NULL AND deleted_reason IS NOT NULL)
    ),
    -- 枚举权威移交 med_sex 字典（ADR-0008）：CHECK 替代 ENUM
    CONSTRAINT lnrs_anon_ck_patient_sex CHECK (sex IN ('0','1','2','9')),
    CONSTRAINT lnrs_anon_ck_patient_ethnicity CHECK (ethnicity IS NULL OR ethnicity ~ '^[0-9]{2}$'),
    CONSTRAINT lnrs_anon_ck_patient_smoking CHECK (smoking_status IS NULL OR smoking_status IN ('1','2','3','9')),
    CONSTRAINT lnrs_anon_ck_patient_abo CHECK (abo_blood_type IS NULL OR abo_blood_type IN ('1','2','3','4','5','6')),
    CONSTRAINT lnrs_anon_ck_patient_rh CHECK (rh_blood_type IS NULL OR rh_blood_type IN ('1','2','3','4')),
    CONSTRAINT lnrs_anon_ck_patient_center CHECK (center_code ~ '^[a-z][a-z0-9_]*$')
);

CREATE INDEX lnrs_anon_ix_patient_center    ON lnrs.lnrs_anon_patient (center_code);
CREATE INDEX lnrs_anon_ix_patient_birth     ON lnrs.lnrs_anon_patient (birth_date);
CREATE INDEX lnrs_anon_ix_patient_anon_id   ON lnrs.lnrs_anon_patient (anon_id);
-- 部分索引: 仅索引软删除行, 加速 PURGE 物理清理扫描
CREATE INDEX lnrs_anon_ix_patient_deleted   ON lnrs.lnrs_anon_patient (deleted_at) WHERE deleted_at IS NOT NULL;
-- patient_meta JSONB GIN 索引 (家族史/合并症等查询)
CREATE INDEX lnrs_anon_ix_patient_meta_gin  ON lnrs.lnrs_anon_patient USING gin (patient_meta);

-- ---------- 4. lnrs_anon_exam (FK 改为 patient_id) ----------

CREATE TABLE lnrs.lnrs_anon_exam (
    anon_exam_id       VARCHAR(40)  PRIMARY KEY,
    patient_id         VARCHAR(16)  NOT NULL REFERENCES lnrs.lnrs_anon_patient(patient_id) ON DELETE CASCADE,
    center_code        VARCHAR(32)  NOT NULL,
    exam_type          VARCHAR(32),
    exam_date          DATE         NOT NULL,
    source_exam_hash   CHAR(64)     NOT NULL,
    -- visit 桥列 (FK 在 lnrs_anon_visit 建表后用 ALTER 补加, 见下文)
    anon_visit_id      VARCHAR(40),
    created_batch_id   UUID         NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
    last_seen_batch_id UUID         NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
    created_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT lnrs_anon_uq_exam_source UNIQUE (center_code, source_exam_hash)
);

CREATE INDEX lnrs_anon_ix_exam_patient      ON lnrs.lnrs_anon_exam (patient_id);
CREATE INDEX lnrs_anon_ix_exam_center_date ON lnrs.lnrs_anon_exam (center_code, exam_date);
CREATE INDEX lnrs_anon_ix_exam_type_date    ON lnrs.lnrs_anon_exam (exam_type, exam_date);
CREATE INDEX lnrs_anon_ix_exam_visit        ON lnrs.lnrs_anon_exam (anon_visit_id);

-- ---------- 5. lnrs_anon_report_text ----------

CREATE TABLE lnrs.lnrs_anon_report_text (
    anon_exam_id        VARCHAR(40)  PRIMARY KEY REFERENCES lnrs.lnrs_anon_exam(anon_exam_id) ON DELETE CASCADE,
    body_clean          TEXT         NOT NULL,
    pii_replaced_count  INT          NOT NULL DEFAULT 0 CHECK (pii_replaced_count >= 0),
    clean_method        lnrs.lnrs_anon_clean_method_enum NOT NULL,
    llm_model           VARCHAR(64),
    review_status       lnrs.lnrs_anon_review_status_enum NOT NULL DEFAULT 'pending',
    created_batch_id    UUID         NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
    created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX lnrs_anon_ix_report_review ON lnrs.lnrs_anon_report_text (review_status);

-- ---------- 6. lnrs_anon_exam_finding ----------

CREATE TABLE lnrs.lnrs_anon_exam_finding (
    finding_id          BIGSERIAL    PRIMARY KEY,
    anon_exam_id        VARCHAR(40)  NOT NULL REFERENCES lnrs.lnrs_anon_exam(anon_exam_id) ON DELETE CASCADE,
    finding_type        VARCHAR(32)  NOT NULL,
    value_numeric       NUMERIC(10,3),
    value_text          VARCHAR(255),
    laterality          VARCHAR(10)  NOT NULL DEFAULT 'N/A',
    raw_value_hash      CHAR(64)     NOT NULL,
    created_batch_id    UUID         NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
    created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT lnrs_anon_uq_finding UNIQUE (anon_exam_id, finding_type, raw_value_hash),
    CONSTRAINT lnrs_anon_ck_finding_value CHECK (value_numeric IS NOT NULL OR value_text IS NOT NULL),
    -- 枚举权威移交 med_laterality 字典（ADR-0008）：CHECK 替代 ENUM
    CONSTRAINT lnrs_anon_ck_finding_laterality CHECK (laterality IN ('L','R','Bilateral','N/A'))
);

CREATE INDEX lnrs_anon_ix_finding_exam    ON lnrs.lnrs_anon_exam_finding (anon_exam_id);
CREATE INDEX lnrs_anon_ix_finding_typeval ON lnrs.lnrs_anon_exam_finding (finding_type, value_numeric);

-- ---------- 7. lnrs_anon_dicom_series ----------

CREATE TABLE lnrs.lnrs_anon_dicom_series (
    series_id           BIGSERIAL    PRIMARY KEY,
    anon_exam_id        VARCHAR(40)  NOT NULL REFERENCES lnrs.lnrs_anon_exam(anon_exam_id) ON DELETE CASCADE,
    dicom_series_uid    VARCHAR(64)  NOT NULL UNIQUE,
    dicom_study_uid     VARCHAR(64)  NOT NULL,
    modality            VARCHAR(8)   NOT NULL,
    body_part           VARCHAR(32),
    instance_count      INT          NOT NULL CHECK (instance_count > 0),
    file_root           TEXT         NOT NULL,
    file_count_actual   INT,
    byte_size           BIGINT,
    series_no           INT          NOT NULL DEFAULT 1,
    created_batch_id    UUID         NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
    created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX lnrs_anon_ix_series_exam      ON lnrs.lnrs_anon_dicom_series (anon_exam_id);
CREATE INDEX lnrs_anon_ix_series_study_uid ON lnrs.lnrs_anon_dicom_series (dicom_study_uid);
CREATE INDEX lnrs_anon_ix_series_modality  ON lnrs.lnrs_anon_dicom_series (modality, body_part);

-- ---------- 8. lnrs_anon_dicom_instance ----------

CREATE TABLE lnrs.lnrs_anon_dicom_instance (
    series_id           BIGINT       NOT NULL REFERENCES lnrs.lnrs_anon_dicom_series(series_id) ON DELETE CASCADE,
    sop_instance_uid    VARCHAR(64)  NOT NULL,
    instance_no         INT          NOT NULL CHECK (instance_no > 0),
    byte_offset         BIGINT       NOT NULL DEFAULT 0,
    PRIMARY KEY (series_id, instance_no),
    CONSTRAINT lnrs_anon_uq_instance_sop UNIQUE (sop_instance_uid)
);

-- ---------- 9. lnrs_anon_dicom_uid_map (审计隔离库) ----------

CREATE TABLE lnrs.lnrs_anon_dicom_uid_map (
    batch_id            UUID         NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id),
    anon_exam_id        VARCHAR(40)  NOT NULL REFERENCES lnrs.lnrs_anon_exam(anon_exam_id),
    kind                lnrs.lnrs_anon_uid_kind_enum NOT NULL,
    old_uid             VARCHAR(64)  NOT NULL,
    new_uid             VARCHAR(64)  NOT NULL,
    created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (batch_id, kind, old_uid)
);

CREATE INDEX lnrs_anon_ix_uidmap_exam ON lnrs.lnrs_anon_dicom_uid_map (anon_exam_id);
CREATE INDEX lnrs_anon_ix_uidmap_new  ON lnrs.lnrs_anon_dicom_uid_map (new_uid);

-- ---------- 10. lnrs_anon_phi_audit ----------

CREATE TABLE lnrs.lnrs_anon_phi_audit (
    audit_id            BIGSERIAL    PRIMARY KEY,
    batch_id            UUID         NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id),
    source_table        VARCHAR(64)  NOT NULL,
    source_field        VARCHAR(64)  NOT NULL,
    source_hash         CHAR(64)     NOT NULL,
    strategy            lnrs.lnrs_anon_phi_strategy_enum NOT NULL,
    confidence          NUMERIC(4,3) NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX lnrs_anon_ix_phi_audit_batch_field ON lnrs.lnrs_anon_phi_audit (batch_id, source_table, source_field);
CREATE INDEX lnrs_anon_ix_phi_audit_strategy     ON lnrs.lnrs_anon_phi_audit (strategy, created_at);

-- ---------- 10b. lnrs_anon_visit (就诊桥, 医疗宽表直入扩展) ----------
-- 从 surgery_record.visit_id 反推生成; FK 指向 patient_id (与全表体系一致)

CREATE TABLE lnrs.lnrs_anon_visit (
    anon_visit_id      VARCHAR(40)  PRIMARY KEY,            -- ANON_VISIT_ + HMAC[:12]
    patient_id         VARCHAR(16)  NOT NULL REFERENCES lnrs.lnrs_anon_patient(patient_id) ON DELETE CASCADE,
    center_code        VARCHAR(32)  NOT NULL,
    visit_ordinal      VARCHAR(64)  NOT NULL,                -- 原始 visit_id (如 153623_1), 保留溯源
    source_visit_hash  CHAR(64)     NOT NULL,                -- (center, visit_id) 裸 SHA256, 幂等用
    created_batch_id   UUID         NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
    last_seen_batch_id UUID         NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
    created_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT lnrs_anon_uq_visit_source  UNIQUE (center_code, source_visit_hash),
    CONSTRAINT lnrs_anon_uq_visit_patient UNIQUE (patient_id, visit_ordinal)
);

CREATE INDEX lnrs_anon_ix_visit_patient    ON lnrs.lnrs_anon_visit (patient_id);
CREATE INDEX lnrs_anon_ix_visit_center     ON lnrs.lnrs_anon_visit (center_code);

-- 给 lnrs_anon_exam.anon_visit_id 补 FK (visit 表此时已存在)
ALTER TABLE lnrs.lnrs_anon_exam
    ADD CONSTRAINT lnrs_anon_fk_exam_visit
    FOREIGN KEY (anon_visit_id) REFERENCES lnrs.lnrs_anon_visit(anon_visit_id) ON DELETE SET NULL;

-- ---------- 10c. lnrs_anon_surgery (visit 级手术记录) ----------

CREATE TABLE lnrs.lnrs_anon_surgery (
    surgery_id          BIGSERIAL    PRIMARY KEY,
    anon_visit_id       VARCHAR(40)  NOT NULL REFERENCES lnrs.lnrs_anon_visit(anon_visit_id) ON DELETE CASCADE,
    patient_id          VARCHAR(16)  NOT NULL REFERENCES lnrs.lnrs_anon_patient(patient_id) ON DELETE CASCADE,
    center_code         VARCHAR(32)  NOT NULL,
    surgery_date        DATE,
    procedure_name      VARCHAR(200) NOT NULL,
    resection_scope     VARCHAR(100),
    surgical_approach   VARCHAR(50),
    procedure_detail    JSONB,                                -- icd9cm3_code/淋巴结清扫/时长/出血量...
    source_surgery_hash CHAR(64)     NOT NULL,                -- (center, visit_id, procedure_name) 裸 SHA256, 幂等用
    created_batch_id    UUID         NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
    created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT lnrs_anon_uq_surgery UNIQUE (anon_visit_id, source_surgery_hash)
);

CREATE INDEX lnrs_anon_ix_surgery_visit   ON lnrs.lnrs_anon_surgery (anon_visit_id);
CREATE INDEX lnrs_anon_ix_surgery_patient ON lnrs.lnrs_anon_surgery (patient_id);
CREATE INDEX lnrs_anon_ix_surgery_date    ON lnrs.lnrs_anon_surgery (surgery_date);

-- ---------- 10d. lnrs_anon_exam_detail (exam 级 JSONB 深结构) ----------
-- 承载病理/基因/IHC/结节的结构化嵌套数据 (detail_type 区分)
-- 与扁平的 lnrs_anon_exam_finding 互补: finding 装 EAV 标量, detail 装嵌套 JSONB
-- Rev 2026-07-24: PK 改为 (anon_exam_id, detail_type, detail_ordinal) 实现 1:N
--   - 同一 exam 可有多个同类型 detail（如 CT 下 n1/n2/n3/n4 多结节）
--   - 不同类型 detail（pathology/ihc 共享 specimen_id）各自独立成行，不互相覆盖
--   - detail_ordinal 默认 1：无 ordinal 的 detail（pathology/genetic/ihc）单行
CREATE TABLE lnrs.lnrs_anon_exam_detail (
    anon_exam_id        VARCHAR(40)  NOT NULL REFERENCES lnrs.lnrs_anon_exam(anon_exam_id) ON DELETE CASCADE,
    detail_type         VARCHAR(32)  NOT NULL,               -- nodule_imaging/pathology/genetic/ihc
    detail_ordinal      SMALLINT     NOT NULL DEFAULT 1,      -- 同类型多实例序号（如多结节 n1/n2/n3/n4）
    detail_json         JSONB        NOT NULL,
    created_batch_id    UUID         NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
    created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT lnrs_anon_pk_exam_detail PRIMARY KEY (anon_exam_id, detail_type, detail_ordinal)
);

CREATE INDEX lnrs_anon_ix_exam_detail_type ON lnrs.lnrs_anon_exam_detail (detail_type);
CREATE INDEX lnrs_anon_ix_exam_detail_gin  ON lnrs.lnrs_anon_exam_detail USING gin (detail_json);

-- ---------- 11. updated_at 触发器 ----------

CREATE OR REPLACE FUNCTION lnrs.lnrs_anon_trg_set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER lnrs_anon_tg_patient_updated BEFORE UPDATE ON lnrs.lnrs_anon_patient       FOR EACH ROW EXECUTE FUNCTION lnrs.lnrs_anon_trg_set_updated_at();
CREATE TRIGGER lnrs_anon_tg_exam_updated    BEFORE UPDATE ON lnrs.lnrs_anon_exam          FOR EACH ROW EXECUTE FUNCTION lnrs.lnrs_anon_trg_set_updated_at();
CREATE TRIGGER lnrs_anon_tg_report_updated  BEFORE UPDATE ON lnrs.lnrs_anon_report_text   FOR EACH ROW EXECUTE FUNCTION lnrs.lnrs_anon_trg_set_updated_at();
CREATE TRIGGER lnrs_anon_tg_series_updated  BEFORE UPDATE ON lnrs.lnrs_anon_dicom_series  FOR EACH ROW EXECUTE FUNCTION lnrs.lnrs_anon_trg_set_updated_at();
CREATE TRIGGER lnrs_anon_tg_visit_updated   BEFORE UPDATE ON lnrs.lnrs_anon_visit         FOR EACH ROW EXECUTE FUNCTION lnrs.lnrs_anon_trg_set_updated_at();

-- ---------- 12. 跨模态视图 ----------

CREATE OR REPLACE VIEW lnrs.lnrs_anon_v_exam_full AS
SELECT
    e.anon_exam_id,
    p.patient_id,
    p.anon_id,
    e.center_code,
    e.exam_type,
    e.exam_date,
    rt.body_clean,
    rt.review_status,
    COUNT(DISTINCT f.finding_id) AS finding_count,
    COUNT(DISTINCT s.series_id)  AS series_count
FROM lnrs.lnrs_anon_exam e
JOIN lnrs.lnrs_anon_patient       p  ON p.patient_id   = e.patient_id
LEFT JOIN lnrs.lnrs_anon_report_text  rt ON rt.anon_exam_id = e.anon_exam_id
LEFT JOIN lnrs.lnrs_anon_exam_finding f  ON f.anon_exam_id  = e.anon_exam_id
LEFT JOIN lnrs.lnrs_anon_dicom_series s  ON s.anon_exam_id  = e.anon_exam_id
GROUP BY e.anon_exam_id, p.patient_id, p.anon_id, rt.body_clean, rt.review_status;

COMMIT;