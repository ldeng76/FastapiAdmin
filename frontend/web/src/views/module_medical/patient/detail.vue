<!-- 医学数据 · 患者多模态详情：基本信息 + 临床/基因/病理/影像 四模态 Tab -->
<template>
  <div class="medical-detail">
    <!-- 顶部：返回 + 患者基本信息 -->
    <ElCard shadow="never" class="mb-12">
      <template #header>
        <div class="detail-header">
          <ElButton :icon="ArrowLeft" link @click="goBack">返回列表</ElButton>
          <span class="patient-title">
            患者多模态数据 · {{ patient?.patient_id }}
            <ElTag v-if="patient?.center_code" type="info" effect="plain" class="ml-8">
              {{ patient.center_code }}
            </ElTag>
          </span>
        </div>
      </template>

      <ElDescriptions v-loading="loading" :column="4" border size="small">
        <ElDescriptionsItem :label="getFieldLabel('patient_id')">{{ patient?.patient_id || "-" }}</ElDescriptionsItem>
        <ElDescriptionsItem :label="getFieldLabel('sex')">{{ dictStore.getDictItemLabel('med_sex',patient?.sex) }}</ElDescriptionsItem>
        <ElDescriptionsItem :label="getFieldLabel('birth_date')">{{ fmtDate(patient?.birth_date) }}</ElDescriptionsItem>
        <ElDescriptionsItem :label="getFieldLabel('ethnicity')">{{ dictStore.getDictItemLabel('med_ethnicity',patient?.ethnicity) }}</ElDescriptionsItem>
        <ElDescriptionsItem :label="getFieldLabel('native_place')">{{ patient?.native_place || "-" }}</ElDescriptionsItem>
        <ElDescriptionsItem :label="getFieldLabel('abo_blood_type')">{{ dictStore.getDictItemLabel('med_blood_type_abo',patient?.abo_blood_type) }}</ElDescriptionsItem>
        <ElDescriptionsItem :label="getFieldLabel('rh_blood_type')">{{ dictStore.getDictItemLabel('med_blood_type_rh',patient?.rh_blood_type) }}</ElDescriptionsItem>
        <ElDescriptionsItem :label="getFieldLabel('smoking_status')">{{ dictStore.getDictItemLabel('med_smoking_status',patient?.smoking_status) }}</ElDescriptionsItem>
        <ElDescriptionsItem :label="getFieldLabel('first_nodule_date')">{{ fmtDate(patient?.first_nodule_date) }}</ElDescriptionsItem>
        <!-- 人口学/病史等 JSON 扩展（按来源中心不同） -->
        <ElDescriptionsItem v-for="n in getExtRow(detail.patient)" :key="n.key" :label="getFieldLabel(n.key)">{{ n.value }}</ElDescriptionsItem>
      </ElDescriptions>
    </ElCard>

    <!-- 四模态 Tab -->
    <ElCard shadow="never" v-loading="loading">
      <ElTabs v-model="activeTab">
        <ElTabPane :label="getFieldLabel('clinical')" name="clinical">
          <ModalityGroup :rows="detail.clinical" name="clinical" />
        </ElTabPane>
        <ElTabPane :label="getFieldLabel('genetic')" name="genetic">
          <ModalityGroup :rows="detail.genetic" name="genetic" />
        </ElTabPane>
        <ElTabPane :label="getFieldLabel('pathology')" name="pathology">
          <ModalityGroup :rows="detail.pathology" name="pathology" />
        </ElTabPane>
        <ElTabPane :label="getFieldLabel('imaging')" name="imaging">
          <ModalityGroup :rows="detail.imaging"  name="imaging" />
        </ElTabPane>
      </ElTabs>
    </ElCard>

  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  ElCard,
  ElButton,
  ElTag,
  ElDescriptions,
  ElDescriptionsItem,
  ElTabs,
  ElTabPane,
} from "element-plus";
import { ArrowLeft } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import PatientAPI, {  type PatientDetail } from "@/api/module_medical/patient";
import ModalityGroup from "@views/module_medical/patient/components/ModalityGroup.vue";
import {getFieldLabel} from "@/components/medical/field-renderer";
import {useDictStore} from "@/store";
defineOptions({ name: "MedicalPatientDetail", inheritAttrs: false });
const props = defineProps<{
  data:{detail : string ,center:string},
  goBack:()=> void
}>()
const dictStore = useDictStore();
const loading = ref(false);
const activeTab = ref("clinical");
const detail = ref<PatientDetail>({
  patient: {},
  clinical: [],
  genetic: [],
  pathology: [],
  imaging: [],
});

const patient = computed(() => detail.value.patient);
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
    detail.value = res.data?.data ?? ({} as PatientDetail);
  } catch (err: any) {
    // 404 / 网络错误等都提示出来，避免静默"暂无数据"
    const msg =
      err?.response?.data?.msg ||
      err?.message ||
      "获取患者详情失败，请稍后重试";
    ElMessage.error(msg);
    detail.value = {} as PatientDetail;
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

onMounted(fetchDetail);

</script>

<style scoped>
.medical-detail {
  padding: 12px;
}
.mb-12 {
  margin-bottom: 12px;
}
.detail-header {
  display: flex;
  align-items: center;
  gap: 12px;
}
.patient-title {
  font-weight: 600;
  font-size: 15px;
}
.ml-8 {
  margin-left: 8px;
}
</style>
