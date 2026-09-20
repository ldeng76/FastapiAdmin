"""ETL-1 适配: 省医(shengyi) 2026-09 全量批次 → ETL-2 staging。

源: /data/wlx/DATABASE/13_multimodal/shengyi/extracted/非隐私信息.*.parquet
    (26 个 parquet, ~1 亿行, 全 VARCHAR; 患者编号/当前命中就诊次数/命中就诊总次数
     为无表前缀顶层列, 其余列带 "非隐私信息.<路径>" 前缀)
列前缀约定: 嵌套文件（如 超声诊断报告.检查子项.parquet）的报告级列前缀是
    文件基名（...超声诊断报告.就诊编号），子项级列前缀带子段
    （...超声诊断报告.检查子项.项目名称）—— 与文件名不同，见 F_COL。
输出: data_shengyi202609/shengyi/*.parquet (23 个 staging 表,
      列名符合 anon_etl_engine._CENTER_PARQUET_SPECS["shengyi"] 契约)

运行: cd backend && uv run python etl1_adapt_shengyi_202609.py [--only name,...]
      [--skip-large]   # 跳过 lab 4 分片(最慢), 其余照常
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import duckdb

BASE = Path("/data/wlx/DATABASE/13_multimodal/shengyi/extracted")
C = "非隐私信息"
OUT = Path(__file__).resolve().parent.parent / "data_shengyi202609" / "shengyi"

# 文件路径（read_parquet 用）
F_FILE = {
    "patient": f"{C}.患者基本信息",
    "visit": f"{C}.就诊.就诊基本信息",
    "pathology": f"{C}.就诊.病理检查报告",
    "imaging": f"{C}.就诊.影像学报告",
    "ultrasound": f"{C}.就诊.超声诊断报告.检查子项",
    "ecg": f"{C}.就诊.心电图报告.检查子项",
    "surgery": f"{C}.就诊.手术信息",
    "surgery_fp": f"{C}.就诊.住院病案首页.手术",
    "diag_fp": f"{C}.就诊.住院病案首页.诊断",
    "lab": f"{C}.就诊.普通检验报告.检验子项",
    "drug_order": f"{C}.就诊.住院医嘱.药物医嘱",
    "no_drug_order": f"{C}.就诊.住院医嘱.非药物医嘱",
    "outp_order": f"{C}.就诊.门诊药物处方",
    "anes_order": f"{C}.就诊.麻醉信息.用药记录",
    "anesthesia": f"{C}.就诊.麻醉信息.子项记录",
    "nursing": f"{C}.就诊.护理记录.测量子项",
    "icu": f"{C}.就诊.ICU护理记录.记录详细信息",
    "history": f"{C}.就诊.病史",
    "document": f"{C}.就诊.病程记录文档",
    "diagnosis": f"{C}.就诊.诊断",
    "genetic_snv": f"{C}.就诊.实体肿瘤基因检测报告.单核苷酸变异基因",
    "genetic_cnv": f"{C}.就诊.实体肿瘤基因检测报告.拷贝数变异基因",
    "genetic_indel": f"{C}.就诊.实体肿瘤基因检测报告.插入缺失突变基因",
    "genetic_fusion": f"{C}.就诊.实体肿瘤基因检测报告.融合基因",
    "genetic_other": f"{C}.就诊.实体肿瘤基因检测报告.其他变异基因",
    "genetic_drugref": f"{C}.就诊.实体肿瘤基因检测报告.用药参考",
}
# 列前缀基名（嵌套文件用报告级基名，其余同文件名）
F_COL = dict(F_FILE)
F_COL.update(
    {
        "ultrasound": f"{C}.就诊.超声诊断报告",
        "ecg": f"{C}.就诊.心电图报告",
        "surgery_fp": f"{C}.就诊.住院病案首页",
        "diag_fp": f"{C}.就诊.住院病案首页",
        "lab": f"{C}.就诊.普通检验报告",
        "anes_order": f"{C}.就诊.麻醉信息",
        "anesthesia": f"{C}.就诊.麻醉信息",
        "nursing": f"{C}.就诊.护理记录",
        "icu": f"{C}.就诊.ICU护理记录",
        "genetic_snv": f"{C}.就诊.实体肿瘤基因检测报告",
        "genetic_cnv": f"{C}.就诊.实体肿瘤基因检测报告",
        "genetic_indel": f"{C}.就诊.实体肿瘤基因检测报告",
        "genetic_fusion": f"{C}.就诊.实体肿瘤基因检测报告",
        "genetic_other": f"{C}.就诊.实体肿瘤基因检测报告",
        "genetic_drugref": f"{C}.就诊.实体肿瘤基因检测报告",
    }
)

# 嵌套子段名（子项级列前缀 = 基名 + "." + 子段 + "." + 列名）
SUB = {
    "ultrasound": "检查子项",
    "ecg": "检查子项",
    "lab": "检验子项",
    "nursing": "测量子项",
    "icu": "记录详细信息",
    "anesthesia": "子项记录",
    "anes_order": "用药记录",
    "diag_fp": "诊断",
    "surgery_fp": "手术",
    "genetic_snv": "单核苷酸变异基因",
    "genetic_cnv": "拷贝数变异基因",
    "genetic_indel": "插入缺失突变基因",
    "genetic_fusion": "融合基因",
    "genetic_other": "其他变异基因",
    "genetic_drugref": "用药参考",
}

def q(f: str) -> str:
    """列引用的双引号包装。"""
    return f'"{f}"'


def src(f: str) -> str:
    return f"read_parquet('{BASE}/{F_FILE[f]}.parquet')"


def c(f: str, name: str) -> str:
    """报告级列引用。"""
    return q(f"{F_COL[f]}.{name}")


def cs(f: str, name: str) -> str:
    """嵌套子项级列引用（基名.子段.列名）。"""
    return q(f"{F_COL[f]}.{SUB[f]}.{name}")


def run(con: duckdb.DuckDBPyConnection, name: str, sql: str) -> int:
    t0 = time.time()
    out = OUT / f"{name}.parquet"
    con.execute(f"COPY ({sql}) TO '{out}' (FORMAT PARQUET)")
    n = con.execute(f"SELECT count(*) FROM '{out}'").fetchone()[0]
    print(f"[{name}] {n:,} 行 -> {out} ({time.time() - t0:.1f}s)", flush=True)
    return n


# --------------------------------------------------------------------------- #
# 各表 SQL（staging 列名 = 引擎 spec 契约）
# --------------------------------------------------------------------------- #

SQL_PATIENT = f"""
SELECT
    {q('患者编号')} AS patient_id,
    {c('patient', '性别')} AS gender,
    {c('patient', '出生日期')} AS birth_date,
    {c('patient', '民族')} AS ethnicity,
    {c('patient', '籍贯')} AS native_place,
    {c('patient', 'ABO血型')} AS abo_blood_type,
    {c('patient', 'RH血型')} AS rh_blood_type
FROM {src('patient')}
WHERE {q('患者编号')} IS NOT NULL AND {q('患者编号')} <> ''
"""

SQL_VISIT = f"""
WITH v AS (
    SELECT
        {q('患者编号')} AS patient_id,
        {c('visit', '就诊编号')} AS visit_id,
        {c('visit', '就诊类别名称')} AS visit_category,
        {c('visit', '入院（就诊）时间')} AS admission_time,
        {c('visit', '出院日期')} AS discharge_date,
        {c('visit', '入院（就诊）科室')} AS admission_dept,
        {c('visit', '出院科室')} AS discharge_dept,
        TRY_CAST({c('visit', '住院天数')} AS INTEGER) AS length_of_stay,
        -- 源列名带尾部空格
        "{F_COL['visit']}.医疗付款方式 " AS payment_method,
        TRY_CAST({c('visit', '就诊年龄（岁）')} AS DOUBLE) AS visit_age,
        {c('visit', '住院号')} AS inpatient_no,
        {c('visit', '门诊号')} AS outpatient_no,
        ROW_NUMBER() OVER (PARTITION BY {c('visit', '就诊编号')}) AS rn
    FROM {src('visit')}
    WHERE {c('visit', '就诊编号')} IS NOT NULL AND {c('visit', '就诊编号')} <> ''
)
SELECT patient_id, visit_id, visit_category, admission_time, discharge_date,
       admission_dept, discharge_dept, length_of_stay, payment_method, visit_age,
       inpatient_no, outpatient_no
FROM v WHERE rn = 1
"""

SQL_PAHOTOLOGY = f"""
WITH adm AS (
    SELECT {c('visit', '就诊编号')} AS visit_id,
           {c('visit', '入院（就诊）时间')} AS admission_time
    FROM {src('visit')}
)
SELECT
    {q('患者编号')} AS patient_id,
    {c('pathology', '就诊编号')} AS visit_id,
    {c('pathology', '报告编号')} AS specimen_id,
    {c('pathology', '标本名称')} AS specimen_name,
    {c('pathology', '检查类型')} AS exam_type,
    -- 检查日期 54.5% 空 / 报告日期 100% 空 → coalesce 回填（引擎 exam_date 守卫）
    COALESCE(
        NULLIF({c('pathology', '检查日期')}, ''),
        NULLIF({c('pathology', '报告日期')}, ''),
        a.admission_time
    ) AS exam_date,
    {c('pathology', '病理诊断')} AS pathology_diagnosis,
    {{'检查名称': {c('pathology', '检查名称')},
      '肉眼所见': {c('pathology', '肉眼所见')},
      '镜下所见': {c('pathology', '镜下所见')},
      '免疫组化': {c('pathology', '免疫组化')},
      '检查方法名称': {c('pathology', '检查方法名称')},
      '特殊检查标志': {c('pathology', '特殊检查标志')},
      '备注': {c('pathology', '备注')}}} AS exam_detail
FROM {src('pathology')}
LEFT JOIN adm a ON a.visit_id = {c('pathology', '就诊编号')}
WHERE {c('pathology', '报告编号')} IS NOT NULL AND {c('pathology', '报告编号')} <> ''
"""
SQL_IMAGING = f"""
SELECT
    {q('患者编号')} AS patient_id,
    {c('imaging', '就诊编号')} AS visit_id,
    {c('imaging', '报告编号')} AS report_id,
    -- 检查类型名称自由文本 → 26 值新词表（Rev 2026-09-19；
    -- 详见 docs/handoff-20260919-reclassify-other-exam-type.md §5 Step 3.3）。
    -- 规则与 backend/etl2/reclassify_shengyi_other_exam_type.py 的 classify()
    -- 一致：ETL1 适配层先把 Other 子集归一化到 26 值，ETL2 引擎不再兜底 Other，
    -- 防止重跑 staging 再次产生 5.7 万行 Other 落入 CHECK 拒绝。
    CASE
        -- 核医学（代码/名称双空 + PET/骨显像等关键词）→ nuclear_medicine
        WHEN ({c('imaging', '检查类型代码')} = '' OR {c('imaging', '检查类型代码')} IS NULL)
          AND ({c('imaging', '检查类型名称')} = '' OR {c('imaging', '检查类型名称')} IS NULL)
          AND ({c('imaging', '检查项目')} ILIKE '%PET%'
            OR {c('imaging', '检查项目')} ILIKE '%骨显像%'
            OR {c('imaging', '检查项目')} ILIKE '%平面采集%'
            OR {c('imaging', '检查项目')} ILIKE '%断层采集%'
            OR {c('imaging', '检查项目')} ILIKE '%动态采集%'
            OR {c('imaging', '检查项目')} ILIKE '%全身平面采集%'
            OR {c('imaging', '检查项目')} ILIKE '%心肌血流灌注%'
            OR {c('imaging', '检查项目')} ILIKE '%心肌灌注%'
            OR {c('imaging', '检查项目')} ILIKE '%肾动态%'
            OR {c('imaging', '检查项目')} ILIKE '%甲状旁腺%'
            OR {c('imaging', '检查项目')} ILIKE '%甲状腺静态%'
            OR {c('imaging', '检查项目')} ILIKE '%唾液腺动态%'
            OR {c('imaging', '检查项目')} ILIKE '%局部淋巴显像%'
            OR {c('imaging', '检查项目')} ILIKE '%脏器断层%'
            OR {c('imaging', '检查项目')} ILIKE '%下肢深静脉%'
            OR {c('imaging', '检查项目')} ILIKE '%心肌淀粉样变%'
            OR {c('imaging', '检查项目')} ILIKE '%骨密度%'
            OR {c('imaging', '检查项目')} ILIKE '%双光子%'
            OR {c('imaging', '检查项目')} ILIKE '%能量骨密度%'
            OR {c('imaging', '检查方法')} ILIKE '%3D%'
            OR {c('imaging', '检查方法')} ILIKE '%平面采集%'
            OR {c('imaging', '检查方法')} ILIKE '%断层采集%'
            OR {c('imaging', '检查方法')} ILIKE '%动态采集%'
            OR {c('imaging', '检查方法')} ILIKE '%心肌灌注%'
            OR {c('imaging', '检查部位')} ILIKE '%会阴－颅底%'
            OR {c('imaging', '检查部位')} ILIKE '%全身骨%'
          ) THEN 'nuclear_medicine'
        -- 支气管镜 → bronchoscope
        WHEN {c('imaging', '检查类型名称')} ILIKE '%支气管镜%' THEN 'bronchoscope'
        -- 消化内镜/胸腔镜/耳鼻喉（决策 1：键义扩展为「内镜」）→ bronchoscope
        WHEN {c('imaging', '检查类型名称')} ILIKE '%胃镜%' THEN 'bronchoscope'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%肠镜%' THEN 'bronchoscope'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%十二指肠镜%' THEN 'bronchoscope'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%小肠镜%' THEN 'bronchoscope'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%ERCP%' THEN 'bronchoscope'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%治疗内镜%' THEN 'bronchoscope'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%胸腔镜%' THEN 'bronchoscope'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%耳鼻喉科%' THEN 'bronchoscope'
        -- MR 高级序列（DWI/SWI/PWI/DTI/VBM/ASL/APT）→ MRI
        WHEN {c('imaging', '检查类型名称')} ILIKE '%DWI%' THEN 'MRI'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%SWI%' THEN 'MRI'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%PWI%' THEN 'MRI'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%DTI%' THEN 'MRI'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%VBM%' THEN 'MRI'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%ASL%' THEN 'MRI'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%APT%' THEN 'MRI'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%弥散%' THEN 'MRI'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%功能成像%' THEN 'MRI'
        -- 穿刺介入 → radiology
        WHEN {c('imaging', '检查类型名称')} ILIKE '%穿刺%' THEN 'radiology'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%活检%' THEN 'radiology'
        -- 造影类 → radiology
        WHEN {c('imaging', '检查类型名称')} ILIKE '%造影%' THEN 'radiology'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%吞钡%' THEN 'radiology'
        -- 普放摄影（含 动力位/开口位/蛙形位/出口位/入口位/双斜）→ radiology
        WHEN {c('imaging', '检查类型名称')} ILIKE '%正位%' THEN 'radiology'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%侧位%' THEN 'radiology'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%斜位%' THEN 'radiology'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%动力位%' THEN 'radiology'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%开口位%' THEN 'radiology'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%双斜%' THEN 'radiology'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%平片%' THEN 'radiology'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%拼接%' THEN 'radiology'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%立位%' THEN 'radiology'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%卧位%' THEN 'radiology'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%蛙形位%' THEN 'radiology'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%蛙型位%' THEN 'radiology'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%出口位%' THEN 'radiology'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%入口位%' THEN 'radiology'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%乳腺CC%' THEN 'radiology'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%MLO%' THEN 'radiology'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%LM%' THEN 'radiology'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%AT%' THEN 'radiology'
        -- CT（平扫 / 增强 / 增强扫描；排除「主动脉全程平扫+增强」类）→ CT
        WHEN {c('imaging', '检查类型名称')} ILIKE '%平扫%' THEN 'CT'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%增强%' THEN 'CT'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%增强扫描%' THEN 'CT'
        -- 代码 5500/6153/5499/7383/6656（名称空，body_clean 实测全为 MR）→ MRI
        WHEN ({c('imaging', '检查类型名称')} = '' OR {c('imaging', '检查类型名称')} IS NULL)
          AND {c('imaging', '检查类型代码')} IN ('5500', '6153', '5499', '7383', '6656') THEN 'MRI'
        -- 会诊读片（决策 2）→ imaging_report
        WHEN {c('imaging', '检查类型名称')} ILIKE '%会诊%' THEN 'imaging_report'
        -- 三维重建加收兜底 → imaging_report
        WHEN {c('imaging', '检查类型名称')} ILIKE '%三维重建%' THEN 'imaging_report'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%加收%' THEN 'imaging_report'
        -- 旧 ETL1 关键词（保持兼容：未来若源数据按旧 ILIKE 命中也能正确归 26 值）
        WHEN {c('imaging', '检查类型名称')} ILIKE '%PET%' THEN 'nuclear_medicine'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%MR%'
          OR {c('imaging', '检查类型名称')} ILIKE '%磁共振%' THEN 'MRI'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%CT%'
          OR {c('imaging', '检查类型名称')} ILIKE '%计算机体层%' THEN 'CT'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%DR%'
          OR {c('imaging', '检查类型名称')} ILIKE '%胸片%'
          OR {c('imaging', '检查类型名称')} ILIKE '%照片%'
          OR {c('imaging', '检查类型名称')} ILIKE '%X线%'
          OR {c('imaging', '检查类型名称')} ILIKE '%放射%' THEN 'radiology'
        WHEN {c('imaging', '检查类型名称')} ILIKE '%超声%' THEN 'ultrasound'
        -- ETL1 不应再产生 'Other'（决策 3 + 0025）：兜底 → imaging_report（最宽语义，
        -- 导入时引擎会按行级 exam_type 兜底逻辑重新分类；但实际不会触发，2026-09-19
        -- 终态后要求 ETL1 自洽覆盖）。
        ELSE 'imaging_report'
    END AS exam_type,
    {c('imaging', '检查部位')} AS exam_body_part,
    {c('imaging', '检查项目')} AS exam_item,
    {c('imaging', '检查日期')} AS exam_date,
    {{'findings': {c('imaging', '检查所见（镜下所见）')},
      'impression': {c('imaging', '印象')}}} AS exam_detail
FROM {src('imaging')}
WHERE {c('imaging', '报告编号')} IS NOT NULL AND {c('imaging', '报告编号')} <> ''
"""
WHERE {c('ultrasound', '报告编号')} IS NOT NULL AND {c('ultrasound', '报告编号')} <> ''
GROUP BY 1, 2, 3
"""

SQL_ECG = f"""
SELECT
    {q('患者编号')} AS patient_id,
    {c('ecg', '就诊编号')} AS visit_id,
    {c('ecg', '报告编号')} AS report_id,
    ANY_VALUE({c('ecg', '检查日期')}) AS exam_date,
    ANY_VALUE({c('ecg', '心电图诊断意见')}) AS ecg_diagnosis,
    LIST(
        {{'item_name': {cs('ecg', '检查子项名称')},
          'item_result': {cs('ecg', '检查子项结果')}}}
        ORDER BY {cs('ecg', '检查子项名称')}
    ) AS sub_items
FROM {src('ecg')}
WHERE {c('ecg', '报告编号')} IS NOT NULL AND {c('ecg', '报告编号')} <> ''
GROUP BY 1, 2, 3
"""

SQL_GENETIC = f"""
WITH
snv AS (
    SELECT 'snv' AS src,
           {q('患者编号')} AS patient_id,
           {c('genetic_snv', '就诊编号')} AS visit_id,
           CASE
             WHEN {cs('genetic_snv', '检测单号')} IS NOT NULL
              AND {cs('genetic_snv', '检测单号')} <> ''
             THEN {cs('genetic_snv', '检测单号')}
             ELSE 'SYG-' || CAST(
               ROW_NUMBER() OVER (
                 PARTITION BY {q('患者编号')},
                              {c('genetic_snv', '就诊编号')}
                 ORDER BY {cs('genetic_snv', '子项编号')}
               ) AS VARCHAR) || '-' || SUBSTRING(SHA256('snv' || '|' || CAST({q('患者编号')} AS VARCHAR) || '|' || CAST({c('genetic_snv', '就诊编号')} AS VARCHAR) || '|' || COALESCE(CAST({cs('genetic_snv', '子项编号')} AS VARCHAR), ''))::VARCHAR, 1, 8)
           END AS report_id,
           {c('genetic_snv', '检测项目名称')} AS test_name,
           {{'子项编号': {cs('genetic_snv', '子项编号')},
             '基因名称': {cs('genetic_snv', '基因名称')},
             '结果正常标志': {cs('genetic_snv', '结果正常标志')},
             '转录本': {cs('genetic_snv', '转录本')},
             '外显子': {cs('genetic_snv', '外显子')},
             'CDS突变': {cs('genetic_snv', 'CDS突变')},
             '氨基酸突变': {cs('genetic_snv', '氨基酸突变')},
             '突变丰度': {cs('genetic_snv', '突变丰度')},
             '结果解读': {cs('genetic_snv', '结果解读')},
             '检测方法': {cs('genetic_snv', '检测方法')},
             '变异意义': {cs('genetic_snv', '变异意义')},
             '纯合/杂合': {cs('genetic_snv', '纯合/杂合')},
             '变异类型': {cs('genetic_snv', '变异类型')}}} AS variant
    FROM {src('genetic_snv')}
),
cnv AS (
    SELECT 'cnv' AS src,
           {q('患者编号')} AS patient_id,
           {c('genetic_cnv', '就诊编号')} AS visit_id,
           CASE
             WHEN {cs('genetic_cnv', '检测单号')} IS NOT NULL
              AND {cs('genetic_cnv', '检测单号')} <> ''
             THEN {cs('genetic_cnv', '检测单号')}
             ELSE 'SYG-' || CAST(
               ROW_NUMBER() OVER (
                 PARTITION BY {q('患者编号')},
                              {c('genetic_cnv', '就诊编号')}
                 ORDER BY {cs('genetic_cnv', '子项编号')}
               ) AS VARCHAR) || '-' || SUBSTRING(SHA256('cnv' || '|' || CAST({q('患者编号')} AS VARCHAR) || '|' || CAST({c('genetic_cnv', '就诊编号')} AS VARCHAR) || '|' || COALESCE(CAST({cs('genetic_cnv', '子项编号')} AS VARCHAR), ''))::VARCHAR, 1, 8)
           END AS report_id,
           {c('genetic_cnv', '检测项目名称')} AS test_name,
           {{'子项编号': {cs('genetic_cnv', '子项编号')},
             '基因名称': {cs('genetic_cnv', '基因名称')},
             '结果正常标志': {cs('genetic_cnv', '结果正常标志')},
             '转录本': {cs('genetic_cnv', '转录本')},
             '拷贝数': {cs('genetic_cnv', '拷贝数')},
             '结果解读': {cs('genetic_cnv', '结果解读')},
             '检测方法': {cs('genetic_cnv', '检测方法')},
             '变异意义': {cs('genetic_cnv', '变异意义')},
             '纯合/杂合': {cs('genetic_cnv', '纯合/杂合')},
             '变异类型': {cs('genetic_cnv', '变异类型')}}} AS variant
    FROM {src('genetic_cnv')}
),
indel AS (
    SELECT 'indel' AS src,
           {q('患者编号')} AS patient_id,
           {c('genetic_indel', '就诊编号')} AS visit_id,
           CASE
             WHEN {cs('genetic_indel', '检测单号')} IS NOT NULL
              AND {cs('genetic_indel', '检测单号')} <> ''
             THEN {cs('genetic_indel', '检测单号')}
             ELSE 'SYG-' || CAST(
               ROW_NUMBER() OVER (
                 PARTITION BY {q('患者编号')},
                              {c('genetic_indel', '就诊编号')}
                 ORDER BY {cs('genetic_indel', '子项编号')}
               ) AS VARCHAR) || '-' || SUBSTRING(SHA256('indel' || '|' || CAST({q('患者编号')} AS VARCHAR) || '|' || CAST({c('genetic_indel', '就诊编号')} AS VARCHAR) || '|' || COALESCE(CAST({cs('genetic_indel', '子项编号')} AS VARCHAR), ''))::VARCHAR, 1, 8)
           END AS report_id,
           {c('genetic_indel', '检测项目名称')} AS test_name,
           {{'子项编号': {cs('genetic_indel', '子项编号')},
             '基因名称': {cs('genetic_indel', '基因名称')},
             '结果正常标志': {cs('genetic_indel', '结果正常标志')},
             '转录本': {cs('genetic_indel', '转录本')},
             '外显子': {cs('genetic_indel', '外显子')},
             'CDS突变': {cs('genetic_indel', 'CDS突变')},
             '氨基酸突变': {cs('genetic_indel', '氨基酸突变')},
             'DNA片段总数': {cs('genetic_indel', 'DNA片段总数')},
             'DNA异常片段总数': {cs('genetic_indel', 'DNA异常片段总数')},
             '突变丰度': {cs('genetic_indel', '突变丰度')},
             '结果解读': {cs('genetic_indel', '结果解读')},
             '检测方法': {cs('genetic_indel', '检测方法')},
             '变异意义': {cs('genetic_indel', '变异意义')},
             '纯合/杂合': {cs('genetic_indel', '纯合/杂合')},
             '变异类型': {cs('genetic_indel', '变异类型')},
             '遗传性疾病/遗传方式': {cs('genetic_indel', '遗传性疾病/遗传方式')},
             '遗传风险评估建议': {cs('genetic_indel', '遗传风险评估建议')}}} AS variant
    FROM {src('genetic_indel')}
),
fusion AS (
    SELECT 'fusion' AS src,
           {q('患者编号')} AS patient_id,
           {c('genetic_fusion', '就诊编号')} AS visit_id,
           CASE
             WHEN {cs('genetic_fusion', '检测单号')} IS NOT NULL
              AND {cs('genetic_fusion', '检测单号')} <> ''
             THEN {cs('genetic_fusion', '检测单号')}
             ELSE 'SYG-' || CAST(
               ROW_NUMBER() OVER (
                 PARTITION BY {q('患者编号')},
                              {c('genetic_fusion', '就诊编号')}
                 ORDER BY {cs('genetic_fusion', '子项编号')}
               ) AS VARCHAR) || '-' || SUBSTRING(SHA256('fusion' || '|' || CAST({q('患者编号')} AS VARCHAR) || '|' || CAST({c('genetic_fusion', '就诊编号')} AS VARCHAR) || '|' || COALESCE(CAST({cs('genetic_fusion', '子项编号')} AS VARCHAR), ''))::VARCHAR, 1, 8)
           END AS report_id,
           {c('genetic_fusion', '检测项目名称')} AS test_name,
           {{'子项编号': {cs('genetic_fusion', '子项编号')},
             '融合类型': {cs('genetic_fusion', '融合类型')},
             '融合位置': {cs('genetic_fusion', '融合位置')},
             '融合基因名称': {cs('genetic_fusion', '融合基因名称')},
             '结果正常标志': {cs('genetic_fusion', '结果正常标志')},
             '融合基因染色体': {cs('genetic_fusion', '融合基因染色体')},
             '融合位点': {cs('genetic_fusion', '融合位点')},
             'DNA片段总数': {cs('genetic_fusion', 'DNA片段总数')},
             'DNA异常片段总数': {cs('genetic_fusion', 'DNA异常片段总数')},
             '突变丰度': {cs('genetic_fusion', '突变丰度')},
             '结果解读': {cs('genetic_fusion', '结果解读')},
             '检测方法': {cs('genetic_fusion', '检测方法')},
             '变异意义': {cs('genetic_fusion', '变异意义')},
             '纯合/杂合': {cs('genetic_fusion', '纯合/杂合')}}} AS variant
    FROM {src('genetic_fusion')}
),
other AS (
    SELECT 'other' AS src,
           {q('患者编号')} AS patient_id,
           {c('genetic_other', '就诊编号')} AS visit_id,
           CASE
             WHEN {cs('genetic_other', '检测单号')} IS NOT NULL
              AND {cs('genetic_other', '检测单号')} <> ''
             THEN {cs('genetic_other', '检测单号')}
             ELSE 'SYG-' || CAST(
               ROW_NUMBER() OVER (
                 PARTITION BY {q('患者编号')},
                              {c('genetic_other', '就诊编号')}
                 ORDER BY {cs('genetic_other', '子项编号')}
               ) AS VARCHAR) || '-' || SUBSTRING(SHA256('other' || '|' || CAST({q('患者编号')} AS VARCHAR) || '|' || CAST({c('genetic_other', '就诊编号')} AS VARCHAR) || '|' || COALESCE(CAST({cs('genetic_other', '子项编号')} AS VARCHAR), ''))::VARCHAR, 1, 8)
           END AS report_id,
           {c('genetic_other', '检测项目名称')} AS test_name,
           {{'子项编号': {cs('genetic_other', '子项编号')},
             '基因名称': {cs('genetic_other', '基因名称')},
             '结果正常标志': {cs('genetic_other', '结果正常标志')},
             '转录本': {cs('genetic_other', '转录本')},
             '外显子': {cs('genetic_other', '外显子')},
             'CDS突变': {cs('genetic_other', 'CDS突变')},
             '氨基酸突变': {cs('genetic_other', '氨基酸突变')},
             '突变丰度': {cs('genetic_other', '突变丰度')},
             '融合类型': {cs('genetic_other', '融合类型')},
             '融合位置': {cs('genetic_other', '融合位置')},
             '融合基因染色体': {cs('genetic_other', '融合基因染色体')},
             '融合位点': {cs('genetic_other', '融合位点')},
             '拷贝数': {cs('genetic_other', '拷贝数')},
             'DNA片段总数': {cs('genetic_other', 'DNA片段总数')},
             'DNA异常片段总数': {cs('genetic_other', 'DNA异常片段总数')},
             '结果解读': {cs('genetic_other', '结果解读')},
             '检测方法': {cs('genetic_other', '检测方法')},
             '变异意义': {cs('genetic_other', '变异意义')},
             '纯合/杂合': {cs('genetic_other', '纯合/杂合')},
             '变异类型': {cs('genetic_other', '变异类型')},
             '遗传性疾病/遗传方式': {cs('genetic_other', '遗传性疾病/遗传方式')},
             '遗传风险评估建议': {cs('genetic_other', '遗传风险评估建议')}}} AS variant
    FROM {src('genetic_other')}
),
drugref AS (
    SELECT 'drugref' AS src,
           {q('患者编号')} AS patient_id,
           {c('genetic_drugref', '就诊编号')} AS visit_id,
           CASE
             WHEN {cs('genetic_drugref', '检测单号')} IS NOT NULL
              AND {cs('genetic_drugref', '检测单号')} <> ''
             THEN {cs('genetic_drugref', '检测单号')}
             ELSE 'SYG-' || CAST(
               ROW_NUMBER() OVER (
                 PARTITION BY {q('患者编号')},
                              {c('genetic_drugref', '就诊编号')}
                 ORDER BY {cs('genetic_drugref', '子项编号')}
               ) AS VARCHAR) || '-' || SUBSTRING(SHA256('drugref' || '|' || CAST({q('患者编号')} AS VARCHAR) || '|' || CAST({c('genetic_drugref', '就诊编号')} AS VARCHAR) || '|' || COALESCE(CAST({cs('genetic_drugref', '子项编号')} AS VARCHAR), ''))::VARCHAR, 1, 8)
           END AS report_id,
           {c('genetic_drugref', '检测项目名称')} AS test_name,
           {{'子项编号': {cs('genetic_drugref', '子项编号')},
             '药物编号': {cs('genetic_drugref', '药物编号')},
             '药物名称': {cs('genetic_drugref', '药物名称')},
             '临床意义': {cs('genetic_drugref', '临床意义')},
             '适用疾病': {cs('genetic_drugref', '适用疾病')},
             '证据级别': {cs('genetic_drugref', '证据级别')},
             '参考文献': {cs('genetic_drugref', '参考文献')}}} AS variant
    FROM {src('genetic_drugref')}
),
u AS (
    SELECT * FROM snv
    UNION ALL SELECT * FROM cnv
    UNION ALL SELECT * FROM indel
    UNION ALL SELECT * FROM fusion
    UNION ALL SELECT * FROM other
    UNION ALL SELECT * FROM drugref
)
SELECT patient_id, visit_id, report_id,
       ANY_VALUE(test_name) AS test_name,
       {{'snv':      LIST(variant) FILTER (WHERE src = 'snv'),
         'cnv':      LIST(variant) FILTER (WHERE src = 'cnv'),
         'indel':    LIST(variant) FILTER (WHERE src = 'indel'),
         'fusion':   LIST(variant) FILTER (WHERE src = 'fusion'),
         'other':    LIST(variant) FILTER (WHERE src = 'other'),
         'drug_ref': LIST(variant) FILTER (WHERE src = 'drugref')}} AS variants
FROM u
GROUP BY 1, 2, 3
"""

SQL_SURGERY = f"""
WITH sv AS (
    SELECT ROW_NUMBER() OVER () AS sid,
           {q('患者编号')} AS pid,
           {c('surgery', '手术名称')} AS procedure_name,
           {c('surgery', '手术日期')} AS surgery_date,
           {c('surgery', '麻醉方式')} AS anesthesia,
           {c('surgery', '手术经过')} AS op_detail
    FROM {src('surgery')}
    WHERE {q('患者编号')} IS NOT NULL AND {q('患者编号')} <> ''
      AND {c('surgery', '手术名称')} IS NOT NULL AND {c('surgery', '手术名称')} <> ''
),
-- 住院就诊窗口 join：手术日期落在 入院~出院（缺出院则入院+90d）内；多命中取最近入院
adm AS (
    SELECT sv.sid,
           ROW_NUMBER() OVER (
               PARTITION BY sv.sid
               ORDER BY TRY_CAST(a.admission_time AS DATE) DESC
           ) AS rn,
           a.visit_id
    FROM sv
    JOIN (
        SELECT {c('visit', '就诊编号')} AS visit_id,
               {q('患者编号')} AS pid,
               {c('visit', '入院（就诊）时间')} AS admission_time,
               {c('visit', '出院日期')} AS discharge_date
        FROM {src('visit')}
    ) a
      ON a.pid = sv.pid
     AND TRY_CAST(sv.surgery_date AS DATE) >= TRY_CAST(a.admission_time AS DATE)
     AND TRY_CAST(sv.surgery_date AS DATE) <= COALESCE(
             TRY_CAST(a.discharge_date AS DATE),
             TRY_CAST(a.admission_time AS DATE) + INTERVAL 90 DAY)
),
from_surgery AS (
    SELECT sv.pid AS patient_id,
           a.visit_id,
           sv.procedure_name,
           sv.surgery_date,
           {{'麻醉方式': sv.anesthesia, '手术经过': sv.op_detail}} AS procedure_detail
    FROM sv JOIN adm a ON a.sid = sv.sid AND a.rn = 1
),
-- 病案首页.手术：自带就诊编号
from_front_page AS (
    SELECT {q('患者编号')} AS patient_id,
           {cs('surgery_fp', '就诊编号')} AS visit_id,
           {cs('surgery_fp', '手术及操作名称')} AS procedure_name,
           {cs('surgery_fp', '手术及操作日期')} AS surgery_date,
           {{'手术等级': {cs('surgery_fp', '手术等级')},
             '切口愈合等级': {cs('surgery_fp', '切口愈合等级')},
             '麻醉方式': {cs('surgery_fp', '麻醉方式')},
             '术者': {cs('surgery_fp', '术者')},
             '麻醉医生': {cs('surgery_fp', '麻醉医生')},
             'Ⅰ助': {cs('surgery_fp', 'Ⅰ助')},
             'Ⅱ助': {cs('surgery_fp', 'Ⅱ助')},
             '病案序号': {cs('surgery_fp', '病案序号')}}} AS procedure_detail
    FROM {src('surgery_fp')}
    WHERE {cs('surgery_fp', '手术及操作名称')} IS NOT NULL
      AND {cs('surgery_fp', '手术及操作名称')} <> ''
)
SELECT patient_id, visit_id, procedure_name, surgery_date, procedure_detail
FROM from_surgery
UNION ALL
SELECT patient_id, visit_id, procedure_name, surgery_date, procedure_detail
FROM from_front_page
"""

_SQL_LAB_BASE = f"""
SELECT
    {q('患者编号')} AS patient_id,
    {c('lab', '就诊编号')} AS visit_id,
    {c('lab', '检验单号')} AS report_id,
    {c('lab', '检验项目名称')} AS test_name,
    {cs('lab', '检验子项中文名')} AS item_name,
    {cs('lab', '检验子项结果')} AS item_result,
    {cs('lab', '检验子项结果数值')} AS item_result_value,
    {cs('lab', '检验子项单位')} AS item_unit,
    {c('lab', '采集时间')} AS collection_time,
    {cs('lab', '参考上限值')} AS ref_upper,
    {cs('lab', '参考下限值')} AS ref_lower
FROM {src('lab')}
WHERE {c('lab', '检验单号')} IS NOT NULL AND {c('lab', '检验单号')} <> ''
"""


def sql_lab_part(i: int) -> str:
    """44M 行拆 4 片（哈希分片，跨运行确定）防单文件内存峰值超限。"""
    return (
        f"SELECT * FROM ({_SQL_LAB_BASE}) "
        f"WHERE MOD(HASH(patient_id, report_id, item_name), 4) = {i}"
    )


def sql_order_drug() -> str:
    o = "drug_order"
    return f"""
SELECT
    {q('患者编号')} AS patient_id,
    NULL::VARCHAR AS visit_id,
    -- 通用名 5.59M 空 → coalesce 商品名恢复
    COALESCE(NULLIF({c(o, '药物通用名')}, ''), NULLIF({c(o, '药物商品名')}, '')) AS order_name,
    {c(o, '医嘱开始时间')} AS order_time,
    {{'长期或临时': {c(o, '长期或临时')},
      '药物编码': {c(o, '药物编码')},
      '药物通用名': {c(o, '药物通用名')},
      '药物商品名': {c(o, '药物商品名')},
      '医嘱停止时间': {c(o, '医嘱停止时间')},
      '药物规格': {c(o, '药物规格')},
      '药物剂量': {c(o, '药物剂量')},
      '剂量单位': {c(o, '剂量单位')},
      '用药频率': {c(o, '用药频率')},
      '用药途径': {c(o, '用药途径')},
      '药物剂型': {c(o, '药物剂型')},
      '开嘱科室': {c(o, '开嘱科室')}}} AS order_detail
FROM {src(o)}
"""


def sql_order_no_drug() -> str:
    o = "no_drug_order"
    return f"""
SELECT
    {q('患者编号')} AS patient_id,
    NULL::VARCHAR AS visit_id,
    {c(o, '医嘱名称')} AS order_name,
    {c(o, '医嘱开始时间')} AS order_time,
    {{'长期或临时': {c(o, '长期或临时')},
      '医嘱停止时间': {c(o, '医嘱停止时间')},
      '开嘱科室': {c(o, '开嘱科室')}}} AS order_detail
FROM {src(o)}
"""


def sql_order_outp() -> str:
    r = "outp_order"
    return f"""
SELECT
    {q('患者编号')} AS patient_id,
    NULL::VARCHAR AS visit_id,
    {c(r, '药物名称')} AS order_name,
    {c(r, '处方开立日期')} AS order_time,
    {{'处方编号': {c(r, '处方编号')},
      '药品类型': {c(r, '药品类型')},
      '药物规格': {c(r, '药物规格')},
      '药物剂型': {c(r, '药物剂型')},
      '药物使用次剂量': {c(r, '药物使用次剂量')},
      '药物使用频次': {c(r, '药物使用频次')},
      '用药途径名称': {c(r, '用药途径名称')},
      '用药天数': {c(r, '用药天数')},
      '处方开立科室名称': {c(r, '处方开立科室名称')},
      '开立医生签名': {c(r, '开立医生签名')}}} AS order_detail
FROM {src(r)}
"""


def sql_order_anesthesia() -> str:
    a = "anes_order"
    return f"""
SELECT
    {q('患者编号')} AS patient_id,
    NULL::VARCHAR AS visit_id,
    {cs(a, '术中用药名称')} AS order_name,
    {c(a, '麻醉开始时间')} AS order_time,
    {{'术中用药剂量': {cs(a, '术中用药剂量')},
      'ASA分级': {c(a, 'ASA分级')},
      '实施手术名称': {c(a, '实施手术名称')},
      '手术开始时间': {c(a, '手术开始时间')},
      '手术结束时间': {c(a, '手术结束时间')},
      '入室时间': {c(a, '入室时间')},
      '出室时间': {c(a, '出室时间')},
      '麻醉开始时间': {c(a, '麻醉开始时间')},
      '麻醉结束时间': {c(a, '麻醉结束时间')},
      '体重（kg）': {c(a, '体重（kg）')}}} AS order_detail
FROM {src(a)}
"""

SQL_DIAGNOSIS = f"""
SELECT
    {q('患者编号')} AS patient_id,
    {c('diagnosis', '诊断编码')} AS diagnosis_code,
    {c('diagnosis', '诊断名称')} AS diagnosis_name,
    {c('diagnosis', '诊断日期')} AS diagnosis_date,
    {c('diagnosis', '是否主要诊断')} AS is_primary,
    {c('diagnosis', '诊断类别')} AS diagnosis_category
FROM {src('diagnosis')}
"""

SQL_DIAGNOSIS_INPATIENT = f"""
SELECT
    {q('患者编号')} AS patient_id,
    {cs('diag_fp', '诊断编码')} AS diagnosis_code,
    {cs('diag_fp', '诊断名称')} AS diagnosis_name,
    COALESCE(NULLIF({cs('diag_fp', '诊断日期')}, ''), NULL) AS diagnosis_date,
    NULL::VARCHAR AS is_primary,
    {cs('diag_fp', '诊断类型')} || '_' || {c('diag_fp', '住院次数')} AS diagnosis_category,
    {{'诊断归转情况': {cs('diag_fp', '诊断归转情况')},
      '入院病情': {cs('diag_fp', '入院病情')},
      '入院途径': {c('diag_fp', '入院途径')},
      '入院状态名称': {c('diag_fp', '入院状态名称')},
      '离院方式': {c('diag_fp', '离院方式')},
      '住院次数': {c('diag_fp', '住院次数')},
      'ABO血型': {c('diag_fp', 'ABO血型')},
      'RH血型': {c('diag_fp', 'RH血型')},
      '输血成分_全血': {c('diag_fp', '输血成分_全血')},
      '输血成分_血浆': {c('diag_fp', '输血成分_血浆')},
      '输血成分_血小板': {c('diag_fp', '输血成分_血小板')},
      '输血成分_红细胞': {c('diag_fp', '输血成分_红细胞')},
      '输血成分_其他': {c('diag_fp', '输血成分_其他')},
      '新生儿出生体重（克）': {c('diag_fp', '新生儿出生体重（克）')},
      '新生儿入院体重（克）': {c('diag_fp', '新生儿入院体重（克）')},
      '抢救次数': {c('diag_fp', '抢救次数')},
      '抢救成功次数': {c('diag_fp', '抢救成功次数')},
      '一级护理天数': {c('diag_fp', '一级护理天数')},
      '二级护理天数': {c('diag_fp', '二级护理天数')},
      '是否为手术后并发症': {c('diag_fp', '是否为手术后并发症')}}} AS detail
FROM {src('diag_fp')}
"""

SQL_DOCUMENT = f"""
SELECT
    {q('患者编号')} AS patient_id,
    {c('document', '文档类型')} AS doc_type,
    {c('document', '记录日期')} AS doc_date,
    {c('document', '文档内容')} AS doc_content
FROM {src('document')}
"""

SQL_HISTORY = f"""
SELECT
    {q('患者编号')} AS patient_id,
    {c('history', '主诉')} AS chief_complaint,
    {c('history', '现病史')} AS present_illness,
    {c('history', '既往史')} AS past_history,
    {c('history', '个人史')} AS personal_history,
    {c('history', '婚育史')} AS marriage_history,
    {c('history', '家族史')} AS family_history,
    {c('history', '记录日期')} AS record_date,
    {c('history', '数据来源')} AS data_source
FROM {src('history')}
"""

SQL_NURSING = f"""
SELECT
    {q('患者编号')} AS patient_id,
    {c('nursing', '就诊编号')} AS visit_id,
    {cs('nursing', '项目名称')} AS item_name,
    {cs('nursing', '测量结果')} AS item_result,
    {cs('nursing', '测量结果数值')} AS item_result_value,
    {cs('nursing', '测量单位')} AS item_unit,
    {cs('nursing', '测量时间')} AS obs_time,
    {{'项目类型': {cs('nursing', '项目类型')},
      '项目编码': {cs('nursing', '项目编码')},
      '测量方法': {cs('nursing', '测量方法')},
      '护理类型': {c('nursing', '护理类型')},
      '护理记录编号': {c('nursing', '护理记录编号')},
      '住院科室': {c('nursing', '住院科室')},
      '护士签名': {c('nursing', '护士签名')}}} AS detail
FROM {src('nursing')}
"""

SQL_ICU = f"""
SELECT
    {q('患者编号')} AS patient_id,
    NULL::VARCHAR AS visit_id,
    {cs('icu', '项目')} AS item_name,
    {cs('icu', '结果')} AS item_result,
    {cs('icu', '结果_数值')} AS item_result_value,
    NULL::VARCHAR AS item_unit,
    {cs('icu', '记录日期')} AS obs_time,
    {{'记录日期': {c('icu', '记录日期')},
      '入院日期': {c('icu', '入院日期')},
      '入ICU时间': {c('icu', '入ICU时间')},
      '出ICU时间': {c('icu', '出ICU时间')},
      '体重（kg）': {c('icu', '体重（kg）')},
      '住院科室': {c('icu', '住院科室')},
      '诊断名称': {c('icu', '诊断名称')}}} AS detail
FROM {src('icu')}
"""

SQL_ANESTHESIA = f"""
SELECT
    {q('患者编号')} AS patient_id,
    NULL::VARCHAR AS visit_id,
    {cs('anesthesia', '项目描述')} AS item_name,
    {cs('anesthesia', '项目值')} AS item_result,
    {cs('anesthesia', '项目值')} AS item_result_value,
    {cs('anesthesia', '项目单位')} AS item_unit,
    {cs('anesthesia', '记录日期')} AS obs_time,
    {{'ASA分级': {c('anesthesia', 'ASA分级')},
      '实施手术名称': {c('anesthesia', '实施手术名称')},
      '手术开始时间': {c('anesthesia', '手术开始时间')},
      '手术结束时间': {c('anesthesia', '手术结束时间')},
      '麻醉开始时间': {c('anesthesia', '麻醉开始时间')},
      '麻醉结束时间': {c('anesthesia', '麻醉结束时间')},
      '入室时间': {c('anesthesia', '入室时间')},
      '出室时间': {c('anesthesia', '出室时间')},
      '体重（kg）': {c('anesthesia', '体重（kg）')}}} AS detail
FROM {src('anesthesia')}
"""

# name -> sql 生成器（顺序 = spec 顺序）
TABLES: dict[str, object] = {
    "patient": SQL_PATIENT,
    "visit_record": SQL_VISIT,
    "pahology_specimen": SQL_PAHOTOLOGY,
    "imaging_report": SQL_IMAGING,
    "ultrasound_report": SQL_ULTRASOUND,
    "ecg_report": SQL_ECG,
    "genetic_report": SQL_GENETIC,
    "surgery_record": SQL_SURGERY,
    "lab_result_p1": sql_lab_part(0),
    "lab_result_p2": sql_lab_part(1),
    "lab_result_p3": sql_lab_part(2),
    "lab_result_p4": sql_lab_part(3),
    "drug_order": sql_order_drug(),
    "no_drug_order": sql_order_no_drug(),
    "outp_order": sql_order_outp(),
    "anesthesia_order": sql_order_anesthesia(),
    "diagnosis": SQL_DIAGNOSIS,
    "diagnosis_inpatient": SQL_DIAGNOSIS_INPATIENT,
    "clinical_document": SQL_DOCUMENT,
    "medical_history": SQL_HISTORY,
    "nursing_observation": SQL_NURSING,
    "icu_observation": SQL_ICU,
    "anesthesia_observation": SQL_ANESTHESIA,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="逗号分隔的表名子集")
    ap.add_argument("--skip-large", action="store_true", help="跳过 lab 4 分片")
    args = ap.parse_args()

    only = {s.strip() for s in args.only.split(",") if s.strip()}
    names = [n for n in TABLES if not only or n in only]
    if args.skip_large:
        names = [n for n in names if not n.startswith("lab_result_")]
    if not names:
        print("无匹配表", file=sys.stderr)
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET threads = 12")
    con.execute("SET memory_limit = '64GB'")
    total_t0 = time.time()
    for name in names:
        run(con, name, str(TABLES[name]))
    print(f"全部完成 {len(names)} 表, 总耗时 {time.time() - total_t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
