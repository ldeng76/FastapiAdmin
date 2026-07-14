<!-- 医院数据概览：各表行数 + 状态徽标 + 上下线按钮 -->
<template>
  <FaDialog
    v-model="visible"
    title="医院数据概览"
    width="720px"
    dialog-class="crud-embed-dialog"
    modal-class="crud-embed-dialog"
    @cancel="handleCancel"
  >
    <div v-loading="loading" class="data-overview">
      <!-- 状态概览 -->
      <div class="status-header">
        <ElDescriptions :column="2" border size="small">
          <ElDescriptionsItem label="医院编码">{{ summary?.hospital_id }}</ElDescriptionsItem>
          <ElDescriptionsItem label="租户ID">{{ summary?.tenant_id }}</ElDescriptionsItem>
          <ElDescriptionsItem label="当前状态">
            <ElTag :type="statusMeta.type" effect="dark" size="small">
              {{ statusMeta.label }}
            </ElTag>
          </ElDescriptionsItem>
          <ElDescriptionsItem label="总行数">
            <strong>{{ totalRowsFormatted }}</strong>
          </ElDescriptionsItem>
        </ElDescriptions>
      </div>

      <!-- 各表行数 -->
      <ElDivider>各表数据</ElDivider>
      <ElTable :data="tableRows" border stripe size="small">
        <ElTableColumn prop="label" label="表名" min-width="160" />
        <ElTableColumn prop="count" label="行数" width="140" align="right">
          <template #default="{ row }">
            {{ row.count.toLocaleString() }}
          </template>
        </ElTableColumn>
        <ElTableColumn label="占比" min-width="200">
          <template #default="{ row }">
            <ElProgress
              :percentage="totalRows > 0 ? Math.round((row.count / totalRows) * 100) : 0"
              :stroke-width="10"
            />
          </template>
        </ElTableColumn>
      </ElTable>
    </div>

    <template #footer>
      <ElButton @click="handleCancel">关闭</ElButton>
      <ElButton
        v-if="summary?.lifecycle_status === 'data_imported'"
        type="success"
        @click="handleGoOnline"
      >
        上线
      </ElButton>
      <ElButton
        v-if="summary?.lifecycle_status === 'live'"
        type="warning"
        @click="handleGoOffline"
      >
        下线
      </ElButton>
    </template>
  </FaDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";

import { ElButton, ElDescriptions, ElDescriptionsItem, ElDivider, ElMessage, ElProgress, ElTable, ElTableColumn, ElTag } from "element-plus";

import FaDialog from "@/components/modal/fa-dialog/index.vue";
import HospitalAPI from "@/api/module_medical/hospital";
import { LIFECYCLE_STATUS_META, type HospitalDataSummary } from "@/types/module_medical/hospital";

const props = defineProps<{ modelValue: boolean; hospitalId: number }>();
const emit = defineEmits<{ "update:modelValue": [boolean]; online: []; offline: [] }>();

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit("update:modelValue", val),
});

const loading = ref(false);
const summary = ref<HospitalDataSummary | null>(null);

const TABLE_LABELS: Record<string, string> = {
  patient: "患者基本信息",
  pathology_specimen: "病理标本",
  surgery_record: "手术记录",
  genetic_test: "基因检测",
  nodule_imaging: "结节影像",
  ihc_result: "免疫组化",
  follow_up: "随访结局",
};

const tableRows = computed(() => {
  if (!summary.value) return [];
  return Object.entries(summary.value.tables).map(([key, count]) => ({
    key,
    label: TABLE_LABELS[key] || key,
    count,
  }));
});

const totalRows = computed(() => summary.value?.total_rows || 0);

const totalRowsFormatted = computed(() => totalRows.value.toLocaleString());

const statusMeta = computed(() => {
  const s = summary.value?.lifecycle_status || "registered";
  return LIFECYCLE_STATUS_META[s as keyof typeof LIFECYCLE_STATUS_META] || { label: s, type: "info" as const };
});

async function loadData() {
  loading.value = true;
  try {
    const res = await HospitalAPI.getDataSummary(props.hospitalId);
    summary.value = res.data?.data || null;
  } finally {
    loading.value = false;
  }
}

async function handleGoOnline() {
  try {
    await HospitalAPI.goOnline(props.hospitalId);
    ElMessage.success("上线成功");
    emit("online");
    visible.value = false;
  } catch {
    // 错误已由拦截器处理
  }
}

async function handleGoOffline() {
  try {
    await HospitalAPI.goOffline(props.hospitalId);
    ElMessage.success("下线成功");
    emit("offline");
    visible.value = false;
  } catch {
    // 错误已由拦截器处理
  }
}

function handleCancel() {
  visible.value = false;
}

watch(visible, (val) => {
  if (val) {
    loadData();
  }
});
</script>

<style scoped>
.status-header {
  margin-bottom: 16px;
}
</style>
