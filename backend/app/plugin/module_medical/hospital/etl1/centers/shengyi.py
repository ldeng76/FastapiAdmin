"""广东省人民医院 center config。

数据源: docs/demodata/shengyi_valid_dicom_and_record/搜索导出.xlsx
       (200MB, 26 sheets, 全部 inline string, 单行表头)

字段映射依据:
- patient / pathology_specimen / surgery_record / genetic_test
  → docs/unified_table_schema.md §1-4 (universal tables)
- visit_record / drug_order / lab_result / imaging_report / ...
  → docs/shengyi_tables.md (核心字段; JSON 折叠段按 unified_table_schema.md 最新决策不采用)
- diagnosis / medical_history / progress_note / nursing_observation /
  icu_observation / anesthesia_event
  → docs/unified_table_schema.md §5-10 (省医追加表, 最新设计)

表头修正: 每张 sheet 都是单行表头 (行 1), 数据从行 2 开始。
Excel 列名是带全路径的中文, 如 '非隐私信息.就诊.病程记录文档.文档内容';
固定列 A='患者编号', B='当前命中就诊次数/命中就诊总次数'。
"""

from __future__ import annotations

from typing import Any

from ..config import (
    CenterConfig,
    ColumnSpec,
    DerivedSpec,
    DerivedSource,
    SheetSpec,
    register_center,
)


# ============================================================
# 辅助函数: 减少重复样板
# ============================================================

def _str(src: str, tgt: str, required: bool = False) -> ColumnSpec:
    """string 列。"""
    return ColumnSpec(src=src, tgt=tgt, type="string", required=required)


def _text(src: str, tgt: str) -> ColumnSpec:
    """text 列 (长文本, 经 normalize_newlines 清洗 \\r\\n → \\n)。"""
    return ColumnSpec(src=src, tgt=tgt, type="text", transform="normalize_newlines")


def _date(src: str, tgt: str) -> ColumnSpec:
    """date 列。"""
    return ColumnSpec(src=src, tgt=tgt, type="date", transform="parse_date")


def _ts(src: str, tgt: str) -> ColumnSpec:
    """timestamp 列。"""
    return ColumnSpec(src=src, tgt=tgt, type="timestamp", transform="parse_timestamp")


def _int(src: str, tgt: str) -> ColumnSpec:
    """int 列。"""
    return ColumnSpec(src=src, tgt=tgt, type="int", transform="to_int")


def _dec(src: str, tgt: str) -> ColumnSpec:
    """decimal 列。"""
    return ColumnSpec(src=src, tgt=tgt, type="decimal", transform="to_decimal")


# 患者编号 + visit_ordinal 是所有 sheet 的固定前 2 列
def _common_keys() -> list[ColumnSpec]:
    return [
        _str("患者编号", "patient_id", required=True),
        _str("当前命中就诊次数/命中就诊总次数", "visit_ordinal"),
    ]


# ============================================================
# 1. patient — 患者基本信息 (universal)
# ============================================================

_PATIENT = SheetSpec(
    sheet_name="非隐私信息.患者基本信息",
    target_table="patient",
    dedup_key=["patient_id"],
    columns=[
        _str("非隐私信息.患者基本信息.患者编号", "patient_id", required=True),
        _str("非隐私信息.患者基本信息.性别", "gender"),
        _date("非隐私信息.患者基本信息.出生日期", "birth_date"),
        _str("非隐私信息.患者基本信息.民族", "ethnicity"),
        _str("非隐私信息.患者基本信息.籍贯", "native_place"),
        _str("非隐私信息.患者基本信息.ABO血型", "abo_blood_type"),
        _str("非隐私信息.患者基本信息.RH血型", "rh_blood_type"),
        # visit_counts: 省医原始是 3 个独立列, 直接扁平保留
        _int("非隐私信息.患者基本信息.门诊总次数", "outpatient_count"),
        _int("非隐私信息.患者基本信息.住院总次数", "inpatient_count"),
        _int("非隐私信息.患者基本信息.就诊总次数", "visit_count"),
    ],
)


# ============================================================
# 2. visit_record — 就诊基本信息 (省医独有, 是 visit 反查字典的源)
# ============================================================

_VISIT_RECORD = SheetSpec(
    sheet_name="非隐私信息.就诊.就诊基本信息",
    target_table="visit_record",
    dedup_key=["patient_id", "visit_id"],
    visit_recovery=False,   # visit_record 自己就有 visit_id
    columns=[
        _str("患者编号", "patient_id", required=True),
        _str("非隐私信息.就诊.就诊基本信息.就诊编号", "visit_id", required=True),
        _str("当前命中就诊次数/命中就诊总次数", "visit_ordinal"),
        _str("非隐私信息.就诊.就诊基本信息.就诊类别名称", "visit_category"),
        _ts("非隐私信息.就诊.就诊基本信息.入院（就诊）时间", "admission_time"),
        _date("非隐私信息.就诊.就诊基本信息.出院日期", "discharge_date"),
        _str("非隐私信息.就诊.就诊基本信息.入院（就诊）科室", "admission_dept"),
        _str("非隐私信息.就诊.就诊基本信息.出院科室", "discharge_dept"),
        _int("非隐私信息.就诊.就诊基本信息.住院天数", "length_of_stay"),
        # 此表头有尾随空格, normalize_header 会 strip
        _str("非隐私信息.就诊.就诊基本信息.医疗付款方式 ", "payment_method"),
        _dec("非隐私信息.就诊.就诊基本信息.就诊年龄（岁）", "visit_age"),
        _str("非隐私信息.就诊.就诊基本信息.住院号", "inpatient_no"),
        _str("非隐私信息.就诊.就诊基本信息.门诊号", "outpatient_no"),
    ],
)


# ============================================================
# 3. drug_order — 药物医嘱 (省医独有)
# ============================================================

_DRUG_ORDER = SheetSpec(
    sheet_name="非隐私信息.就诊.住院医嘱.药物医嘱",
    target_table="drug_order",
    visit_recovery=True,    # 无 就诊编号 列
    columns=[
        *_common_keys(),
        # order_source: 住院医嘱固定为 'inpatient'
        _str("非隐私信息.就诊.住院医嘱.药物医嘱.药物通用名", "drug_generic_name"),
        _ts("非隐私信息.就诊.住院医嘱.药物医嘱.医嘱开始时间", "order_time"),
        # order_detail 子字段扁平保留
        _str("非隐私信息.就诊.住院医嘱.药物医嘱.长期或临时", "duration_type"),
        _str("非隐私信息.就诊.住院医嘱.药物医嘱.药物编码", "drug_code"),
        _str("非隐私信息.就诊.住院医嘱.药物医嘱.药物商品名", "drug_trade_name"),
        _ts("非隐私信息.就诊.住院医嘱.药物医嘱.医嘱停止时间", "stop_time"),
        _str("非隐私信息.就诊.住院医嘱.药物医嘱.药物规格", "specification"),
        _str("非隐私信息.就诊.住院医嘱.药物医嘱.药物剂量", "dose"),
        _str("非隐私信息.就诊.住院医嘱.药物医嘱.剂量单位", "dose_unit"),
        _str("非隐私信息.就诊.住院医嘱.药物医嘱.用药频率", "frequency"),
        _str("非隐私信息.就诊.住院医嘱.药物医嘱.用药途径", "route"),
        _str("非隐私信息.就诊.住院医嘱.药物医嘱.药物剂型", "dosage_form"),
        _str("非隐私信息.就诊.住院医嘱.药物医嘱.开嘱科室", "order_dept"),
    ],
)


# ============================================================
# 4. non_drug_order — 非药物医嘱 (省医独有)
# ============================================================

_NON_DRUG_ORDER = SheetSpec(
    sheet_name="非隐私信息.就诊.住院医嘱.非药物医嘱",
    target_table="non_drug_order",
    visit_recovery=True,
    columns=[
        *_common_keys(),
        _str("非隐私信息.就诊.住院医嘱.非药物医嘱.医嘱名称", "order_name"),
        _ts("非隐私信息.就诊.住院医嘱.非药物医嘱.医嘱开始时间", "order_start_time"),
        _ts("非隐私信息.就诊.住院医嘱.非药物医嘱.医嘱停止时间", "order_stop_time"),
        _str("非隐私信息.就诊.住院医嘱.非药物医嘱.长期或临时", "duration_type"),
        _str("非隐私信息.就诊.住院医嘱.非药物医嘱.开嘱科室", "order_dept"),
    ],
)


# ============================================================
# 5. lab_result — 检验报告子项 (省医独有)
# ============================================================

_LAB_RESULT = SheetSpec(
    sheet_name="非隐私信息.就诊.普通检验报告.检验子项",
    target_table="lab_result",
    visit_recovery=False,   # 此 sheet 有 就诊编号 列
    columns=[
        _str("患者编号", "patient_id", required=True),
        _str("非隐私信息.就诊.普通检验报告.就诊编号", "visit_id"),
        _str("非隐私信息.就诊.普通检验报告.检验子项.检验单号", "report_id"),
        _str("非隐私信息.就诊.普通检验报告.检验项目名称", "test_name"),
        _str("非隐私信息.就诊.普通检验报告.检验子项.检验子项中文名", "item_name"),
        _str("非隐私信息.就诊.普通检验报告.检验子项.检验子项结果", "item_result"),
        _dec("非隐私信息.就诊.普通检验报告.检验子项.检验子项结果数值", "item_result_value"),
        _str("非隐私信息.就诊.普通检验报告.检验子项.检验子项单位", "item_unit"),
        _dec("非隐私信息.就诊.普通检验报告.检验子项.参考下限值", "ref_lower"),
        _dec("非隐私信息.就诊.普通检验报告.检验子项.参考上限值", "ref_upper"),
        _ts("非隐私信息.就诊.普通检验报告.采集时间", "collection_time"),
        # test_detail.overall_result 扁平保留
        _str("非隐私信息.就诊.普通检验报告.检验结果", "overall_result"),
    ],
)


# ============================================================
# 6. imaging_report — 影像学报告 (省医独有)
# ============================================================

_IMAGING_REPORT = SheetSpec(
    sheet_name="非隐私信息.就诊.影像学报告",
    target_table="imaging_report",
    visit_recovery=False,
    columns=[
        _str("患者编号", "patient_id", required=True),
        _str("非隐私信息.就诊.影像学报告.就诊编号", "visit_id"),
        _str("非隐私信息.就诊.影像学报告.报告编号", "report_id"),
        _str("非隐私信息.就诊.影像学报告.检查类型名称", "exam_type"),
        _str("非隐私信息.就诊.影像学报告.检查部位", "exam_body_part"),
        _date("非隐私信息.就诊.影像学报告.检查日期", "exam_date"),
        _str("非隐私信息.就诊.影像学报告.检查项目", "exam_item"),
        # exam_detail 子字段扁平保留 (findings/impression 等是核心文本)
        _str("非隐私信息.就诊.影像学报告.检查类型代码", "type_code"),
        _str("非隐私信息.就诊.影像学报告.检查方法", "exam_method"),
        _text("非隐私信息.就诊.影像学报告.检查所见（镜下所见）", "findings"),
        _text("非隐私信息.就诊.影像学报告.印象", "impression"),
    ],
)


# ============================================================
# 7. ultrasound_report — 超声诊断报告子项 (省医独有)
# ============================================================

_ULTRASOUND_REPORT = SheetSpec(
    sheet_name="非隐私信息.就诊.超声诊断报告.检查子项",
    target_table="ultrasound_report",
    visit_recovery=False,
    columns=[
        _str("患者编号", "patient_id", required=True),
        _str("非隐私信息.就诊.超声诊断报告.就诊编号", "visit_id"),
        _str("非隐私信息.就诊.超声诊断报告.报告编号", "report_id"),
        _str("非隐私信息.就诊.超声诊断报告.检查名称", "exam_name"),
        _str("非隐私信息.就诊.超声诊断报告.部位", "body_part"),
        _date("非隐私信息.就诊.超声诊断报告.检查日期", "exam_date"),
        _text("非隐私信息.就诊.超声诊断报告.超声提示", "ultrasound_finding"),
        # 子项扁平
        _text("非隐私信息.就诊.超声诊断报告.检查所见", "findings"),
        _str("非隐私信息.就诊.超声诊断报告.检查子项.项目名称", "item_name"),
        _str("非隐私信息.就诊.超声诊断报告.检查子项.检查结果", "item_result"),
        _dec("非隐私信息.就诊.超声诊断报告.检查子项.检查结果数值", "item_value"),
        _str("非隐私信息.就诊.超声诊断报告.检查子项.检查项目单位", "item_unit"),
        _str("非隐私信息.就诊.超声诊断报告.检查子项.数据来源", "data_source"),
    ],
)


# ============================================================
# 8. ecg_report — 心电图报告子项 (省医独有)
# ============================================================

_ECG_REPORT = SheetSpec(
    sheet_name="非隐私信息.就诊.心电图报告.检查子项",
    target_table="ecg_report",
    visit_recovery=False,
    columns=[
        _str("患者编号", "patient_id", required=True),
        _str("非隐私信息.就诊.心电图报告.就诊编号", "visit_id"),
        _str("非隐私信息.就诊.心电图报告.报告编号", "report_id"),
        _date("非隐私信息.就诊.心电图报告.检查日期", "exam_date"),
        _text("非隐私信息.就诊.心电图报告.心电图诊断意见", "impression"),
        _str("非隐私信息.就诊.心电图报告.检查子项.检查子项名称", "item_name"),
        _str("非隐私信息.就诊.心电图报告.检查子项.检查子项结果", "item_result"),
    ],
)


# ============================================================
# 9. pathology_specimen — 病理检查报告 (universal)
# ============================================================
# 省医原始表名是 pathology_report, 统一更名为 pathology_specimen
# report_id → specimen_id

_PATHOLOGY_SPECIMEN = SheetSpec(
    sheet_name="非隐私信息.就诊.病理检查报告",
    target_table="pathology_specimen",
    visit_recovery=False,
    columns=[
        _str("患者编号", "patient_id", required=True),
        _str("非隐私信息.就诊.病理检查报告.就诊编号", "visit_id"),
        # report_id → specimen_id (字段重命名)
        _str("非隐私信息.就诊.病理检查报告.报告编号", "specimen_id"),
        # 省医有 exam_date 没有 submission_date/report_date/specimen_type/sampling_site
        _date("非隐私信息.就诊.病理检查报告.报告日期", "report_date"),
        _str("非隐私信息.就诊.病理检查报告.标本名称", "specimen_name"),
        _str("非隐私信息.就诊.病理检查报告.检查名称", "exam_name"),
        _str("非隐私信息.就诊.病理检查报告.检查类型", "exam_type"),
        _date("非隐私信息.就诊.病理检查报告.检查日期", "exam_date"),
        _text("非隐私信息.就诊.病理检查报告.病理诊断", "pathology_diagnosis"),
        # exam_detail 子字段扁平
        _str("非隐私信息.就诊.病理检查报告.申请单号", "request_id"),
        _text("非隐私信息.就诊.病理检查报告.肉眼所见", "gross_findings"),
        _text("非隐私信息.就诊.病理检查报告.镜下所见", "microscopic_findings"),
        _text("非隐私信息.就诊.病理检查报告.免疫组化", "immunohistochemistry"),
        _str("非隐私信息.就诊.病理检查报告.检查方法名称", "exam_method"),
        _str("非隐私信息.就诊.病理检查报告.特殊检查标志", "special_markers"),
        _text("非隐私信息.就诊.病理检查报告.备注", "remarks"),
    ],
)


# ============================================================
# 10. diagnosis — 诊断事件 (省医追加表 §5, 跨 sheet 合并)
# ============================================================
# sheet4 住院病案首页.诊断 (21,317 行, diagnosis_source='front_page')
#   + 35 列里含父级住院病案首页字段 (入院途径/状态/离院方式/血型/输血/出生地/...)
#   这些父级字段在本表里**只取诊断子项**, 父级走 visit_record.inpatient_front_page
# sheet6 就诊.诊断 (280,938 行, diagnosis_source='visit')

_DIAGNOSIS_FRONT_PAGE = SheetSpec(
    sheet_name="非隐私信息.就诊.住院病案首页.诊断",
    target_table="diagnosis",
    visit_recovery=True,    # 病案首页诊断没有独立 就诊编号 列, 走 visit_ordinal 反查
    columns=[
        *_common_keys(),
        _str("非隐私信息.就诊.住院病案首页.诊断.诊断编码", "diagnosis_code"),
        _str("非隐私信息.就诊.住院病案首页.诊断.诊断名称", "diagnosis_name"),
        _str("非隐私信息.就诊.住院病案首页.诊断.诊断类型", "diagnosis_type"),
        _str("非隐私信息.就诊.住院病案首页.诊断.诊断归转情况", "diagnosis_outcome"),
        _date("非隐私信息.就诊.住院病案首页.诊断.诊断日期", "diagnosis_date"),
        _str("非隐私信息.就诊.住院病案首页.诊断.入院病情", "admission_condition"),
        # diagnosis_no: 病案首页没有显式次序列, 留 null (ETL-2 端可按出现顺序补)
    ],
)

_DIAGNOSIS_VISIT = SheetSpec(
    sheet_name="非隐私信息.就诊.诊断",
    target_table="diagnosis",
    visit_recovery=True,
    columns=[
        *_common_keys(),
        _str("非隐私信息.就诊.诊断.诊断编码", "diagnosis_code"),
        _str("非隐私信息.就诊.诊断.诊断名称", "diagnosis_name"),
        _date("非隐私信息.就诊.诊断.诊断日期", "diagnosis_date"),
        _str("非隐私信息.就诊.诊断.是否主要诊断", "is_primary_diagnosis_raw"),
        _str("非隐私信息.就诊.诊断.诊断类别", "diagnosis_category"),
    ],
)

_DIAGNOSIS_DERIVED = DerivedSpec(
    target_table="diagnosis",
    sources=[
        DerivedSource(
            spec=_DIAGNOSIS_FRONT_PAGE,
            constants={"diagnosis_source": "front_page"},
        ),
        DerivedSource(
            spec=_DIAGNOSIS_VISIT,
            constants={"diagnosis_source": "visit"},
        ),
    ],
    # 不在 ETL-1 去重: 同 visit 同编码的诊断可能因 diagnosis_no/diagnosis_category
    # 不同而合法存在; 让 ETL-2 端按业务规则去重。
    dedup_key=None,
    visit_recovery=True,
)


# ============================================================
# 11. medical_history — 病史记录 (省医追加表 §6)
# ============================================================

_MEDICAL_HISTORY = SheetSpec(
    sheet_name="非隐私信息.就诊.病史",
    target_table="medical_history",
    visit_recovery=True,
    columns=[
        *_common_keys(),
        _text("非隐私信息.就诊.病史.主诉", "chief_complaint"),
        _text("非隐私信息.就诊.病史.现病史", "present_illness"),
        _text("非隐私信息.就诊.病史.既往史", "past_history"),
        _text("非隐私信息.就诊.病史.个人史", "personal_history"),
        _text("非隐私信息.就诊.病史.婚育史", "marriage_history"),
        _text("非隐私信息.就诊.病史.家族史", "family_history"),
        _date("非隐私信息.就诊.病史.记录日期", "record_date"),
        _str("非隐私信息.就诊.病史.数据来源", "source_document"),
    ],
)


# ============================================================
# 12. progress_note — 病程记录文档 (省医追加表 §7)
# ============================================================

_PROGRESS_NOTE = SheetSpec(
    sheet_name="非隐私信息.就诊.病程记录文档",
    target_table="progress_note",
    visit_recovery=True,
    dedup_key=["patient_id", "visit_ordinal", "note_type", "note_date", "content"],
    columns=[
        *_common_keys(),
        _text("非隐私信息.就诊.病程记录文档.文档内容", "content"),
        _date("非隐私信息.就诊.病程记录文档.记录日期", "note_date"),
        _str("非隐私信息.就诊.病程记录文档.文档类型", "note_type"),
    ],
)


# ============================================================
# 13. nursing_observation — 护理测量子项 (省医追加表 §8)
# ============================================================
# 此 sheet 有父级 就诊编号 列 (visit_id 直接可用), 不需要 visit_recovery

_NURSING_OBSERVATION = SheetSpec(
    sheet_name="非隐私信息.就诊.护理记录.测量子项",
    target_table="nursing_observation",
    visit_recovery=False,
    columns=[
        _str("患者编号", "patient_id", required=True),
        # 优先用父级 就诊编号, 没有则用子项的 (Excel 中两处都有)
        _str("非隐私信息.就诊.护理记录.就诊编号", "visit_id"),
        _str("非隐私信息.就诊.护理记录.护理记录编号", "record_id"),
        _str("非隐私信息.就诊.护理记录.测量子项.子项编号", "item_id"),
        _str("非隐私信息.就诊.护理记录.测量子项.项目编码", "item_code"),
        _str("非隐私信息.就诊.护理记录.测量子项.项目名称", "item_name"),
        _str("非隐私信息.就诊.护理记录.测量子项.项目类型", "item_category"),
        _dec("非隐私信息.就诊.护理记录.测量子项.测量结果数值", "item_value"),
        _str("非隐私信息.就诊.护理记录.测量子项.测量单位", "item_unit"),
        _ts("非隐私信息.就诊.护理记录.测量子项.测量时间", "measurement_time"),
        _str("非隐私信息.就诊.护理记录.测量子项.测量方法", "measurement_method"),
        # PHI 警告: 护士签名 是 PHI, ETL-1 阶段保留供审计, ETL-2 脱敏时剔除
        _str("非隐私信息.就诊.护理记录.护士签名", "nurse_signature"),
        _str("非隐私信息.就诊.护理记录.住院科室", "department"),
        _date("非隐私信息.就诊.护理记录.入院日期", "admission_date"),
    ],
)


# ============================================================
# 14. icu_observation — ICU 护理记录观察项 (省医追加表 §9)
# ============================================================

_ICU_OBSERVATION = SheetSpec(
    sheet_name="非隐私信息.就诊.ICU护理记录.记录详细信息",
    target_table="icu_observation",
    visit_recovery=True,
    columns=[
        *_common_keys(),
        _str("非隐私信息.就诊.ICU护理记录.住院科室", "department"),
        _date("非隐私信息.就诊.ICU护理记录.入院日期", "admission_date"),
        _ts("非隐私信息.就诊.ICU护理记录.入ICU时间", "icu_in_time"),
        _ts("非隐私信息.就诊.ICU护理记录.出ICU时间", "icu_out_time"),
        _dec("非隐私信息.就诊.ICU护理记录.体重（kg）", "weight_kg"),
        _str("非隐私信息.就诊.ICU护理记录.诊断名称", "diagnosis_summary"),
        # 子项字段 (粒度)
        _ts("非隐私信息.就诊.ICU护理记录.记录详细信息.记录日期", "record_date"),
        _str("非隐私信息.就诊.ICU护理记录.记录详细信息.项目", "item_name"),
        _str("非隐私信息.就诊.ICU护理记录.记录详细信息.结果", "item_result"),
        _dec("非隐私信息.就诊.ICU护理记录.记录详细信息.结果_数值", "item_result_value"),
    ],
)


# ============================================================
# 15. anesthesia_event — 麻醉事件 (省医追加表 §10, 跨 sheet 合并)
# ============================================================
# sheet8 用药记录 (6,085 行, event_kind='medication')
# sheet9 子项记录 (45,488 行, event_kind='observation')
# 两表共享 9 个父级会话字段 (体重/入室/出室/麻醉开始/结束/ASA/手术名/手术开始/结束)

# 父级会话字段 (两 source 共用)
_ANES_PARENT_COLS = [
    _dec("非隐私信息.就诊.麻醉信息.体重（kg）", "weight_kg"),
    _ts("非隐私信息.就诊.麻醉信息.入室时间", "room_in_time"),
    _ts("非隐私信息.就诊.麻醉信息.出室时间", "room_out_time"),
    _ts("非隐私信息.就诊.麻醉信息.麻醉开始时间", "anesthesia_start_time"),
    _ts("非隐私信息.就诊.麻醉信息.麻醉结束时间", "anesthesia_end_time"),
    _str("非隐私信息.就诊.麻醉信息.ASA分级", "asa_level"),
    _str("非隐私信息.就诊.麻醉信息.实施手术名称", "surgery_name"),
    _ts("非隐私信息.就诊.麻醉信息.手术开始时间", "surgery_start_time"),
    _ts("非隐私信息.就诊.麻醉信息.手术结束时间", "surgery_end_time"),
]

_ANES_MEDICATION = SheetSpec(
    sheet_name="非隐私信息.就诊.麻醉信息.用药记录",
    target_table="anesthesia_event",
    visit_recovery=True,
    columns=[
        *_common_keys(),
        *_ANES_PARENT_COLS,
        _str("非隐私信息.就诊.麻醉信息.用药记录.术中用药名称", "drug_name"),
        _dec("非隐私信息.就诊.麻醉信息.用药记录.术中用药剂量", "drug_dose"),
    ],
)

_ANES_OBSERVATION = SheetSpec(
    sheet_name="非隐私信息.就诊.麻醉信息.子项记录",
    target_table="anesthesia_event",
    visit_recovery=True,
    columns=[
        *_common_keys(),
        *_ANES_PARENT_COLS,
        _ts("非隐私信息.就诊.麻醉信息.子项记录.记录日期", "event_time"),
        _str("非隐私信息.就诊.麻醉信息.子项记录.项目描述", "observation_name"),
        _str("非隐私信息.就诊.麻醉信息.子项记录.项目值", "observation_value"),
        _str("非隐私信息.就诊.麻醉信息.子项记录.项目单位", "observation_unit"),
    ],
)

_ANESTHESIA_DERIVED = DerivedSpec(
    target_table="anesthesia_event",
    sources=[
        DerivedSource(spec=_ANES_MEDICATION,  constants={"event_kind": "medication"}),
        DerivedSource(spec=_ANES_OBSERVATION, constants={"event_kind": "observation"}),
    ],
    dedup_key=["patient_id", "visit_ordinal", "room_in_time",
               "event_kind", "drug_name", "observation_name"],
    visit_recovery=True,
)


# ============================================================
# 16. surgery_record — 手术记录 (universal, 跨 sheet 合并)
# ============================================================
# sheet3 住院病案首页.手术 (6,884 行): 结构化字段 (手术等级/切口愈合/麻醉方式/术者/Ⅰ助/Ⅱ助)
# sheet7 手术信息 (1,388 行): 自由文本 手术经过
# 两表靠 (patient_id, visit_ordinal, 手术日期) 关联; 列集不同, 用 NULL 补齐

_SURGERY_FRONT_PAGE = SheetSpec(
    sheet_name="非隐私信息.就诊.住院病案首页.手术",
    target_table="surgery_record",
    visit_recovery=False,   # sheet3 有 就诊编号 列
    columns=[
        _str("患者编号", "patient_id", required=True),
        _str("非隐私信息.就诊.住院病案首页.手术.就诊编号", "visit_id"),
        _str("非隐私信息.就诊.住院病案首页.手术.手术及操作名称", "procedure_name"),
        _date("非隐私信息.就诊.住院病案首页.手术.手术及操作日期", "surgery_date"),
        _str("非隐私信息.就诊.住院病案首页.手术.手术等级", "surgery_level"),
        _str("非隐私信息.就诊.住院病案首页.手术.切口愈合等级", "incision_healing"),
        _str("非隐私信息.就诊.住院病案首页.手术.麻醉方式", "anesthesia_method"),
        _str("非隐私信息.就诊.住院病案首页.手术.术者", "surgeon"),
        _str("非隐私信息.就诊.住院病案首页.手术.麻醉医生", "anesthesiologist"),
        _str("非隐私信息.就诊.住院病案首页.手术.Ⅰ助", "assistant_1"),
        _str("非隐私信息.就诊.住院病案首页.手术.Ⅱ助", "assistant_2"),
        _str("非隐私信息.就诊.住院病案首页.手术.病案序号", "case_seq"),
        _str("当前命中就诊次数/命中就诊总次数", "visit_ordinal"),
    ],
)

_SURGERY_OP_NOTE = SheetSpec(
    sheet_name="非隐私信息.就诊.手术信息",
    target_table="surgery_record",
    visit_recovery=True,    # sheet7 没有 就诊编号 列
    columns=[
        *_common_keys(),
        _str("非隐私信息.就诊.手术信息.手术名称", "procedure_name"),
        _date("非隐私信息.就诊.手术信息.手术日期", "surgery_date"),
        _str("非隐私信息.就诊.手术信息.麻醉方式", "anesthesia_method"),
        _text("非隐私信息.就诊.手术信息.手术经过", "op_note"),
    ],
)

_SURGERY_DERIVED = DerivedSpec(
    target_table="surgery_record",
    sources=[
        DerivedSource(spec=_SURGERY_FRONT_PAGE, constants={"surgery_source": "front_page"}),
        DerivedSource(spec=_SURGERY_OP_NOTE,    constants={"surgery_source": "op_note"}),
    ],
    # 不去重: 两 source 是不同的手术记录视角 (结构化 vs 自由文本), 各自独立存在
    dedup_key=None,
    visit_recovery=True,    # 因 op_note source 需要 visit 反查
)


# ============================================================
# 17. genetic_test — 基因检测 (universal, 6 个子表都空)
# ============================================================
# 6 个 sheet 全部 header-only (本导出无基因检测数据),
# 不在 config 里登记; 若未来有数据再补。
# 输出文件 genetic_test.parquet 也不生成 (与 schema 文档一致: 空表保留 schema 兼容)。
# 当前实现: 缺失 target_table 时, manifest 里也不会出现; 下游 ETL-2 看到 absence 即跳过。


# ============================================================
# CenterConfig
# ============================================================

SHENGYI_CONFIG: CenterConfig = CenterConfig(
    code="shengyi",
    display_name="广东省人民医院",
    source_kind="xlsx",
    universal_tables=[_PATIENT, _PATHOLOGY_SPECIMEN],
    hospital_tables=[
        _VISIT_RECORD,
        _DRUG_ORDER,
        _NON_DRUG_ORDER,
        _LAB_RESULT,
        _IMAGING_REPORT,
        _ULTRASOUND_REPORT,
        _ECG_REPORT,
        _MEDICAL_HISTORY,
        _PROGRESS_NOTE,
        _NURSING_OBSERVATION,
        _ICU_OBSERVATION,
    ],
    derived_tables=[_DIAGNOSIS_DERIVED, _ANESTHESIA_DERIVED, _SURGERY_DERIVED],
)

register_center(SHENGYI_CONFIG)
