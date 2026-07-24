/**
 * 医院管理模块 · API
 * 后端：FastAPI module_medical/hospital 子模块（自动发现挂到 /medical）
 */
import { request } from "@utils";

import type {
  AnonHospitalDataSummary,
  AnonImportStatusData,
  AnonImportTriggerRequest,
  EtlImportResponse,
  EtlImportStatusData,
  HospitalDataSummary,
  HospitalFormData,
  HospitalPageQuery,
  HospitalTable,
  MappingRuleBatchData,
  MappingRuleRow,
  MappingTemplate,
  MappingTemplateDetail,
} from "@/types/module_medical/hospital";

const API_PATH = /** 容器前缀由顶级目录名自动生成: /medical */ "/medical";

/**
 * 医院管理 API
 */
const HospitalAPI = {
  // ── 医院 CRUD ──────────────────────────────────────────────

  /** 医院分页列表 */
  listHospital(query?: HospitalPageQuery) {
    return request<ApiResponse<PageResult<HospitalTable>>>({
      url: `${API_PATH}/hospital`,
      method: "get",
      params: query,
    });
  },

  /** 医院详情 */
  detailHospital(id: number) {
    return request<ApiResponse<HospitalTable>>({
      url: `${API_PATH}/hospital/${id}`,
      method: "get",
    });
  },

  /** 注册医院（带 template_code 和 data_dir 则自动推进到 mapping_configured） */
  createHospital(data: HospitalFormData) {
    return request<ApiResponse<HospitalTable>>({
      url: `${API_PATH}/hospital`,
      method: "post",
      data,
    });
  },

  /** 更新医院基本信息（不允许改 code/tenant_id/lifecycle_status） */
  updateHospital(id: number, data: Partial<HospitalFormData>) {
    return request<ApiResponse<HospitalTable>>({
      url: `${API_PATH}/hospital/${id}`,
      method: "put",
      data,
    });
  },

  // ── 映射规则 ──────────────────────────────────────────────

  /** 查看医院映射规则 */
  listMappings(id: number) {
    return request<ApiResponse<MappingRuleRow[]>>({
      url: `${API_PATH}/hospital/${id}/mappings`,
      method: "get",
    });
  },

  /** 全量替换医院映射规则 */
  replaceMappings(id: number, data: MappingRuleBatchData) {
    return request<ApiResponse<MappingRuleRow[]>>({
      url: `${API_PATH}/hospital/${id}/mappings`,
      method: "put",
      data,
    });
  },

  /** 列出可用映射模板 */
  listTemplates() {
    return request<ApiResponse<MappingTemplate[]>>({
      url: `${API_PATH}/mapping-templates`,
      method: "get",
    });
  },

  /** 查看模板详情（含规则列表） */
  getTemplate(templateCode: string) {
    return request<ApiResponse<MappingTemplateDetail>>({
      url: `${API_PATH}/mapping-templates/${templateCode}`,
      method: "get",
    });
  },

  /** 应用模板到医院（覆盖现有规则） */
  applyTemplate(id: number, templateCode: string) {
    return request<ApiResponse<MappingRuleRow[]>>({
      url: `${API_PATH}/hospital/${id}/mappings/apply-template`,
      method: "post",
      params: { template_code: templateCode },
    });
  },

  // ── 选项归一化映射（Excel 批量导入） ─────────────────────────

  /** Excel 批量导入选项映射（覆盖更新模式） */
  importDictMapping(body: FormData) {
    return request<ApiResponse<string>>({
      url: `${API_PATH}/mapping/import`,
      method: "post",
      data: body,
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  /** 下载选项映射导入模板 */
  downloadDictMappingTemplate() {
    return request<Blob>({
      url: `${API_PATH}/mapping/import/template`,
      method: "post",
      responseType: "blob",
    });
  },

  /** 导出全部选项映射到 Excel（每家医院一个 sheet，可直接用于导入） */
  exportDictMapping() {
    return request<Blob>({
      url: `${API_PATH}/mapping/export`,
      method: "post",
      responseType: "blob",
    });
  },

  // ── ETL 导入 ──────────────────────────────────────────────

  /** 触发 ETL 导入（返回 job_id） */
  triggerImport(id: number) {
    return request<ApiResponse<EtlImportResponse>>({
      url: `${API_PATH}/hospital/${id}/import`,
      method: "post",
    });
  },

  /** 查询导入状态 */
  getImportStatus(id: number) {
    return request<ApiResponse<EtlImportStatusData>>({
      url: `${API_PATH}/hospital/${id}/import/status`,
      method: "get",
    });
  },

  // ── 上下线 + 数据概览 ──────────────────────────────────────

  /** 获取医院数据摘要（各表行数） */
  getDataSummary(id: number) {
    return request<ApiResponse<HospitalDataSummary>>({
      url: `${API_PATH}/hospital/${id}/data-summary`,
      method: "get",
    });
  },

  /** 上线（data_imported → live） */
  goOnline(id: number) {
    return request<ApiResponse<HospitalTable>>({
      url: `${API_PATH}/hospital/${id}/online`,
      method: "post",
    });
  },

  /** 下线（live → data_imported） */
  goOffline(id: number) {
    return request<ApiResponse<HospitalTable>>({
      url: `${API_PATH}/hospital/${id}/offline`,
      method: "post",
    });
  },

  // ── anon ETL 导入（2026-07-24 补全，与旧 ETL 平行） ───────────

  /** 触发 anon ETL 导入（parquet → lnrs_anon_*） */
  triggerImportAnon(id: number, body?: AnonImportTriggerRequest) {
    return request<ApiResponse<EtlImportResponse>>({
      url: `${API_PATH}/hospital/${id}/import/anon`,
      method: "post",
      data: body || {},
    });
  },

  /** 查询 anon ETL 导入状态 */
  getAnonImportStatus(id: number) {
    return request<ApiResponse<AnonImportStatusData>>({
      url: `${API_PATH}/hospital/${id}/import/anon/status`,
      method: "get",
    });
  },

  /** 获取医院 anon 数据摘要（lnrs_anon_* 各表行数） */
  getAnonDataSummary(id: number, centerCodes?: string[]) {
    return request<ApiResponse<AnonHospitalDataSummary>>({
      url: `${API_PATH}/hospital/${id}/anon-data-summary`,
      method: "get",
      params: centerCodes?.length ? { center_codes: centerCodes } : undefined,
    });
  },
};

export default HospitalAPI;
