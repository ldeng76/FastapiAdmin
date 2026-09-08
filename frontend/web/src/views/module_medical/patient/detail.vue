<!-- 医学数据 · 患者多模态详情：基本信息 + 临床/基因/病理/影像 四模态 Tab -->
<template>
  <div class="medical-detail fa-full-height" v-loading="loading">
    <ElDescriptions :column="4" border size="small" class="mb-5">
      <ElDescriptionsItem :label="getFieldLabel('patient_id')">{{ patient?.patient_id || "-" }}</ElDescriptionsItem>
      <ElDescriptionsItem :label="getFieldLabel('sex')">{{ dictStore.getDictItemLabel('med_sex',patient?.sex) }}</ElDescriptionsItem>
      <ElDescriptionsItem :label="getFieldLabel('birth_date')">{{ fmtDate(patient?.birth_date) }}</ElDescriptionsItem>
      <ElDescriptionsItem :label="getFieldLabel('ethnicity')">{{ dictStore.getDictItemLabel('med_ethnicity',patient?.ethnicity) }}</ElDescriptionsItem>
      <ElDescriptionsItem :label="getFieldLabel('native_place')">{{ patient?.native_place || "-" }}</ElDescriptionsItem>
      <ElDescriptionsItem :label="getFieldLabel('abo_blood_type')">{{ dictStore.getDictItemLabel('med_blood_type_abo',patient?.abo_blood_type) }}</ElDescriptionsItem>
      <ElDescriptionsItem :label="getFieldLabel('rh_blood_type')">{{ dictStore.getDictItemLabel('med_blood_type_rh',patient?.rh_blood_type) }}</ElDescriptionsItem>
      <ElDescriptionsItem :label="getFieldLabel('smoking_status')">{{ dictStore.getDictItemLabel('med_smoking_status',patient?.smoking_status) }}</ElDescriptionsItem>
      <ElDescriptionsItem :label="getFieldLabel('first_nodule_date')">{{ fmtDate(patient?.first_nodule_date) }}</ElDescriptionsItem>
      <!-- 最新 Lung-RADS（2026-09 新增）：取最新一次含 lung_rads 的 detail -->
      <ElDescriptionsItem :label="`${getFieldLabel('lung_rads')}`">
        <span>{{ patient?.latest_lung_rads || "-" }}</span>
        <span v-if="patient?.latest_lung_rads_date" style="color: var(--el-text-color-secondary); margin-left: 6px;">
          ({{ fmtDate(patient.latest_lung_rads_date) }})
        </span>
      </ElDescriptionsItem>
      <!-- 人口学/病史等 JSON 扩展（按来源中心不同） -->
      <ElDescriptionsItem v-for="n in getExtRow(patient)" :key="n.key" :label="getFieldLabel(n.key)">{{ n.value }}</ElDescriptionsItem>
    </ElDescriptions>
    <!-- 四模态 Tab -->
    <ElTabs  class="patient-detail-tab" v-model="activeTab">
      <ElTabPane v-for="[key, value] in [...detail.entries()]"
        :label="getFieldLabel(key)"
        :name="key"
        :key="key"
      >
        <ModalityGroup :rows="value" :name="key" />
      </ElTabPane>
    </ElTabs>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  ElDescriptions,
  ElDescriptionsItem,
  ElTabs,
  ElTabPane,
} from "element-plus";
import { ElMessage } from "element-plus";
import PatientAPI, { ModalityRowData, type PatientDetail} from "@/api/module_medical/patient";
import ModalityGroup from "@views/module_medical/patient/components/ModalityGroup.vue";
import {getFieldLabel} from "@/components/medical/field-renderer";
import {useDictStore} from "@/store";
defineOptions({ name: "MedicalPatientDetail", inheritAttrs: false });
const props = defineProps<{
  data:{detail : string ,center:string}
}>()
const dictStore = useDictStore();
const loading = ref(false);
const activeTab = ref("clinical");
const detail = ref<Map<string, ModalityRowData[]>>(
  new Map<string, ModalityRowData[]>([
    ['clinical', []],
    ['surgery', []],
    ['order', []],
    ['collection', []],
    ['genetic', []],
    ['pathology', []],
    ['ihc', []],
    ['ct', []],
    ['radiology', []],
    ['ultrasound', []]
  ])
);

const patient = ref<Record<string, any>>({});
const patientId = computed(() => (props.data.detail as string) || "");
const center = computed(() => (props.data.center as string) || undefined);

function fmtDate(v?: string): string {
  if (!v) return "-";
  return v.length > 10 ? v.slice(0, 10) : v;
}

async function fetchDetail() {
  if (!patientId.value) return;
  loading.value = true;
  try {
    const res = await PatientAPI.detailPatient(patientId.value, center.value);
    let data = res.data?.data ?? ({} as PatientDetail);
    let modal_data = data.modal_data;
    let mapData = new Map()
    mapData.set("clinical",modal_data.clinical || [])
    mapData.set("surgery",modal_data.surgery || [])
    mapData.set("order",modal_data.order || [])
    mapData.set("collection",modal_data.collection || [])
    mapData.set("genetic",modal_data.genetic || [])
    mapData.set("pathology",modal_data.pathology || [])
    mapData.set("ihc",modal_data.ihc || [])
    mapData.set("ct",modal_data.ct || [])
    mapData.set("radiology",modal_data.radiology || [])
    mapData.set("ultrasound",modal_data.ultrasound || [])
    detail.value = mapData;
    patient.value = data.patient
  } catch (err: any) {
    // 404 / 网络错误等都提示出来，避免静默"暂无数据"
    const msg =
      err?.response?.data?.msg ||
      err?.message ||
      "获取患者详情失败，请稍后重试";
    ElMessage.error(msg);
  } finally {
    loading.value = false;
  }
}
const FIXED_BASIC_KEYS = new Set([
  "patient_id",
  "center_code",
  "sex",
  "birth_date",
  "ethnicity",
  "native_place",
  "abo_blood_type",
  "rh_blood_type",
  "smoking_status",
  "first_nodule_date",
  "raw_text",
  "is_placeholder"
]);
const PRIORITY_EXT_KEYS = ["demographics", "medical_history"];
function isEmpty(v: unknown): boolean {
  if (v === null || v === undefined || v === "") return true;
  return typeof v === "object" && Object.keys(v).length === 0;
}
function getExtRow(patient:any){
  const p = patient || {};
  const rows: { key: string; value: unknown }[] = [];

  // 优先项
  for (const k of PRIORITY_EXT_KEYS) {
    if (p[k] && !isEmpty(p[k])) rows.push({ key: k, value: p[k] });
  }
  // 自动枚举其余非空、非固定的 key
  for (let [k, v] of Object.entries(p)) {
    if (PRIORITY_EXT_KEYS.includes(k)) continue;
    if (FIXED_BASIC_KEYS.has(k)) continue;
    if (isEmpty(v)) continue;
    if (typeof v === "boolean"){
       v = v ? "是" : "否"
    }
    rows.push({ key: k, value: v });
  }
  return rows;
}
onBeforeMount(async ()=>{
  await dictStore.getDict(['med_sex','med_ethnicity','med_blood_type_abo','med_blood_type_rh','med_smoking_status'])
})
onMounted(fetchDetail);

</script>

<style scoped>
.medical-detail {
  height: 100%;
}
.patient-detail-tab-324{
  height: calc(100% - 150px);
}
hr{
  border: 1px solid transparent;
  border-bottom-color: var(--default-border)
}
</style>
<style>
.patient-detail-tab .el-tabs__content,
.patient-detail-tab .el-tabs__content > .el-tab-pane{
  height: 100%;
}
</style>
