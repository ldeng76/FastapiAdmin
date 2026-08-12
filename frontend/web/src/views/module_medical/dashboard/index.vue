<template>
  <el-container class="layout-container">
    <el-header class="top-header flex">
      <el-text size="large" :style="'width: '+asideWidth+'px'">肺结节/肺癌科研数据管理仪表板</el-text>
<!--      <div style="position: relative">-->
<!--        <el-tabs style="position: absolute;bottom:0;margin-bottom: -15px" :default-value="'first'" @tab-click="function(){}">-->
<!--          <el-tab-pane label="数据概览" name="first"></el-tab-pane>-->
<!--          <el-tab-pane label="影像特征" name="second"></el-tab-pane>-->
<!--          <el-tab-pane label="病理与分子" name="third"></el-tab-pane>-->
<!--          <el-tab-pane label="生存随访" name="fourth"></el-tab-pane>-->
<!--        </el-tabs>-->
<!--      </div>-->
    </el-header>
    <el-container class="layout-body">
      <!-- 2. 左侧侧边栏 -->
      <el-aside :width="asideWidth+'px'" class="layout-aside">
        <el-menu class="el-menu-vertical" :unique-opened="true">
          <div class="pt-2 pl-6 pr-2 pb-2">
            <el-button type="warning" @click="clearSearch()" size="small" style="vertical-align: initial" plain>重置所有筛选条件</el-button>
          </div>
          <el-sub-menu v-for="item1 in searchConfig" :index="item1.key || ''" :key="item1.key">
            <template #title>
              <div style="display: flex; justify-content: space-between;align-items: center;width: 100%;">
                <div>
                  <el-icon v-if="item1.currFilter" :size="20">
                    <CircleCheckFilled color="var(--color-success)" />
                  </el-icon>
                  <el-icon v-else :size="20">
                    <CirclePlus />
                  </el-icon>
                  <el-text style="width: 160px" truncated>
                    {{ item1.dict_label}}{{ item1.currFilterText ? "：" + item1.currFilterText : "" }}
                  </el-text>
                </div>
                <div v-if="item1.currFilterText">
                  <el-button type="danger" style="vertical-align: initial" size="small" @click="clearSearch(item1,$event)" plain>清除</el-button>
                </div>
              </div>
            </template>
            <el-menu-item
              v-for="item2 in item1.children"
              @click="search(item1, item2)"
              :index="item2.key || ''"
              :key="item2.key"
              :class="{'selected' : item1.currFilter === item2.dict_value}"
              class="menu-item"
            >
              {{ item2.dict_label }}
            </el-menu-item>
          </el-sub-menu>
        </el-menu>
      </el-aside>

      <!-- 3. 右侧主要内容区域 -->
      <el-main class="layout-main">
        <el-row :gutter="20">
          <el-col :sm="6" v-for="n in overviewCount" :key="n.key">
            <Total :label="n.label" :icon="n.icon" :value="n.value"/>
          </el-col>
        </el-row>
        <el-row :gutter="20" class="mt-5">
           <el-col :sm="6">
            <el-card class="echarts-card">
              <div class="pb-3.5"><span class="text-base font-medium">各中心患者例数</span></div>
              <FaHBarChart
                :data="centerCount.data"
                :xAxisData="centerCount.names"
                :onClick="chartSelect"
              />
            </el-card>
          </el-col>
          <el-col :sm="9">
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
          <el-col :sm="9">
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
               <div class="pb-3.5"><span class="text-base font-medium">模态检查量比</span></div>
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
                <ElTableColumn prop="patient_id" label="患者编号" width="120" />
                <ElTableColumn prop="center_code" label="中心">
                  <template #default="{ row: row }">
                    {{ getDictLabel('med_center', row.center_code) }}
                  </template>
                </ElTableColumn>
                <ElTableColumn prop="birth_date" label="出生日期" />
                <ElTableColumn prop="age" label="年龄" />
                <ElTableColumn prop="sex" label="性别">
                  <template #default="{ row: row }">
                    {{ getDictLabel('med_sex', row.sex) }}
                  </template>
                </ElTableColumn>
                <ElTableColumn prop="smoking_status" label="吸烟情况">
                  <template #default="{ row: row }">
                    {{ getDictLabel('med_smoking_status', row.smoking_status) }}
                  </template>
                </ElTableColumn>
                <ElTableColumn prop="abo_blood_type" label="ABO血型">
                  <template #default="{ row: row }">
                    {{ getDictLabel('med_blood_type_abo', row.abo_blood_type) }}
                  </template>
                </ElTableColumn>
                 <ElTableColumn prop="rh_blood_type" label="RH血型">
                  <template #default="{ row: row }">
                    {{ getDictLabel('med_blood_type_rh', row.rh_blood_type) }}
                  </template>
                </ElTableColumn>
                <ElTableColumn prop="native_place" label="籍贯"/>
                <ElTableColumn prop="bmi" label="BMI" />
                <ElTableColumn prop="first_nodule_date" label="首次发现结节日期"  />
              </FaTable>
            </el-card>
          </el-col>
        </el-row>
      </el-main>
    </el-container>
  </el-container>
  <el-dialog class="flex flex-col" :bodyClass="'patientDetailBody'" v-model="showPatientDetail" fullscreen>
    <PatientDetail v-if="showPatientDetail" :data="showPatientDetailData" :getDictLabel="getDictLabel" />
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="showPatientDetail = false" type="primary"  plain>关闭</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { CirclePlus, CircleCheckFilled } from "@element-plus/icons-vue";
import PatientDetail from "./PatientDetail.vue"

import filterConfig, {
  addConfigKey,
  FilterDictDataTable,
  FilterConfigType
} from "./filterConfig.ts";
import { ref , onMounted } from "vue";
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
import { ElLoading } from 'element-plus'

const asideWidth = 300;
const searchConfig = ref(filterConfig);
const overviewCount = ref<StatsKpi[]>([]);
const ageCount : any = ref({
  names :[],
  data :[]
})
const centerCount : any = ref({
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
    let params = getSearchParams();
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
function getSearchParams(){
  let params : any = {}
  searchConfig.value.forEach(function (item){
    if(item.currFilter && item.name){
      params[item.name] = item.currFilter
    }
  })
  return params
}

async function searchCall(){
  const loading = ElLoading.service({
    lock: true,
    text: 'Loading',
  })
  let params = getSearchParams();
  let res = await StatisticsAPI.getOverview(params)
  let tableRes = await patientList.getData(params)
  upDateChatsView(res?.data?.data,tableRes?.data?.data)
  loading.close()
}

function clearSearch(item1?:FilterConfigType,e?:Event) {
  if(item1 && e){
    item1.currFilter = '';
    item1.currFilterText = '';
    e.stopPropagation()
  } else {
    searchConfig.value.forEach(function (item1){
      item1.currFilter = '';
      item1.currFilterText = '';
    })
  }
  searchCall()

}

function search(item1:FilterConfigType, item2:FilterDictDataTable ) {
  item1.currFilter = item2.dict_value;
  item1.currFilterText = item2.dict_label;
  searchCall()
}

function chartSelect(obj:any){
  let item1 =  searchConfig.value.find(function (n){
    return n.name === obj?.data?.filterName
  })
  if(item1 !== undefined){
    let item2 = item1?.children?.find(function (n){
      return n.dict_value === obj?.data?.filterValue
    })
    if(item2){
      search(item1,item2)
    }
  }
}

function getDictLabel(key:string,value:any){
  let item = dictStore.getDictLabel(key, value)
  if(typeof item !== "string" && item?.dict_label){
    return item.dict_label
  } else {
    return value
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
  let center_distribution = dimensions.find(function (n){
    return n.key === 'center_distribution'
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
  if(center_distribution != null){
     centerCount.value = {
      names :center_distribution.data.map(function (n){
        let res = dictStore.getDictLabel('med_center', n.center_code);
        if (typeof res !== "string" && res?.dict_label) {
          return res?.dict_label
        } else {
          return n.center_code
        }
      }),
      data : center_distribution.data.map(function (n){
        return {
          value:n.count,
          name:n.center_code,
          filterValue: n.center_code,
          filterName: 'center'
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
const dictStore = useDictStore();
onMounted(async function () {
  const dictKeyArr = [
    "med_sex",
    "med_exam_type",
    "med_smoking_status",
    "med_ethnicity",
    "med_blood_type_abo",
    "med_blood_type_rh",
    "med_center",
  ]
  const ageBuckets = await StatisticsAPI.getAgeBuckets()
  const dictMap = await dictStore.getDict(dictKeyArr);
  searchConfig.value.forEach(function (n){
    if(dictMap[n.dict_type] != null){
      n.children = dictMap[n.dict_type]
    }
  })
  let med_age = searchConfig.value.find(function (n){
    return n.dict_type === 'med_age'
  })
  if(med_age){
    med_age.children = ageBuckets.map(function (n:any){
      return {
        dict_label:n.label,
        dict_value:n.value,
      }
    })
  }
  addConfigKey(searchConfig.value, null);
  await searchCall();
});
</script>
<style>
.patientDetailBody{
  flex: 1;
}
</style>
<style scoped>
.layout-aside{
  border-right: 1px solid #ccc;
}
.top-header{
  background-color: #fff;
  border-bottom: 1px solid #ccc;
}
.layout-container {
  height: 100vh;
  background-color: #f0f2f5;
}
.menu-item.is-active{
  color: inherit;
}
.menu-item.selected{
  color:  var(--el-menu-active-color);
}
.el-menu-vertical {
  height: 100%;
  border-right: none;
}
.layout-main {
  padding: 20px;
  background-color: #f8f9fa;
  height: 100%;
  overflow-y: auto;
}
.echarts-card{
  --el-card-border-radius : 20px !important;
  --el-card-border-color:#ccc
}

</style>
