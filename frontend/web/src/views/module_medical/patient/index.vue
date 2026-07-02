<!-- 医学数据 · 患者浏览：跨中心患者列表，点击「查看」进入多模态详情 -->
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
import { h, ref } from "vue";
import { useRouter } from "vue-router";
import { ElTag, ElButton } from "element-plus";
import type { ColumnOption } from "@/types/component";
import { useTable } from "@/hooks/core/useTable";
import PatientAPI, { type PatientPageQuery, type PatientTable } from "@/api/module_medical/patient";

defineOptions({ name: "MedicalPatient", inheritAttrs: false });

const router = useRouter();

// 中心选项
const CENTER_OPTIONS = [
  { label: "全部", value: "" },
  { label: "省医", value: "省医" },
  { label: "珠江", value: "珠江" },
  { label: "新桥", value: "新桥" },
];

// 搜索表单
interface PatientSearchForm {
  center: string;
  keyword: string;
}
const searchForm = ref<PatientSearchForm>({ center: "", keyword: "" });
const showSearchBar = ref(true);

const patientSearchItems = [
  {
    prop: "center",
    label: "来源中心",
    type: "select",
    options: CENTER_OPTIONS,
    span: 6,
  },
  {
    prop: "keyword",
    label: "关键词",
    type: "input",
    placeholder: "患者编号 / 中心",
    span: 6,
  },
];

// 跳转多模态详情（独立隐藏路由，patient_id/center 走 query 参数）
function goDetail(row: PatientTable) {
  router.push({
    path: "/medical/patient/detail",
    query: { detail: row.patient_id, center: row.source_center || "" },
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
      { type: "globalIndex", width: 56, label: "序号" },
      { prop: "patient_id", label: "患者编号", minWidth: 120, showOverflowTooltip: true },
      {
        prop: "source_center",
        label: "来源中心",
        width: 100,
        formatter: (row) =>
          h(ElTag, { type: "info", effect: "plain" }, () => row.source_center || "-"),
      },
      { prop: "gender", label: "性别", width: 70 },
      { prop: "birth_date", label: "出生日期", width: 120, formatter: (row) => fmtDate(row.birth_date) },
      { prop: "ethnicity", label: "民族", width: 80, formatter: (row) => row.ethnicity || "-" },
      {
        prop: "smoking_status",
        label: "吸烟状态",
        width: 100,
        formatter: (row) => row.smoking_status || "-",
      },
      {
        prop: "first_nodule_date",
        label: "首结节日期",
        width: 120,
        formatter: (row) => fmtDate(row.first_nodule_date),
      },
      {
        prop: "operation",
        label: "操作",
        width: 100,
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
</script>
