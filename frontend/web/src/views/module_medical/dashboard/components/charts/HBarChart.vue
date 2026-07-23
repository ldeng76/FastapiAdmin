<!-- 横向柱状图 — 用于中心分布等 -->
<template>
  <ECharts :options="chartOptions" height="280px" />
</template>

<script setup lang="ts">
import { computed } from "vue";

import type { EChartsOption } from "@/plugins/echarts";
import ECharts from "@/components/ECharts/index.vue";

const props = defineProps<{ data: Record<string, any>[] }>();

const chartOptions = computed<EChartsOption>(() => {
  // 横向柱状图：数值在 X 轴，类别在 Y 轴；按 count 升序（最大值在顶部）
  const sorted = [...props.data].sort((a, b) => a.count - b.count);
  return {
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
    grid: { left: "3%", right: "10%", bottom: "3%", top: "5%", containLabel: true },
    xAxis: {
      type: "value",
      axisLabel: { color: "#94a3b8" },
      splitLine: { lineStyle: { color: "#1e293b" } },
    },
    yAxis: {
      type: "category",
      data: sorted.map((d) => d.center_code),
      axisLabel: { color: "#cbd5e1" },
      axisLine: { lineStyle: { color: "#334155" } },
    },
    series: [
      {
        type: "bar",
        data: sorted.map((d) => d.count),
        itemStyle: {
          color: {
            type: "linear",
            x: 0, y: 0, x2: 1, y2: 0,
            colorStops: [
              { offset: 0, color: "#8b5cf680" },
              { offset: 1, color: "#8b5cf6" },
            ],
          },
          borderRadius: [0, 4, 4, 0],
        },
        barWidth: "50%",
        label: { show: true, position: "right", color: "#94a3b8", formatter: "{c}" },
      },
    ],
  };
});
</script>
