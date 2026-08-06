/**
 * 字段名 → 中文 label 字典。
 *
 * 由 detail.vue 迁移至此（2026-08-05）。覆盖：
 * - 基础 / anon 主键 / 就诊 / 手术 / 检验结果 / 医嘱 / 检查 + 报告 + detail
 * - 历史跨阶段保留字段（med_* 兼容）
 *
 * 扩充（2026-08-05）：新增病史 / 病案首页 / 人口学常用键，
 * 用于 KeyValueCard 在没有 schema.labelMap 时也能给出中文 label。
 */

export const FIELD_LABELS: Record<string, string> = {
  // ───── 基础 ─────
  patient_id: "患者编号",
  center_code: "中心编码",
  birth_date: "出生日期",
  ethnicity: "民族",
  native_place: "籍贯",
  sex: "性别",
  abo_blood_type: "ABO血型",
  rh_blood_type: "RH血型",
  smoking_status: "吸烟状态",
  first_nodule_date: "首结节日期",
  bmi: "BMI",

  // ───── anon 主键 ─────
  anon_visit_id: "就诊编号",
  anon_exam_id: "检查编号",
  visit_ordinal: "就诊序号",

  // ───── 就诊 ─────
  visit_category: "就诊类别",
  admission_time: "入院时间",
  discharge_date: "出院日期",
  admission_dept: "入院科室",
  discharge_dept: "出院科室",
  length_of_stay: "住院天数",
  payment_method: "支付方式",
  visit_age: "就诊年龄",
  visit_detail_json: "就诊详情(JSONB)",

  // ───── 手术 ─────
  surgery_id: "手术编号",
  surgery_date: "手术日期",
  procedure_name: "术式",
  resection_scope: "切除范围",
  surgical_approach: "手术入路",
  procedure_detail: "手术详情",

  // ───── 检验结果 ─────
  lab_result_id: "检验编号",
  report_id: "报告号",
  test_name: "检验项目",
  item_name: "检验项",
  item_result: "结果",
  item_result_value: "数值结果",
  item_unit: "单位",
  collection_time: "采集时间",
  lab_detail_json: "检验详情(JSONB)",

  // ───── 医嘱 ─────
  order_id: "医嘱编号",
  order_type: "医嘱类型",
  order_name: "医嘱名称",
  order_time: "医嘱时间",
  order_source: "医嘱来源",
  order_detail_json: "医嘱详情(JSONB)",

  // ───── 检查 + 报告 + detail ─────
  exam_type: "检查类型",
  exam_date: "检查日期",
  body_clean: "报告正文",
  pii_replaced_count: "已替换 PII 数",
  review_status: "审核状态",
  detail_type: "详情类型",
  detail_ordinal: "详情序号",
  detail_json: "检查详情(JSONB)",

  // ───── 诊断数组子键 ─────
  code: "诊断编码",
  name: "诊断名称",
  type: "类型",
  category: "类别",
  is_primary: "是否主诊断",
  diagnosis_date: "诊断日期",
  outcome: "转归",
  admission_condition: "入院病情",

  // ───── 临床文档子键 ─────
  doc_type: "文档类型",
  content: "内容",
  record_date: "记录日期",

  // ───── 病史 / 既往病史（visit_detail_json.medical_history） ─────
  data_source: "数据来源",
  chief_complaint: "主诉",
  present_illness: "现病史",
  past_history: "既往史",
  personal_history: "个人史",
  family_history: "家族史",
  allergic_history: "过敏史",
  physical_exam: "体格检查",
  auxiliary_exam: "辅助检查",

  // ───── 病案首页（visit_detail_json.inpatient_front_page） ─────
  birth_place: "出生地",
  birth_province: "出生省",
  occupation: "职业",
  marital_status: "婚姻状况",
  transfusion: "输血史",
  allergy: "过敏史",
  operation_history: "手术史",
  discharge_diagnosis: "出院诊断",
  // 输血史子项
  rbc: "红细胞",
  plasma: "血浆",
  platelet: "血小板",
  other: "其他",

  // ───── 人口学（patient_meta.demographics） ─────
  education: "学历",
  income: "收入",
  insurance: "医保",
  address: "地址",

  // ───── 历史/已退役字段（保留兼容） ─────
  specimen_id: "标本号",
  test_id: "检测号",
  nodule_no: "结节编号",
  nodule_location: "结节位置",
  long_diameter: "长径(mm)",
  density_type: "密度类型",
  nodule_morphology: "形态征象",
  nodule_quantitative: "定量参数",
  follow_up_comparison: "对比变化",
  exam_meta: "检查元数据",
  ki67_pct: "Ki-67(%)",
  markers: "标志物",
  test_method: "检测方法",
  variant_type: "变异类型",
  test_meta: "检测元数据",
  variant_result: "变异结果",
  driver_mutations: "驱动基因",
  immune_markers: "免疫标志物",
  histology_class: "组织学分类",
  pathology_diagnosis: "病理诊断",
  tumor_total_size_mm: "肿瘤大小(mm)",
  specimen_type: "标本类型",
  sampling_site: "取材部位",
  adenocarcinoma_subtypes: "腺癌亚型",
  tumor_measurement: "肿瘤测量",
  high_risk_factors: "高危因素",
  staging: "分期",
  specimen_meta: "标本元数据",
  exam_body_part: "检查部位",
  exam_item: "检查项目",
  order_detail: "医嘱详情",
  drug_generic_name: "药物",
  ref_lower: "参考下限",
  ref_upper: "参考上限",
  diagnoses: "诊断",
  demographics: "人口学",
  medical_history: "既往病史",
};

/** 取字段中文 label，未命中回退为原 key。 */
export function getFieldLabel(key: string): string {
  return FIELD_LABELS[key] || key;
}
