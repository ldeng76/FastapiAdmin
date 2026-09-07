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
        @sort-change="onSortChange"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      />
    </ElCard>
  </div>
  <el-dialog :bodyClass="'patientDetailBody'" v-model="showDetail" fullscreen>
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
import { computed, h, ref } from "vue";
import { ElButton, ElTag } from "element-plus";
import type { SearchFormItem } from "@/components/forms/fa-search-bar/index.vue";
import type { ColumnOption } from "@/types/component";
import { useTable } from "@/hooks/core/useTable";
import PatientAPI, { type PatientTable } from "@/api/module_medical/patient";
import Detail from "./detail.vue";
import {useDictStore} from "@/store";
import {ArrowLeft} from "@element-plus/icons-vue";
import {getFieldLabel} from "@/components/medical/field-renderer";
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
  include_placeholders?: boolean;
}
const searchForm = ref<PatientSearchForm>({
  center: "",
  keyword: "",
  // 默认隐藏占位患者（无人口学，仅检查/就诊/手术导入自动发号）
  include_placeholders: false,
});
const showSearchBar = ref(true);

const patientSearchItems = computed<SearchFormItem[]>(() => [
  {
    key: "keyword",
    label: "患者编号",
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
  {
    key: "include_placeholders",
    label: "占位患者",
    type: "switch",
    props: {
      inlinePrompt: true,
      activeText: "显示",
      inactiveText: "隐藏",
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
const sortParams = ref({sort_field:"",sort_order:""})
function onSortChange({ prop, order }:any){
  if(order){
     order = order.replace("ending","")
  }
  sortParams.value = {
    sort_field:prop,
    sort_order:order
  }
}
const {
  columns,
  columnChecks,
  data,
  loading,
  pagination,
  replaceSearchParams,
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
        label: getFieldLabel("patient_id"),
        minWidth: 170,
        sortable: "custom",
        showOverflowTooltip: true,
        formatter: (row) =>
          row.is_placeholder
            ? h("span", [
                h("span", row.patient_id),
                h(
                  ElTag,
                  { size: "small", type: "info", style: "margin-left: 6px" },
                  () => "占位",
                ),
              ])
            : row.patient_id,
      },
      {
        prop: "sex",
        label: getFieldLabel("sex"),
        minWidth: 80,
        sortable :'custom',
        formatter: (row) => dictStore.getDictItemLabel("med_sex",row.sex),
      },
      {
        prop: "birth_date",
        label: "年龄（出生日期）",
        minWidth: 150,
        sortable :'custom',
        formatter: (row) => fmtAgeBirthday(row.birth_date),
      },
      {
        prop: "abo_blood_type",
        label: getFieldLabel("abo_blood_type"),
        minWidth: 80,
        sortable :'custom',
        formatter: (row) => dictStore.getDictItemLabel("med_blood_type_abo",row.abo_blood_type),
      },
      {
        prop: "med_blood_type_rh",
        label: getFieldLabel("rh_blood_type"),
        minWidth: 80,
        sortable :'custom',
        formatter: (row) => dictStore.getDictItemLabel("med_blood_type_rh",row.rh_blood_type),
      },
      {
        prop: "smoking_status",
        label: getFieldLabel("smoking_status"),
        minWidth: 110,
        sortable :'custom',
        formatter: (row) => dictStore.getDictItemLabel("med_smoking_status",row.smoking_status),
      },
      {
        prop: "first_nodule_date",
        label: getFieldLabel("first_nodule_date"),
        minWidth: 130,
        sortable :'custom',
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

watch([sortParams],function (){
  handleSearchBarSearch()
})

// 搜索
function handleSearchBarSearch() {
  let params:any = Object.assign({},searchForm.value)
  if(sortParams.value.sort_field && sortParams.value.sort_order){
    let obj :any = {}
    obj[sortParams.value.sort_field] = sortParams.value.sort_order
    params.order_by = JSON.stringify([obj])
  }
  replaceSearchParams(params)
  getData(params);
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

onBeforeMount(async ()=>{
  await dictStore.getDict(['med_sex','med_blood_type_abo','med_blood_type_rh','med_smoking_status'])
})
</script>
<style>
.patientDetailBody{
  height: calc(100% - 60px);
  overflow: auto;
}
</style>
