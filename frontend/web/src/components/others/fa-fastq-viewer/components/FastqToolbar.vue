<!-- FASTQ · 工具栏（搜索/排序/过滤/视图切换/统计） -->
<template>
  <div class="fastq-toolbar">
    <ElInput
      v-model="searchModel"
      :placeholder="searchPlaceholder"
      clearable
      class="fastq-toolbar-search"
    >
      <template #prefix>
        <ElIcon><Search /></ElIcon>
      </template>
    </ElInput>

    <ElRadioGroup v-model="viewModel" size="small">
      <ElRadioButton label="structured">结构化</ElRadioButton>
      <ElRadioButton label="raw">原始</ElRadioButton>
    </ElRadioGroup>

    <ElSelect v-model="sortModel" size="small" class="fastq-toolbar-sort" placeholder="排序">
      <ElOption label="按 ID" value="id" />
      <ElOption label="按长度" value="length" />
      <ElOption label="按平均质量" value="avgQuality" />
      <ElOption label="按 pairKey" value="pairKey" />
    </ElSelect>

    <ElSelect v-model="pairModel" size="small" class="fastq-toolbar-pair">
      <ElOption label="全部" value="all" />
      <ElOption label="单端" value="singleton" />
      <ElOption label="R1" value="r1" />
      <ElOption label="R2" value="r2" />
    </ElSelect>

    <div class="fastq-toolbar-quality">
      <span class="label">最小平均质量</span>
      <ElSlider
        v-model="qualityModel"
        :min="0"
        :max="41"
        :step="1"
        :show-input="true"
        size="small"
        class="slider"
      />
    </div>

    <div class="fastq-toolbar-stats">
      <ElTag size="small" type="info" effect="plain">总数 {{ stats.total }}</ElTag>
      <ElTag size="small" type="primary" effect="plain">双端对 {{ stats.pairCount }}</ElTag>
      <ElTag size="small" effect="plain">单端 {{ stats.singletons }}</ElTag>
      <ElTag v-if="stats.errorCount" size="small" type="warning" effect="plain">
        错误 {{ stats.errorCount }}
      </ElTag>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import {
  ElInput,
  ElIcon,
  ElRadioGroup,
  ElRadioButton,
  ElSelect,
  ElOption,
  ElSlider,
  ElTag,
} from "element-plus";
import { Search } from "@element-plus/icons-vue";
import type {
  FastqPairFilter,
  FastqSortKey,
  FastqStats,
  FastqViewMode,
} from "@/utils/fastq/types";

const props = defineProps<{
  search: string;
  viewMode: FastqViewMode;
  sortBy: FastqSortKey;
  pairFilter: FastqPairFilter;
  minAvgQuality: number;
  stats: FastqStats;
}>();

const emit = defineEmits<{
  (e: "update:search", v: string): void;
  (e: "update:viewMode", v: FastqViewMode): void;
  (e: "update:sortBy", v: FastqSortKey): void;
  (e: "update:pairFilter", v: FastqPairFilter): void;
  (e: "update:minAvgQuality", v: number): void;
}>();

const searchModel = computed({
  get: () => props.search,
  set: (v) => emit("update:search", v),
});
const viewModel = computed({
  get: () => props.viewMode,
  set: (v) => emit("update:viewMode", v),
});
const sortModel = computed({
  get: () => props.sortBy,
  set: (v) => emit("update:sortBy", v),
});
const pairModel = computed({
  get: () => props.pairFilter,
  set: (v) => emit("update:pairFilter", v),
});
const qualityModel = computed({
  get: () => props.minAvgQuality,
  set: (v) => emit("update:minAvgQuality", v),
});

const searchPlaceholder = "搜索 Read ID / pairKey / 序列子串";
</script>

<style scoped>
.fastq-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 8px 0;
}
.fastq-toolbar-search {
  width: 260px;
}
.fastq-toolbar-sort,
.fastq-toolbar-pair {
  width: 140px;
}
.fastq-toolbar-quality {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 280px;
}
.fastq-toolbar-quality .label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}
.fastq-toolbar-quality .slider {
  flex: 1;
  margin: 0;
}
.fastq-toolbar-stats {
  margin-left: auto;
  display: flex;
  gap: 6px;
  align-items: center;
}
</style>
