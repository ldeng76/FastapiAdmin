-- 0016-imaging-orphan-registry.sql
-- 2026-09-03:孤儿影像研究登记表 + 审计批次表 + 视图
-- 业务 ID `study_orphan_id` 由 (center_code, rel_path_from_dicom_root) SHA256[:8] 哈希派生,不依赖任何全局序列
-- 部署无关:rel_path 去掉 dicom 根绝对前缀,NFS 挂载点/主机 IP 变更不影响 ID
-- 跨中心:source_orphan_hash 含 center_code,跨中心路径不撞
-- **不建全局 SEQUENCE**;唯一序列是 orphan_key BIGSERIAL(物理 PK)

BEGIN;

-- 1.1 孤儿审计批次元数据表(参考 lnrs_anon_ingest_batch)— 先建,因为 1.2 主表有 FK 引用
CREATE TABLE lnrs.lnrs_anon_orphan_audit_batch (
    audit_batch_id        UUID         PRIMARY KEY,                              -- 应用层 gen_random_uuid()
    center_code           VARCHAR(32)  NOT NULL,
    audit_locator         TEXT         NOT NULL,                                -- 中间 CSV 路径,如 'docs/孤儿文件研究/2026-09-03珠江医院CT文件/orphan_diagnosis_v4.csv'
    audit_sha256          CHAR(64),                                              -- CSV SHA256,锚定审计版本
    discovered_count      INT          NOT NULL CHECK (discovered_count >= 0),   -- 本次发现孤儿总数
    patient_missing_count INT          NOT NULL CHECK (patient_missing_count >= 0),
    dual_disk_copy_count  INT          NOT NULL CHECK (dual_disk_copy_count >= 0),
    empty_dir_count       INT          NOT NULL CHECK (empty_dir_count >= 0),
    other_count           INT          NOT NULL CHECK (other_count >= 0),
    ran_by                VARCHAR(64)  NOT NULL,                                -- 'script:scripts/import_orphan_diagnosis.py@2026-09-03'
    ran_at                TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes                 TEXT,
    CONSTRAINT lnrs_anon_ck_orphan_audit_center CHECK (center_code ~ '^[a-z][a-z0-9_]*$')
);

CREATE INDEX lnrs_anon_ix_orphan_audit_center ON lnrs.lnrs_anon_orphan_audit_batch (center_code);
CREATE INDEX lnrs_anon_ix_orphan_audit_time   ON lnrs.lnrs_anon_orphan_audit_batch (ran_at DESC);


-- 1.2 主表:实体登记表 + ID↔磁盘元数据双向映射(主表本身即中间表)
CREATE TABLE lnrs.lnrs_anon_imaging_orphan (
    orphan_key        BIGSERIAL    PRIMARY KEY,                         -- 物理 PK(BigSerial,内部锚定)
    -- 业务 ID:由信息映射生成,不依赖任何序列;同一 (center_code, rel_path_from_dicom_root) → 同一 ID
    study_orphan_id   VARCHAR(16)  NOT NULL,                            -- OR_<8hex>, = 'OR_' || sha256('{center_code}:{rel_path_from_dicom_root}')[:8];rel_path 去掉 dicom 根绝对前缀,部署无关
    center_code       VARCHAR(32)  NOT NULL,                            -- zhujiang/shengyi/xinqiao/hos301
    -- 6 个 patient_missing 孤儿无对应 patient,FK 可空;其余孤儿 FK→patient CASCADE
    patient_id        VARCHAR(16)  REFERENCES lnrs.lnrs_anon_patient(patient_id) ON DELETE CASCADE,
    dicom_study_uid   VARCHAR(64)  NOT NULL,
    image_path        TEXT         NOT NULL,                            -- 磁盘绝对路径(主定位键,可随运维迁移)
    -- 跨中心唯一指纹(对齐 source_*_hash 模式,CHAR(64) 单列 UNIQUE)
    source_orphan_hash CHAR(64)    NOT NULL,                            -- = sha256('{center_code}:{image_path}')
    path_date_prefix  VARCHAR(32)  NOT NULL,                            -- ymd / yd / new / pn / ymd_N
    modality          VARCHAR(16)  NOT NULL DEFAULT 'CT',
    sop_count         INT          NOT NULL DEFAULT 0 CHECK (sop_count >= 0),
    source            VARCHAR(64)  NOT NULL DEFAULT 'orphan_audit_2026_09_03',  -- 数据来源盘标识
    orphan_kind       VARCHAR(16)  NOT NULL,                            -- csv_uncovered/patient_missing/dual_disk_copy/empty_dir/other
    orphan_status     VARCHAR(16)  NOT NULL DEFAULT 'discovered',       -- discovered/reviewed/pending_ingest/ingested/rejected/archived
    review_notes      TEXT,                                             -- 人工审核备注
    -- 锚定本次审计的批次(可空;不依赖 ingest_batch,因孤儿审计非 ETL)
    audit_batch_id    UUID         REFERENCES lnrs.lnrs_anon_orphan_audit_batch(audit_batch_id) ON DELETE SET NULL,
    created_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- 业务编号格式校验(8hex 截断)
    CONSTRAINT lnrs_anon_ck_imaging_orphan_id_fmt   CHECK (study_orphan_id ~ '^OR_[0-9a-f]{8}$'),
    -- 业务 ID 单列 UNIQUE(同 image_path → 同 ID,但跨中心不同 image_path 也不撞)
    CONSTRAINT lnrs_anon_uq_imaging_orphan_id      UNIQUE (study_orphan_id),
    -- 跨中心唯一指纹(单列 UNIQUE,审计重跑幂等 + 多中心路径不撞)
    CONSTRAINT lnrs_anon_uq_imaging_orphan_hash    UNIQUE (source_orphan_hash),
    -- 业务口径锁(中心 + StudyUID + 路径)— 防止"同一磁盘目录被两个不同审计 run 重复登记"
    CONSTRAINT lnrs_anon_uq_imaging_orphan_path    UNIQUE (center_code, dicom_study_uid, image_path),
    -- center_code 正则
    CONSTRAINT lnrs_anon_ck_imaging_orphan_center   CHECK (center_code ~ '^[a-z][a-z0-9_]*$'),
    -- modality 限定 9 种
    CONSTRAINT lnrs_anon_ck_imaging_orphan_modality CHECK (modality IN ('CT','MR','XR','US','PET','NM','Pathology','Genetic','Other')),
    -- orphan_kind 5 类(语义化英文)
    CONSTRAINT lnrs_anon_ck_imaging_orphan_kind    CHECK (orphan_kind IN ('csv_uncovered','patient_missing','dual_disk_copy','empty_dir','other')),
    -- orphan_status 6 态状态机
    CONSTRAINT lnrs_anon_ck_imaging_orphan_status  CHECK (orphan_status IN ('discovered','reviewed','pending_ingest','ingested','rejected','archived')),
    -- path_date_prefix 5 类
    CONSTRAINT lnrs_anon_ck_imaging_orphan_prefix  CHECK (path_date_prefix IN ('ymd','yd','new','pn','ymd_N')),
    -- patient_missing 必须 patient_id NULL;其他 4 类若患者注册则 FK 必填
    CONSTRAINT lnrs_anon_ck_imaging_orphan_patient CHECK (
        (orphan_kind = 'patient_missing' AND patient_id IS NULL) OR
        (orphan_kind <> 'patient_missing')
    )
);

-- 索引
CREATE INDEX lnrs_anon_ix_imaging_orphan_patient    ON lnrs.lnrs_anon_imaging_orphan (patient_id) WHERE patient_id IS NOT NULL;
CREATE INDEX lnrs_anon_ix_imaging_orphan_center     ON lnrs.lnrs_anon_imaging_orphan (center_code);
CREATE INDEX lnrs_anon_ix_imaging_orphan_study_uid  ON lnrs.lnrs_anon_imaging_orphan (dicom_study_uid);
CREATE INDEX lnrs_anon_ix_imaging_orphan_kind       ON lnrs.lnrs_anon_imaging_orphan (orphan_kind);
CREATE INDEX lnrs_anon_ix_imaging_orphan_status     ON lnrs.lnrs_anon_imaging_orphan (orphan_status);
CREATE INDEX lnrs_anon_ix_imaging_orphan_audit      ON lnrs.lnrs_anon_imaging_orphan (audit_batch_id) WHERE audit_batch_id IS NOT NULL;

-- updated_at 触发器(沿用 0006 既有 lnrs_anon_trg_set_updated_at 函数,无需新建)
CREATE TRIGGER lnrs_anon_tg_imaging_orphan_updated
    BEFORE UPDATE ON lnrs.lnrs_anon_imaging_orphan
    FOR EACH ROW EXECUTE FUNCTION lnrs.lnrs_anon_trg_set_updated_at();


-- 1.3 视图(模仿 lnrs_anon_v_imaging_study)
CREATE OR REPLACE VIEW lnrs.lnrs_anon_v_imaging_orphan AS
SELECT
    o.orphan_key,
    o.study_orphan_id,
    o.source_orphan_hash,
    o.center_code,
    o.patient_id,
    p.anon_id,
    o.dicom_study_uid,
    o.image_path,
    o.path_date_prefix,
    o.modality,
    o.sop_count,
    o.source,
    o.orphan_kind,
    o.orphan_status,
    o.review_notes,
    o.audit_batch_id,
    b.ran_at      AS audited_at,
    b.audit_locator,
    o.created_at,
    o.updated_at
FROM lnrs.lnrs_anon_imaging_orphan o
LEFT JOIN lnrs.lnrs_anon_patient p ON p.patient_id = o.patient_id
LEFT JOIN lnrs.lnrs_anon_orphan_audit_batch b ON b.audit_batch_id = o.audit_batch_id;


COMMENT ON TABLE  lnrs.lnrs_anon_imaging_orphan           IS '影像孤儿登记表/中间表(ID ↔ 磁盘元数据双向映射);study_orphan_id 由 (center_code, rel_path_from_dicom_root) SHA256[:8] 哈希派生,部署无关';
COMMENT ON COLUMN lnrs.lnrs_anon_imaging_orphan.study_orphan_id   IS '业务编号 OR_<8hex>,由 (center_code, rel_path_from_dicom_root) SHA256[:8] 哈希派生;同一 dicom 子路径 → 同一 ID(可反查);rel_path 去掉 dicom 根绝对前缀,NFS 挂载点变更不影响 ID';
COMMENT ON COLUMN lnrs.lnrs_anon_imaging_orphan.source_orphan_hash IS '跨中心唯一指纹 sha256(center_code:image_path),CHAR(64) 单列 UNIQUE;含完整 abs_path 便于磁盘运维定位;对齐 source_*_hash 模式';
COMMENT ON COLUMN lnrs.lnrs_anon_imaging_orphan.orphan_kind  IS '成因分类:csv_uncovered/patient_missing/dual_disk_copy/empty_dir/other';
COMMENT ON COLUMN lnrs.lnrs_anon_imaging_orphan.orphan_status IS '状态机:discovered→reviewed→pending_ingest→ingested;旁支 rejected/archived';
COMMENT ON TABLE  lnrs.lnrs_anon_orphan_audit_batch       IS '孤儿审计批次元数据(每次磁盘扫描/反查的批次锚定)';

COMMIT;
