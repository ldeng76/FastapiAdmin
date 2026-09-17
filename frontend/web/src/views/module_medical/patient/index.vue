<!-- 医学数据 · 患者浏览：患者列表，点击「查看」进入多模态详情 -->
<template>
  <div class="fa-full-height">
    <FaSearchBar
      v-show="showSearchBar"
      ref="searchBarRef"
      v-model="searchForm"
      :items="patientSearchItems"
      :is-expand="true"
      :show-reset="true"
      :show-search="true"
      @search="handleSearchBarSearch"
      @reset="()=>{
        searchForm = {}
        replaceSearchParams({})
        getData(getNewQuery({}))
      }"
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
    <template #header>
      <ElButton :icon="ArrowLeft" link @click="showDetail = false">返回列表</ElButton>
      <span class="patient-title">
        患者多模态数据 ·  <el-tag type="primary" round>{{ showPatientId }}</el-tag>
      </span>
    </template>
    <Detail v-if="showDetail" :data="showDetailData" :goBack="()=>{showDetail = false}" />
  </el-dialog>
</template>

<script setup lang="ts">
import {  h, ref } from "vue";
import { ElButton, ElTag } from "element-plus";
import type { SearchFormItem } from "@/components/forms/fa-search-bar/index.vue";
import type { ColumnOption } from "@/types/component";
import { useTable } from "@/hooks/core/useTable";
import PatientAPI, { type PatientTable } from "@/api/module_medical/patient";
import Detail from "./detail.vue";
import {useDictStore} from "@/store";
import {ArrowLeft} from "@element-plus/icons-vue";
import {getFieldLabel} from "@/components/medical/field-renderer";
import StatisticsAPI from "@api/module_medical/statistics.ts";
defineOptions({ name: "MedicalPatient", inheritAttrs: false });
const dictStore = useDictStore()
const route = useRoute();
const showPatientId = ref('')
const showDetail = ref(false);
const showDetailData = ref({
  detail: '',
  center: ""
});
let query:any = getNewQuery(route.query);

const searchForm = ref<any>(query);
const showSearchBar = ref(true);
const patientSearchItems = ref<SearchFormItem[]>([])

function getNewQuery(query:any){
  query.is_placeholders = true;
  return query
}

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
  handleSizeChange,
  handleCurrentChange,
  refreshData,
} = useTable({
  core: {
    apiFn: PatientAPI.listPatient,
    apiParams: Object.assign({ page_no: 1, page_size: 10 },query),
    columnsFactory: (): ColumnOption<PatientTable>[] => [
      { type: "globalIndex", width: 60, label: "序号" },
      {
        prop: "patient_id",
        label: getFieldLabel("patient_id"),
        minWidth: 120,
        sortable: "custom",
        showOverflowTooltip: true
      },
      {
        prop: "sex",
        label: getFieldLabel("sex"),
        minWidth: 120,
        sortable :'custom',
        formatter: (row) => dictStore.getDictItemLabel("med_sex",row.sex),
      },
      {
        prop: "birth_date",
        label: "年龄（出生日期）",
        minWidth: 160,
        sortable :'custom',
        formatter: (row) => fmtAgeBirthday(row.birth_date),
      },
      {
        prop: "abo_blood_type",
        label: getFieldLabel("abo_blood_type"),
        minWidth: 120,
        sortable :'custom',
        formatter: (row) => dictStore.getDictItemLabel("med_blood_type_abo",row.abo_blood_type),
      },
      {
        prop: "med_blood_type_rh",
        label: getFieldLabel("rh_blood_type"),
        minWidth: 110,
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
        prop: "bmi",
        label: getFieldLabel("bmi"),
        minWidth: 80,
        sortable :'custom'
      },
      {
        prop: "first_nodule_date",
        label: getFieldLabel("first_nodule_date"),
        minWidth: 130,
        sortable :'custom',
        formatter: (row) => fmtDate(row.first_nodule_date),
      },
      {
        prop: "latest_lung_rads",
        label: `${getFieldLabel("lung_rads")}(最新)`,
        minWidth: 170,
        sortable :'custom'
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
  let params:any = Object.assign({is_placeholders:true},searchForm.value)
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
  const ageBuckets = await StatisticsAPI.getAgeBuckets()
  const bmiBuckets = await StatisticsAPI.getBmiBuckets()
  await dictStore.getDict(['med_sex','med_center','med_exam_type','med_blood_type_abo','med_blood_type_rh','med_smoking_status'])
  patientSearchItems.value = [
    {key: "center", label: getFieldLabel("source_center"),type: "select",placeholder: "请选择", options: dictStore.getDictArrayForSearch('med_center'), clearable: true,span: 4},
    {key: "modality", label: getFieldLabel("modality"),type: "select",placeholder: "请选择", options: dictStore.getDictArrayForSearch('med_exam_type'), clearable: true,span: 4},
    {key: "patient_id", label: getFieldLabel("patient_id"), type: "input" ,clearable: true, placeholder: "请输入"+getFieldLabel("patient_id"), span: 4},
    {key: "sex", label: getFieldLabel("sex"),type: "select",placeholder: "请选择", options: dictStore.getDictArrayForSearch('med_sex'), clearable: true,span: 4},
    {key: "age_bucket", label: getFieldLabel("age"),type: "select", clearable: true, options:ageBuckets, placeholder: "请选择", span: 4 },
    {key: "abo_blood_type", label: getFieldLabel("abo_blood_type"),labelWidth:80, type: "select", clearable: true, options:dictStore.getDictArrayForSearch('med_blood_type_abo'), placeholder: "请选择", span: 4 },
    {key: "smoking_status",label: getFieldLabel("smoking_status"),  type: "select", placeholder: "请选择", options: dictStore.getDictArrayForSearch('med_smoking_status'), clearable: true,span: 4},
    {key: "bmi_bucket",label: getFieldLabel("bmi"),  type: "select", placeholder: "请选择", options: bmiBuckets, clearable: true,span: 4},
    {key: "latest_lung_rads",label: getFieldLabel("lung_rads")+"(最新)", labelWidth:150,  type: "select", placeholder: "请选择",
      options:[
        {label:'1',value:"1"},
        {label:'2',value:"2"},
        {label:'3',value:"3"},
        {label:'4A',value:"4A"},
        {label:'4B',value:"4B"},
        {label:'4X',value:"4X"}
      ],
      clearable: true,
      span: 4
    }
  ]
})
onActivated(function (){
  let newQuery = getNewQuery(route.query)
  if(JSON.stringify(searchForm.value) !== JSON.stringify(newQuery)){
    searchForm.value = newQuery
    handleSearchBarSearch()
  }
})
</script>
<style>
.patientDetailBody{
  height: calc(100% - 60px);
  overflow: auto;
}
</style>
