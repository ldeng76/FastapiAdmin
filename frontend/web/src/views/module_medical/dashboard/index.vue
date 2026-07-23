<!-- 医疗数据概览仪表板 — ECharts 可视化 ETL2 脱敏落库的真实数据 -->
<!-- 结构遵循 ADR-0007：{filters, kpis, dimensions} 维度数组，前端按 chart_type 动态选图 -->
<template>
  <div class="medical-dashboard" v-loading="loading && !error">
    <!-- 错误态 -->
    <div v-if="error" class="error-state">
      <ElResult icon="error" title="加载失败" :sub-title="error">
        <template #extra>
          <ElButton type="primary" @click="loadData">重试</ElButton>
        </template>
      </ElResult>
    </div>

    <!-- 空状态 -->
    <div v-else-if="!loading && isEmpty" class="empty-state">
      <ElEmpty description="暂无数据，请等待 ETL2 导入" />
    </div>

    <template v-else>
      <!-- 顶部 KPI 卡 -->
      <div class="kpi-row">
        <KpiCard
          v-for="kpi in overview?.kpis"
          :key="kpi.key"
          :label="kpi.label"
          :value="kpi.value"
          :format="kpi.format"
          :loading="loading"
        />
      </div>

      <!-- 维度图表 — 动态渲染 -->
      <div class="chart-grid">
        <div
          v-for="dim in overview?.dimensions"
          :key="dim.key"
          class="chart-card"
          :class="{ 'full-width': dim.chart_type === 'line' }"
          v-loading="loading"
        >
          <div class="chart-title">
            <span class="title-dot" :style="{ background: getDimensionColor(dim.key) }" />
            {{ dim.label }}
          </div>
          <!-- 有数据：按 chart_type 选组件 -->
          <component
            :is="getChartComponent(dim.chart_type)"
            v-if="getChartComponent(dim.chart_type) && dim.data.length > 0"
            :data="dim.data"
          />
          <!-- 无数据：占位 -->
          <div v-else-if="dim.data.length === 0" class="chart-empty">
            <ElEmpty description="暂无数据" :image-size="60" />
          </div>
          <!-- 未知 chart_type -->
          <div v-else class="chart-empty">
            <ElEmpty description="未知图表类型" :image-size="60" />
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { ElButton, ElEmpty, ElResult } from "element-plus";

import type { StatsOverview } from "@/types/module_medical/hospital";
import StatisticsAPI from "@/api/module_medical/statistics";

import KpiCard from "./components/KpiCard.vue";
import { getChartComponent } from "./components/charts/chartRegistry";

defineOptions({ name: "MedicalDashboard", inheritAttrs: false });

const loading = ref(false);
const error = ref<string | null>(null);
const overview = ref<StatsOverview | null>(null);

/** 是否完全无数据（KPIs 全部为 0） */
const isEmpty = computed(() => {
  if (!overview.value) return false;
  const totalPatients = overview.value.kpis.find((k) => k.key === "total_patients")?.value ?? 0;
  return totalPatients === 0;
});

/** 各维度的主题色 */
const DIMENSION_COLORS: Record<string, string> = {
  age_distribution: "#3b82f6",
  gender_ratio: "#ec4899",
  center_distribution: "#8b5cf6",
  modality_counts: "#f59e0b",
  exam_trend: "#10b981",
};

function getDimensionColor(key: string): string {
  return DIMENSION_COLORS[key] || "#3b82f6";
}

/** 数据加载 */
async function loadData() {
  loading.value = true;
  error.value = null;
  try {
    const res = await StatisticsAPI.getOverview();
    overview.value = res.data?.data || null;
  } catch (e: any) {
    overview.value = null;
    error.value = e?.msg || e?.message || "请求失败，请稍后重试";
  } finally {
    loading.value = false;
  }
}

onMounted(loadData);
</script>

<style scoped>
.medical-dashboard {
  padding: 16px;
  min-height: calc(100vh - 120px);
}

/* ── 错误态 ───────────────────────────────── */
.error-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 400px;
}

/* ── 空状态 ───────────────────────────────── */
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 400px;
}

/* ── KPI 卡行 ────────────────────────────── */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

/* ── 图表网格 ────────────────────────────── */
.chart-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.chart-card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 12px;
  padding: 16px;
  min-height: 360px;
}

.chart-card.full-width {
  grid-column: 1 / -1;
}

.chart-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #e2e8f0;
  margin-bottom: 8px;
}

.title-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.chart-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 280px;
}

/* ── 响应式 ───────────────────────────────── */
@media (max-width: 1024px) {
  .kpi-row {
    grid-template-columns: repeat(2, 1fr);
  }
  .chart-grid {
    grid-template-columns: 1fr;
  }
}
</style>
