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
        <ElDescriptionsItem label="患者编号">{{ patient?.patient_id || "-" }}</ElDescriptionsItem>
        <ElDescriptionsItem label="中心编码">{{ patient?.center_code || "-" }}</ElDescriptionsItem>
        <ElDescriptionsItem label="性别">{{ sexLabel(patient?.sex) }}</ElDescriptionsItem>
        <ElDescriptionsItem label="出生日期">{{ fmtDate(patient?.birth_date) }}</ElDescriptionsItem>
        <ElDescriptionsItem label="民族">{{ ethnicityLabel(patient?.ethnicity) }}</ElDescriptionsItem>
        <ElDescriptionsItem label="籍贯">{{ patient?.native_place || "-" }}</ElDescriptionsItem>
        <ElDescriptionsItem label="ABO血型">{{ aboLabel(patient?.abo_blood_type) }}</ElDescriptionsItem>
        <ElDescriptionsItem label="RH血型">{{ rhLabel(patient?.rh_blood_type) }}</ElDescriptionsItem>
        <ElDescriptionsItem label="吸烟状态">{{ smokingLabel(patient?.smoking_status) }}</ElDescriptionsItem>
        <ElDescriptionsItem label="首结节日期">{{ fmtDate(patient?.first_nodule_date) }}</ElDescriptionsItem>
      </ElDescriptions>

      <!-- 人口学/病史等 JSON 扩展（按来源中心不同） -->
      <div v-if="extRows.length" class="ext-block">
        <FieldRenderer
          v-for="r in extRows"
          :key="r.key"
          :key-name="r.key"
          :value="r.value"
        />
      </div>
    </ElCard>

    <!-- 四模态 Tab -->
    <ElCard shadow="never" v-loading="loading">
      <ElTabs v-model="activeTab">
        <ElTabPane label="临床" name="clinical">
          <ModalityGroup :rows="detail.clinical" empty-text="暂无临床数据" />
        </ElTabPane>
        <ElTabPane label="基因" name="genetic">
          <ModalityGroup :rows="detail.genetic" empty-text="暂无基因检测数据" />
          <FastqSection />
        </ElTabPane>
        <ElTabPane label="病理" name="pathology">
          <ModalityGroup :rows="detail.pathology" empty-text="暂无病理数据" />
        </ElTabPane>
        <ElTabPane label="影像" name="imaging">
          <div class="imaging-toolbar">
            <ElButton type="primary" :icon="Picture" @click="openDicomViewer">
              查看 DICOM 影像
            </ElButton>
            <span class="imaging-hint">在 PACS 阅片器中逐层浏览 / 调窗 / 测量</span>
          </div>
          <ModalityGroup :rows="detail.imaging" empty-text="暂无影像数据" />
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
import { computed, h, onMounted, ref, defineComponent } from "vue";
import {
  ElCard,
  ElButton,
  ElTag,
  ElDescriptions,
  ElDescriptionsItem,
  ElTabs,
  ElTabPane,
  ElCollapse,
  ElCollapseItem,
  ElEmpty,
} from "element-plus";
import { ArrowLeft, Picture } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import PatientAPI, { type ModalityRow, type PatientDetail } from "@/api/module_medical/patient";
import DicomAPI from "@/api/module_medical/dicom";
import DicomViewerDialog from "./components/DicomViewerDialog.vue";
import FastqSection from "./components/FastqSection.vue";
import FieldRenderer from "@/components/medical/field-renderer";
import { getFieldLabel } from "@/components/medical/field-renderer/field-labels";

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

const extRows = computed(() => {
  const p = detail.value.patient || {};
  const rows: { key: string; value: unknown }[] = [];
  // 优先项
  for (const k of PRIORITY_EXT_KEYS) {
    if (p[k] && !isEmpty(p[k])) rows.push({ key: k, value: p[k] });
  }
  // 自动枚举其余非空、非固定的 key
  for (const [k, v] of Object.entries(p)) {
    if (PRIORITY_EXT_KEYS.includes(k)) continue;
    if (FIXED_BASIC_KEYS.has(k)) continue;
    if (isEmpty(v)) continue;
    rows.push({ key: k, value: v });
  }
  return rows;
});

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

// --------------------------------------------------------------------------- //
// 子组件：模态分组展示。按 _table 折叠面板分组，每条记录用 ElDescriptions 平铺字段
// --------------------------------------------------------------------------- //
const ModalityGroup = defineComponent({
  name: "ModalityGroup",
  props: {
    rows: { type: Array as () => ModalityRow[], default: () => [] },
    emptyText: { type: String, default: "暂无数据" },
    /** ElDescriptions 列数；同时用作"独占整行 item 的 span"基数 */
    column: { type: Number, default: 3 },
  },
  setup(props) {
    // 按 _table 分组
    const groups = computed(() => {
      const map = new Map<string, ModalityRow[]>();
      for (const r of props.rows) {
        const key = r._table || "其他";
        if (!map.has(key)) map.set(key, []);
        map.get(key)!.push(r);
      }
      return Array.from(map.entries()).map(([name, rows]) => ({ name, rows }));
    });

    return () =>
      props.rows.length === 0
        ? h(ElEmpty, { description: props.emptyText })
        : h(
            ElCollapse,
            { modelValue: groups.value.map((_, i) => i.toString()) },
            () =>
              groups.value.map((g, gi) =>
                h(ElCollapseItem, { title: `${g.name}（${g.rows.length}）`, name: gi.toString() }, () =>
                  g.rows.map((row, ri) =>
                    h(
                      "div",
                      { class: "record-card", key: ri },
                      [
                        h(
                          ElDescriptions,
                          {
                            column: props.column,
                            border: true,
                            size: "small",
                            title: `记录 ${ri + 1}`,
                          },
                          () => renderRowFields(row, props.column),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
          );
  },
});

// 把一行记录的字段平铺为 DescriptionsItem。
//  - 标量：span=1（默认），与同行其他字段平铺
//  - object/array（FieldRenderer）：span=column，独占整行，避免挤压旁列
//    show-title=false：DescriptionsItem label 已提供语义，避免与卡片标题重复
function renderRowFields(row: ModalityRow, column: number) {
  const items: any[] = [];
  for (const [k, v] of Object.entries(row)) {
    if (k === "_table" || k === "_modality") continue;
    if (v === null || v === undefined) continue;
    if (typeof v === "object") {
        items.push(
          h(ElDescriptionsItem,
            { label: fieldLabel(k), span: column },
            () => h(FieldRenderer, { keyName: k, value: v, showTitle: false })),
        );
    } else {
      items.push(
        h(ElDescriptionsItem, { label: fieldLabel(k) },
          () => formatScalar(v)),
      );
    }
  }
  return items;
}

/** 标量格式化（与原 formatValue 标量分支一致，长文本 >200 字折叠 + 字数提示） */
function formatScalar(v: unknown): string {
  if (v === null || v === undefined || v === "") return "-";
  if (typeof v === "boolean") return v ? "是" : "否";
  const s = String(v);
  return s.length > 200 ? `${s.slice(0, 200)}…（共 ${s.length} 字）` : s;
}

// 字段名 → 中文 label（已迁出至 @/components/medical/field-renderer/field-labels）。
// 保留 FIELD_LABELS 引用以兼容旧调用；新增字段请直接改那边。
function fieldLabel(k: string): string {
  return getFieldLabel(k);
}
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
