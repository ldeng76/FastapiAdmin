"""预置映射模板（Python 常量，非数据库表）。

注册医院时按 template_code 将模板里的规则批量复制到 med_mapping_rule；
之后该医院的映射规则可独立编辑，与模板解耦。

当前已实现模板：
- zhujiang_xinqiao：珠江-新桥（parquet 已是统一英文格式，几乎全 rename）

待实现（数据就绪后补充）：
- shengyi：省医（原始为中文长字段名 CSV，需 100+ 条规则 + 嵌套展平）

字段映射约定：
- src_table/src_field：医院原始数据的表名/字段名（珠江-新桥 parquet 的表名和列名）
- tgt_table/tgt_field：统一表的表名（med_ 前缀）/列名
- transform_type=rename：字段值不变，仅名称映射
- transform_type=constant：目标字段填充固定值（transform_value）
- transform_type=expression：目标字段经注册函数变换（transform_value=函数 key）
"""

from __future__ import annotations

# 单条规则的类型（与 med_mapping_rule 列对应）
RuleDef = dict[str, str | int | None]


def _rename(src_table: str, tgt_table: str, fields: list[tuple[str, str, str]]) -> list[RuleDef]:
    """批量生成 rename 规则。

    参数:
        src_table: 源表名
        tgt_table: 目标表名（med_* 前缀）
        fields: [(src_field, tgt_field, description), ...]

    返回:
        规则字典列表
    """
    return [
        {
            "src_table": src_table,
            "src_field": sf,
            "tgt_table": tgt_table,
            "tgt_field": tf,
            "transform_type": "rename",
            "transform_value": None,
            "description": desc,
            "sort": i,
        }
        for i, (sf, tf, desc) in enumerate(fields)
    ]


def _constant(
    src_table: str, tgt_table: str, tgt_field: str, value: str, desc: str, sort: int
) -> RuleDef:
    """生成 constant 规则。"""
    return {
        "src_table": src_table,
        "src_field": "__constant__",
        "tgt_table": tgt_table,
        "tgt_field": tgt_field,
        "transform_type": "constant",
        "transform_value": value,
        "description": desc,
        "sort": sort,
    }


# --------------------------------------------------------------------------- #
# 珠江-新桥模板
# --------------------------------------------------------------------------- #
# 珠江-新桥 parquet 已是统一英文格式，故映射几乎全是 rename。
# src_table 为 parquet 文件名（去掉 .parquet），tgt_table 为 med_* 表名。

_ZHUJIANG_PATIENT = _rename(
    "patient", "med_patient",
    [
        ("patient_id", "patient_id", "患者编号"),
        ("source_center", "source_center", "来源中心"),
        ("gender", "gender", "性别"),
        ("birth_date", "birth_date", "出生日期"),
        ("ethnicity", "ethnicity", "民族"),
        ("native_place", "native_place", "籍贯"),
        ("abo_blood_type", "abo_blood_type", "ABO血型"),
        ("rh_blood_type", "rh_blood_type", "RH血型"),
        ("smoking_status", "smoking_status", "吸烟状态"),
        ("first_nodule_date", "first_nodule_date", "首次发现结节日期"),
        ("demographics", "demographics", "人口学扩展(JSON)"),
        ("medical_history", "medical_history", "既往病史(JSON)"),
    ],
)

_ZHUJIANG_PATHOLOGY = _rename(
    "pathology_specimen", "med_pathology_specimen",
    [
        ("patient_id", "patient_id", "患者编号"),
        ("visit_id", "visit_id", "就诊编号"),
        ("specimen_id", "specimen_id", "标本号"),
        ("submission_date", "submission_date", "送检日期"),
        ("report_date", "report_date", "报告日期"),
        ("specimen_type", "specimen_type", "标本类型"),
        ("sampling_site", "sampling_site", "取材部位"),
        ("histology_class", "histology_class", "组织学大类"),
        ("pathology_diagnosis", "pathology_diagnosis", "病理诊断"),
        ("tumor_total_size_mm", "tumor_total_size_mm", "肿瘤总大小(mm)"),
        ("specimen_meta", "specimen_meta", "标本元数据(JSON)"),
        ("adenocarcinoma_subtypes", "adenocarcinoma_subtypes", "腺癌亚型(JSON)"),
        ("tumor_measurement", "tumor_measurement", "肿瘤测量(JSON)"),
        ("high_risk_factors", "high_risk_factors", "高危因素(JSON)"),
        ("staging", "staging", "病理分期(JSON)"),
        ("exam_meta", "exam_meta", "检查元数据(JSON)"),
    ],
)

_ZHUJIANG_SURGERY = _rename(
    "surgery_record", "med_surgery_record",
    [
        ("patient_id", "patient_id", "患者编号"),
        ("visit_id", "visit_id", "就诊编号"),
        ("surgery_date", "surgery_date", "手术日期"),
        ("procedure_name", "procedure_name", "手术及操作名称"),
        ("resection_scope", "resection_scope", "切除范围"),
        ("surgical_approach", "surgical_approach", "手术入路"),
        ("procedure_detail", "procedure_detail", "手术详情(JSON)"),
    ],
)

_ZHUJIANG_GENETIC = _rename(
    "genetic_test", "med_genetic_test",
    [
        ("patient_id", "patient_id", "患者编号"),
        ("visit_id", "visit_id", "就诊编号"),
        ("test_id", "test_id", "检测唯一号"),
        ("test_date", "test_date", "检测日期"),
        ("variant_type", "variant_type", "变异类型"),
        ("test_method", "test_method", "检测方法"),
        ("test_meta", "test_meta", "检测元数据(JSON)"),
        ("driver_mutations", "driver_mutations", "驱动基因突变(JSON)"),
        ("immune_markers", "immune_markers", "免疫相关标志物(JSON)"),
    ],
)

_ZHUJIANG_NODULE_IMAGING = _rename(
    "nodule_imaging", "med_nodule_imaging",
    [
        ("exam_id", "exam_id", "检查唯一号"),
        ("patient_id", "patient_id", "患者编号"),
        ("exam_date", "exam_date", "检查日期时间"),
        ("exam_type", "exam_type", "检查类型"),
        ("nodule_no", "nodule_no", "结节编号"),
        ("nodule_location", "nodule_location", "结节位置"),
        ("long_diameter", "long_diameter", "长径(mm)"),
        ("density_type", "density_type", "密度类型"),
        ("exam_meta", "exam_meta", "检查元数据(JSON)"),
        ("nodule_morphology", "nodule_morphology", "结节形态(JSON)"),
        ("nodule_quantitative", "nodule_quantitative", "结节定量(JSON)"),
        ("follow_up_comparison", "follow_up_comparison", "对比既往(JSON)"),
    ],
)

_ZHUJIANG_IHC = _rename(
    "ihc_result", "med_ihc_result",
    [
        ("patient_id", "patient_id", "患者编号"),
        ("specimen_id", "specimen_id", "病理标本号"),
        ("ki67_pct", "ki67_pct", "Ki-67(%)"),
        ("markers", "markers", "免疫组化标志物(JSON)"),
    ],
)

_ZHUJIANG_FOLLOW_UP = _rename(
    "follow_up", "med_follow_up",
    [
        ("patient_id", "patient_id", "患者编号"),
        ("last_followup_date", "last_followup_date", "末次随访日期"),
        ("recurrence", "recurrence", "是否复发"),
        ("survival_status", "survival_status", "生存状态"),
        ("treatment_detail", "treatment_detail", "辅助治疗详情(JSON)"),
        ("recurrence_detail", "recurrence_detail", "复发详情(JSON)"),
    ],
)

ZHUJIANG_XINQIAO_RULES: list[RuleDef] = (
    _ZHUJIANG_PATIENT
    + _ZHUJIANG_PATHOLOGY
    + _ZHUJIANG_SURGERY
    + _ZHUJIANG_GENETIC
    + _ZHUJIANG_NODULE_IMAGING
    + _ZHUJIANG_IHC
    + _ZHUJIANG_FOLLOW_UP
)


# --------------------------------------------------------------------------- #
# 模板注册表
# --------------------------------------------------------------------------- #

TEMPLATES: dict[str, dict] = {
    "zhujiang_xinqiao": {
        "name": "珠江-新桥完整映射",
        "description": "珠江-新桥全量表映射（parquet 已是统一英文格式，共 7 张表）",
        "rules": ZHUJIANG_XINQIAO_RULES,
    },
    # 省医模板待省医原始 parquet 数据就绪后补充
    # "shengyi": {
    #     "name": "广东省人民医院（省医）完整映射",
    #     "description": "省医全量表映射（原始为中文长字段名 CSV）",
    #     "rules": [...],
    # },
}


def get_template(template_code: str) -> dict | None:
    """按编码获取模板。返回 {name, description, rules} 或 None。"""
    return TEMPLATES.get(template_code)


def list_templates() -> list[dict]:
    """列出所有可用模板（不含 rules 详情，仅元信息）。"""
    return [
        {
            "code": code,
            "name": tpl["name"],
            "description": tpl["description"],
            "rule_count": len(tpl["rules"]),
        }
        for code, tpl in TEMPLATES.items()
    ]
