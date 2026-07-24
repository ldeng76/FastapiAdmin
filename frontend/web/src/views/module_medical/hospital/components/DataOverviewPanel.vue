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
          <ElDescriptionsItem label="中心列表">
            <span v-for="c in summary?.center_codes" :key="c" class="center-chip">
              {{ c }}
            </span>
            <span v-if="!summary?.center_codes?.length">-</span>
          </ElDescriptionsItem>
          <ElDescriptionsItem label="当前状态">
            <ElTag :type="statusMeta.type" effect="dark" size="small">
              {{ statusMeta.label }}
            </ElTag>
          </ElDescriptionsItem>
          <ElDescriptionsItem label="总行数">
            <strong>{{ summary ? totalRowsFormatted : "-" }}</strong>
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
        v-if="canGoOnline"
        type="success"
        @click="handleGoOnline"
      >
        上线
      </ElButton>
      <ElButton
        v-if="canGoOffline"
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
import { LIFECYCLE_STATUS_META, type AnonHospitalDataSummary } from "@/types/module_medical/hospital";
import { useAuth } from "@/hooks/core/useAuth";

const props = defineProps<{ modelValue: boolean; hospitalId: number }>();
const emit = defineEmits<{ "update:modelValue": [boolean]; online: []; offline: [] }>();

const { hasAuth } = useAuth();

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit("update:modelValue", val),
});

const loading = ref(false);
const summary = ref<AnonHospitalDataSummary | null>(null);

// 请求序号，避免短时间内多次打开覆盖最新数据
let loadSeq = 0;

// NOTE: keep in sync with backend AnonHospitalDataSummary.tables
// 2026-07-24 改：med_* 7 表 → lnrs_anon_* 7 表
const TABLE_LABELS: Record<keyof AnonHospitalDataSummary["tables"], string> = {
  patient: "患者基本信息（lnrs_anon_patient）",
  exam: "检查主表（lnrs_anon_exam）",
  report_text: "报告文本（lnrs_anon_report_text）",
  exam_detail: "检查深结构（lnrs_anon_exam_detail）",
  visit: "就诊桥（lnrs_anon_visit）",
  surgery: "手术记录（lnrs_anon_surgery）",
  ingest_batch: "导入批次（lnrs_anon_ingest_batch）",
};

const tableRows = computed(() => {
  if (!summary.value) return [];
  return Object.entries(summary.value.tables).map(([key, count]) => ({
    key,
    label: TABLE_LABELS[key as keyof AnonHospitalDataSummary["tables"]] || key,
    count,
  }));
});

const totalRows = computed(() => summary.value?.total_rows || 0);

const totalRowsFormatted = computed(() => totalRows.value.toLocaleString());

const statusMeta = computed(() => {
  const s = summary.value?.lifecycle_status || "registered";
  return LIFECYCLE_STATUS_META[s as keyof typeof LIFECYCLE_STATUS_META] || { label: s, type: "info" as const };
});

const canGoOnline = computed(
  () =>
    summary.value?.lifecycle_status === "data_imported" &&
    hasAuth("module_medical:hospital:online"),
);
const canGoOffline = computed(
  () =>
    summary.value?.lifecycle_status === "live" &&
    hasAuth("module_medical:hospital:offline"),
);

async function loadData() {
  const seq = ++loadSeq;
  loading.value = true;
  try {
    // 2026-07-24 改：用 anon 体系（getAnonDataSummary）替代 med_* 体系
    const res = await HospitalAPI.getAnonDataSummary(props.hospitalId);
    if (seq !== loadSeq) return; // 已被新的请求覆盖，丢弃过期响应
    summary.value = res.data?.data || null;
  } finally {
    if (seq === loadSeq) loading.value = false;
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

watch(
  [visible, () => props.hospitalId],
  ([val]) => {
    if (val) {
      loadData();
    } else {
      summary.value = null;
    }
  },
);
</script>

<style scoped>
.status-header {
  margin-bottom: 16px;
}
</style>
