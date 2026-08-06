<!-- FASTQ · 上传/粘贴面板 -->
<template>
  <div class="fastq-upload">
    <ElInput
      v-model="text"
      type="textarea"
      :rows="6"
      :placeholder="placeholder"
      resize="none"
      class="fastq-upload-textarea"
    />
    <div class="fastq-upload-actions">
      <ElUpload
        :auto-upload="false"
        :show-file-list="false"
        :accept="ACCEPT"
        :on-change="onFile"
        drag
      >
        <ElButton type="primary" :icon="Upload" plain>选择 .fq / .fastq 文件</ElButton>
        <template #tip>
          <div class="el-upload__tip">支持拖拽；单文件不超过 {{ MAX_FILE_MB }} MB</div>
        </template>
      </ElUpload>
      <ElButton type="success" :icon="MagicStick" :loading="loading" @click="onParse">
        解析
      </ElButton>
      <ElButton :icon="Document" @click="onLoadSample">载入示例</ElButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import { ElInput, ElUpload, ElButton, ElMessage } from "element-plus";
import { Upload, MagicStick, Document } from "@element-plus/icons-vue";
import { FASTQ_I18N_KEYS } from "../i18n";

const ACCEPT = ".fq,.fastq,.fq.gz,.fastq.gz,text/plain";
const MAX_FILE_MB = 50;

const emit = defineEmits<{
  (e: "parsed", text: string): void;
  (e: "loadSample"): void;
}>();

const text = ref("");
const loading = ref(false);
const placeholder = computed(
  () => "粘贴 FASTQ 文本，或拖拽/选择 .fq / .fastq 文件，或点击「载入示例」",
);

async function onFile(file: { raw?: File }) {
  const f = file?.raw;
  if (!f) return;
  if (f.size > MAX_FILE_MB * 1024 * 1024) {
    ElMessage.warning(`文件超过 ${MAX_FILE_MB} MB，建议先拆分或压缩`);
    return;
  }
  try {
    text.value = await f.text();
  } catch (err: any) {
    ElMessage.error(`读取文件失败：${err?.message ?? err}`);
  }
}

function onParse() {
  const t = text.value.trim();
  if (!t) {
    ElMessage.warning("请先粘贴或选择 FASTQ 文本");
    return;
  }
  loading.value = true;
  emit("parsed", t);
  // 实际 loading 状态由上层解析结果后清零（通过 prop.sync 不好做，简化处理：2s 后兜底）
  setTimeout(() => (loading.value = false), 2000);
}

function onLoadSample() {
  emit("loadSample");
  setTimeout(() => (loading.value = false), 200);
}
</script>

<style scoped>
.fastq-upload {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.fastq-upload-textarea :deep(textarea) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
}
.fastq-upload-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
:deep(.el-upload) {
  display: inline-block;
}
:deep(.el-upload-dragger) {
  padding: 8px 16px;
}
</style>
