"""陆军军医大学新桥医院 center config。

数据源: docs/demodata/01_disk_字段与原始数据_2新桥/
    ├── 1_5万例排除术后_单一影像号_已处理/  (6 × CSV, 17 列, 纯 CT)
    └── 2_5万例时序影像_带病理_新_待处理/   (6 × CSV, 30 列, CT + 病理 LEFT JOIN)

源字段 (中文带点号):
    patients.*                          患者级冗余字段 (姓名/性别/出生日期/身份证)
    检查报告.患者ID                      患者院内 ID (8 位数字, 真实 ID, 用于 HMAC)
    检查报告.性别                        男/女
    检查报告.报告中图像编号                = DICOM SOPInstanceUID 末段数字, 检查级 ID
    检查报告.检查日期时间                 检查日期 (子目录 1: 1956/1/17; 子目录 2: 1971-09-12)
    检查报告.检查类别                    'CT' (半角)
    检查报告.检查所见                    长文本
    检查报告.检查结论                    长文本 (用于肺结节 WHERE 过滤)
    病理.病理系统编号                    病理标本号 (specimen_id); 多值/可空
    病理.送检时间 / 报告时间              逗号分隔多值 (ETL-2 用 string_split+UNNEST)
    病理.送检部位 / 肉眼所见 / 镜下所见   长文本
    病理.病理诊断 / 报告状态              长文本 / 状态码

约束:
    - source_kind='csv' → core 走 CsvReader (DuckDB 原生 read_csv)
    - 父目录传入 CsvReader; sheet_name 为子目录名
    - 不做 visit_id 反查 (无 visit_ordinal, visit_recovery=False)
    - 姓名 / 身份证号 = `***` (源已脱敏); 不入库
    - 病理多值字段原样入 parquet (一行 = 一份病理报告), ETL-2 拆

字段映射依据:
    patient            → unified_table_schema.md §1 (核心字段并集, 新桥填 source_center='xinqiao')
    nodule_imaging     → zhujiang_xinqiao_tables.md (一次 CT 一行, 肺结节 ILIKE 过滤)
    pathology_specimen → unified_table_schema.md §2 (specimen_id = 病理.病理系统编号)
"""

from __future__ import annotations

from ..column_specs import col_date, col_str, col_text
from ..config import (
    CenterConfig,
    SheetSpec,
    register_center,
)


# 子目录名 (作为 SheetSpec.sheet_name, 也就是 CsvReader.read_sheet 的入参)
SUB_1 = "1_5万例排除术后_单一影像号_已处理"
SUB_2 = "2_5万例时序影像_带病理_新_待处理"

# WHERE 子句集中定义, 方便维护
# 半角 'CT' (新桥字面量) + 肺/结节 ILIKE 过滤
# 中文/点号列名必须用双引号包裹 (DuckDB SQL 语义; 否则会被解析为 schema.table.column)
WHERE_CT_LUNG_NODULE = (
    "\"检查报告.检查类别\" = 'CT' "
    "AND ("
    "\"检查报告.检查结论\" ILIKE '%肺%' "
    "OR \"检查报告.检查结论\" ILIKE '%结节%' "
    "OR \"检查报告.检查所见\" ILIKE '%肺%' "
    "OR \"检查报告.检查所见\" ILIKE '%结节%'"
    ")"
)

WHERE_PATHOLOGY_HAS_SPECIMEN = (
    "\"病理.病理系统编号\" IS NOT NULL AND \"病理.病理系统编号\" <> ''"
)


# ============================================================
# SheetSpec 派生顺序:
#   1) SUB1 的 patient (去重得到子目录 1 的患者集)
#   2) SUB2 的 patient (扩展患者集; run_etl1 顺序处理, 后者按 dedup_key 去重)
#   3) SUB1 的 nodule_imaging
#   4) SUB2 的 nodule_imaging
#   5) SUB2 的 pathology_specimen
#
# 说明: patient/nodule_imaging 在两个子目录都派生, 因为:
#   - SUB1 的患者可能不在 SUB2 (SUB2 是"时序+病理", 只覆盖有病理的病人)
#   - SUB2 的 nodule_imaging 包含更详细的临床诊断
# run_etl1 会按顺序写 parquet (后者覆盖前者, dedup_key=patient_id / exam_id 自动去重)
# ============================================================


# ------------------------------------------------------------
# 1. SUB1 patient
# ------------------------------------------------------------
_PATIENT_FROM_SUB1 = SheetSpec(
    sheet_name=SUB_1,
    target_table="patient",
    dedup_key=["patient_id"],
    where=WHERE_CT_LUNG_NODULE,
    columns=[
        col_str("检查报告.患者ID", "patient_id", required=True),
        col_str("检查报告.性别", "gender"),
        # patients.* 与 检查报告.* 冗余, 取检查报告侧 (更靠近事件)
        # 姓名 / 身份证号 = `***` 不入库
        # 出生日期 TRY_CAST 为出生年份, 简化字段 (后续 ETL-2 可补 birth_year)
    ],
)


# ------------------------------------------------------------
# 2. SUB2 patient (扩展)
# ------------------------------------------------------------
_PATIENT_FROM_SUB2 = SheetSpec(
    sheet_name=SUB_2,
    target_table="patient",
    dedup_key=["patient_id"],
    where=WHERE_CT_LUNG_NODULE,
    columns=[
        col_str("检查报告.患者ID", "patient_id", required=True),
        col_str("检查报告.性别", "gender"),
    ],
)


# ------------------------------------------------------------
# 3. SUB1 nodule_imaging
# ------------------------------------------------------------
_NODULE_IMAGING_FROM_SUB1 = SheetSpec(
    sheet_name=SUB_1,
    target_table="nodule_imaging",
    dedup_key=["exam_id"],
    where=WHERE_CT_LUNG_NODULE,
    columns=[
        col_str("检查报告.患者ID", "patient_id", required=True),
        col_str("检查报告.报告中图像编号", "exam_id", required=True),
        col_date("检查报告.检查日期时间", "exam_date"),
        col_text("检查报告.检查所见", "findings"),
        col_text("检查报告.检查结论", "impression"),
        # 子目录 1 无 visit_ordinal; visit_id 留 NULL
        # 子目录 1 无结构化结节字段 (nodule_no / location / long_diameter / density_type),
        # 全部 NULL, 等 ETL-2 用 IMPRESSION 文本解析或人工标注补齐
    ],
)


# ------------------------------------------------------------
# 4. SUB2 nodule_imaging
# ------------------------------------------------------------
_NODULE_IMAGING_FROM_SUB2 = SheetSpec(
    sheet_name=SUB_2,
    target_table="nodule_imaging",
    dedup_key=["exam_id"],
    where=WHERE_CT_LUNG_NODULE,
    columns=[
        col_str("检查报告.患者ID", "patient_id", required=True),
        col_str("检查报告.报告中图像编号", "exam_id", required=True),
        col_date("检查报告.检查日期时间", "exam_date"),
        col_text("检查报告.检查所见", "findings"),
        col_text("检查报告.检查结论", "impression"),
    ],
)


# ------------------------------------------------------------
# 5. SUB2 pathology_specimen
# ------------------------------------------------------------
_PATHOLOGY_SPECIMEN_FROM_SUB2 = SheetSpec(
    sheet_name=SUB_2,
    target_table="pathology_specimen",
    dedup_key=["specimen_id"],
    where=WHERE_PATHOLOGY_HAS_SPECIMEN,
    columns=[
        col_str("检查报告.患者ID", "patient_id", required=True),
        # 字段重命名: 病理.病理系统编号 → specimen_id
        col_str("病理.病理系统编号", "specimen_id", required=True),
        # 多值字段: 逗号分隔, 原样入 parquet (type=text 走 normalize_newlines)
        # ETL-2 用 string_split + UNNEST 拆开为多行
        col_text("病理.送检时间", "specimen_received_at"),
        col_text("病理.报告时间", "report_released_at"),
        col_text("病理.送检部位", "sampling_site"),
        col_text("病理.病理所见-肉眼所见", "gross_findings"),
        col_text("病理.病理所见-镜下所见", "microscopic_findings"),
        col_text("病理.病理诊断", "pathology_diagnosis"),
        col_text("病理.报告状态", "report_status"),
        # exam_date 用 CT 报告日期作为关联锚 (病理有独立报告时间, 但 CT 日期作为
        # 与 nodule_imaging join 的桥梁)
        col_date("检查报告.检查日期时间", "exam_date"),
    ],
)


# ============================================================
# CenterConfig
# ============================================================

XINQIAO_CONFIG: CenterConfig = CenterConfig(
    code="xinqiao",
    display_name="陆军军医大学新桥医院",
    source_kind="csv",
    # 4 张通用表本次不生成
    universal_tables=[],
    hospital_tables=[
        _PATIENT_FROM_SUB1,
        _PATIENT_FROM_SUB2,
        _NODULE_IMAGING_FROM_SUB1,
        _NODULE_IMAGING_FROM_SUB2,
        _PATHOLOGY_SPECIMEN_FROM_SUB2,
    ],
    derived_tables=[],
    output_dir_template="data/{code}",
)

register_center(XINQIAO_CONFIG)