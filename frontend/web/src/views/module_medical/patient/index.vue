<!-- 医学数据 · 患者浏览：患者列表，点击「查看」进入多模态详情 -->
<template>
  <div class="fa-full-height">
    <FaSearchBar
      v-show="showSearchBar"
      ref="searchBarRef"
      v-model="searchForm"
      :items="patientSearchItems"
      :is-expand="false"
      :show-expand="true"
      :show-reset="true"
      :show-search="true"
      :disabled-search="false"
      :default-expanded="false"
      @search="handleSearchBarSearch"
      @reset="onResetSearch"
    />

    <ElCard
      shadow="hover"
      class="fa-table-card"
      :style="{ 'margin-top': showSearchBar ? '12px' : '0' }"
    >
      <FaTableHeader
        v-model:columns="columnChecks"
        v-model:showSearchBar="showSearchBar"
        :loading="loading"
        @refresh="refreshData"
      />

      <FaTable
        ref="faTableRef"
        :loading="loading"
        :data="data"
        :columns="columns"
        :pagination="pagination"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      />
    </ElCard>
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElButton } from "element-plus";
import type { SearchFormItem } from "@/components/forms/fa-search-bar/index.vue";
import type { ColumnOption } from "@/types/component";
import { useTable } from "@/hooks/core/useTable";
import PatientAPI, { type PatientPageQuery, type PatientTable } from "@/api/module_medical/patient";

defineOptions({ name: "MedicalPatient", inheritAttrs: false });

const router = useRouter();

// 中心选项：从后端动态枚举（数据当前为「珠江」单中心）
const centerOptions = ref<{ label: string; value: string }[]>([{ label: "全部", value: "" }]);

// 搜索表单
interface PatientSearchForm {
  center: string;
  keyword: string;
}
const searchForm = ref<PatientSearchForm>({ center: "", keyword: "" });
const showSearchBar = ref(true);

const patientSearchItems = computed<SearchFormItem[]>(() => [
  {
    key: "center",
    label: "来源中心",
    type: "select",
    options: centerOptions.value as unknown as Record<string, any>,
    span: 6,
  },
  {
    key: "keyword",
    label: "关键词",
    type: "input",
    placeholder: "患者编号 / 中心",
    span: 6,
  },
]);

// 跳转多模态详情（独立隐藏路由，patient_id/center 走 query 参数）
function goDetail(row: PatientTable) {
  router.push({
    path: "/medical/patient/detail",
    query: { detail: row.patient_id, center: row.center_code || "" },
  });
}

const {
  columns,
  columnChecks,
  data,
  loading,
  pagination,
  getData,
  replaceSearchParams,
  resetSearchParams,
  handleSizeChange,
  handleCurrentChange,
  refreshData,
} = useTable({
  core: {
    apiFn: PatientAPI.listPatient,
    apiParams: { page_no: 1, page_size: 10 },
    columnsFactory: (): ColumnOption<PatientTable>[] => [
      { type: "globalIndex", width: 60, label: "序号" },
      {
        prop: "patient_id",
        label: "患者编号",
        minWidth: 140,
        showOverflowTooltip: true,
      },
      {
        prop: "sex",
        label: "性别",
        minWidth: 80,
        formatter: (row) => sexLabel(row.sex),
      },
      {
        prop: "birth_date",
        label: "年龄（出生日期）",
        minWidth: 150,
        formatter: (row) => fmtAgeBirthday(row.birth_date),
      },
      {
        prop: "abo_blood_type",
        label: "血型",
        minWidth: 110,
        formatter: (row) => bloodTypeLabel(row),
      },
      {
        prop: "smoking_status",
        label: "吸烟状态",
        minWidth: 110,
        formatter: (row) => smokingLabel(row.smoking_status),
      },
      {
        prop: "first_nodule_date",
        label: "首结节日期",
        minWidth: 130,
        formatter: (row) => fmtDate(row.first_nodule_date),
      },
      {
        prop: "operation",
        label: "操作",
        width: 120,
        fixed: "right",
        formatter: (row) =>
          h(
            ElButton,
            { type: "primary", link: true, onClick: () => goDetail(row) },
            () => "多模态查看",
          ),
      },
    ],
  },
});

// ISO 日期 → YYYY-MM-DD
function fmtDate(v?: string): string {
  if (!v) return "-";
  return v.length > 10 ? v.slice(0, 10) : v;
}

// 搜索
function handleSearchBarSearch() {
  replaceSearchParams({
    center: searchForm.value.center || undefined,
    keyword: searchForm.value.keyword || undefined,
  });
  getData();
}

function onResetSearch() {
  searchForm.value = { center: "", keyword: "" };
  resetSearchParams();
  getData();
}

// 拉取来源中心枚举，填充下拉
async function loadCenters() {
  try {
    const res = await PatientAPI.listCenters();
    const list = res.data?.data || [];
    centerOptions.value = [
      { label: "全部", value: "" },
      ...list.map((c: string) => ({ label: c, value: c })),
    ];
  } catch {
    centerOptions.value = [{ label: "全部", value: "" }];
  }
}

onMounted(loadCenters);

// 枚举值翻译（国标码 → 中文）—— 2026-07-24 改 anon 体系后，原生是国标码

const SEX_LABEL: Record<string, string> = {
  "0": "未知",
  "1": "男",
  "2": "女",
  "9": "未说明",
};
function sexLabel(code?: string) {
  if (!code) return "-";
  return SEX_LABEL[code] || code;
}

// 1=从不, 2=既往, 3=现在, 9=未知
const SMOKING_LABEL: Record<string, string> = {
  "1": "从不",
  "2": "既往",
  "3": "现在",
  "9": "未知",
};
function smokingLabel(code?: string) {
  if (!code) return "-";
  return SMOKING_LABEL[code] || code;
}

// 年龄（出生日期）合并显示：如 "62（1963-05）"
function calcAge(birthIso?: string): number | null {
  if (!birthIso) return null;
  const b = new Date(birthIso.slice(0, 10));
  if (isNaN(b.getTime())) return null;
  const now = new Date();
  let age = now.getFullYear() - b.getFullYear();
  const m = now.getMonth() - b.getMonth();
  if (m < 0 || (m === 0 && now.getDate() < b.getDate())) age--;
  return age >= 0 && age < 150 ? age : null;
}
function fmtAgeBirthday(v?: string): string {
  if (!v) return "-";
  const age = calcAge(v);
  const ym = v.length >= 7 ? v.slice(0, 7) : v;
  return age !== null ? `${age}（${ym}）` : ym;
}

// HQMS RC030 ABO 血型：1=A型 2=B型 3=O型 4=AB型 5=不详 6=未查
const ABO_LABEL: Record<string, string> = {
  "1": "A型",
  "2": "B型",
  "3": "O型",
  "4": "AB型",
  "5": "不详",
  "6": "未查",
};
// HQMS RC031 Rh 血型：1=阴性 2=阳性 3=不详 4=未查
const RH_LABEL: Record<string, string> = {
  "1": "阴性",
  "2": "阳性",
  "3": "不详",
  "4": "未查",
};
// 血型合并显示：ABO/Rh，如 "A型/阳性"；缺失则单独显示已有项；都无则 "-"
function bloodTypeLabel(row: PatientTable): string {
  const a = row.abo_blood_type
    ? ABO_LABEL[row.abo_blood_type] || row.abo_blood_type
    : null;
  const r = row.rh_blood_type
    ? RH_LABEL[row.rh_blood_type] || row.rh_blood_type
    : null;
  if (a && r) return `${a}/${r}`;
  return a || r || "-";
}
</script>
