/**
 * 业务字段渲染 schema。
 *
 * FieldRenderer 按 key 在本表查找，决定走：
 * - `table`：数组 → ElTable（DiagnosesTableCard）
 * - `kv`：dict → 分层卡片（KeyValueCard）
 * - 未命中 → 折叠 JSON 树（FaJsonPretty 兜底）
 *
 * 添加新业务字段：在此处声明；无需改动 FieldRenderer.vue。
 */

import type { VNode } from "vue";

export type TableColumn = {
  /** 数据字段 */
  key: string;
  /** 列头中文 */
  label: string;
  width?: number;
  minWidth?: number;
  /** 自定义单元格渲染；返回 VNode 或字符串 */
  formatter?: (value: unknown, row: Record<string, unknown>) => VNode | string;
};

export type TableSchema = {
  type: "table";
  /** 卡片标题 */
  title: string;
  columns: TableColumn[];
};

export type KvSchema = {
  type: "kv";
  /** 卡片标题 */
  title: string;
  /** 一级 key → 中文 label；优先于 FIELD_LABELS */
  labelMap?: Record<string, string>;
  /** 长文本字符数阈值，超过则启用折叠按钮，默认 120 */
  longTextThreshold?: number;
};

export type FieldSchema = TableSchema | KvSchema;

/** 诊断数组 → 表格（主诊断用红色 Tag 标识） */
const diagnosesColumns: TableColumn[] = [
  { key: "code", label: "诊断编码", width: 110 },
  { key: "name", label: "诊断名称", minWidth: 140 },
  { key: "type", label: "类型", minWidth: 130 },
  { key: "category", label: "类别", minWidth: 130 },
  {
    key: "is_primary",
    label: "主诊断",
    width: 80,
    formatter: (v) => {
      const s = v === true || v === "是" || v === 1 || v === "1";
      return s ? "是" : v == null ? "-" : "否";
    },
  },
  { key: "diagnosis_date", label: "诊断日期", width: 120 },
  { key: "outcome", label: "转归", minWidth: 100 },
  { key: "admission_condition", label: "入院病情", minWidth: 100 },
];

/** 临床文档数组 → 表格 */
const clinicalDocsColumns: TableColumn[] = [
  { key: "doc_type", label: "文档类型", minWidth: 200 },
  { key: "record_date", label: "记录日期", width: 120 },
  {
    key: "content",
    label: "内容",
    minWidth: 240,
    formatter: (v) => {
      if (v == null || v === "") return "-";
      const s = String(v);
      return s.length > 200 ? `${s.slice(0, 200)}…` : s;
    },
  },
];

export const FIELD_SCHEMAS: Record<string, FieldSchema> = {
  // ─── 诊断数组 → 表格 ───
  diagnoses: {
    type: "table",
    title: "诊断",
    columns: diagnosesColumns,
  },

  // ─── 临床文档数组 → 表格 ───
  clinical_documents: {
    type: "table",
    title: "临床文档",
    columns: clinicalDocsColumns,
  },

  // ─── 病史 / 既往病史 dict → 分层卡片 ───
  medical_history: {
    type: "kv",
    title: "既往病史",
    labelMap: {
      data_source: "数据来源",
      record_date: "记录日期",
      chief_complaint: "主诉",
      present_illness: "现病史",
      past_history: "既往史",
      personal_history: "个人史",
      family_history: "家族史",
      allergic_history: "过敏史",
      physical_exam: "体格检查",
      auxiliary_exam: "辅助检查",
    },
  },

  // ─── 病案首页 dict → 分层卡片（含 transfusion/allergy 等嵌套） ───
  inpatient_front_page: {
    type: "kv",
    title: "病案首页",
    labelMap: {
      birth_place: "出生地",
      birth_province: "出生省",
      native_place: "籍贯",
      occupation: "职业",
      marital_status: "婚姻状况",
      transfusion: "输血史",
      allergy: "过敏史",
      chief_complaint: "主诉",
      present_illness: "现病史",
      past_history: "既往史",
      operation_history: "手术史",
      family_history: "家族史",
      discharge_diagnosis: "出院诊断",
    },
  },

  // ─── 患者卡：人口学 ───
  demographics: {
    type: "kv",
    title: "人口学",
    labelMap: {
      occupation: "职业",
      marital_status: "婚姻状况",
      education: "学历",
      income: "收入",
      insurance: "医保",
      address: "地址",
      birth_place: "出生地",
      native_place: "籍贯",
    },
  },
};

/** 按 key 取业务 schema，未命中返回 undefined（走兜底）。 */
export function getFieldSchema(key: string): FieldSchema | undefined {
  return FIELD_SCHEMAS[key];
}
