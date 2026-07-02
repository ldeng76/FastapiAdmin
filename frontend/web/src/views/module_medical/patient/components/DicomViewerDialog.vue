<!--
  DICOM 影像查看器弹窗（FaDialog fullscreen 包裹层）。

  设计要点：
  - 默认全屏，给影像最大展示空间（cornerstone 需要足够大的容器）。
  - FaDialog 的 destroy-on-close 在关闭时销毁 DicomViewer，
    触发其 onBeforeUnmount → destroyEngine，避免 WebGL 上下文累积。
  - 用 @opened 时机把 studyId 传给 viewer 开始加载，确保 DOM 已挂载有尺寸。
-->
<template>
  <FaDialog
    v-model="visible"
    :title="dialogTitle"
    :fullscreen="true"
    modal-class="dicom-viewer-modal"
    dialog-class="dicom-viewer-dialog"
    @opened="onOpened"
  >
    <div class="dicom-viewer-wrapper">
      <DicomViewer v-if="ready && studyId" :study-id="studyId" />
    </div>
  </FaDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import FaDialog from "@/components/modal/fa-dialog/index.vue";
import DicomViewer from "./DicomViewer.vue";

const props = defineProps<{
  /** 控制显隐 */
  modelValue: boolean;
  /** 初始 Study ID（目录名） */
  studyId?: string;
  /** 标题补充信息（如患者姓名） */
  patientName?: string;
}>();

const emit = defineEmits<{
  "update:modelValue": [v: boolean];
}>();

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit("update:modelValue", v),
});

// 延迟挂载 DicomViewer，等 @opened 后再渲染，确保容器有真实尺寸
const ready = ref(false);

const dialogTitle = computed(() => {
  const name = props.patientName ? ` · ${props.patientName}` : "";
  return `DICOM 影像查看${name}`;
});

function onOpened() {
  ready.value = true;
}

watch(visible, (v) => {
  if (!v) ready.value = false;
});
</script>

<style scoped>
.dicom-viewer-wrapper {
  width: 100%;
  height: calc(100vh - 110px);
  min-height: 500px;
}
</style>

<style>
/* 全局样式：让弹窗 body 撑满，去掉默认 padding 给 viewer 最大空间 */
.dicom-viewer-modal .dicom-viewer-dialog {
  margin: 0 !important;
}
.dicom-viewer-dialog .el-dialog__body {
  padding: 0 !important;
}
</style>
