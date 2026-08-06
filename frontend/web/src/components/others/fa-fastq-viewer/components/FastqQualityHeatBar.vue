<!-- FASTQ · 质量热力条（迷你条 / 全长条两用） -->
<template>
  <div :class="['fastq-heat', { compact }]" :title="title">
    <span
      v-for="(q, i) in displayScores"
      :key="i"
      class="fastq-heat-cell"
      :style="{ backgroundColor: qualityBg(q) }"
      :title="`Q${q}`"
    />
    <span v-if="overflow > 0" class="fastq-heat-overflow">+{{ overflow }}</span>
  </div>
</template>

<script setup lang="ts">
/**
 * 质量热力条。
 * - 紧凑模式：仅取首/尾/均分若干点，避免渲染过多 DOM
 * - 全长模式：渲染所有 cell（10k 以内可接受；>10k 自动切到 compact）
 */
import { computed } from "vue";
import { qualityBg } from "../constants/colors";

const props = withDefaults(
  defineProps<{
    scores: number[];
    compact?: boolean;
    /** 紧凑模式最多显示多少 cell（默认 40） */
    compactMax?: number;
  }>(),
  { compact: false, compactMax: 40 },
);

const MAX_FULL = 10_000;
const needCompact = computed(() => props.compact || props.scores.length > MAX_FULL);

const displayScores = computed<number[]>(() => {
  if (!needCompact.value) return props.scores;
  const n = Math.min(props.compactMax, props.scores.length);
  if (n === 0) return [];
  const step = props.scores.length / n;
  const out: number[] = new Array(n);
  for (let i = 0; i < n; i++) {
    out[i] = props.scores[Math.floor(i * step)];
  }
  return out;
});

const overflow = computed(() =>
  needCompact.value ? Math.max(0, props.scores.length - props.compactMax) : 0,
);

const title = computed(
  () => `${props.scores.length} 个碱基；平均 Q${avg(props.scores).toFixed(1)}`,
);
function avg(arr: number[]): number {
  if (arr.length === 0) return 0;
  let s = 0;
  for (const v of arr) s += v;
  return s / arr.length;
}
</script>

<style scoped>
.fastq-heat {
  display: inline-flex;
  align-items: center;
  gap: 1px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 10px;
}
.fastq-heat-cell {
  width: 3px;
  height: 14px;
  border-radius: 1px;
  flex-shrink: 0;
}
.fastq-heat.compact .fastq-heat-cell {
  width: 2px;
  height: 12px;
}
.fastq-heat-overflow {
  margin-left: 4px;
  color: var(--el-text-color-secondary);
}
</style>
