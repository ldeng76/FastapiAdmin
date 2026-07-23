/**
 * 图表注册表 — chart_type → 图表组件映射（ADR-0007 决策 5）
 *
 * 新增图表类型：
 * 1. 创建 Wrapper 组件（接收 data: Record<string, any>[]，输出 ECharts options）
 * 2. 在此文件的 CHART_COMPONENTS 中添加映射
 */
import type { Component } from "vue";

import BarChart from "./BarChart.vue";
import HBarChart from "./HBarChart.vue";
import LineChart from "./LineChart.vue";
import PieChart from "./PieChart.vue";

const CHART_COMPONENTS: Record<string, Component> = {
  bar: BarChart,
  pie: PieChart,
  "h-bar": HBarChart,
  line: LineChart,
};

/**
 * 根据 chart_type 返回对应的图表组件。
 * 未识别的类型返回 null（前端应显示 fallback）。
 */
export function getChartComponent(chartType: string): Component | null {
  return CHART_COMPONENTS[chartType] || null;
}

export { BarChart, PieChart, HBarChart, LineChart };
