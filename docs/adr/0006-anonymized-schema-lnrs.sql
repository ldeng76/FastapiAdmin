-- =====================================================================
-- 脱敏后病例数据 schema (执行版)
-- 依据: docs/adr/0006-anonymized-data-schema.md
-- 目标: PostgreSQL 14+, schema = lnrs (与 backend app 配置一致)
-- 与 docs/adr/0006-anonymized-schema.sql 的差异:
--   1. 所有对象落到 lnrs schema, 加 lnrs. 前缀
--   2. 设置 search_path 避免每次写前缀
--   3. 加 DROP IF EXISTS 幂等保护 (失败时回滚到无变更)
-- =====================================================================

BEGIN;

-- 切换目标 schema
SET LOCAL search_path = lnrs, public;
-- 注意: 索引/触发器名只属于当前 schema, 不能带 lnrs. 前缀

-- ---------- 0. 幂等清理 (仅首次有意义) ----------

DROP VIEW IF EXISTS lnrs.lnrs_anon_v_exam_full;
DROP TABLE IF EXISTS lnrs.lnrs_anon_phi_audit               CASCADE;
DROP TABLE IF EXISTS lnrs.lnrs_anon_dicom_uid_map      CASCADE;
DROP TABLE IF EXISTS lnrs.lnrs_anon_dicom_instance          CASCADE;
DROP TABLE IF EXISTS lnrs.lnrs_anon_dicom_series            CASCADE;
DROP TABLE IF EXISTS lnrs.lnrs_anon_exam_finding       CASCADE;
DROP TABLE IF EXISTS lnrs.lnrs_anon_report_text        CASCADE;
DROP TABLE IF EXISTS lnrs.lnrs_anon_exam               CASCADE;
DROP TABLE IF EXISTS lnrs.lnrs_anon_patient            CASCADE;
DROP TABLE IF EXISTS lnrs.lnrs_anon_ingest_batch            CASCADE;

DROP TYPE IF EXISTS lnrs.lnrs_anon_phi_strategy_enum CASCADE;
DROP TYPE IF EXISTS lnrs.lnrs_anon_clean_method_enum CASCADE;
DROP TYPE IF EXISTS lnrs.lnrs_anon_uid_kind_enum     CASCADE;
DROP TYPE IF EXISTS lnrs.lnrs_anon_laterality_enum   CASCADE;
DROP TYPE IF EXISTS lnrs.lnrs_anon_review_status_enum CASCADE;
DROP TYPE IF EXISTS lnrs.lnrs_anon_source_kind_enum  CASCADE;
DROP TYPE IF EXISTS lnrs.lnrs_anon_ingest_status_enum CASCADE;
DROP TYPE IF EXISTS lnrs.lnrs_anon_sex_enum           CASCADE;

DROP FUNCTION IF EXISTS lnrs.lnrs_anon_trg_set_updated_at() CASCADE;

-- ---------- 1. 枚举 ----------

CREATE TYPE lnrs.lnrs_anon_sex_enum            AS ENUM ('M','F','U');
CREATE TYPE lnrs.lnrs_anon_ingest_status_enum  AS ENUM ('running','success','failed','partial');
CREATE TYPE lnrs.lnrs_anon_source_kind_enum    AS ENUM ('csv_report','dicom_dir','dicom_zip');
CREATE TYPE lnrs.lnrs_anon_review_status_enum  AS ENUM ('pending','reviewed','flagged');
CREATE TYPE lnrs.lnrs_anon_laterality_enum     AS ENUM ('L','R','Bilateral','N/A');
CREATE TYPE lnrs.lnrs_anon_uid_kind_enum       AS ENUM ('study','series','sop');
CREATE TYPE lnrs.lnrs_anon_clean_method_enum   AS ENUM ('regex_only','regex+llm','manual_review');
CREATE TYPE lnrs.lnrs_anon_phi_strategy_enum   AS ENUM ('hmac','clear','partial_keep','llm_replace','manual_review');

-- ---------- 2. ingest_batch ----------

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
    CONSTRAINT uq_batch_center_secret UNIQUE (center_code, secret_version, key_fingerprint, schema_hash, started_at)
);

CREATE INDEX lnrs_anon_ix_batch_status ON lnrs.lnrs_anon_ingest_batch (status);
CREATE INDEX lnrs_anon_ix_batch_secret_ver ON lnrs.lnrs_anon_ingest_batch (secret_version, key_fingerprint, schema_hash);

-- ---------- 3. anon_patient ----------

CREATE TABLE lnrs.lnrs_anon_patient (
    anon_id            VARCHAR(32)  PRIMARY KEY,
    center_code        VARCHAR(32)  NOT NULL,
    birth_year         SMALLINT     CHECK (birth_year BETWEEN 1900 AND 2100),
    sex                lnrs.lnrs_anon_sex_enum NOT NULL DEFAULT 'U',
    created_batch_id   UUID         NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
    last_seen_batch_id UUID         NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
    created_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_patient_center UNIQUE (center_code, anon_id)
);

CREATE INDEX lnrs_anon_ix_patient_center ON lnrs.lnrs_anon_patient (center_code);
CREATE INDEX lnrs_anon_ix_patient_birth ON lnrs.lnrs_anon_patient (birth_year);

-- ---------- 4. anon_exam ----------

CREATE TABLE lnrs.lnrs_anon_exam (
    anon_exam_id       VARCHAR(40)  PRIMARY KEY,
    anon_id            VARCHAR(32)  NOT NULL REFERENCES lnrs.lnrs_anon_patient(anon_id) ON DELETE CASCADE,
    center_code        VARCHAR(32)  NOT NULL,
    exam_type          VARCHAR(32),
    exam_date          DATE         NOT NULL,
    source_exam_hash   CHAR(64)     NOT NULL,
    created_batch_id   UUID         NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
    last_seen_batch_id UUID         NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
    created_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_exam_source UNIQUE (center_code, source_exam_hash)
);

CREATE INDEX lnrs_anon_ix_exam_patient ON lnrs.lnrs_anon_exam (anon_id);
CREATE INDEX lnrs_anon_ix_exam_center_date ON lnrs.lnrs_anon_exam (center_code, exam_date);
CREATE INDEX lnrs_anon_ix_exam_type_date ON lnrs.lnrs_anon_exam (exam_type, exam_date);

-- ---------- 5. anon_report_text ----------

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

-- ---------- 6. anon_exam_finding ----------

CREATE TABLE lnrs.lnrs_anon_exam_finding (
    finding_id          BIGSERIAL    PRIMARY KEY,
    anon_exam_id        VARCHAR(40)  NOT NULL REFERENCES lnrs.lnrs_anon_exam(anon_exam_id) ON DELETE CASCADE,
    finding_type        VARCHAR(32)  NOT NULL,
    value_numeric       NUMERIC(10,3),
    value_text          VARCHAR(255),
    laterality          lnrs.lnrs_anon_laterality_enum NOT NULL DEFAULT 'N/A',
    raw_value_hash      CHAR(64)     NOT NULL,
    created_batch_id    UUID         NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
    created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_finding UNIQUE (anon_exam_id, finding_type, raw_value_hash),
    CONSTRAINT ck_finding_value CHECK (value_numeric IS NOT NULL OR value_text IS NOT NULL)
);

CREATE INDEX lnrs_anon_ix_finding_exam ON lnrs.lnrs_anon_exam_finding (anon_exam_id);
CREATE INDEX lnrs_anon_ix_finding_typeval ON lnrs.lnrs_anon_exam_finding (finding_type, value_numeric);

-- ---------- 7. dicom_series ----------

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

CREATE INDEX lnrs_anon_ix_series_exam ON lnrs.lnrs_anon_dicom_series (anon_exam_id);
CREATE INDEX lnrs_anon_ix_series_study_uid ON lnrs.lnrs_anon_dicom_series (dicom_study_uid);
CREATE INDEX lnrs_anon_ix_series_modality ON lnrs.lnrs_anon_dicom_series (modality, body_part);

-- ---------- 8. dicom_instance ----------

CREATE TABLE lnrs.lnrs_anon_dicom_instance (
    series_id           BIGINT       NOT NULL REFERENCES lnrs.lnrs_anon_dicom_series(series_id) ON DELETE CASCADE,
    sop_instance_uid    VARCHAR(64)  NOT NULL,
    instance_no         INT          NOT NULL CHECK (instance_no > 0),
    byte_offset         BIGINT       NOT NULL DEFAULT 0,
    PRIMARY KEY (series_id, instance_no),
    CONSTRAINT uq_instance_sop UNIQUE (sop_instance_uid)
);

-- ---------- 9. anon_dicom_uid_map (仅审计隔离库) ----------

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
CREATE INDEX lnrs_anon_ix_uidmap_new ON lnrs.lnrs_anon_dicom_uid_map (new_uid);

-- ---------- 10. phi_audit ----------

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
CREATE INDEX lnrs_anon_ix_phi_audit_strategy ON lnrs.lnrs_anon_phi_audit (strategy, created_at);

-- ---------- 11. updated_at 触发器 ----------

CREATE OR REPLACE FUNCTION lnrs.lnrs_anon_trg_set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER lnrs_anon_tg_patient_updated BEFORE UPDATE ON lnrs.lnrs_anon_patient     FOR EACH ROW EXECUTE FUNCTION lnrs.lnrs_anon_trg_set_updated_at();
CREATE TRIGGER lnrs_anon_tg_exam_updated    BEFORE UPDATE ON lnrs.lnrs_anon_exam        FOR EACH ROW EXECUTE FUNCTION lnrs.lnrs_anon_trg_set_updated_at();
CREATE TRIGGER lnrs_anon_tg_report_updated  BEFORE UPDATE ON lnrs.lnrs_anon_report_text FOR EACH ROW EXECUTE FUNCTION lnrs.lnrs_anon_trg_set_updated_at();
CREATE TRIGGER lnrs_anon_tg_series_updated  BEFORE UPDATE ON lnrs.lnrs_anon_dicom_series     FOR EACH ROW EXECUTE FUNCTION lnrs.lnrs_anon_trg_set_updated_at();

-- ---------- 12. lnrs_anon_v_exam_full 跨模态视图 ----------

CREATE OR REPLACE VIEW lnrs.lnrs_anon_v_exam_full AS
SELECT
    e.anon_exam_id,
    e.anon_id,
    e.center_code,
    e.exam_type,
    e.exam_date,
    rt.body_clean,
    rt.review_status,
    COUNT(DISTINCT f.finding_id) AS finding_count,
    COUNT(DISTINCT s.series_id)  AS series_count
FROM lnrs.lnrs_anon_exam e
LEFT JOIN lnrs.lnrs_anon_report_text  rt ON rt.anon_exam_id = e.anon_exam_id
LEFT JOIN lnrs.lnrs_anon_exam_finding f  ON f.anon_exam_id  = e.anon_exam_id
LEFT JOIN lnrs.lnrs_anon_dicom_series      s  ON s.anon_exam_id  = e.anon_exam_id
GROUP BY e.anon_exam_id, rt.body_clean, rt.review_status;

COMMIT;
