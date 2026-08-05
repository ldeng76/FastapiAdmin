/**
 * 数据统计模块 · API
 * 后端：FastAPI /medical/statistics/overview
 */
import { request } from "@utils";

import type { StatsOverview } from "@/types/module_medical/hospital";

const API_PATH = "/medical/statistics";

const StatisticsAPI = {
  /** 仪表板全量概览（维度数组结构，ADR-0007） */
  getOverview(params?:any) {
    return request<ApiResponse<StatsOverview>>({
      url: `${API_PATH}/overview`,
      method: "get",
      params : params ? params : null
    });
  },
  async getAgeBuckets() {
    try {
      const res = await request<ApiResponse>({
        url: `${API_PATH}/age-buckets`,
        method: "get",
      });
      return res.data.data;
    } catch {
      return [];
    }
  }
};

export default StatisticsAPI;
