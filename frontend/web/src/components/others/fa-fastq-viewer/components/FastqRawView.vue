<!-- FASTQ · 原始文本视图 -->
<template>
  <div class="fastq-raw-wrap">
    <pre v-if="text" class="fastq-raw">{{ text }}</pre>
    <ElEmpty v-else description="暂无原始文本" />
  </div>
</template>

<script setup lang="ts">
import { ElEmpty } from "element-plus";
defineProps<{ text: string }>();
</script>

<style scoped>
.fastq-raw-wrap {
  max-height: 60vh;
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
  white-space: pre;
  /* 不自动换行；横向滚动（依据 §4.5） */
  word-break: normal;
  overflow-wrap: normal;
}
</style>
