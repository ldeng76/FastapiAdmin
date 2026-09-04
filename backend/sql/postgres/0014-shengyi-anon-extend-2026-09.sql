-- =====================================================================
-- 0014 - 省医(shengyi) 2026-09 全量批次扩展: 新增 4 张匿名表
-- 目标: PostgreSQL 14+, schema = lnrs
-- 背景:
--   省医 extracted 批次（2026-09, 26 个 parquet / ~1 亿行）中，
--   诊断/病程记录文档/病史/护理测量(ICU/麻醉子项) 在现有 14 张
--   lnrs_anon_* 表无对应落点（visit_detail 是 visit 1:1，装不下
--   这些 visit 级 N:1 或 patient 级 N:1 数据），故新增 4 张专用表
--   （仿 0010 lab_result/order 模板）。
-- 内容（增量建表，不 DROP 已有匿名表，可重复执行）:
--   1. lnrs_anon_diagnosis          患者级诊断（就诊.诊断 + 住院病案首页.诊断 合并，source 区分）
--   2. lnrs_anon_clinical_document  病程记录文档（自由文本，文档类型+日期+内容）
--   3. lnrs_anon_medical_history    就诊病史（主诉/现病史/既往史/个人史/婚育史/家族史）
--   4. lnrs_anon_vital_observation  生命体征/观察测量（护理记录+ICU护理+麻醉子项 合并，obs_type 区分）
-- 设计约定（与 0006/0010 一致）:
--   - 公共列: center_code / created_batch_id(UUID FK CASCADE) / created_at
--   - 幂等键: source_*_hash CHAR(64) 裸 SHA256 单列 UNIQUE（不依赖可空列，
--     规避 PG NULL 不参与 UNIQUE 冲突导致重跑重复插入的问题，同 0010 修订版）
--   - FK 用 ON DELETE CASCADE 级联清理
--   - vital_observation 的 obs_time 用 TIMESTAMP（体征是日内多次测量，
--     DATE 会丢日内序，这是对 0010 lab.collection_time DATE 的有意偏离）
-- =====================================================================

BEGIN;

-- 索引/触发器名只属于当前 schema，不能带 lnrs. 前缀
SET LOCAL search_path = lnrs, public;

-- --------------------------------------------------------------------- #
-- 1. lnrs_anon_diagnosis (患者级诊断)
--    源: 非隐私信息.就诊.诊断.parquet (4,925,535 行, 无就诊编号列, patient 级)
--        + 非隐私信息.就诊.住院病案首页.诊断.parquet (1,000,030 行, 无就诊编号列)
--    两文件合并一表，source 区分来源；病案首页上下文（血型/入院途径/离院方式...）
--    落 diagnosis_detail_json。
-- --------------------------------------------------------------------- #
CREATE TABLE lnrs.lnrs_anon_diagnosis (
    diagnosis_id        BIGSERIAL    PRIMARY KEY,
    patient_id          VARCHAR(16)  NOT NULL REFERENCES lnrs.lnrs_anon_patient(patient_id) ON DELETE CASCADE,
    center_code         VARCHAR(32)  NOT NULL,
    source              VARCHAR(32)  NOT NULL,               -- diagnosis / inpatient_front_page
    diagnosis_code      VARCHAR(64),
    diagnosis_name      VARCHAR(255),
    diagnosis_date      DATE,
    is_primary          VARCHAR(8),                          -- 是/否 原值保留（未字典化）
    diagnosis_category  VARCHAR(64),                         -- 第一诊断/门诊诊断/入院诊断/出院诊断/次要诊断...
    diagnosis_detail_json JSONB,                             -- 病案首页上下文/诊断归转情况/入院病情
    source_diag_hash    CHAR(64)     NOT NULL,               -- SHA256(center:source:pid:code:name:date:category:primary)
    created_batch_id    UUID         NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
    created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT lnrs_anon_uq_diagnosis UNIQUE (source_diag_hash)
);

CREATE INDEX lnrs_anon_ix_diag_patient   ON lnrs.lnrs_anon_diagnosis (patient_id);
CREATE INDEX lnrs_anon_ix_diag_date      ON lnrs.lnrs_anon_diagnosis (diagnosis_date);
CREATE INDEX lnrs_anon_ix_diag_category  ON lnrs.lnrs_anon_diagnosis (diagnosis_category);

-- --------------------------------------------------------------------- #
-- 2. lnrs_anon_clinical_document (病程记录文档)
--    源: 非隐私信息.就诊.病程记录文档.parquet (5,164,052 行, 无就诊编号列, patient 级)
--    文档类型: 门诊病历.处理/入院记录.辅助检查/首次病程记录.病历特点/日常病程记录...
--    2,481,498 行内容为空（随全量一并入库，source_doc_hash 去重）。
-- --------------------------------------------------------------------- #
CREATE TABLE lnrs.lnrs_anon_clinical_document (
    document_id         BIGSERIAL    PRIMARY KEY,
    patient_id          VARCHAR(16)  NOT NULL REFERENCES lnrs.lnrs_anon_patient(patient_id) ON DELETE CASCADE,
    center_code         VARCHAR(32)  NOT NULL,
    doc_type            VARCHAR(64),                         -- 门诊病历.处理 / 出院记录.诊疗经过 ...
    doc_date            DATE,
    doc_content         TEXT,                                -- 自由文本（PHI 风险见 skill 注意事项）
    source_doc_hash     CHAR(64)     NOT NULL,               -- SHA256(center:pid:doc_type:doc_date:md5(content))
    created_batch_id    UUID         NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
    created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT lnrs_anon_uq_clinical_doc UNIQUE (source_doc_hash)
);

CREATE INDEX lnrs_anon_ix_doc_patient    ON lnrs.lnrs_anon_clinical_document (patient_id);
CREATE INDEX lnrs_anon_ix_doc_date       ON lnrs.lnrs_anon_clinical_document (doc_date);
CREATE INDEX lnrs_anon_ix_doc_type       ON lnrs.lnrs_anon_clinical_document (doc_type);

-- --------------------------------------------------------------------- #
-- 3. lnrs_anon_medical_history (就诊病史)
--    源: 非隐私信息.就诊.病史.parquet (1,403,598 行, 无就诊编号列, patient 级)
--    数据来源: 门诊病历/住院病案首页/入院记录/首次病程记录/24小时入出院记录/转入记录
-- --------------------------------------------------------------------- #
CREATE TABLE lnrs.lnrs_anon_medical_history (
    history_id          BIGSERIAL    PRIMARY KEY,
    patient_id          VARCHAR(16)  NOT NULL REFERENCES lnrs.lnrs_anon_patient(patient_id) ON DELETE CASCADE,
    center_code         VARCHAR(32)  NOT NULL,
    chief_complaint     TEXT,                                -- 主诉
    present_illness     TEXT,                                -- 现病史
    past_history        TEXT,                                -- 既往史
    personal_history    TEXT,                                -- 个人史
    marriage_history    TEXT,                                -- 婚育史
    family_history      TEXT,                                -- 家族史
    record_date         DATE,
    data_source         VARCHAR(64),                         -- 门诊病历/住院病案首页/入院记录...
    source_hist_hash    CHAR(64)     NOT NULL,               -- SHA256(center:pid:data_source:record_date:md5(六文本拼接))
    created_batch_id    UUID         NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
    created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT lnrs_anon_uq_medical_history UNIQUE (source_hist_hash)
);

CREATE INDEX lnrs_anon_ix_hist_patient   ON lnrs.lnrs_anon_medical_history (patient_id);
CREATE INDEX lnrs_anon_ix_hist_date      ON lnrs.lnrs_anon_medical_history (record_date);

-- --------------------------------------------------------------------- #
-- 4. lnrs_anon_vital_observation (生命体征/观察测量)
--    源: 非隐私信息.就诊.护理记录.测量子项.parquet (13,824,664 行, obs_type=nursing,
--         报告级就诊编号 100% 非空 → 挂 visit)
--        + 非隐私信息.就诊.ICU护理记录.记录详细信息.parquet (2,911,682 行, obs_type=icu, 无就诊编号)
--        + 非隐私信息.就诊.麻醉信息.子项记录.parquet (2,981,080 行, obs_type=anesthesia, 无就诊编号)
--    item_name: 体温/脉搏/收缩压/HR/SBP/脉搏血氧饱和度...（原始项目名保留，未归一化）
-- --------------------------------------------------------------------- #
CREATE TABLE lnrs.lnrs_anon_vital_observation (
    observation_id      BIGSERIAL    PRIMARY KEY,
    anon_visit_id       VARCHAR(40)  REFERENCES lnrs.lnrs_anon_visit(anon_visit_id) ON DELETE CASCADE,
    patient_id          VARCHAR(16)  NOT NULL REFERENCES lnrs.lnrs_anon_patient(patient_id) ON DELETE CASCADE,
    center_code         VARCHAR(32)  NOT NULL,
    obs_type            VARCHAR(16)  NOT NULL,               -- nursing / icu / anesthesia
    item_name           VARCHAR(255),                        -- 体温/HR/项目描述 原值
    item_result         VARCHAR(255),                        -- 字符串结果（含定性）
    item_result_value   NUMERIC(12,4),                       -- 数值结果（非数值时 NULL）
    item_unit           VARCHAR(64),
    obs_time            TIMESTAMP,                           -- 日内多次测量，保留时分秒（对 0010 DATE 的有意偏离）
    obs_detail_json     JSONB,                               -- 项目类型/项目编码/护理类型/护士签名/ASA分级/体重...
    source_obs_hash     CHAR(64)     NOT NULL,               -- SHA256(center:obs_type:pid:visit:item:result:value:unit:time)
    created_batch_id    UUID         NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
    created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT lnrs_anon_uq_vital_observation UNIQUE (source_obs_hash)
);

CREATE INDEX lnrs_anon_ix_obs_visit      ON lnrs.lnrs_anon_vital_observation (anon_visit_id);
CREATE INDEX lnrs_anon_ix_obs_patient    ON lnrs.lnrs_anon_vital_observation (patient_id);
CREATE INDEX lnrs_anon_ix_obs_time       ON lnrs.lnrs_anon_vital_observation (obs_time);
CREATE INDEX lnrs_anon_ix_obs_type_item  ON lnrs.lnrs_anon_vital_observation (obs_type, item_name);

COMMIT;
