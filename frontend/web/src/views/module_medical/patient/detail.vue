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
            <ElTag v-if="patient?.source_center" type="info" effect="plain" class="ml-8">
              {{ patient.source_center }}
            </ElTag>
          </span>
        </div>
      </template>

      <ElDescriptions v-loading="loading" :column="4" border size="small">
        <ElDescriptionsItem label="患者编号">{{ patient?.patient_id || "-" }}</ElDescriptionsItem>
        <ElDescriptionsItem label="来源中心">{{ patient?.source_center || "-" }}</ElDescriptionsItem>
        <ElDescriptionsItem label="性别">{{ patient?.gender || "-" }}</ElDescriptionsItem>
        <ElDescriptionsItem label="出生日期">{{ fmtDate(patient?.birth_date) }}</ElDescriptionsItem>
        <ElDescriptionsItem label="民族">{{ patient?.ethnicity || "-" }}</ElDescriptionsItem>
        <ElDescriptionsItem label="籍贯">{{ patient?.native_place || "-" }}</ElDescriptionsItem>
        <ElDescriptionsItem label="ABO血型">{{ patient?.abo_blood_type || "-" }}</ElDescriptionsItem>
        <ElDescriptionsItem label="RH血型">{{ patient?.rh_blood_type || "-" }}</ElDescriptionsItem>
        <ElDescriptionsItem label="吸烟状态">{{ patient?.smoking_status || "-" }}</ElDescriptionsItem>
        <ElDescriptionsItem label="首结节日期">{{ fmtDate(patient?.first_nodule_date) }}</ElDescriptionsItem>
      </ElDescriptions>

      <!-- 人口学/病史等 JSON 扩展（按来源中心不同） -->
      <div v-if="extRows.length" class="ext-block">
        <div v-for="r in extRows" :key="r.label" class="ext-item">
          <span class="ext-label">{{ r.label }}：</span>
          <span class="ext-value">{{ r.text }}</span>
        </div>
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
        </ElTabPane>
        <ElTabPane label="病理" name="pathology">
          <ModalityGroup :rows="detail.pathology" empty-text="暂无病理数据" />
        </ElTabPane>
        <ElTabPane label="影像" name="imaging">
          <ModalityGroup :rows="detail.imaging" empty-text="暂无影像数据" />
        </ElTabPane>
      </ElTabs>
    </ElCard>
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, ref, defineComponent } from "vue";
import { useRoute, useRouter } from "vue-router";
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
import { ArrowLeft } from "@element-plus/icons-vue";
import PatientAPI, { type ModalityRow, type PatientDetail } from "@/api/module_medical/patient";

defineOptions({ name: "MedicalPatientDetail", inheritAttrs: false });

const route = useRoute();
const router = useRouter();

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
const patientId = computed(() => (route.query.detail as string) || "");
const center = computed(() => (route.query.center as string) || undefined);

// 基本信息 JSON 扩展列（visit_counts / demographics / medical_history）
const extRows = computed(() => {
  const p = detail.value.patient || {};
  const rows: { label: string; text: string }[] = [];
  if (p.visit_counts) rows.push({ label: "就诊次数", text: JSON.stringify(p.visit_counts) });
  if (p.demographics) rows.push({ label: "人口学", text: JSON.stringify(p.demographics) });
  if (p.medical_history) rows.push({ label: "既往病史", text: JSON.stringify(p.medical_history) });
  return rows;
});

function fmtDate(v?: string): string {
  if (!v) return "-";
  return v.length > 10 ? v.slice(0, 10) : v;
}

function goBack() {
  router.push("/medical/patient");
}

// 兼容：若直接通过 /medical/patient/detail 进入但无 detail 参数，回列表


async function fetchDetail() {
  if (!patientId.value) return;
  loading.value = true;
  try {
    const res = await PatientAPI.detailPatient(patientId.value, center.value);
    detail.value = res.data;
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
                          { column: 3, border: true, size: "small", title: `记录 ${ri + 1}` },
                          () => renderRowFields(row),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
          );
  },
});

// 把一行记录的字段平铺为 DescriptionsItem（跳过 _table，JSON 对象递归展示）
function renderRowFields(row: ModalityRow) {
  const items: any[] = [];
  for (const [k, v] of Object.entries(row)) {
    if (k === "_table") continue;
    items.push(
      h(ElDescriptionsItem, { label: fieldLabel(k) }, () => formatValue(v)),
    );
  }
  return items;
}

function formatValue(v: any): string {
  if (v === null || v === undefined || v === "") return "-";
  if (typeof v === "object") return JSON.stringify(v);
  if (typeof v === "boolean") return v ? "是" : "否";
  return String(v);
}

// 字段名中文映射（覆盖常见字段，未命中原样返回）
const FIELD_LABELS: Record<string, string> = {
  patient_id: "患者编号",
  source_center: "来源中心",
  visit_id: "就诊编号",
  specimen_id: "标本号",
  test_id: "检测号",
  surgery_date: "手术日期",
  procedure_name: "术式",
  resection_scope: "切除范围",
  surgical_approach: "手术入路",
  procedure_detail: "手术详情",
  exam_date: "检查日期",
  exam_type: "检查类型",
  nodule_no: "结节编号",
  nodule_location: "结节位置",
  long_diameter: "长径(mm)",
  density_type: "密度类型",
  nodule_morphology: "形态征象",
  nodule_quantitative: "定量参数",
  follow_up_comparison: "对比变化",
  exam_meta: "检查元数据",
  ki67_pct: "Ki-67(%)",
  markers: "标志物",
  last_followup_date: "末次随访",
  recurrence: "复发",
  survival_status: "生存状态",
  treatment_detail: "治疗详情",
  recurrence_detail: "复发详情",
  test_method: "检测方法",
  variant_type: "变异类型",
  test_meta: "检测元数据",
  variant_result: "变异结果",
  driver_mutations: "驱动基因",
  immune_markers: "免疫标志物",
  histology_class: "组织学分类",
  pathology_diagnosis: "病理诊断",
  tumor_total_size_mm: "肿瘤大小(mm)",
  specimen_type: "标本类型",
  sampling_site: "取材部位",
  adenocarcinoma_subtypes: "腺癌亚型",
  tumor_measurement: "肿瘤测量",
  high_risk_factors: "高危因素",
  staging: "分期",
  specimen_meta: "标本元数据",
  exam_detail: "检查详情",
  order_time: "医嘱时间",
  drug_generic_name: "药物",
  order_detail: "医嘱详情",
  order_source: "医嘱来源",
  item_name: "检验项",
  item_result: "结果",
  item_unit: "单位",
  ref_lower: "参考下限",
  ref_upper: "参考上限",
  collection_time: "采集时间",
  test_name: "检验项目",
  report_id: "报告号",
  visit_category: "就诊类别",
  admission_time: "入院时间",
  discharge_date: "出院日期",
  admission_dept: "入院科室",
  length_of_stay: "住院天数",
  visit_age: "就诊年龄",
  diagnoses: "诊断",
  exam_body_part: "检查部位",
  exam_item: "检查项目",
  gender: "性别",
  birth_date: "出生日期",
};

function fieldLabel(k: string): string {
  return FIELD_LABELS[k] || k;
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
</style>
