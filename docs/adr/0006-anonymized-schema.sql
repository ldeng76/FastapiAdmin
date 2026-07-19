-- =====================================================================
-- 脱敏后病例数据 schema (Anonymized Data Schema)
-- 依据: docs/adr/0006-anonymized-data-schema.md
-- 兼容: MySQL 8.0+ / PostgreSQL 14+ / SQLite 3.35+
-- 注意事项:
--   * 所有"原始 ID/姓名"不落库
--   * ANON_ID 与 ANON_EXAM_ID 的生成见 ADR-0001
--   * 跨模态关联唯一桥梁: anon_exam_id
--   * anon_dicom_uid_map 仅供审计物理隔离库使用
-- =====================================================================

-- ---------- 0. 枚举与扩展 (PostgreSQL 用原生 ENUM，MySQL 用 VARCHAR+CHECK) ----------

-- 注: 不同 DB 用不同语法。这里给出 PostgreSQL 友好版本，
-- MySQL 部署时请用 VARCHAR(16) + CHECK 约束替换。

CREATE TYPE sex_enum AS ENUM ('M','F','U');
CREATE TYPE ingest_status_enum AS ENUM ('running','success','failed','partial');
CREATE TYPE source_kind_enum AS ENUM ('csv_report','dicom_dir','dicom_zip');
CREATE TYPE review_status_enum AS ENUM ('pending','reviewed','flagged');
CREATE TYPE laterality_enum AS ENUM ('L','R','Bilateral','N/A');
CREATE TYPE uid_kind_enum AS ENUM ('study','series','sop');
CREATE TYPE clean_method_enum AS ENUM ('regex_only','regex+llm','manual_review');
CREATE TYPE phi_strategy_enum AS ENUM ('hmac','clear','partial_keep','llm_replace','manual_review');

-- ---------- 1. ingest_batch ----------

CREATE TABLE lnrs_anon_ingest_batch (
    batch_id           UUID PRIMARY KEY,
    center_code        VARCHAR(32)  NOT NULL,
    source_kind        source_kind_enum NOT NULL,
    source_locator     TEXT         NOT NULL,
    source_sha256      CHAR(64),
    secret_version     VARCHAR(32)  NOT NULL,
    key_fingerprint    CHAR(16)     NOT NULL,
    schema_hash        CHAR(64)     NOT NULL,
    row_counts         JSONB        NOT NULL DEFAULT '{}'::jsonb,
    started_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at        TIMESTAMP,
    status             ingest_status_enum NOT NULL DEFAULT 'running',
    error              TEXT,
    CONSTRAINT uq_batch_center_secret UNIQUE (center_code, secret_version, key_fingerprint, schema_hash, started_at)
);

CREATE INDEX lnrs_anon_ix_batch_status       ON ingest_batch (status);
CREATE INDEX lnrs_anon_ix_batch_secret_ver   ON ingest_batch (secret_version, key_fingerprint, schema_hash);

-- ---------- 2. anon_patient ----------

CREATE TABLE lnrs_anon_patient (
    anon_id            VARCHAR(32)  PRIMARY KEY,
    center_code        VARCHAR(32)  NOT NULL,
    birth_year         SMALLINT     CHECK (birth_year BETWEEN 1900 AND 2100),
    sex                sex_enum     NOT NULL DEFAULT 'U',
    created_batch_id   UUID         NOT NULL REFERENCES lnrs_anon_ingest_batch(batch_id),
    last_seen_batch_id UUID         NOT NULL REFERENCES lnrs_anon_ingest_batch(batch_id),
    created_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_patient_center UNIQUE (center_code, anon_id)
);

CREATE INDEX lnrs_anon_ix_patient_center ON anon_patient (center_code, center_code);  -- 冗余索引给跨中心统计
CREATE INDEX lnrs_anon_ix_patient_birth  ON anon_patient (birth_year);

-- ---------- 3. anon_exam  (跨模态桥梁) ----------

CREATE TABLE lnrs_anon_exam (
    anon_exam_id       VARCHAR(40)  PRIMARY KEY,  -- 'ANON_EXAM_' + 12hex
    anon_id            VARCHAR(32)  NOT NULL REFERENCES lnrs_anon_patient(anon_id) ON DELETE CASCADE,
    center_code        VARCHAR(32)  NOT NULL,
    exam_type          VARCHAR(32),
    exam_date          DATE         NOT NULL,
    source_exam_hash   CHAR(64)     NOT NULL,
    created_batch_id   UUID         NOT NULL REFERENCES lnrs_anon_ingest_batch(batch_id),
    last_seen_batch_id UUID         NOT NULL REFERENCES lnrs_anon_ingest_batch(batch_id),
    created_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_exam_source UNIQUE (center_code, source_exam_hash)
);

CREATE INDEX lnrs_anon_ix_exam_patient       ON anon_exam (anon_id);
CREATE INDEX lnrs_anon_ix_exam_center_date  ON anon_exam (center_code, exam_date);
CREATE INDEX lnrs_anon_ix_exam_type_date     ON anon_exam (exam_type, exam_date);

-- ---------- 4. anon_report_text ----------

CREATE TABLE lnrs_anon_report_text (
    anon_exam_id        VARCHAR(40)  PRIMARY KEY REFERENCES lnrs_anon_exam(anon_exam_id) ON DELETE CASCADE,
    body_clean          TEXT         NOT NULL,
    pii_replaced_count  INT          NOT NULL DEFAULT 0 CHECK (pii_replaced_count >= 0),
    clean_method        clean_method_enum NOT NULL,
    llm_model           VARCHAR(64),
    review_status       review_status_enum NOT NULL DEFAULT 'pending',
    created_batch_id    UUID         NOT NULL REFERENCES lnrs_anon_ingest_batch(batch_id),
    created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX lnrs_anon_ix_report_review ON anon_report_text (review_status);

-- ---------- 5. anon_exam_finding ----------

CREATE TABLE lnrs_anon_exam_finding (
    finding_id          BIGSERIAL    PRIMARY KEY,
    anon_exam_id        VARCHAR(40)  NOT NULL REFERENCES lnrs_anon_exam(anon_exam_id) ON DELETE CASCADE,
    finding_type        VARCHAR(32)  NOT NULL,
    value_numeric       NUMERIC(10,3),
    value_text          VARCHAR(255),
    laterality          laterality_enum NOT NULL DEFAULT 'N/A',
    raw_value_hash      CHAR(64)     NOT NULL,
    created_batch_id    UUID         NOT NULL REFERENCES lnrs_anon_ingest_batch(batch_id),
    created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_finding UNIQUE (anon_exam_id, finding_type, raw_value_hash),
    CONSTRAINT ck_finding_value CHECK (value_numeric IS NOT NULL OR value_text IS NOT NULL)
);

CREATE INDEX lnrs_anon_ix_finding_exam    ON anon_exam_finding (anon_exam_id);
CREATE INDEX lnrs_anon_ix_finding_typeval ON anon_exam_finding (finding_type, value_numeric);

-- ---------- 6. dicom_series ----------

CREATE TABLE lnrs_anon_dicom_series (
    series_id           BIGSERIAL    PRIMARY KEY,
    anon_exam_id        VARCHAR(40)  NOT NULL REFERENCES lnrs_anon_exam(anon_exam_id) ON DELETE CASCADE,
    dicom_series_uid    VARCHAR(64)  NOT NULL UNIQUE,
    dicom_study_uid     VARCHAR(64)  NOT NULL,
    modality            VARCHAR(8)   NOT NULL,
    body_part           VARCHAR(32),
    instance_count      INT          NOT NULL CHECK (instance_count > 0),
    file_root           TEXT         NOT NULL,
    file_count_actual   INT,
    byte_size           BIGINT,
    series_no           INT          NOT NULL DEFAULT 1,
    created_batch_id    UUID         NOT NULL REFERENCES lnrs_anon_ingest_batch(batch_id),
    created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX lnrs_anon_ix_series_exam      ON dicom_series (anon_exam_id);
CREATE INDEX lnrs_anon_ix_series_study_uid ON dicom_series (dicom_study_uid);
CREATE INDEX lnrs_anon_ix_series_modality  ON dicom_series (modality, body_part);

-- ---------- 7. dicom_instance (按需建) ----------

CREATE TABLE lnrs_anon_dicom_instance (
    series_id           BIGINT       NOT NULL REFERENCES lnrs_anon_dicom_series(series_id) ON DELETE CASCADE,
    sop_instance_uid    VARCHAR(64)  NOT NULL,
    instance_no         INT          NOT NULL CHECK (instance_no > 0),
    byte_offset         BIGINT       NOT NULL DEFAULT 0,
    PRIMARY KEY (series_id, instance_no),
    CONSTRAINT uq_instance_sop UNIQUE (sop_instance_uid)
);

-- ---------- 8. anon_dicom_uid_map (审计隔离库) ----------
-- ⚠️ 此表不进生产库，仅供审计归档使用

CREATE TABLE lnrs_anon_dicom_uid_map (
    batch_id            UUID         NOT NULL REFERENCES lnrs_anon_ingest_batch(batch_id),
    anon_exam_id        VARCHAR(40)  NOT NULL REFERENCES lnrs_anon_exam(anon_exam_id),
    kind                uid_kind_enum NOT NULL,
    old_uid             VARCHAR(64)  NOT NULL,
    new_uid             VARCHAR(64)  NOT NULL,
    created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (batch_id, kind, old_uid)
);

CREATE INDEX lnrs_anon_ix_uidmap_exam ON anon_dicom_uid_map (anon_exam_id);
CREATE INDEX lnrs_anon_ix_uidmap_new  ON anon_dicom_uid_map (new_uid);

-- ---------- 9. phi_audit ----------

CREATE TABLE lnrs_anon_phi_audit (
    audit_id            BIGSERIAL    PRIMARY KEY,
    batch_id            UUID         NOT NULL REFERENCES lnrs_anon_ingest_batch(batch_id),
    source_table        VARCHAR(64)  NOT NULL,
    source_field        VARCHAR(64)  NOT NULL,
    source_hash         CHAR(64)     NOT NULL,
    strategy            phi_strategy_enum NOT NULL,
    confidence          NUMERIC(4,3) NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX lnrs_anon_ix_phi_audit_batch_field ON phi_audit (batch_id, source_table, source_field);
CREATE INDEX lnrs_anon_ix_phi_audit_strategy     ON phi_audit (strategy, created_at);

-- ---------- 视图: 跨模态一站式 ----------

CREATE OR REPLACE VIEW v_exam_full AS
SELECT
    e.anon_exam_id,
    e.anon_id,
    e.center_code,
    e.exam_type,
    e.exam_date,
    rt.body_clean,
    rt.review_status,
    COUNT(DISTINCT f.finding_id)      AS finding_count,
    COUNT(DISTINCT s.series_id)       AS series_count
FROM lnrs_anon_exam e
LEFT JOIN lnrs_anon_report_text  rt ON rt.anon_exam_id = e.anon_exam_id
LEFT JOIN lnrs_anon_exam_finding f  ON f.anon_exam_id  = e.anon_exam_id
LEFT JOIN lnrs_anon_dicom_series      s  ON s.anon_exam_id  = e.anon_exam_id
GROUP BY e.anon_exam_id, rt.body_clean, rt.review_status;

-- ---------- 触发器: updated_at 自动维护 ----------

CREATE OR REPLACE FUNCTION lnrs_anon_trg_set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER lnrs_anon_tg_patient_updated BEFORE UPDATE ON anon_patient      FOR EACH ROW EXECUTE FUNCTION lnrs_anon_trg_set_updated_at();
CREATE TRIGGER lnrs_anon_tg_exam_updated    BEFORE UPDATE ON anon_exam         FOR EACH ROW EXECUTE FUNCTION lnrs_anon_trg_set_updated_at();
CREATE TRIGGER lnrs_anon_tg_report_updated  BEFORE UPDATE ON anon_report_text  FOR EACH ROW EXECUTE FUNCTION lnrs_anon_trg_set_updated_at();
CREATE TRIGGER lnrs_anon_tg_series_updated  BEFORE UPDATE ON dicom_series      FOR EACH ROW EXECUTE FUNCTION lnrs_anon_trg_set_updated_at();

-- ---------- 完成 ----------
-- 跨模态联结示例:
--   SELECT s.dicom_series_uid, rt.body_clean
--   FROM   dicom_series s JOIN lnrs_anon_report_text rt USING (anon_exam_id)
--   WHERE  s.anon_exam_id = 'ANON_EXAM_xxxxxxxxxxxx';
