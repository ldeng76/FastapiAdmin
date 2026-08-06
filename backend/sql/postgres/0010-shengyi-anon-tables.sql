-- =====================================================================
-- 0010 - 省医(shengyi)扩展: 新增 visit_detail / lab_result / order 匿名表
-- 依据: docs/spec-shengyi-anon-etl-design.md / ADR-0006（匿名 schema）
-- 目标: PostgreSQL 14+, schema = lnrs
-- 背景:
--   珠江(6表)的 lnrs_anon_* 体系只覆盖 patient/exam/report/visit/surgery，
--   省医有 9 类数据，其中 visit_record/lab_result/drug_order/no_drug_order
--   在现有表中无对应落点，故新增 3 张专用表（仿 lnrs_anon_surgery 模板）。
-- 内容（增量建表，不 DROP 已有匿名表，可重复执行）:
--   1. lnrs_anon_visit_detail: visit 1:1 富信息（病案首页/病史/诊断/临床文档）
--   2. lnrs_anon_lab_result:   visit 级检验结果
--   3. lnrs_anon_order:        visit 级医嘱（drug + non_drug 合并，order_type 区分）
-- 设计约定（与 0006 一致）:
--   - 公共列: center_code / created_batch_id(UUID FK CASCADE) / created_at
--   - 幂等键: source_*_hash CHAR(64) 裸 SHA256 + UNIQUE 约束
--   - FK 用 ON DELETE CASCADE 级联清理
--   - lab/order 的 anon_visit_id 可空（visit 缺失时退化为只挂 patient）
-- =====================================================================

BEGIN;

-- 索引/触发器名只属于当前 schema，不能带 lnrs. 前缀
SET LOCAL search_path = lnrs, public;

-- --------------------------------------------------------------------- #
-- 0. 幂等清理（重复执行时先删本批新增表，不碰 0006 已建的表）
--    删除顺序: 先子表（FK 指向 visit/patient）再触发器
-- --------------------------------------------------------------------- #
DROP TABLE IF EXISTS lnrs.lnrs_anon_order        CASCADE;
DROP TABLE IF EXISTS lnrs.lnrs_anon_lab_result   CASCADE;
DROP TABLE IF EXISTS lnrs.lnrs_anon_visit_detail CASCADE;

-- --------------------------------------------------------------------- #
-- 1. lnrs_anon_visit_detail (visit 1:1 富信息)
--    省医 visit_record.parquet 含病案首页/病史/诊断数组/临床文档等富信息，
--    与 lnrs_anon_visit 轻量桥表 1:1。visit_detail_json 忠实保留原始嵌套结构。
--    前置: lnrs_anon_visit 桥行由 ETL _import_visit_detail_table 自建（不依赖 surgery 反推）。
-- --------------------------------------------------------------------- #
CREATE TABLE lnrs.lnrs_anon_visit_detail (
    visit_detail_id     BIGSERIAL    PRIMARY KEY,
    anon_visit_id       VARCHAR(40)  NOT NULL REFERENCES lnrs.lnrs_anon_visit(anon_visit_id) ON DELETE CASCADE,
    patient_id          VARCHAR(16)  NOT NULL REFERENCES lnrs.lnrs_anon_patient(patient_id) ON DELETE CASCADE,
    center_code         VARCHAR(32)  NOT NULL,
    visit_category      VARCHAR(32),                          -- 住院/门诊
    admission_time      DATE,
    discharge_date      DATE,
    admission_dept      VARCHAR(100),
    discharge_dept      VARCHAR(100),
    length_of_stay      INTEGER,
    payment_method      VARCHAR(100),
    visit_age           NUMERIC(5,1),
    visit_detail_json   JSONB        NOT NULL,                -- inpatient_front_page/medical_history/diagnoses[]/clinical_documents[]
    source_visit_hash   CHAR(64)     NOT NULL,                -- 复用 visit 桥 hash（1:1 关联，UNIQUE anon_visit_id 保证幂等）
    created_batch_id    UUID         NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
    created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT lnrs_anon_uq_visit_detail UNIQUE (anon_visit_id)
);

CREATE INDEX lnrs_anon_ix_visit_detail_patient ON lnrs.lnrs_anon_visit_detail (patient_id);
CREATE INDEX lnrs_anon_ix_visit_detail_admit   ON lnrs.lnrs_anon_visit_detail (admission_time);

-- --------------------------------------------------------------------- #
-- 2. lnrs_anon_lab_result (visit 级检验结果)
--    源: lab_result.parquet。提取关键标量列，test_detail 等剩余结构落 lab_detail_json。
--    anon_visit_id 可空: visit_id 缺失时退化为只挂 patient（NULL 不参与 UNIQUE 冲突）。
-- --------------------------------------------------------------------- #
CREATE TABLE lnrs.lnrs_anon_lab_result (
    lab_result_id      BIGSERIAL    PRIMARY KEY,
    anon_visit_id      VARCHAR(40)  REFERENCES lnrs.lnrs_anon_visit(anon_visit_id) ON DELETE CASCADE,
    patient_id         VARCHAR(16)  NOT NULL REFERENCES lnrs.lnrs_anon_patient(patient_id) ON DELETE CASCADE,
    center_code        VARCHAR(32)  NOT NULL,
    report_id          VARCHAR(64),
    test_name          VARCHAR(200),                          -- 检验组合名
    item_name          VARCHAR(200),                          -- 单项名
    item_result        VARCHAR(255),                          -- 字符串结果（含定性/比值）
    item_result_value  NUMERIC(12,4),                         -- 数值结果（非数值结果时 NULL）
    item_unit          VARCHAR(64),
    collection_time    DATE,
    lab_detail_json    JSONB,                                 -- test_detail 等剩余结构
    source_lab_hash    CHAR(64)     NOT NULL,                 -- SHA256(center:report_id:item_name)，全局唯一
    created_batch_id   UUID         NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
    created_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- 幂等键用单列 source_lab_hash：该值 = SHA256(center:report_id:item_name) 已全局唯一，
    -- 不依赖 anon_visit_id（visit 缺失时为 NULL，NULL 不参与 PG UNIQUE 冲突会导致重跑重复插入）
    CONSTRAINT lnrs_anon_uq_lab_result UNIQUE (source_lab_hash)
);

CREATE INDEX lnrs_anon_ix_lab_visit     ON lnrs.lnrs_anon_lab_result (anon_visit_id);
CREATE INDEX lnrs_anon_ix_lab_patient   ON lnrs.lnrs_anon_lab_result (patient_id);
CREATE INDEX lnrs_anon_ix_lab_time      ON lnrs.lnrs_anon_lab_result (collection_time);

-- --------------------------------------------------------------------- #
-- 3. lnrs_anon_order (visit 级医嘱, drug + non_drug 合并)
--    源: drug_order.parquet + no_drug_order.parquet，order_type 区分。
--    提取 order_name/order_time/order_source，order_detail struct 落 order_detail_json。
--    anon_visit_id 可空: visit_id 缺失时退化为只挂 patient。
--    幂等键 (anon_visit_id, source_order_hash)；NULL visit_id 的行 NULL 不参与冲突。
-- --------------------------------------------------------------------- #
CREATE TABLE lnrs.lnrs_anon_order (
    order_id           BIGSERIAL    PRIMARY KEY,
    anon_visit_id      VARCHAR(40)  REFERENCES lnrs.lnrs_anon_visit(anon_visit_id) ON DELETE CASCADE,
    patient_id         VARCHAR(16)  NOT NULL REFERENCES lnrs.lnrs_anon_patient(patient_id) ON DELETE CASCADE,
    center_code        VARCHAR(32)  NOT NULL,
    order_type         VARCHAR(16)  NOT NULL,                 -- drug / non_drug
    order_name         VARCHAR(200) NOT NULL,
    order_time         DATE,
    order_source       VARCHAR(32),                           -- inpatient/outpatient
    order_detail_json  JSONB,                                 -- order_detail struct (剂量/频次/途径...)
    source_order_hash  CHAR(64)     NOT NULL,                 -- SHA256(center:order_time:order_name:order_type)
    created_batch_id   UUID         NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
    created_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- 幂等键用单列 source_order_hash：该值全局唯一，不依赖 anon_visit_id（同 lab）
    CONSTRAINT lnrs_anon_uq_order UNIQUE (source_order_hash)
);

CREATE INDEX lnrs_anon_ix_order_visit   ON lnrs.lnrs_anon_order (anon_visit_id);
CREATE INDEX lnrs_anon_ix_order_patient ON lnrs.lnrs_anon_order (patient_id);
CREATE INDEX lnrs_anon_ix_order_type    ON lnrs.lnrs_anon_order (order_type);

COMMIT;
