"""南方医科大学珠江医院 center config。

数据源: docs/demodata/珠江的CT与病理数据/CT与病理数据.xlsx
       (~30 MB, 1 个数据 sheet 'Select v_exam_patient_rpt', 202,618 行,
        11 列原始字段, 来自 HIS 视图 v_exam_patient_rpt)

源字段:
    EXAM_NO       报告/检查唯一号
    PAT_LOCAL_ID  患者院内 ID
    SICK_ID       就诊号 (同 PAT 可能多个 SICK, 但本次 ETL-1 不使用)
    NAME          患者姓名 (PHI, 不入库)
    SEX           性别 (男/女)
    AGE           年龄文本 (如 '67岁', 不入库)
    EXAM_CLASS    'ＣＴ' (全角) 或 '病理' (半角)
    DESCRIPTION   检查所见 (长文本)
    IMPRESSION    诊断意见 (长文本)
    EXAM_DATE     检查日期 (YYYY-MM-DD)

字段映射依据:
    patient            → unified_table_schema.md §1 (核心字段并集, 珠江填 source_center='珠江')
    nodule_imaging     → zhujiang_xinqiao_tables.md (一次 CT 一行, xlsx 粒度)
    pathology_specimen → unified_table_schema.md §2 (specimen_id 用 EXAM_NO 充任)

约束:
    - 不做 visit_id 反查 (xlsx 无 visit_ordinal, 框架 visit_recovery=False)
    - 整张 sheet 是 HIS 视图原始 dump, 包含大量非肺结节数据 (宫颈细胞学/肝病等);
      通过 WHERE 子句在 SQL 层做行级过滤 (text contains 肺/结节/胸部CT/肺癌/腺癌/鳞癌/小细胞)
    - first_nodule_date 不在 ETL-1 内派生, 由 scripts/etl1_postprocess_zhujiang.py 二阶段注入
"""

from __future__ import annotations

from ..column_specs import col_date, col_str, col_text
from ..config import (
    CenterConfig,
    SheetSpec,
    register_center,
)


SHEET = "Select v_exam_patient_rpt"

# WHERE 子句集中定义, 方便维护
WHERE_CT = "EXAM_CLASS = 'ＣＴ'"  # 全角 CT 字面量, 跟原始 xlsx 一致
WHERE_PATHOLOGY = (
    "EXAM_CLASS = '病理' "
    "AND ("
    "IMPRESSION ILIKE '%肺%' "
    "OR IMPRESSION ILIKE '%结节%' "
    "OR IMPRESSION ILIKE '%肺癌%' "
    "OR IMPRESSION ILIKE '%腺癌%' "
    "OR IMPRESSION ILIKE '%鳞癌%' "
    "OR IMPRESSION ILIKE '%小细胞%' "
    "OR DESCRIPTION ILIKE '%肺%'"
    ")"
)


# ============================================================
# 1. patient — 患者基本信息 (本次仅基于 CT 行 DISTINCT)
# ============================================================

_PATIENT = SheetSpec(
    sheet_name=SHEET,
    target_table="patient",
    dedup_key=["patient_id"],
    where=WHERE_CT,
    columns=[
        col_str("PAT_LOCAL_ID", "patient_id", required=True),
        col_str("SEX", "gender"),
        # NAME / AGE / SICK_ID / EXAM_NO / EXAM_CLASS / EXAM_DATE / DESCRIPTION / IMPRESSION
        # 全部丢弃 (patient 表只关心身份字段; PHI 在 ETL-2 脱敏)
    ],
)


# ============================================================
# 2. nodule_imaging — 结节影像 (一次 CT 一行)
# ============================================================

_NODULE_IMAGING = SheetSpec(
    sheet_name=SHEET,
    target_table="nodule_imaging",
    dedup_key=["exam_id"],
    where=(
        "EXAM_CLASS = 'ＣＴ' "
        "AND ("
        "IMPRESSION ILIKE '%肺%' "
        "OR IMPRESSION ILIKE '%结节%' "
        "OR DESCRIPTION ILIKE '%肺%' "
        "OR DESCRIPTION ILIKE '%结节%' "
        "OR DESCRIPTION ILIKE '%胸部CT%'"
        ")"
    ),
    columns=[
        col_str("PAT_LOCAL_ID", "patient_id", required=True),
        col_str("EXAM_NO", "exam_id", required=True),
        col_date("EXAM_DATE", "exam_date"),
        # xlsx 无结构化结节字段 (nodule_no / location / long_diameter / density_type),
        # 全部 NULL, 等后续 ETL-2 用 IMPRESSION 文本解析或人工标注补齐
        # visit_id 留 NULL (xlsx 无 visit_ordinal)
        col_text("DESCRIPTION", "findings"),
        col_text("IMPRESSION", "impression"),
    ],
)


# ============================================================
# 3. pathology_specimen — 病理标本 (一份报告一行)
# ============================================================

_PATHOLOGY_SPECIMEN = SheetSpec(
    sheet_name=SHEET,
    target_table="pathology_specimen",
    dedup_key=["specimen_id"],
    where=WHERE_PATHOLOGY,
    columns=[
        col_str("PAT_LOCAL_ID", "patient_id", required=True),
        # 字段重命名: EXAM_NO → specimen_id (满足统一表 schema)
        col_str("EXAM_NO", "specimen_id", required=True),
        col_date("EXAM_DATE", "exam_date"),
        col_text("IMPRESSION", "pathology_diagnosis"),
        # 其余结构化字段 (specimen_type / sampling_site / histology_class /
        # tumor_total_size_mm / staging / high_risk_factors / adenocarcinoma_subtypes /
        # tumor_measurement / specimen_meta) 全部 NULL, 后续由 ETL-2 用文本解析或人工标注补齐
    ],
)


# ============================================================
# CenterConfig
# ============================================================

ZHUJIANG_CONFIG: CenterConfig = CenterConfig(
    code="zhujiang",
    display_name="南方医科大学珠江医院",
    source_kind="xlsx",
    # 4 张通用表本次不生成 (按用户决定: 只生成有数据的表)
    universal_tables=[],
    hospital_tables=[_PATIENT, _NODULE_IMAGING, _PATHOLOGY_SPECIMEN],
    derived_tables=[],
    output_dir_template="data/{code}",
)

register_center(ZHUJIANG_CONFIG)