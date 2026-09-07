<template>
  <el-container v-loading="loading" class="layout-container">
    <el-header shadow="hover" class="top-header">
      <FaSearchBar
        v-model="searchForm"
        :items="searchItems"
        :is-expand="true"
        :show-reset="true"
        :show-search="true"
        style="border: 0 !important;"
        @search="searchCall"
        @reset="clearSearch"
      />
    </el-header>
    <el-main>
      <el-row :gutter="20">
        <el-col :sm="8" v-for="n in overviewCount" :key="n.key">
          <Total :label="n.label" :icon="n.icon" :value="n.value"/>
        </el-col>
      </el-row>
      <el-row :gutter="20" class="mt-5">
        <el-col :sm="12">
          <el-card class="echarts-card">
            <div class="pb-3.5"><span class="text-base font-medium">各年龄段患者例数</span></div>
            <FaBarChart
              :data="ageCount.data"
              :xAxisData="ageCount.names"
              :showLegend="true"
              legendPosition="right"
              :onClick="chartSelect"
            />
          </el-card>
        </el-col>
        <el-col :sm="12">
          <el-card class="echarts-card">
             <div class="pb-3.5"><span class="text-base font-medium">患者例数性别比</span></div>
             <FaRingChart
              :data="genderCount"
              :radius="['0%', '70%']"
              :showLegend="true"
              :showLabel="true"
              :onClick="chartSelect"
            />
          </el-card>
        </el-col>
      </el-row>
      <el-row :gutter="20" class="mt-5">
        <el-col :sm="12">
          <el-card class="echarts-card">
             <div class="pb-3.5"><span class="text-base font-medium">多模态检查量比</span></div>
             <FaRingChart
              :data="modalityCount"
              :radius="['0%', '70%']"
              :showLegend="true"
              :showLabel="true"
              :onClick="chartSelect"
            />
          </el-card>
        </el-col>
        <el-col :sm="12">
          <el-card class="echarts-card">
             <div class="pb-3.5"><span class="text-base font-medium">检查量时间趋势</span></div>
             <FaLineChart
                :data="trendCount.data"
                :xAxisData="trendCount.names"
                :showLegend="true"
                :showAxisLabel="true"
                :showAxisLine="false"
                :showSplitLine="true"
              />
          </el-card>
        </el-col>
        <el-col :sm="24" class="mt-5">
          <el-card class="echarts-card">
            <div class="pb-3.5"><span class="text-base font-medium">患者列表</span></div>
            <FaTable
              :data="patientData.data"
              :border="false"
              :height="500"
              :stripe="false"
              :pagination="patientData.pagination"
              @pagination:size-change="patientList.handlePatientSizeChange"
              @pagination:current-change="patientList.handlePatientCurrentChange"
              style="--default-box-color:var(--el-fill-color-light)"
            >
              <ElTableColumn type="index" label="操作" width="120">
                <template #default="{ row: row }">
                  <ElButton type="primary" size="small" @click="patientList.showDicom(row)" plain>查看影像</ElButton>
                </template>
              </ElTableColumn>
              <ElTableColumn prop="patient_id" :label="getFieldLabel('patient_id')" width="120" />
              <ElTableColumn prop="birth_date" :label="getFieldLabel('birth_date')" />
              <ElTableColumn prop="age" :label="getFieldLabel('age')" />
              <ElTableColumn prop="sex" :label="getFieldLabel('sex')">
                <template #default="{ row: row }">
                  {{ dictStore.getDictItemLabel('med_sex', row.sex) }}
                </template>
              </ElTableColumn>
              <ElTableColumn prop="smoking_status" :label="getFieldLabel('smoking_status')">
                <template #default="{ row: row }">
                  {{ dictStore.getDictItemLabel('med_smoking_status', row.smoking_status) }}
                </template>
              </ElTableColumn>
              <ElTableColumn prop="abo_blood_type" :label="getFieldLabel('abo_blood_type')">
                <template #default="{ row: row }">
                  {{ dictStore.getDictItemLabel('med_blood_type_abo', row.abo_blood_type) }}
                </template>
              </ElTableColumn>
              <ElTableColumn prop="rh_blood_type" :label="getFieldLabel('rh_blood_type')">
                <template #default="{ row: row }">
                  {{ dictStore.getDictItemLabel('med_blood_type_rh', row.rh_blood_type) }}
                </template>
              </ElTableColumn>
              <ElTableColumn prop="native_place" :label="getFieldLabel('native_place')"/>
              <ElTableColumn prop="bmi" :label="getFieldLabel('bmi')" />
              <ElTableColumn prop="first_nodule_date" :label="getFieldLabel('first_nodule_date')"  />
            </FaTable>
          </el-card>
        </el-col>
      </el-row>
    </el-main>
  </el-container>
  <el-dialog class="flex flex-col" :bodyClass="'patientDetailBody'" v-model="showPatientDetail" fullscreen>
    <PatientDetail v-if="showPatientDetail" :data="showPatientDetailData" />
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="showPatientDetail = false" type="primary"  plain>关闭</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import PatientDetail from "./PatientDetail.vue"
import { ref , onMounted ,onBeforeMount} from "vue";
import {useDictStore} from "@stores";
import Total from "./components/Total.vue";
import StatisticsAPI from "@api/module_medical/statistics.ts";
import {
  StatsDimension,
  StatsKpi,
  type StatsOverview,
  PatientData,
  PatientListItem,
} from "@/types/module_medical/hospital.ts";
import type {LineDataItem} from "@/types/component/chart.ts";
import FaSearchBar, {SearchFormItem} from "@/components/forms/fa-search-bar/index.vue";
import {getFieldLabel} from "@/components/medical/field-renderer";
const dictStore = useDictStore();
const loading = ref(false)
const searchForm = ref<any>({gender:'',age_bucket:"",abo_blood_type:"",rh_blood_type:"",smoking_status:""});
const searchItems = ref<SearchFormItem[]>([])
const overviewCount = ref<StatsKpi[]>([]);
const ageCount : any = ref({
  names :[],
  data :[]
})
const genderCount : any = ref([])
const modalityCount : any = ref([])
const trendCount : Ref<{ data: LineDataItem[], names: string[] }>  = ref({
  names :[],
  data :[]
})

const patientData = ref<{
  pagination:any
  data:PatientListItem[]
}>({
  pagination :{
    current: 1,
    size: 10,
    total: 0
  },
  data:[]
})
const showPatientDetail = ref(false)
const showPatientDetailData = ref<PatientListItem>()
const patientList = {
  handlePatientSizeChange(newSize: number){
    patientList.upData(1,newSize)
  },
  handlePatientCurrentChange(newCurrent: number){
    patientList.upData(newCurrent,patientData.value.pagination.size)
  },
  showDicom(row:PatientListItem){
    showPatientDetailData.value = row
    showPatientDetail.value = true;
  },
  upData(current:number,size:number){
    let params = Object.assign({},searchForm.value);
    params.current = current
    params.size = size
    this.getData(params).then( (res)=>{
      this.setData(res.data.data)
       patientData.value.pagination.size = size
       patientData.value.pagination.current = current
    })
  },
  getData(params:object){
    return StatisticsAPI.getPatients(Object.assign({
      current : patientData.value.pagination.current,
      size : patientData.value.pagination.size,
    },params))
  },
  setData(newPatientData:PatientData){
    if(newPatientData != null){
      patientData.value.pagination = Object.assign({},patientData.value.pagination,{
        total:newPatientData.total
      })
      patientData.value.data = newPatientData.items
    }
  }
}

const kpisIcon = {
  total_patients:"ri:user-heart-fill",
  total_exams:"ri:chat-check-fill",
  center_count:"ri:hospital-fill",
  modality_count:"ri:mail-line",
}

async function searchCall(){
  loading.value = true
  let params = searchForm.value;
  let res = await StatisticsAPI.getOverview(params)
  let tableRes = await patientList.getData(params)
  upDateChatsView(res?.data?.data,tableRes?.data?.data)
  loading.value = false
}

function clearSearch() {
  searchForm.value = {gender:'',age_bucket:"",abo_blood_type:"",rh_blood_type:"",smoking_status:""}
  searchCall()
}

function chartSelect(obj:any){
  if(searchForm.value[obj?.data?.filterName] !== undefined){
    searchForm.value[obj?.data?.filterName] = obj?.data?.filterValue
    searchCall()
  }
}

function upDateChatsView(overview:StatsOverview,newPatientData:PatientData){
  overviewCount.value = overview.kpis || []
  overviewCount.value.forEach(function (n){
    n.icon = kpisIcon[n.key as keyof typeof kpisIcon]
  })
  let dimensions:StatsDimension[] = overview.dimensions;
  let gender_ratio = dimensions.find(function (n){
    return n.key === 'gender_ratio'
  })
  let age_distribution = dimensions.find(function (n){
    return n.key === 'age_distribution'
  })
  let modality_counts = dimensions.find(function (n){
    return n.key === 'modality_counts'
  })
  let exam_trend = dimensions.find(function (n){
    return n.key === 'exam_trend'
  })
  if(age_distribution != null){
    ageCount.value = {
      names :age_distribution.data.map(function (n){
        return n.label
      }),
      data : age_distribution.data.map(function (n){
        return {
          value:n.count,
          name:n.label,
          filterValue: n.label,
          filterName: 'age_bucket'
        }
      })
    }
  }

  if(gender_ratio != null){
    genderCount.value = gender_ratio.data.map(function (n){
      return {
        name : n.label,
        value : n.count,
        filterValue : n.sex,
        filterName: 'gender'
      }
    })
  }
  if(modality_counts != null){
    modalityCount.value = modality_counts.data.map(function (n){
      return {
        name : n.label,
        value : n.count,
        filterValue : n.exam_type,
        filterName: 'modality'
      }
    })
  }
  if(exam_trend != null){
    trendCount.value = {
      names : exam_trend.data.map(function (n){
         return n.year +"-" +n.month
      }),
      data : [
        {
          name:"",
          data: exam_trend.data.map(function (n){
            return n.count
          }),
          areaStyle: {
            startOpacity: 0.08,
            endOpacity: 0,
          }
        }
      ]
    }
  }
  patientList.setData(newPatientData);
}
onBeforeMount(async function (){
  const ageBuckets = await StatisticsAPI.getAgeBuckets()
  const dictObj = await dictStore.getDict(['med_sex','med_blood_type_abo','med_blood_type_rh','med_smoking_status'],true)
  searchItems.value = [
    { key: "sex", label: getFieldLabel("sex"),labelWidth:100,type :"select", clearable: true,options: dictObj.med_sex, placeholder: "请选择", span: 4 },
    { key: "age_bucket", label: getFieldLabel("age_bucket"),labelWidth:100, type: "select", clearable: true, options:ageBuckets, placeholder: "请选择", span: 4 },
    { key: "abo_blood_type", label: getFieldLabel("abo_blood_type"),labelWidth:100, type: "select", clearable: true, options: dictObj.med_blood_type_abo, placeholder: "请选择", span: 4 },
    { key: "rh_blood_type", label: getFieldLabel("rh_blood_type"),labelWidth:100, type: "select", clearable: true, options: dictObj.med_blood_type_rh, placeholder: "请选择", span: 4 },
    { key: "smoking_status", label: getFieldLabel("smoking_status"),labelWidth:100, type: "select", clearable: true, options: dictObj.med_smoking_status, placeholder: "请选择", span: 4 },
  ];
})

onMounted(async function () {
  await searchCall();
});

</script>
<style>
.patientDetailBody{
  flex: 1;
}
</style>
<style scoped>
.top-header{
  background-color: #fff;
  height: auto;
  padding: 0;
  --custom-radius:0;
  box-shadow: var(--el-box-shadow);
  border-bottom: 1px solid #ccc;
}
.layout-container {
  background-color: #f0f2f5;
  height: 100%;
  margin: -10px;
}
.echarts-card{
  --el-card-border-radius : 20px !important;
  --el-card-border-color:#ccc;
}

</style>
