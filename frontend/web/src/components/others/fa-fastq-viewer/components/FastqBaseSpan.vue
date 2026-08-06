<!-- FASTQ · 碱基着色 span（带质量背景与原生 title tooltip） -->
<template>
  <span
    class="fastq-base"
    :style="style"
    :title="title"
    :aria-label="title"
  >{{ base }}</span>
</template>

<script setup lang="ts">
/**
 * 单个碱基的渲染单元。
 * - 文字色 = BASE_COLOR[base]
 * - 背景色 = qualityBg(quality)（如有 quality）
 * - tooltip = "Q{quality} {base}"（原生 title，性能最优）
 */
import { computed } from "vue";
import { BASE_COLOR, qualityBg } from "../constants/colors";

const props = withDefaults(
  defineProps<{
    base: string;
    /** 该碱基质量分（Phred+33），可选 */
    quality?: number;
  }>(),
  { quality: undefined },
);

const upper = computed(() => (props.base || "").toUpperCase());
const fg = computed(() => BASE_COLOR[upper.value] ?? BASE_COLOR.default);
const bg = computed(() => (props.quality !== undefined ? qualityBg(props.quality) : "transparent"));
const title = computed(() =>
  props.quality !== undefined ? `Q${props.quality} ${upper.value}` : upper.value,
);
const style = computed(() => ({
  color: fg.value,
  backgroundColor: bg.value,
}));
</script>

<style scoped>
.fastq-base {
  display: inline-block;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono",
    "Courier New", monospace;
  font-size: 12px;
  line-height: 1.2;
  padding: 0 1px;
  border-radius: 2px;
  cursor: default;
}
</style>
