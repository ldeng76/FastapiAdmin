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
      :buttonLeftLimit="10"
      :default-expanded="false"
      @search="handleSearchBarSearch"
      @reset="resetSearchParams"
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
        :header-cell-style="{ backgroundColor: '#f5f7fa' }"
        :columns="columns"
        :pagination="pagination"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      />
    </ElCard>
  </div>
  <el-dialog class="flex flex-col" v-model="showDetail" fullscreen>
    <template #title>
      <ElButton :icon="ArrowLeft" link @click="showDetail = false">返回列表</ElButton>
      <span class="patient-title">
        患者多模态数据 ·  <el-tag type="primary" round>{{ showPatientId }}</el-tag>
      </span>
    </template>
    <Detail v-if="showDetail" :data="showDetailData" :goBack="()=>{showDetail = false}" />
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, h, onMounted, ref } from "vue";
import { ElButton } from "element-plus";
import type { SearchFormItem } from "@/components/forms/fa-search-bar/index.vue";
import type { ColumnOption } from "@/types/component";
import { useTable } from "@/hooks/core/useTable";
import PatientAPI, { type PatientTable } from "@/api/module_medical/patient";
import Detail from "./detail.vue";
import {useDictStore} from "@/store";
import {ArrowLeft} from "@element-plus/icons-vue";
defineOptions({ name: "MedicalPatient", inheritAttrs: false });
const dictStore = useDictStore()
const showPatientId = ref('')
const showDetail = ref(false);
const showDetailData = ref({
  detail: '',
  center: ""
});


// 搜索表单
interface PatientSearchForm {
  center: string;
  keyword: string;
}
const searchForm = ref<PatientSearchForm>({ center: "", keyword: "" });
const showSearchBar = ref(true);

const patientSearchItems = computed<SearchFormItem[]>(() => [
  {
    key: "keyword",
    label: "关键词",
    type: "input",
    placeholder: "患者编号",
    span: 4,
  },
  {
    label: "性别",
    key: "sex",
    type: "select",
    props: {
      placeholder: "请选择",
      options: dictStore.getDictArray('med_sex').map(function (n){
        return {value:n.dict_value,label:n.dict_label}
      }),
      clearable: true,
    },
    span: 4,
  },
  {
    label: "吸烟状态",
    key: "smoking_status",
    type: "select",
    props: {
      placeholder: "请选择",
      options: dictStore.getDictArray('med_smoking_status').map(function (n){
        return {value:n.dict_value,label:n.dict_label}
      }),
      clearable: true,
    },
    span: 4,
  },
]);

// 跳转多模态详情（独立隐藏路由，patient_id/center 走 query 参数）
function goDetail(row: PatientTable) {
  showPatientId.value = row.patient_id
  showDetailData.value = { detail: row.patient_id, center: row.center_code || "" }
  showDetail.value = true
}

const {
  columns,
  columnChecks,
  data,
  loading,
  pagination,
  getData,
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
        formatter: (row) => dictStore.getDictItemLabel("med_sex",row.sex),
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
        formatter: (row) => dictStore.getDictItemLabel("med_smoking_status",row.smoking_status),
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
            { type: "primary",size:"small", onClick: () => goDetail(row) },
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
  getData(searchForm.value);
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

// 血型合并显示：ABO/Rh，如 "A型/阳性"；缺失则单独显示已有项；都无则 "-"
function bloodTypeLabel(row: PatientTable): string {
  const a = dictStore.getDictItemLabel("med_blood_type_abo",row.abo_blood_type);
  const r = dictStore.getDictItemLabel("med_blood_type_rh",row.rh_blood_type);
  if (a && r) return `${a}/${r}`;
  return a || r || "-";
}

</script>
<style>

</style>
