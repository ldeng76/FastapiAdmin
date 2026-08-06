/** 医院管理模块 · TypeScript 类型定义 */

/** 医院就绪状态（与后端 lifecycle_status 字段值一致） */
export type HospitalLifecycleStatus =
  | "registered" // 已注册
  | "mapping_configured" // 映射已配置
  | "data_imported" // 数据已导入
  | "live"; // 已上线

/** 医院列表行 */
export interface HospitalTable {
  id: number;
  code: string;
  name: string;
  full_name: string | null;
  tenant_id: number;
  /** 就绪状态 */
  lifecycle_status: HospitalLifecycleStatus;
  /** 原始数据目录路径 */
  data_dir: string | null;
  /** 最近导入时间 */
  last_import_time: string | null;
  /** 最近导入行数 */
  last_import_rows: number;
  /** 导入失败时的错误信息 */
  import_error: string | null;
  /** 创建时间 */
  created_time: string;
}

/** 医院注册/编辑表单 */
export interface HospitalFormData {
  code: string;
  name: string;
  full_name?: string;
  contact_name?: string;
  contact_phone?: string;
  contact_email?: string;
  address?: string;
  data_dir?: string;
  template_code?: string;
}

/** 映射规则转换类型 */
export type MappingTransformType = "rename" | "constant" | "expression";

/** 映射规则行 */
export interface MappingRuleRow {
  id?: number;
  hospital_id?: number;
  src_table: string;
  src_field: string;
  tgt_table: string;
  tgt_field: string;
  transform_type: MappingTransformType;
  transform_value: string | null;
  description: string | null;
  sort: number;
  created_time?: string;
}

/** 映射规则批量提交 */
export interface MappingRuleBatchData {
  rules: Omit<MappingRuleRow, "id" | "hospital_id" | "created_time">[];
}

/** 映射模板 */
export interface MappingTemplate {
  code: string;
  name: string;
  description: string;
  rule_count: number;
}

/** 映射模板详情（含规则列表） */
export interface MappingTemplateDetail extends MappingTemplate {
  rules: Array<Omit<MappingRuleRow, "id" | "hospital_id" | "created_time">>;
}

/** ETL 导入任务状态 */
export type EtlImportStatusValue =
  | "idle"
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "unknown";

/** ETL 导入状态响应 */
export interface EtlImportStatusData {
  job_id: string;
  status: EtlImportStatusValue;
  total: number;
  processed: number;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
}

/** ETL 导入触发响应 */
export interface EtlImportResponse {
  job_id: string;
  status: string;
}

// =========================================================================== //
// anon ETL 导入（2026-07-24 补全）—— 与旧 ETL 平行存在
// =========================================================================== //

/** anon ETL 触发请求体（可选字段，不传则走默认） */
export interface AnonImportTriggerRequest {
  /** 中心列表（shengyi/xinqiao/zhujiang）；不传=全部 */
  center_codes?: string[];
  /** 覆盖 hospital.data_dir */
  data_dir_override?: string;
}

/** anon ETL 导入状态（轮询返回，比 EtlImportStatusData 多 centers/results 字段） */
export interface AnonImportStatusData {
  job_id: string;
  status: string;
  total: number;
  processed: number;
  centers: string[];
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
  results?: Array<{
    center: string;
    status: string;
    rows?: Record<string, number>;
    batch_id?: string;
    error?: string;
  }>;
}

/** anon 数据摘要（lnrs_anon_* 各表行数） */
export interface AnonHospitalDataSummary {
  hospital_id: number;
  lifecycle_status: HospitalLifecycleStatus;
  center_codes: string[];
  total_rows: number;
  tables: {
    patient: number;
    exam: number;
    report_text: number;
    exam_detail: number;
    visit: number;
    surgery: number;
    ingest_batch: number;
  };
}

/** 医院数据概览（各表行数） */
export interface HospitalDataSummary {
  hospital_id: number;
  lifecycle_status: HospitalLifecycleStatus;
  tenant_id: number;
  total_rows: number;
  tables: {
    patient: number;
    pathology_specimen: number;
    surgery_record: number;
    genetic_test: number;
    nodule_imaging: number;
    ihc_result: number;
    follow_up: number;
  };
}

/** 医院列表查询参数 */
export interface HospitalPageQuery {
  page_no: number;
  page_size: number;
  name?: string;
  code?: string;
  lifecycle_status?: HospitalLifecycleStatus;
}

// ── 数据统计（仪表板）──────────────────────────────────────
// 结构遵循 ADR-0007：{filters, kpis, dimensions}

/** 图表类型 — 前端按此字段选渲染组件 */
export type StatsChartType = "bar" | "pie" | "h-bar" | "line";

/** 筛选条件 */
export interface StatsFilterOption {
  applied: string | null;
  options: string[] | { min: number; max: number } | null;
}

export interface StatsFilters {
  center: StatsFilterOption | null;
  year_range: StatsFilterOption | null;
}

/** KPI 指标卡 */
export interface StatsKpi {
  key: string;
  label: string;
  value: number;
  icon ?: string;
  format: "number" | "wan";
}

/** 统计维度 — 前端按 chart_type 选图表组件渲染 */
export interface StatsDimension {
  key: string;
  label: string;
  chart_type: StatsChartType;
  data: Record<string, any>[];
}

/** 仪表板全量概览（ADR-0007 维度数组结构） */
export interface StatsOverview {
  filters: StatsFilters | null;
  kpis: StatsKpi[];
  dimensions: StatsDimension[];
}
export interface PatientData{
  total: number
  current: number
  size: number
  items:PatientListItem[]
}
export interface PatientListItem{
    patient_id: string
    center_code: string
    birth_date: Date | null
    sex: string
    ethnicity: string | null
    smoking_status: string | null
    abo_blood_type: string | null
    rh_blood_type: string | null
    native_place: string | null
    bmi: number | null
    first_nodule_date: Date | null
}

/** 状态徽标配置 */
export const LIFECYCLE_STATUS_META: Record<
  HospitalLifecycleStatus,
  { label: string; type: "info" | "primary" | "success" | "warning" }
> = {
  registered: { label: "已注册", type: "info" },
  mapping_configured: { label: "映射已配置", type: "primary" },
  data_imported: { label: "数据已导入", type: "warning" },
  live: { label: "已上线", type: "success" },
};
