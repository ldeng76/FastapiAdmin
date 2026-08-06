<!-- FASTQ · R1/R2/单端 徽标 -->
<template>
  <ElTag v-if="pairEnd === 1" type="primary" size="small" effect="plain">R1</ElTag>
  <ElTag v-else-if="pairEnd === 2" type="success" size="small" effect="plain">R2</ElTag>
  <ElTag v-else type="info" size="small" effect="plain">{{ singleText }}</ElTag>
</template>

<script setup lang="ts">
import { ElTag } from "element-plus";
import type { FastqPairEnd } from "@/utils/fastq/types";

defineProps<{ pairEnd: FastqPairEnd }>();

// "单端" 文案：使用 useI18n 优先；否则回退中文
const singleText = "单端";
</script>
