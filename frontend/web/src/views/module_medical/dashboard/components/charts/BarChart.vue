<!-- 柱状图 — 用于年龄分布等 -->
<template>
  <ECharts :options="chartOptions" height="280px" />
</template>

<script setup lang="ts">
import { computed } from "vue";

import type { EChartsOption } from "@/plugins/echarts";
import ECharts from "@/components/ECharts/index.vue";

const props = defineProps<{ data: Record<string, any>[] }>();

const chartOptions = computed<EChartsOption>(() => ({
  tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
  grid: { left: "3%", right: "4%", bottom: "3%", top: "8%", containLabel: true },
  xAxis: {
    type: "category",
    data: props.data.map((d) => d.label),
    axisLabel: { color: "#94a3b8", fontSize: 11 },
    axisLine: { lineStyle: { color: "#334155" } },
  },
  yAxis: {
    type: "value",
    axisLabel: { color: "#94a3b8" },
    splitLine: { lineStyle: { color: "#1e293b" } },
  },
  series: [
    {
      type: "bar",
      data: props.data.map((d) => d.count),
      itemStyle: {
        color: {
          type: "linear",
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: "#3b82f6" },
            { offset: 1, color: "#1d4ed880" },
          ],
        },
        borderRadius: [4, 4, 0, 0],
      },
      barWidth: "55%",
    },
  ],
}));
</script>
