<!-- 环形饼图 — 用于性别比、模态检查量等 -->
<template>
  <ECharts :options="chartOptions" height="280px" />
</template>

<script setup lang="ts">
import { computed } from "vue";

import type { EChartsOption } from "@/plugins/echarts";
import ECharts from "@/components/ECharts/index.vue";

const props = defineProps<{
  data: Record<string, any>[];
  /** 颜色映射（可选），key 为数据中的 sex 等字段值 */
  colorMap?: Record<string, string>;
}>();

const defaultColors = ["#3b82f6", "#10b981", "#f59e0b", "#ec4899", "#8b5cf6", "#ef4444", "#06b6d4"];

const chartOptions = computed<EChartsOption>(() => {
  const data = props.data;
  return {
    tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
    legend: { bottom: "0%", type: "scroll", textStyle: { color: "#94a3b8", fontSize: 11 } },
    series: [
      {
        type: "pie",
        radius: ["38%", "65%"],
        center: ["50%", "42%"],
        avoidLabelOverlap: true,
        itemStyle: { borderRadius: 6, borderColor: "#1e293b", borderWidth: 2 },
        label: { show: true, formatter: "{b}\n{d}%", color: "#cbd5e1", fontSize: 11 },
        data: data.map((d, i) => ({
          name: d.label || d.exam_type || d.sex,
          value: d.count,
          itemStyle: {
            color: props.colorMap?.[d.sex] || defaultColors[i % defaultColors.length],
          },
        })),
      },
    ],
  };
});
</script>
