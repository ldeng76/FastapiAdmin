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

export interface StatisticsCount {
  file_count?:number,
  patient_count?:number,
  total_size_bytes?:number,
  total_size_text?:string
}

const FilesApi = {
  list(params = {}){
    return request<ApiResponse>({
      url: `${API_PATH}files/list`,
      params :params,
      method: "get",
    });
  },
  statistics(params = {}){
    const data = {
      file_count:0,
      patient_count:0,
      total_size_bytes:0,
      total_size_text :""
    }
    return request<ApiResponse<StatisticsCount>>({
      url: `${API_PATH}files/statistics`,
      params :params,
      method: "get",
    }).then(function (res:any){
      return res?.data?.data || data
    }).catch(function (){
      return data
    });
  },
  getStudyUid(file_id:any){
    return request<ApiResponse<string>>({
      url: `${API_PATH}files/study-uid/${file_id}`,
      method: "get",
    });
  },
  getFileType(){
    return request<ApiResponse>({
      url: `${API_PATH}files/dict/file-types`,
      method: "get",
    }).then(function (res:any){
      return (res?.data?.data?.file_type_options || []).map(function (n:any){
        return {dict_value:n.value,dict_label:n.label}
      })
    }).catch(function (){
      return []
    });
  }
}
export default FilesApi;
