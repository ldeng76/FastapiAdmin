<!-- 折线图 — 用于检查时间趋势等 -->
<template>
  <ECharts :options="chartOptions" height="280px" />
</template>

<script setup lang="ts">
import { computed } from "vue";

import type { EChartsOption } from "@/plugins/echarts";
import ECharts from "@/components/ECharts/index.vue";

const props = defineProps<{ data: Record<string, any>[] }>();

const chartOptions = computed<EChartsOption>(() => {
  const labels = props.data.map((d) => `${d.year}-${String(d.month).padStart(2, "0")}`);
  const counts = props.data.map((d) => d.count);
  return {
    tooltip: { trigger: "axis" },
    grid: { left: "3%", right: "4%", bottom: "3%", top: "8%", containLabel: true },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: labels,
      axisLabel: {
        color: "#94a3b8",
        fontSize: 11,
        rotate: labels.length > 12 ? 45 : 0,
      },
      axisLine: { lineStyle: { color: "#334155" } },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: "#94a3b8" },
      splitLine: { lineStyle: { color: "#1e293b" } },
    },
    series: [
      {
        type: "line",
        smooth: true,
        data: counts,
        areaStyle: {
          color: {
            type: "linear",
            x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [
              { offset: 0, color: "#10b98150" },
              { offset: 1, color: "#10b98105" },
            ],
          },
        },
        lineStyle: { color: "#10b981", width: 2 },
        itemStyle: { color: "#10b981" },
        symbol: "circle",
        symbolSize: 5,
      },
    ],
  };
});
</script>
