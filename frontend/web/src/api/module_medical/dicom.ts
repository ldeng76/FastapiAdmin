import { request } from "@utils";

const API_PATH = "/medical/dicom";

/**
 * 医学数据 · DICOM 影像浏览 API
 * 后端 pydicom 直读本地 .dcm，不入库；接口均为只读。
 * 切片原始文件由 cornerstone dicom-image-loader 通过 wadouri scheme 拉取，
 * 故此处只提供元数据查询，文件拉取在 viewer 组件内配置。
 */
const DicomAPI = {
  /** Study 列表（扫描 DICOM 数据目录） */
  listStudies() {
    return request<ApiResponse<DicomStudy[]>>({
      url: `${API_PATH}/studies`,
      method: "get",
    });
  },

  /** 某 Study 下所有 Series */
  listSeries(studyId: string) {
    return request<ApiResponse<DicomSeries[]>>({
      url: `${API_PATH}/studies/${studyId}/series`,
      method: "get",
    });
  },

  /** 某 Series 所有切片（已按 Z 轴排序） */
  listInstances(seriesUid: string) {
    return request<ApiResponse<DicomInstance[]>>({
      url: `${API_PATH}/series/${seriesUid}/instances`,
      method: "get",
    });
  },
};

export default DicomAPI;

/** 一次检查（对应数据目录下的一个子目录） */
export interface DicomStudy {
  study_id: string;
  patient_id?: string;
  patient_name?: string;
  study_uid?: string;
  study_description?: string;
  study_date?: string;
  modality?: string;
  series_count: number;
}

/** 一个序列（一组连续切片） */
export interface DicomSeries {
  series_uid: string;
  series_description?: string;
  modality?: string;
  instance_count: number;
  rows?: number;
  columns?: number;
  slice_thickness?: number;
  pixel_spacing?: number[];
  default_window_width?: number;
  default_window_center?: number;
}

/** 一张切片（已排序） */
export interface DicomInstance {
  sop_uid: string;
  index: number;
  instance_number?: string;
  position_z?: number;
  window_width?: number;
  window_center?: number;
}
