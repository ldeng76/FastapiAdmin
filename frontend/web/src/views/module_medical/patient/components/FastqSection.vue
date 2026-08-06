<!--
  多模态详情页 · 基因 Tab 内的"测序 reads"子组容器
  复用 fa-fastq-viewer，仅做文案包装与卡片化
-->
<template>
  <ElCard shadow="never" class="fastq-section">
    <template #header>
      <div class="fastq-section-header">
        <span class="title">测序 reads（FASTQ 结构化展示）</span>
        <ElTag size="small" type="info" effect="plain">本地解析 · 无后端依赖</ElTag>
      </div>
    </template>
    <p class="fastq-section-desc">
      粘贴本患者的 FASTQ 测序文本（.fq / .fastq），或拖拽文件至下方面板，
      即可在前端解析为结构化 Reads 并按双端/质量/序列片段检索；仅在本浏览器内存中处理，不上传服务器。
    </p>
    <FaFastqViewer />
  </ElCard>
</template>

<script setup lang="ts">
import { ElCard, ElTag } from "element-plus";
import FaFastqViewer from "@/components/others/fa-fastq-viewer/index.vue";

defineOptions({ name: "MedicalPatientFastqSection" });
</script>

<style scoped>
.fastq-section {
  margin-top: 12px;
}
.fastq-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.fastq-section-header .title {
  font-weight: 600;
  font-size: 14px;
}
.fastq-section-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 0 0 12px 0;
  line-height: 1.6;
}
</style>
