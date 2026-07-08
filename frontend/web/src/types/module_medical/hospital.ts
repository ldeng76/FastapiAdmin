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
