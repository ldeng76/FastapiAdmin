import { request } from "@utils";

const API_PATH = "/medical";

/**
 * 医学数据 · 患者多模态浏览 API
 * 后端以 DuckDB 直读 parquet，不入库；接口均为只读。
 */
const PatientAPI = {
  /** 来源中心枚举（动态，反映 parquet 中实际出现的中心） */
  listCenters() {
    return request<ApiResponse<string[]>>({
      url: `${API_PATH}/centers`,
      method: "get",
    });
  },

  /** 患者分页列表 */
  listPatient(query?: PatientPageQuery) {
    return request<ApiResponse<PageResult<PatientTable>>>({
      url: `${API_PATH}/patients`,
      method: "get",
      params: query,
    });
  },

  /** 患者多模态详情（临床/基因/病理/影像 四模态） */
  detailPatient(patientId: string, center?: string) {
    return request<ApiResponse<PatientDetail>>({
      url: `${API_PATH}/patients/${patientId}`,
      method: "get",
      params: center ? { center } : undefined,
    });
  },
};

export default PatientAPI;

/** 患者列表查询参数 */
export interface PatientPageQuery extends PageQuery {
  /** 来源中心（动态枚举，当前为「珠江」） */
  center?: string;
  /** 患者编号 / 中心 关键词 */
  keyword?: string;
}

/** 患者列表行（核心字段，跨院统一） */
export interface PatientTable {
  patient_id: string;
  source_center?: string;
  gender?: string;
  birth_date?: string;
  ethnicity?: string;
  native_place?: string;
  abo_blood_type?: string;
  rh_blood_type?: string;
  smoking_status?: string;
  first_nodule_date?: string;
}

/** 多模态详情中任一模态的一行（字段因表而异，含 JSON 扩展列） */
export interface ModalityRow {
  /** 数据来源子表名（就诊记录/手术记录/结节影像…），前端展示用 */
  _table?: string;
  [key: string]: any;
}

/** 患者多模态详情 */
export interface PatientDetail {
  /** 患者基本信息（含 demographics/medical_history 等 JSON 扩展列） */
  patient: Record<string, any>;
  /** 临床模态：手术记录/随访结局 等 */
  clinical: ModalityRow[];
  /** 基因模态：基因检测记录 */
  genetic: ModalityRow[];
  /** 病理模态：病理标本 */
  pathology: ModalityRow[];
  /** 影像模态：结节影像 */
  imaging: ModalityRow[];
}
