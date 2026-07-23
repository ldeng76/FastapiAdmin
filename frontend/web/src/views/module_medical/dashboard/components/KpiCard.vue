<!-- 核心指标卡 — 用于仪表板顶部 KPI 展示 -->
<template>
  <div class="kpi-card" :style="{ '--accent': color }">
    <div class="kpi-content">
      <span class="kpi-value">
        <span v-if="loading" class="skeleton" />
        <span v-else>{{ formattedValue }}</span>
      </span>
      <span class="kpi-label">{{ label }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  label: string;
  value: number | undefined;
  /** 显示格式：number=原样，wan=万 */
  format?: "number" | "wan";
  loading?: boolean;
}>();

const color = computed(() => {
  // 根据 label 推断颜色（简单启发式）
  if (props.label.includes("患者")) return "#3b82f6";
  if (props.label.includes("检查") && props.label.includes("总量")) return "#10b981";
  if (props.label.includes("中心")) return "#8b5cf6";
  if (props.label.includes("模态")) return "#f59e0b";
  return "#3b82f6";
});

const formattedValue = computed(() => {
  const v = props.value;
  if (v == null) return "-";
  if (props.format === "wan" && v >= 10000) return (v / 10000).toFixed(1) + "万";
  return v.toLocaleString();
});
</script>

<style scoped>
.kpi-card {
  display: flex;
  align-items: center;
  padding: 20px 24px;
  background: #1e293b;
  border: 1px solid #334155;
  border-left: 4px solid var(--accent);
  border-radius: 12px;
  transition: box-shadow 0.2s ease;
}

.kpi-card:hover {
  box-shadow: 0 4px 16px color-mix(in srgb, var(--accent) 20%, transparent);
}

.kpi-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.kpi-value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1.2;
  color: #f1f5f9;
}

.kpi-label {
  font-size: 13px;
  color: #94a3b8;
}

.skeleton {
  display: inline-block;
  width: 80px;
  height: 28px;
  background: linear-gradient(90deg, #334155 25%, #475569 50%, #334155 75%);
  background-size: 200% 100%;
  border-radius: 4px;
  animation: shimmer 1.5s infinite;
}

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
</style>
