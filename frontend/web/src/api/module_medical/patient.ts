import { request } from "@utils";

const API_PATH = "/medical";

/**
 * 医学数据 · 患者多模态浏览 API
 * 2026-07-24 改：数据源从 med_* 中间层切到 lnrs_anon_* 直入（parquet → ETL2 → PG）。
 * 接口均为只读。
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

/** 患者列表行（核心字段，跨院统一，2026-07-24 改用 anon 字段名）
 *
 * 字段映射：med_*.source_center/gender → anon.center_code/sex
 * - center_code: 中心编码（shengyi/xinqiao/zhujiang）
 * - sex: HQMS RC001 国标码（0=未知/1=男/2=女/9=未说明）
 * - ethnicity: GB/T 3304 国标码（01-56）
 * - abo_blood_type: HQMS RC030 国标码（1-6）
 * - rh_blood_type: HQMS RC031 国标码（1-3）
 * - smoking_status: 国标码（1=从不/2=既往/3=现在/9=未知）
 */
export interface PatientTable {
  patient_id: string;
  center_code?: string;
  sex?: string;
  birth_date?: string;
  ethnicity?: string;
  native_place?: string;
  abo_blood_type?: string;
  rh_blood_type?: string;
  smoking_status?: string;
  first_nodule_date?: string;
}

/** 多模态详情中任一模态的一行（字段因表而异，JSONB 已顶层展开）
 *
 * 2026-08-05 改：data source 切到 anon_* PG 体系，JSONB 字段在后端就地顶层展开
 * - _table: 前端折叠面板分组标题（如 "就诊" / "手术" / "检验结果" / "医嘱" /
 *   "CT 检查" / "结节 #2"）
 * - _modality: 模态名（"clinical" / "genetic" / "pathology" / "imaging"）
 * - clinical 行包含 visit/surgery/lab/order/未映射 exam 共 5 种异构行
 * - genetic/pathology/imaging 行共享同一 shape:
 *   {anon_exam_id, exam_type, exam_date, anon_visit_id, report_text, detail_type, ...detail_json 顶层展开}
 */
export interface ModalityRow {
  /** 数据来源中文标签（折叠面板标题） */
  _table?: string;
  /** 模态名(临床/基因/病理/影像) */
  _modality?: "clinical" | "genetic" | "pathology" | "imaging";
  [key: string]: any;
}

/** 患者多模态详情 */
export interface PatientDetail {
  /** 患者基本信息（含 patient_meta JSONB，替代原 demographics+medical_history） */
  patient: Record<string, any>;
  /** 临床模态：就诊/手术/其它 */
  clinical: ModalityRow[];
  /** 基因模态：Genetic 检查 + detail */
  genetic: ModalityRow[];
  /** 病理模态：Pathology/IHC + detail + report_text */
  pathology: ModalityRow[];
  /** 影像模态：CT 检查 + detail */
  imaging: ModalityRow[];
}
