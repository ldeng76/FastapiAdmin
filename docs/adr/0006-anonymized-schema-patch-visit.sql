-- =====================================================================
-- 脱敏库 visit 级扩展补丁 (Anonymized Schema Patch — Visit Layer)
-- 依据: docs/adr/0006-anonymized-schema-vs-unified-tables.md §7 (2026-07-19 改写)
-- 前置: 先执行 0006-anonymized-schema.sql (9 表基础结构)
-- 兼容: PostgreSQL 14+
--
-- 命名约定:
--   * 表名/类型名/索引名/触发器名均带 lnrs_anon_ / lnrs_ 前缀,
--     与 0006-anonymized-schema.sql 保持一致 (不依赖 search_path 解析).
--   * 列名保持短名 (anon_id / anon_visit_id ...), 因为列名无歧义.
--
-- 本补丁解决一个问题:
--   现有脱敏库只有 lnrs_anon_exam (检查级) 一条桥, 而 unified_table_schema 里
--   新增的 6 张宽表 (diagnosis / medical_history / progress_note /
--   nursing_observation / icu_observation / anesthesia_event) 全是
--   visit (就诊) 级数据, 与影像检查无关. 强行塞进 anon_exam / finding
--   会丢"非影像就诊"的所有信息.
--   因此新增第二条桥 lnrs_anon_visit, 让 6 张业务表挂在它下面.
--
-- 原始 PHI 处理约定 (与 0006 一致):
--   * 原始 patient_id / visit_id / 护士签名 / 医生姓名 一律不落库
--   * 长文本字段 (主诉/现病史/病程正文) 经 regex+LLM 清洗后落 body_clean
--   * 结构化字段直接落库, 不含 PHI
--   * 每张业务表都带 created_batch_id, 与 ingest_batch 关联
-- =====================================================================

BEGIN;

-- ---------- 0. 新增枚举 ----------

-- 就诊类型: 门诊 / 住院 / 急诊 / 体检
CREATE TYPE lnrs_anon_visit_type_enum AS ENUM ('outpatient','inpatient','emergency','health_check','unknown');

-- 诊断来源: 病案首页 / 诊疗过程
CREATE TYPE lnrs_anon_diagnosis_source_enum AS ENUM ('front_page','visit');

-- 诊断类型: 主要 / 次要 / 其他
CREATE TYPE lnrs_anon_diagnosis_type_enum AS ENUM ('primary','secondary','other');

-- 麻醉 / 护理事件类型
CREATE TYPE lnrs_anon_event_kind_enum AS ENUM ('medication','observation');


-- ---------- 1. lnrs_anon_visit (新桥) ----------

CREATE TABLE lnrs_anon_visit (
    anon_visit_id      VARCHAR(40)  PRIMARY KEY,            -- 'ANON_VIS_' + 12hex = HMAC(secret, center + PAT_LOCAL_ID + ':' + VISIT_ORDINAL)
    anon_id            VARCHAR(32)  NOT NULL REFERENCES lnrs_anon_patient(anon_id) ON DELETE CASCADE,
    center_code        VARCHAR(32)  NOT NULL,
    visit_ordinal      VARCHAR(16)  NOT NULL,                -- 原始 m/n 文本, 保留以便溯源
    visit_type         lnrs_anon_visit_type_enum NOT NULL DEFAULT 'unknown',
    visit_start_date   DATE,                                 -- 就诊开始日期 (visit_record.就诊日期)
    visit_end_date     DATE,                                 -- 出院/结束日期 (可空)
    source_visit_hash  CHAR(64)     NOT NULL,                -- (center, PAT_LOCAL_ID, VISIT_NO) 的 SHA-256, 幂等用
    created_batch_id   UUID         NOT NULL REFERENCES lnrs_anon_ingest_batch(batch_id),
    last_seen_batch_id UUID         NOT NULL REFERENCES lnrs_anon_ingest_batch(batch_id),
    created_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_visit_source UNIQUE (center_code, source_visit_hash),
    CONSTRAINT uq_visit_patient_ordinal UNIQUE (anon_id, visit_ordinal)
);

CREATE INDEX lnrs_anon_ix_visit_patient ON lnrs_anon_visit (anon_id);
CREATE INDEX lnrs_anon_ix_visit_center_date ON lnrs_anon_visit (center_code, visit_start_date);


-- ---------- 2. 给 lnrs_anon_exam 加可空 visit 桥 ----------

-- 影像检查在 ETL 反查 visit_record 成功时回填, 失败置 null (保持原 anon_exam 语义不变)
ALTER TABLE lnrs_anon_exam
    ADD COLUMN anon_visit_id VARCHAR(40) REFERENCES lnrs_anon_visit(anon_visit_id) ON DELETE SET NULL;

CREATE INDEX lnrs_anon_ix_exam_visit ON lnrs_anon_exam (anon_visit_id);


-- ---------- 3. lnrs_anon_diagnosis — 诊断事件 (visit 级, 一就诊多条) ----------

CREATE TABLE lnrs_anon_diagnosis (
    diagnosis_id       BIGSERIAL    PRIMARY KEY,
    anon_visit_id      VARCHAR(40)  NOT NULL REFERENCES lnrs_anon_visit(anon_visit_id) ON DELETE CASCADE,
    anon_id            VARCHAR(32)  NOT NULL REFERENCES lnrs_anon_patient(anon_id),
    center_code        VARCHAR(32)  NOT NULL,
    diagnosis_source   lnrs_anon_diagnosis_source_enum NOT NULL,    -- front_page / visit
    diagnosis_no       INT,                                          -- 诊断次序 (1..N)
    diagnosis_code     VARCHAR(64),                                  -- ICD-10 / 院内码, 例如 C34.001, M80410/3
    diagnosis_name     VARCHAR(255) NOT NULL,
    diagnosis_type     lnrs_anon_diagnosis_type_enum,                -- primary / secondary / other
    diagnosis_outcome  VARCHAR(32),                                  -- 治愈/好转/未愈/死亡/其他 (front_page 才有)
    admission_condition VARCHAR(32),                                 -- 入院病情 (front_page 才有)
    diagnosis_date     DATE,
    is_primary_diagnosis BOOLEAN      NOT NULL DEFAULT FALSE,
    diagnosis_category VARCHAR(32),                                  -- visit 诊断才有: 出院诊断/入院主要诊断/初步诊断 ...
    front_page_meta    JSONB,                                        -- 仅 front_page 行有值, 承载 35 列扩展结构
    created_batch_id   UUID         NOT NULL REFERENCES lnrs_anon_ingest_batch(batch_id),
    created_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- 幂等: 同一就诊 + 同序号 + 同编码视为同一条, 重复导入只 UPDATE
    CONSTRAINT uq_diagnosis UNIQUE (anon_visit_id, diagnosis_source, diagnosis_no, diagnosis_code)
);

CREATE INDEX lnrs_anon_ix_dx_visit     ON lnrs_anon_diagnosis (anon_visit_id);
CREATE INDEX lnrs_anon_ix_dx_code      ON lnrs_anon_diagnosis (diagnosis_code);
CREATE INDEX lnrs_anon_ix_dx_primary   ON lnrs_anon_diagnosis (anon_id, is_primary_diagnosis) WHERE is_primary_diagnosis;


-- ---------- 4. lnrs_anon_medical_history — 病史记录 (visit 级, 一就诊一份) ----------

-- 长文本 6 段 (主诉/现病史/既往史/个人史/婚育史/家族史) 经清洗后落 body_clean,
-- 与 lnrs_anon_report_text 复用同一字段语义但独立建表, 避免污染 exam 级语义.
CREATE TABLE lnrs_anon_medical_history (
    anon_visit_id      VARCHAR(40)  PRIMARY KEY REFERENCES lnrs_anon_visit(anon_visit_id) ON DELETE CASCADE,
    anon_id            VARCHAR(32)  NOT NULL REFERENCES lnrs_anon_patient(anon_id),
    center_code        VARCHAR(32)  NOT NULL,
    record_date        DATE,
    source_document    VARCHAR(64),                           -- 门诊病历/住院病历/首次病程 ...
    body_clean         TEXT         NOT NULL,                 -- 6 段长文本合并并经 regex+LLM 清洗
    body_structure     JSONB,                                 -- 结构化拆分, 例: {"chief_complaint":"...","present_illness":"...", ...}
    pii_replaced_count INT          NOT NULL DEFAULT 0 CHECK (pii_replaced_count >= 0),
    clean_method       lnrs_anon_clean_method_enum NOT NULL,
    llm_model          VARCHAR(64),
    review_status      lnrs_anon_review_status_enum NOT NULL DEFAULT 'pending',
    created_batch_id   UUID         NOT NULL REFERENCES lnrs_anon_ingest_batch(batch_id),
    created_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX lnrs_anon_ix_mh_patient   ON lnrs_anon_medical_history (anon_id);
CREATE INDEX lnrs_anon_ix_mh_review    ON lnrs_anon_medical_history (review_status);


-- ---------- 5. lnrs_anon_progress_note — 病程记录 (visit 级, 一就诊多条) ----------

CREATE TABLE lnrs_anon_progress_note (
    note_id            BIGSERIAL    PRIMARY KEY,
    anon_visit_id      VARCHAR(40)  NOT NULL REFERENCES lnrs_anon_visit(anon_visit_id) ON DELETE CASCADE,
    anon_id            VARCHAR(32)  NOT NULL REFERENCES lnrs_anon_patient(anon_id),
    center_code        VARCHAR(32)  NOT NULL,
    note_date          DATE,                                  -- 约 19% 行为空, 保留 null
    note_type          VARCHAR(64)  NOT NULL,                  -- 门诊病历.处理/首次病程记录/日常病程记录/查房记录 ...
    body_clean         TEXT         NOT NULL,                  -- 经清洗的正文
    pii_replaced_count INT          NOT NULL DEFAULT 0 CHECK (pii_replaced_count >= 0),
    clean_method       lnrs_anon_clean_method_enum NOT NULL,
    llm_model          VARCHAR(64),
    review_status      lnrs_anon_review_status_enum NOT NULL DEFAULT 'pending',
    source_note_hash   CHAR(64)     NOT NULL,                  -- (visit_id, note_type, note_date, body_clean 原文) 的 SHA-256, 幂等用
    created_batch_id   UUID         NOT NULL REFERENCES lnrs_anon_ingest_batch(batch_id),
    created_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_progress_note UNIQUE (anon_visit_id, source_note_hash)
);

CREATE INDEX lnrs_anon_ix_pn_visit   ON lnrs_anon_progress_note (anon_visit_id);
CREATE INDEX lnrs_anon_ix_pn_type    ON lnrs_anon_progress_note (note_type, note_date);
CREATE INDEX lnrs_anon_ix_pn_review  ON lnrs_anon_progress_note (review_status);


-- ---------- 6. lnrs_anon_nursing_observation — 护理测量子项 (visit 级, 时序) ----------

-- 粒度: 每条测量子项一行. 护士签名等 PHI 字段不入库.
CREATE TABLE lnrs_anon_nursing_observation (
    nursing_item_id    BIGSERIAL    PRIMARY KEY,
    anon_visit_id      VARCHAR(40)  NOT NULL REFERENCES lnrs_anon_visit(anon_visit_id) ON DELETE CASCADE,
    anon_id            VARCHAR(32)  NOT NULL REFERENCES lnrs_anon_patient(anon_id),
    center_code        VARCHAR(32)  NOT NULL,
    record_id          VARCHAR(64)  NOT NULL,                  -- 护理记录 UUID (脱敏后哈希)
    item_id            VARCHAR(96)  NOT NULL,                  -- 子项编号 <uuid>_<指标>_<seq>, 天然主键来源
    item_code          VARCHAR(64),
    item_name          VARCHAR(64)  NOT NULL,                  -- 体温/脉搏/呼吸/血压/大便次 ...
    item_category      VARCHAR(64),                            -- 基础护理/专科护理
    item_value         NUMERIC(12,3),
    item_unit          VARCHAR(32),
    measurement_time   TIMESTAMP,                             -- 测量时间
    measurement_method VARCHAR(64),                            -- 呼吸辅助措施/血压辅助 ...
    department         VARCHAR(64),                            -- 住院科室 (非 PHI)
    record_date        DATE,                                   -- 护理记录日期 (父级冗余)
    nursing_meta       JSONB,                                  -- 参考上下限等扩展元数据
    created_batch_id   UUID         NOT NULL REFERENCES lnrs_anon_ingest_batch(batch_id),
    created_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_nursing_item UNIQUE (anon_visit_id, item_id)
);

CREATE INDEX lnrs_anon_ix_nursing_visit     ON lnrs_anon_nursing_observation (anon_visit_id);
CREATE INDEX lnrs_anon_ix_nursing_time      ON lnrs_anon_nursing_observation (measurement_time);
CREATE INDEX lnrs_anon_ix_nursing_name_time ON lnrs_anon_nursing_observation (item_name, measurement_time);


-- ---------- 7. lnrs_anon_icu_observation — ICU 观察项 (visit 级, 时序) ----------

CREATE TABLE lnrs_anon_icu_observation (
    icu_item_id        BIGSERIAL    PRIMARY KEY,
    anon_visit_id      VARCHAR(40)  NOT NULL REFERENCES lnrs_anon_visit(anon_visit_id) ON DELETE CASCADE,
    anon_id            VARCHAR(32)  NOT NULL REFERENCES lnrs_anon_patient(anon_id),
    center_code        VARCHAR(32)  NOT NULL,
    department         VARCHAR(64),
    admission_date     DATE,
    icu_in_time        TIMESTAMP,
    icu_out_time       TIMESTAMP,
    weight_kg          NUMERIC(6,2),
    diagnosis_summary  VARCHAR(255),                          -- 仅诊断名称 (非 PHI), 不存完整诊断文本
    record_date        TIMESTAMP    NOT NULL,
    item_name          VARCHAR(64)  NOT NULL,                  -- SPO2/脉搏/呼吸/血压(收缩) ...
    item_result        VARCHAR(255),
    item_result_value  NUMERIC(12,3),
    source_item_hash   CHAR(64)     NOT NULL,                  -- (visit_id, icu_in_time, record_date, item_name) SHA-256
    created_batch_id   UUID         NOT NULL REFERENCES lnrs_anon_ingest_batch(batch_id),
    created_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_icu_item UNIQUE (anon_visit_id, source_item_hash)
);

CREATE INDEX lnrs_anon_ix_icu_visit    ON lnrs_anon_icu_observation (anon_visit_id);
CREATE INDEX lnrs_anon_ix_icu_intime   ON lnrs_anon_icu_observation (icu_in_time);
CREATE INDEX lnrs_anon_ix_icu_name_val ON lnrs_anon_icu_observation (item_name, record_date);


-- ---------- 8. lnrs_anon_anesthesia_event — 麻醉事件 (visit 级, 含 medication + observation 双事件) ----------

CREATE TABLE lnrs_anon_anesthesia_event (
    anesthesia_event_id BIGSERIAL   PRIMARY KEY,
    anon_visit_id       VARCHAR(40) NOT NULL REFERENCES lnrs_anon_visit(anon_visit_id) ON DELETE CASCADE,
    anon_id             VARCHAR(32) NOT NULL REFERENCES lnrs_anon_patient(anon_id),
    center_code         VARCHAR(32) NOT NULL,
    session_id          VARCHAR(64) NOT NULL,                  -- (patient_id, 入室时间) 哈希; 一张麻醉记录展开为多行
    event_kind          lnrs_anon_event_kind_enum NOT NULL,    -- medication / observation
    event_time          TIMESTAMP,
    -- 会话级字段 (一session多行冗余, 但便于单行查询)
    asa_level           VARCHAR(16),                           -- Ⅰ级 / Ⅱ级 / Ⅲ级 / Ⅳ级
    surgery_name        VARCHAR(255),
    surgery_start_time  TIMESTAMP,
    surgery_end_time    TIMESTAMP,
    anesthesia_start_time TIMESTAMP,
    anesthesia_end_time TIMESTAMP,
    room_in_time        TIMESTAMP,
    room_out_time       TIMESTAMP,
    weight_kg           NUMERIC(6,2),
    -- medication 行专用
    drug_name           VARCHAR(128),
    drug_dose           NUMERIC(12,3),
    drug_unit           VARCHAR(32),
    -- observation 行专用
    observation_name    VARCHAR(255),
    observation_value   VARCHAR(255),
    observation_unit    VARCHAR(32),
    anesthesia_extra    JSONB,                                 -- 药房/批次等扩展元数据
    created_batch_id    UUID        NOT NULL REFERENCES lnrs_anon_ingest_batch(batch_id),
    created_at          TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
    -- 注: 不在 UNIQUE 里使用 COALESCE 表达式 (与 ON CONFLICT 不兼容); 改用 source_event_hash 幂等
);

-- 幂等: 整行级哈希, 涵盖 medication / observation 两种事件
-- 由 ETL 在加载前算好: source_event_hash = sha256(session_id | event_kind | drug_name | drug_dose | drug_unit | observation_name | observation_value | observation_unit)
ALTER TABLE lnrs_anon_anesthesia_event
    ADD COLUMN source_event_hash CHAR(64) NOT NULL,
    ADD CONSTRAINT uq_anesthesia_event UNIQUE (anon_visit_id, source_event_hash);

CREATE INDEX lnrs_anon_ix_anes_visit   ON lnrs_anon_anesthesia_event (anon_visit_id);
CREATE INDEX lnrs_anon_ix_anes_session ON lnrs_anon_anesthesia_event (session_id);
CREATE INDEX lnrs_anon_ix_anes_kind    ON lnrs_anon_anesthesia_event (event_kind, event_time);


-- ---------- 9. 视图: 就诊级一站式 (含 6 类业务数据计数) ----------

CREATE OR REPLACE VIEW lnrs_anon_v_visit_full AS
SELECT
    v.anon_visit_id,
    v.anon_id,
    v.center_code,
    v.visit_ordinal,
    v.visit_type,
    v.visit_start_date,
    v.visit_end_date,
    COUNT(DISTINCT d.diagnosis_id)                  AS diagnosis_count,
    BOOL_OR(d.is_primary_diagnosis)                 AS has_primary_diagnosis,
    COUNT(DISTINCT mh.anon_visit_id)                AS has_medical_history,   -- 0/1
    COUNT(DISTINCT pn.note_id)                      AS progress_note_count,
    COUNT(DISTINCT n.nursing_item_id)               AS nursing_observation_count,
    COUNT(DISTINCT i.icu_item_id)                   AS icu_observation_count,
    COUNT(DISTINCT CASE WHEN ae.event_kind='medication'   THEN ae.anesthesia_event_id END) AS anesthesia_medication_count,
    COUNT(DISTINCT CASE WHEN ae.event_kind='observation'  THEN ae.anesthesia_event_id END) AS anesthesia_observation_count,
    COUNT(DISTINCT ex.anon_exam_id)                 AS exam_count
FROM lnrs_anon_visit v
LEFT JOIN lnrs_anon_diagnosis          d  ON d.anon_visit_id  = v.anon_visit_id
LEFT JOIN lnrs_anon_medical_history    mh ON mh.anon_visit_id = v.anon_visit_id
LEFT JOIN lnrs_anon_progress_note      pn ON pn.anon_visit_id = v.anon_visit_id
LEFT JOIN lnrs_anon_nursing_observation n ON n.anon_visit_id = v.anon_visit_id
LEFT JOIN lnrs_anon_icu_observation    i  ON i.anon_visit_id  = v.anon_visit_id
LEFT JOIN lnrs_anon_anesthesia_event   ae ON ae.anon_visit_id = v.anon_visit_id
LEFT JOIN lnrs_anon_exam               ex ON ex.anon_visit_id = v.anon_visit_id
GROUP BY v.anon_visit_id, v.anon_id, v.center_code, v.visit_ordinal, v.visit_type, v.visit_start_date, v.visit_end_date;


-- ---------- 10. 触发器: 新表的 updated_at 自动维护 ----------

-- 复用已定义的 lnrs_anon_trg_set_updated_at() 函数 (0006-anonymized-schema.sql 已建)

CREATE TRIGGER lnrs_anon_tg_visit_updated    BEFORE UPDATE ON lnrs_anon_visit          FOR EACH ROW EXECUTE FUNCTION lnrs_anon_trg_set_updated_at();
CREATE TRIGGER lnrs_anon_tg_medhist_updated  BEFORE UPDATE ON lnrs_anon_medical_history FOR EACH ROW EXECUTE FUNCTION lnrs_anon_trg_set_updated_at();
CREATE TRIGGER lnrs_anon_tg_progress_updated BEFORE UPDATE ON lnrs_anon_progress_note   FOR EACH ROW EXECUTE FUNCTION lnrs_anon_trg_set_updated_at();


-- ---------- 完成 ----------
-- 使用示例:
--   1) 查一个就诊的全部诊断 + 病史 + 病程:
--      SELECT * FROM lnrs_anon_v_visit_full WHERE anon_visit_id = 'ANON_VIS_xxxxxxxxxxxx';
--
--   2) 跨就诊找"有 III 级 ASA 且诊断含肺癌"的病人:
--      SELECT DISTINCT v.anon_id
--      FROM   lnrs_anon_visit v
--      JOIN   lnrs_anon_anesthesia_event ae ON ae.anon_visit_id = v.anon_visit_id
--      JOIN   lnrs_anon_diagnosis d          ON d.anon_visit_id  = v.anon_visit_id
--      WHERE  ae.asa_level = 'Ⅲ级'
--        AND  d.diagnosis_code LIKE 'C34%';
--
--   3) 把影像检查与就诊对齐:
--      SELECT ex.anon_exam_id, v.anon_visit_id, d.diagnosis_name
--      FROM   lnrs_anon_exam ex
--      JOIN   lnrs_anon_visit v ON v.anon_visit_id = ex.anon_visit_id
--      JOIN   lnrs_anon_diagnosis d ON d.anon_visit_id = v.anon_visit_id
--      WHERE  d.is_primary_diagnosis;

COMMIT;
