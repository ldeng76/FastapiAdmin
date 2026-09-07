-- =====================================================================
-- lnrs_anon_imaging_study — 影像研究桥接表（PID ↔ 影像绝对路径）
-- 依据: docs/sour/ct_image_patient_map.csv（盘 1 + 盘 2 珠江数据）
-- 目标: PostgreSQL 14+, schema = lnrs
--
-- 设计要点:
--   * patient_id (FK 到 lnrs_anon_patient.patient_id) — 仅存脱敏后 PT_xxx
--   * dicom_study_uid VARCHAR(64) — DICOM StudyInstanceUID（明文，磁盘索引可反查）
--   * image_path TEXT — 磁盘上 Study 根目录的绝对路径（不含 SeriesUID 拆解）
--   * modality VARCHAR(16) DEFAULT 'CT' — 当前先支撑 CT，未来扩 pathology/genetic
--   * sop_count INT — 该 Study 下影像切片数（仅作展示/统计，不入 query plan）
--   * source VARCHAR(32) — 数据来源盘标识（disk1_zhujiang/disk2_zhujiang_supplement/...）
--   * center_code VARCHAR(32) NOT NULL — 多中心支持；当前仅 zhujiang
--   * 联合主键 (patient_id, dicom_study_uid, source) — 同一 StudyUID 在盘 1 + 盘 2
--     都会出现（handoff 验证：120 个 study 双源），不强制唯一允许重复；
--     image_path 天然不同
--   * exam_type 允许扩展：当前仅 'CT'，未来 pathology/genetic 共用此表
--
-- ETL-2 回写：anon_etl_engine 在 _import_exam_text_table 写 CT 完毕后，
--             从 parquet 中如能拿到 dicom_study_uid 也补一行到本表
--             （详见 anon_etl_engine.py:911 后的扩展点）
--
-- 触发器：lnrs_anon_tg_imaging_study_updated
-- =====================================================================

BEGIN;

SET LOCAL search_path = lnrs, public;

-- ---------- 0. 幂等清理（重建场景） ----------

DROP TABLE IF EXISTS lnrs.lnrs_anon_imaging_study CASCADE;
DROP TRIGGER IF EXISTS lnrs_anon_tg_imaging_study_updated ON lnrs.lnrs_anon_imaging_study;

-- ---------- 1. lnrs_anon_imaging_study ----------

CREATE TABLE lnrs.lnrs_anon_imaging_study (
    study_key          BIGSERIAL    PRIMARY KEY,
    patient_id         VARCHAR(16)  NOT NULL REFERENCES lnrs.lnrs_anon_patient(patient_id) ON DELETE CASCADE,
    center_code        VARCHAR(32)  NOT NULL,
    dicom_study_uid    VARCHAR(64)  NOT NULL,
    modality           VARCHAR(16)  NOT NULL DEFAULT 'CT',
    image_path         TEXT         NOT NULL,
    sop_count          INT          NOT NULL CHECK (sop_count >= 0),
    source             VARCHAR(64)  NOT NULL DEFAULT 'disk_index',
    -- 冗余 FK：可空；只有 ETL-2 写出 anon_exam_id 时回填（脱敏 exam 体系关联）
    anon_exam_id       VARCHAR(40)  REFERENCES lnrs.lnrs_anon_exam(anon_exam_id) ON DELETE SET NULL,
    created_batch_id   UUID         REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE SET NULL,
    created_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- 同一 PID + StudyUID + source 唯一（同源不会出现两次）；
    -- 跨源允许重复（盘 1 + 盘 2 同 StudyUID 不同 image_path）
    CONSTRAINT lnrs_anon_uq_imaging_study UNIQUE (patient_id, dicom_study_uid, source),
    CONSTRAINT lnrs_anon_ck_imaging_center CHECK (center_code ~ '^[a-z][a-z0-9_]*$'),
    CONSTRAINT lnrs_anon_ck_imaging_modality CHECK (modality IN ('CT','MR','XR','US','PET','NM','Pathology','Genetic','Other'))
);

-- 业务查询索引
CREATE INDEX lnrs_anon_ix_imaging_patient     ON lnrs.lnrs_anon_imaging_study (patient_id);
CREATE INDEX lnrs_anon_ix_imaging_center      ON lnrs.lnrs_anon_imaging_study (center_code);
CREATE INDEX lnrs_anon_ix_imaging_study_uid   ON lnrs.lnrs_anon_imaging_study (dicom_study_uid);
CREATE INDEX lnrs_anon_ix_imaging_exam        ON lnrs.lnrs_anon_imaging_study (anon_exam_id) WHERE anon_exam_id IS NOT NULL;
CREATE INDEX lnrs_anon_ix_imaging_path_hash   ON lnrs.lnrs_anon_imaging_study (image_path);

-- ---------- 2. 触发器 ----------

CREATE OR REPLACE FUNCTION lnrs.lnrs_anon_trg_imaging_study_set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

CREATE TRIGGER lnrs_anon_tg_imaging_study_updated
    BEFORE UPDATE ON lnrs.lnrs_anon_imaging_study
    FOR EACH ROW
    EXECUTE FUNCTION lnrs.lnrs_anon_trg_imaging_study_set_updated_at();

-- ---------- 3. 同步 lnrs.lnrs_anon_patient FK 兼容性 ----------

-- patient_id 已通过 REFERENCES lnrs.lnrs_anon_patient(patient_id) FK 锁死；
-- 若离线灌库时 patient_id 还未在 lnrs_anon_patient 中（先有影像后入 patient 的批次），
-- 构建脚本需先 INSERT patient，再 INSERT imaging_study。FK 保证参照完整性。

-- ---------- 4. 视图（前端取 study 列表时直接 JOIN view） ----------

CREATE OR REPLACE VIEW lnrs.lnrs_anon_v_imaging_study AS
SELECT
    s.study_key,
    s.patient_id,
    p.anon_id,
    s.center_code,
    s.dicom_study_uid,
    s.modality,
    s.image_path,
    s.sop_count,
    s.source,
    s.anon_exam_id,
    s.created_at,
    s.updated_at
FROM lnrs.lnrs_anon_imaging_study s
JOIN lnrs.lnrs_anon_patient p ON p.patient_id = s.patient_id;

COMMENT ON TABLE  lnrs.lnrs_anon_imaging_study           IS '影像研究桥接表（patient_id ↔ 影像绝对路径，仅脱敏 ID）';
COMMENT ON COLUMN lnrs.lnrs_anon_imaging_study.image_path IS '磁盘上 Study 目录的绝对路径';
COMMENT ON COLUMN lnrs.lnrs_anon_imaging_study.anon_exam_id IS '冗余 FK：ETL-2 落 exam 时回填；离线灌库时可空';
COMMENT ON COLUMN lnrs.lnrs_anon_imaging_study.source    IS '数据来源标识（disk1_zhujiang/disk2_zhujiang_supplement/etl_ingest/...）';

COMMIT;