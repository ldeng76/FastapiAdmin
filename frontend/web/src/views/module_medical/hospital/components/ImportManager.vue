<!-- ETL 导入管理：触发/进度/错误/重新导入 -->
<template>
  <FaDialog
    v-model="visible"
    title="ETL 数据导入"
    width="640px"
    dialog-class="crud-embed-dialog"
    modal-class="crud-embed-dialog"
    @cancel="handleCancel"
  >
    <div class="import-manager">
      <!-- 状态展示 -->
      <ElDescriptions :column="1" border>
        <ElDescriptionsItem label="导入状态">
          <ElTag :type="statusTagType" effect="dark" size="small">
            {{ statusLabel }}
          </ElTag>
        </ElDescriptionsItem>
        <ElDescriptionsItem v-if="statusData.job_id" label="任务ID">
          {{ statusData.job_id }}
        </ElDescriptionsItem>
        <ElDescriptionsItem v-if="statusData.total > 0" label="总行数">
          {{ statusData.total.toLocaleString() }}
        </ElDescriptionsItem>
        <ElDescriptionsItem v-if="statusData.started_at" label="开始时间">
          {{ statusData.started_at }}
        </ElDescriptionsItem>
        <ElDescriptionsItem v-if="statusData.completed_at" label="完成时间">
          {{ statusData.completed_at }}
        </ElDescriptionsItem>
      </ElDescriptions>

      <!-- 进度条 -->
      <div v-if="status === 'running'" class="progress-section">
        <ElProgress
          :percentage="progressPercent"
          :stroke-width="16"
          striped
          striped-flow
          :duration="3"
        />
        <div class="progress-text">
          {{ statusData.processed.toLocaleString() }} / {{ statusData.total.toLocaleString() }}
        </div>
      </div>

      <!-- 错误信息 -->
      <ElAlert v-if="status === 'failed'" type="error" :closable="false" style="margin-top: 16px">
        <template #title>导入失败</template>
        <div class="error-message">{{ statusData.error || "未知错误" }}</div>
      </ElAlert>

      <!-- 完成提示 -->
      <ElAlert v-if="status === 'completed'" type="success" :closable="false" style="margin-top: 16px">
        导入完成！共 {{ statusData.processed?.toLocaleString() }} 行数据已入库。
      </ElAlert>
    </div>

    <template #footer>
      <ElButton @click="handleCancel">{{ status === "running" ? "后台运行" : "关闭" }}</ElButton>
      <ElButton
        v-if="status !== 'running' && status !== 'pending'"
        type="primary"
        :loading="triggerLoading"
        @click="handleTrigger"
      >
        重新导入
      </ElButton>
    </template>
  </FaDialog>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";

import { ElAlert, ElButton, ElDescriptions, ElDescriptionsItem, ElMessage, ElProgress, ElTag } from "element-plus";

import FaDialog from "@/components/modal/fa-dialog/index.vue";
import HospitalAPI from "@/api/module_medical/hospital";
import type { EtlImportStatusData, EtlImportStatusValue } from "@/types/module_medical/hospital";

const props = defineProps<{ modelValue: boolean; hospitalId: number }>();
const emit = defineEmits<{ "update:modelValue": [boolean]; completed: [] }>();

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit("update:modelValue", val),
});

const statusData = ref<EtlImportStatusData>({
  job_id: "",
  status: "idle",
  total: 0,
  processed: 0,
  error: null,
  started_at: null,
  completed_at: null,
});
const triggerLoading = ref(false);
const pollingTimer = ref<ReturnType<typeof setInterval> | null>(null);

const status = computed<EtlImportStatusValue>(() => statusData.value.status);

const statusLabel = computed(() => {
  const map: Record<string, string> = {
    idle: "未开始",
    pending: "排队中",
    running: "导入中",
    completed: "已完成",
    failed: "失败",
    unknown: "未知",
  };
  return map[status.value] || status.value;
});

const statusTagType = computed(() => {
  const map: Record<string, "info" | "warning" | "success" | "danger"> = {
    idle: "info",
    pending: "info",
    running: "warning",
    completed: "success",
    failed: "danger",
    unknown: "info",
  };
  return map[status.value] || "info";
});

const progressPercent = computed(() => {
  if (statusData.value.total <= 0) return 0;
  return Math.min(100, Math.round((statusData.value.processed / statusData.value.total) * 100));
});

async function refreshStatus() {
  try {
    const res = await HospitalAPI.getImportStatus(props.hospitalId);
    statusData.value = res.data?.data || statusData.value;
  } catch {
    // 忽略
  }
}

function startPolling() {
  stopPolling();
  pollingTimer.value = setInterval(async () => {
    await refreshStatus();
    if (status.value === "completed" || status.value === "failed") {
      stopPolling();
      if (status.value === "completed") {
        emit("completed");
      }
    }
  }, 2000);
}

function stopPolling() {
  if (pollingTimer.value) {
    clearInterval(pollingTimer.value);
    pollingTimer.value = null;
  }
}

async function handleTrigger() {
  triggerLoading.value = true;
  try {
    const res = await HospitalAPI.triggerImport(props.hospitalId);
    statusData.value = {
      ...statusData.value,
      job_id: res.data?.data?.job_id || "",
      status: "pending",
      processed: 0,
      error: null,
      started_at: new Date().toISOString(),
      completed_at: null,
    };
    ElMessage.success("导入任务已触发");
    startPolling();
  } finally {
    triggerLoading.value = false;
  }
}

function handleCancel() {
  visible.value = false;
}

watch(visible, (val) => {
  if (val) {
    refreshStatus();
  } else {
    stopPolling();
  }
});

onBeforeUnmount(stopPolling);
</script>

<style scoped>
.import-manager {
  min-height: 120px;
}
.progress-section {
  margin-top: 16px;
}
.progress-text {
  text-align: center;
  margin-top: 8px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.error-message {
  white-space: pre-wrap;
  word-break: break-all;
  font-family: monospace;
  font-size: 12px;
}
</style>
