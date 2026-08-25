import { request } from "@utils";

const API_PATH = "medical/";

export interface FilesTable {
  patient_id: string;
  file_name?: string;
  exam_type?: string;
  file_type?: string;
  file_size?: number;
  id?:number
}

const FilesApi = {
  list(params = {}){
    return request<ApiResponse<string[]>>({
      url: `${API_PATH}files/list`,
      params :params,
      method: "get",
    });
  },
  getStudyUid(file_id:any){
    return request<ApiResponse<string[]>>({
      url: `${API_PATH}files/study-uid/${file_id}`,
      method: "get",
    });
  }
}
export default FilesApi;
