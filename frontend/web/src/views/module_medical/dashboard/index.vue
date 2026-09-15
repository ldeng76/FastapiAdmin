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
        @search="()=>{searchCall()}"
        @reset="clearSearch"
      />
    </el-header>
    <el-main>
      <el-row :gutter="20">
        <el-col :xs="24" :sm="12" :md="8" :lg="5" v-for="n in overviewCount" :key="n.key">
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
      </el-row>
    </el-main>
  </el-container>
</template>

<script setup lang="ts">

import { ref , onMounted ,onBeforeMount} from "vue";
import {useDictStore} from "@stores";
import Total from "./components/Total.vue";
import StatisticsAPI from "@api/module_medical/statistics.ts";
import {
  StatsDimension,
  StatsKpi,
  type StatsOverview
} from "@/types/module_medical/hospital.ts";
import type {LineDataItem} from "@/types/component/chart.ts";
import FaSearchBar, {SearchFormItem} from "@/components/forms/fa-search-bar/index.vue";
import {getFieldLabel} from "@/components/medical/field-renderer";
import {useRouter} from "vue-router";
const dictStore = useDictStore();
const router = useRouter();
const loading = ref(false)
const searchForm = ref<any>({sex:'',age_bucket:"",abo_blood_type:"",rh_blood_type:"",smoking_status:""});
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

const kpisIcon = {
  case_total_patients: "ri:user-heart-fill",
  case_patients_with_exam: "ri:user-star-fill",
  case_total_exams: "ri:file-list-3-fill",
  total_exams: "ri:chat-check-fill",
  center_count: "ri:hospital-fill",
  modality_count: "ri:mail-line",
}

async function searchCall(isRedirectPatient = false,query = {}){
  const params = Object.assign({is_placeholders:false},searchForm.value,query);
  if(isRedirectPatient){
    await router.push({path: '/medicalPatient', query: params});
    return;
  }
  loading.value = true
  let res = await StatisticsAPI.getOverview(params)
  upDateChatsView(res?.data?.data)
  loading.value = false
}

function clearSearch() {
  searchForm.value = {sex:'',age_bucket:"",abo_blood_type:"",rh_blood_type:"",smoking_status:""}
  searchCall()
}

function chartSelect(obj:any){
  if(searchForm.value[obj?.data?.filterName] !== undefined){
    let query:any = {}
    query[obj?.data?.filterName] = obj?.data?.filterValue
    searchCall(true,query)
  }
}

function upDateChatsView(overview:StatsOverview){
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
        filterName: 'sex'
      }
    })
  }
  if(modality_counts != null){
    modalityCount.value = modality_counts.data.map(function (n){
      return {
        name : n.label,
        value : n.count
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

}
onBeforeMount(async function (){
  const ageBuckets = await StatisticsAPI.getAgeBuckets()
  const dictObj = await dictStore.getDict(['med_sex','med_exam_type','med_blood_type_abo','med_blood_type_rh','med_smoking_status'],true)
  searchItems.value = [
    { key: "sex", label: getFieldLabel("sex"),labelWidth:100,type :"select", clearable: true,options: dictObj.med_sex, placeholder: "请选择", span: 4 },
    { key: "age_bucket", label: getFieldLabel("age_bucket"),labelWidth:100, type: "select", clearable: true, options:ageBuckets, placeholder: "请选择", span: 4 },
    { key: "abo_blood_type", label: getFieldLabel("abo_blood_type"),labelWidth:100, type: "select", clearable: true, options: dictObj.med_blood_type_abo, placeholder: "请选择", span: 4 },
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
