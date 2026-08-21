<!-- FASTQ · 原始文本视图（支持可选碱基着色） -->
<template>
  <div class="fastq-raw-wrap">
    <pre
      v-if="text"
      class="fastq-raw"
      :class="{ 'fastq-raw--colored': colored }"
      v-html="renderedHtml"
    ></pre>
    <ElEmpty v-else description="暂无原始文本" />
  </div>
</template>

<script setup lang="ts">
/**
 * 原始文本视图。
 * - colored=false（默认）：纯文本，等宽字体，不换行横向滚动（§4.5）
 * - colored=true：按碱基 A/T/C/G/N 着色，自动换行
 *
 * 着色实现：computed 一次性把 text 转成 HTML 字符串（每字符包 <span style="color:...">），
 * 用 v-html 渲染。对 ≤ 几万字符性能足够；几十万字符建议切到 Canvas。
 */
import { computed } from "vue";
import { ElEmpty } from "element-plus";
import { BASE_COLOR } from "../constants/colors";

const props = withDefaults(
  defineProps<{
    text: string;
    /** 是否启用碱基着色（A/T/C/G/N 各自颜色） */
    colored?: boolean;
  }>(),
  { colored: false },
);

/** 转义 HTML 特殊字符（支持整段文本或单字符） */
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** 着色模式：把 text 转成带颜色 span 的 HTML */
const coloredHtml = computed(() => {
  if (!props.text) return "";
  const out: string[] = [];
  const len = props.text.length;
  for (let i = 0; i < len; i++) {
    const ch = props.text[i];
    if (ch === "\n") {
      out.push("\n");
      continue;
    }
    if (ch === "\r") continue;
    const upper = ch.toUpperCase();
    const color = BASE_COLOR[upper] ?? BASE_COLOR.default;
    out.push(`<span style="color:${color}">${escapeHtml(ch)}</span>`);
  }
  return out.join("");
});

const renderedHtml = computed(() => (props.colored ? coloredHtml.value : escapeHtml(props.text)));
</script>

<style scoped>
.fastq-raw-wrap {
  height: 100%;
  overflow: auto;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  background: var(--el-fill-color-blank);
}
.fastq-raw {
  margin: 0;
  padding: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono",
    "Courier New", monospace;
  font-size: 12px;
  line-height: 1.5;
  /* 默认（不着色）：保持原始格式，不换行横向滚动（§4.5） */
  white-space: pre;
  word-break: normal;
  overflow-wrap: normal;
}
/* 着色模式：自动换行，保证完整可见 */
.fastq-raw--colored {
  white-space: pre-wrap;
  word-break: break-all;
  overflow-wrap: break-word;
}
</style>
