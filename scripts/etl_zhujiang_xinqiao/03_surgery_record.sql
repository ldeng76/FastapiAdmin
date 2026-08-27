-- 03_surgery_record.sql
-- 珠江-新桥 surgery_record 表 (unified, Zhujiang side)
-- Source: 胸外历史病人编码后手术记录.csv (99 列)
-- IPID 格式: "001321_4" (patient_id + "_" + visit_seq)
-- OPERATION_TIME 是 BIGINT 形如 20241206000000
-- OPERATION_START_TIME / OPERATION_END_TIME 已是 DATE 类型
INSTALL spatial; LOAD spatial;

COPY (
  SELECT
    CAST(split_part(IPID, '_', 1) AS VARCHAR)                AS patient_id,
    CAST(NULL AS VARCHAR)                                    AS visit_id,
    -- 优先用 OPERATION_START_TIME (DATE),缺失时回退到 OPERATION_TIME 转日期
    COALESCE(
      OPERATION_START_TIME,
      TRY_CAST(
        STRPTIME(substr(CAST(OPERATION_TIME AS VARCHAR), 1, 8), '%Y%m%d') AS DATE
      )
    )                                                        AS surgery_date,
    CAST(OPERATION_NAME AS VARCHAR)                          AS procedure_name,
    CAST(NULL AS VARCHAR)                                    AS resection_scope,
    CAST(NULL AS VARCHAR)                                    AS surgical_approach,
    to_json({
      'icd9cm3_code':           OPERATION_CODE,
      'ln_dissection_strategy': NULL,
      'dissected_ln_groups':    NULL,
      'duration_minutes':       NULL,
      'asa_score':              ASA_LEVEL,
      'blood_loss_ml':          NULL,
      'complications':          NULL,
      'los_days':               NULL,
      'surgeon':                OPERATION_DOCTOR,
      'anesthesiologist':       ANESTHESIA_DOCTOR,
      'assistant_1':            ASSISTANT_I,
      'assistant_2':            ASSISTANT_II,
      'assistant_3':            ASSISTANT_III,
      'incision_healing':       HEAL_GRADE,
      'cut_grade':              CUT_GRADE,
      'risk_level':             RISK_LEVEL,
      'operation_level':        OPERATION_LEVEL,
      'is_elective':            IS_ELECTIVE,
      'is_emergency':           IS_EMERGENCY,
      'dept_name':              DEPT_NAME,
      'operation_desc':         OPERATION_DESC,
      'clinic_diag':            CLINIC_DIAG_NAME_VIEW
    })                                                        AS procedure_detail
  FROM read_csv(
    '/data/wlx/DATABASE/0605_small/01disk/_字段与原始数据/胸外历史病人编码后手术记录.csv',
    header=true, delim=',', quote='"', escape='"',
    null_padding=true, sample_size=-1
  )
  WHERE OPERATION_NAME IS NOT NULL
    AND IPID IS NOT NULL
) TO '/data/wlx/DATABASE/0605_small/01disk/zhujiang_xinqiao_parquet/surgery_record.parquet'
  (FORMAT PARQUET, COMPRESSION 'zstd', ROW_GROUP_SIZE 100000);
