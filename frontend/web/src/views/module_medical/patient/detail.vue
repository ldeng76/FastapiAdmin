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
        <ElDescriptionsItem :label="getFieldLabel('sex')">{{ sexLabel(patient?.sex) }}</ElDescriptionsItem>
        <ElDescriptionsItem :label="getFieldLabel('birth_date')">{{ fmtDate(patient?.birth_date) }}</ElDescriptionsItem>
        <ElDescriptionsItem :label="getFieldLabel('ethnicity')">{{ ethnicityLabel(patient?.ethnicity) }}</ElDescriptionsItem>
        <ElDescriptionsItem :label="getFieldLabel('native_place')">{{ patient?.native_place || "-" }}</ElDescriptionsItem>
        <ElDescriptionsItem :label="getFieldLabel('abo_blood_type')">{{ aboLabel(patient?.abo_blood_type) }}</ElDescriptionsItem>
        <ElDescriptionsItem :label="getFieldLabel('rh_blood_type')">{{ rhLabel(patient?.rh_blood_type) }}</ElDescriptionsItem>
        <ElDescriptionsItem :label="getFieldLabel('smoking_status')">{{ smokingLabel(patient?.smoking_status) }}</ElDescriptionsItem>
        <ElDescriptionsItem :label="getFieldLabel('first_nodule_date')">{{ fmtDate(patient?.first_nodule_date) }}</ElDescriptionsItem>
        <!-- 人口学/病史等 JSON 扩展（按来源中心不同） -->
<!--        <ElDescriptionsItem v-for="n in getExtRow(detail.patient)" :key="n.key" :label="n.key">{{ n.value }}</ElDescriptionsItem>-->
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
          <FastqSection />
        </ElTabPane>
        <ElTabPane :label="getFieldLabel('pathology')" name="pathology">
          <ModalityGroup :rows="detail.pathology" name="pathology" />
        </ElTabPane>
        <ElTabPane :label="getFieldLabel('imaging')" name="imaging">
          <div class="imaging-toolbar">
            <ElButton type="primary" :icon="Picture" @click="openDicomViewer">
              查看 DICOM 影像
            </ElButton>
            <span class="imaging-hint">在 PACS 阅片器中逐层浏览 / 调窗 / 测量</span>
          </div>
          <ModalityGroup :rows="detail.imaging"  name="imaging" />
        </ElTabPane>
      </ElTabs>
    </ElCard>

    <!-- DICOM 影像查看器（全屏弹窗） -->
    <DicomViewerDialog
      v-model="dicomViewerVisible"
      :study-id="dicomStudyId"
      :patient-name="patient?.patient_name as string"
    />
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
import { ArrowLeft, Picture } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import PatientAPI, {  type PatientDetail } from "@/api/module_medical/patient";
import ModalityGroup from "@views/module_medical/patient/components/ModalityGroup.vue";
import DicomAPI from "@/api/module_medical/dicom";
import DicomViewerDialog from "./components/DicomViewerDialog.vue";
import FastqSection from "./components/FastqSection.vue";
import {getFieldLabel} from "@/components/medical/field-renderer";
defineOptions({ name: "MedicalPatientDetail", inheritAttrs: false });
const props = defineProps<{
  data:{detail : string ,center:string},
  goBack:()=> void
}>()

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

// DICOM 影像查看器
const dicomViewerVisible = ref(false);
const dicomStudyId = ref<string>("");
// 首期按数据目录浏览：按约定 Study 目录名 = <patient_id>_1 查找；
// 若该目录不存在（如 demo 患者无对应 DICOM），回退到数据目录中第一个可用 Study，
// 便于开发期用示例数据验证阅片功能。后续可由 nodule_imaging.exam_id 映射真实 Study。
async function openDicomViewer() {
  const expected = patientId.value ? `${patientId.value}_1` : "";
  let target = expected;
  try {
    const res = await DicomAPI.listStudies();
    const studies = res.data?.data || [];
    if (studies.length) {
      const matched = studies.find((s) => s.study_id === expected);
      target = matched ? expected : studies[0].study_id;
      if (!matched && expected) {
        ElMessage.info(`未找到 ${expected} 的 DICOM 数据，已切换至示例数据 ${target}`);
      }
    }
  } catch {
    /* 查询失败则用约定值，由 viewer 内部报错 */
  }
  dicomStudyId.value = target;
  dicomViewerVisible.value = true;
}

// 基本信息 JSON 扩展列。
//   - 优先渲染 demographics / medical_history（高频语义字段）
//   - 自动枚举 patient dict 里其它未在固定 ElDescriptionsItem 中展示的 key
//   - 全部走 FieldRenderer：命中 schema → 业务卡片；未命中 → FaJsonPretty 折叠 JSON 树
// 固定的 10 项基本信息已显式列在 ElDescriptionsItem 里，这里跳过避免重复。
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
]);
const PRIORITY_EXT_KEYS = ["demographics", "medical_history"];

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

function isEmpty(v: unknown): boolean {
  if (v === null || v === undefined || v === "") return true;
  if (typeof v === "object" && Object.keys(v).length === 0) return true;
  return false;
}

function fmtDate(v?: string): string {
  if (!v) return "-";
  return v.length > 10 ? v.slice(0, 10) : v;
}

// 国标码翻译（2026-07-24 改 anon 体系后用）
const SEX_LABEL: Record<string, string> = { "0": "未知", "1": "男", "2": "女", "9": "未说明" };
function sexLabel(code?: string) { return code ? (SEX_LABEL[code] || code) : "-"; }

const ETHNICITY_LABEL: Record<string, string> = { "01": "汉族", "99": "其他" };
function ethnicityLabel(code?: string) { return code ? (ETHNICITY_LABEL[code] || code) : "-"; }

const SMOKING_LABEL: Record<string, string> = { "1": "从不", "2": "既往", "3": "现在", "9": "未知" };
function smokingLabel(code?: string) { return code ? (SMOKING_LABEL[code] || code) : "-"; }

// HQMS RC030 ABO 血型：1=A型, 2=B型, 3=O型, 4=AB型, 5=不详, 6=未查
const ABO_LABEL: Record<string, string> = {
  "1": "A型", "2": "B型", "3": "O型", "4": "AB型", "5": "不详", "6": "未查",
};
function aboLabel(code?: string) { return code ? (ABO_LABEL[code] || code) : "-"; }

// HQMS RC031 Rh 血型：1=阴性, 2=阳性, 3=不详
const RH_LABEL: Record<string, string> = { "1": "阴性", "2": "阳性", "3": "不详" };
function rhLabel(code?: string) { return code ? (RH_LABEL[code] || code) : "-"; }

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
.ext-block {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px 24px;
}
.ext-item {
  font-size: 13px;
  color: #606266;
}
.ext-label {
  color: #909399;
}
.ext-value {
  color: #303133;
}
:deep(.record-card) {
  margin-bottom: 10px;
}
:deep(.el-collapse-item__header) {
  font-weight: 600;
}
.imaging-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.imaging-hint {
  font-size: 13px;
  color: #909399;
}
</style>
