<template>
  <ElTable :data="rows" border size="small" :stripe="true" :header-cell-style="{ color:'#333' }">
    <ElTableColumn type="expand" v-if="isShowExpand">
      <template #default="{ row }" >
        <div v-if="expandTableList[rows.indexOf(row)] !== undefined" style="padding: 20px">
          <template v-for="(table,index) in expandTableList[rows.indexOf(row)]" :key="index" >
            <div class="mb-1 font-bold">{{table.tableName}}</div>
            <ElTable  style="margin-bottom: 20px" border :header-cell-style="{ backgroundColor: '#f5f7fa' }" :data="table.tableData" size="small">
              <ElTableColumn v-for="(col,index) in table.tableColumn" :width="col.prop === 'raw_text' ? 600 : undefined" :key="index" :prop="col.prop" :label="col.label">
                <template #default="{ row }" >
                  <div v-if="col.prop === 'raw_text'" class="marked-content"  v-html="marked(row[col.prop] || '')"></div>
                  <div v-else-if="['pre_admission','post_admission'].includes(col.prop)">{{getDateStr(row[col.prop])}}</div>
                  <div v-else-if="['nursing_days'].includes(col.prop)">{{nursingDays(row[col.prop])}}</div>
                  <div v-else-if="typeof row[col.prop] !== 'object' || row[col.prop] == null">{{row[col.prop]}}</div>
                  <div v-else>{{JSON.stringify(row[col.prop])}}</div>
                </template>
              </ElTableColumn>
            </ElTable>
          </template>
        </div>
      </template>
    </ElTableColumn>
    <ElTableColumn v-if="getIsImage() || tableName === '基因检测'" label="操作" width="120" :align="'center'">
      <template #default="{ row }" >
        <div v-if="getIsImage()" style="margin-top: 5px"><ElButton type="success" @click="ctToggle()" size="small">查看影像</ElButton></div>
        <div v-else-if="tableName === '基因检测'" style="margin-top: 5px"><ElButton type="success" @click="fsqToggle()" size="small">查看基因数据</ElButton></div>
      </template>
    </ElTableColumn>
    <ElTableColumn v-if="getIsVisit()" prop="anon_visit_id" :label="getFieldLabel('anon_visit_id')"  width="200" />
    <ElTableColumn v-else-if="tableName !== '医嘱'" prop="anon_exam_id" :label="getFieldLabel('anon_exam_id')"   width="200"  />
    <template v-if="tableName === '就诊'">
      <ElTableColumn prop="length_of_stay" :label="getFieldLabel('length_of_stay')" />
      <ElTableColumn prop="admission_time" :label="getFieldLabel('admission_time')" />
      <ElTableColumn prop="inpatient_no" :label="getFieldLabel('inpatient_no')" />
      <ElTableColumn prop="visit_ordinal" :label="getFieldLabel('visit_ordinal')" />
      <ElTableColumn prop="visit_category" :label="getFieldLabel('visit_category')" />
      <ElTableColumn prop="visit_age" :label="getFieldLabel('visit_age')" />
      <ElTableColumn prop="payment_method" :label="getFieldLabel('payment_method')" />
      <ElTableColumn prop="outpatient_no" :label="getFieldLabel('outpatient_no')" />
    </template>
    <template v-else-if="tableName === '手术'">
      <ElTableColumn prop="surgery_id" :label="getFieldLabel('surgery_id')" />
      <ElTableColumn prop="surgery_date" :label="getFieldLabel('surgery_date')" />
      <ElTableColumn prop="surgical_approach" :label="getFieldLabel('surgical_approach')" />
      <ElTableColumn prop="procedure_name" :label="getFieldLabel('procedure_name')" />
    </template>
    <template v-else-if="tableName === '检查'">
      <ElTableColumn prop="item_name" :label="getFieldLabel('item_name')" />
      <ElTableColumn prop="item_result" :label="getFieldLabel('item_result')" />
      <ElTableColumn prop="item_result_value" :label="getFieldLabel('item_result_value')" />
      <ElTableColumn prop="item_unit" :label="getFieldLabel('item_unit')" />
      <ElTableColumn prop="lab_result_id" :label="getFieldLabel('lab_result_id')" />
      <ElTableColumn prop="report_id" :label="getFieldLabel('report_id')" />
      <ElTableColumn prop="test_name" :label="getFieldLabel('test_name')" />
      <ElTableColumn prop="collection_time" :label="getFieldLabel('collection_time')" />
    </template>
    <template v-else-if="tableName === '医嘱'">
      <ElTableColumn prop="dosage_form" :label="getFieldLabel('dosage_form')" />
      <ElTableColumn prop="dose" :label="getFieldLabel('dose')" />
      <ElTableColumn prop="dose_per_use" :label="getFieldLabel('dose_per_use')" />
      <ElTableColumn prop="dose_unit" :label="getFieldLabel('dose_unit')" />
      <ElTableColumn prop="drug_code" :label="getFieldLabel('drug_code')" />
      <ElTableColumn prop="drug_name" :label="getFieldLabel('drug_name')" />
      <ElTableColumn prop="drug_trade_name" :label="getFieldLabel('drug_trade_name')" />
      <ElTableColumn prop="drug_type" :label="getFieldLabel('drug_type')" />
      <ElTableColumn prop="duration_days" :label="getFieldLabel('duration_days')" />
      <ElTableColumn prop="duration_type" :label="getFieldLabel('duration_type')" />
      <ElTableColumn prop="frequency" :label="getFieldLabel('frequency')" />
      <ElTableColumn prop="order_dept" :label="getFieldLabel('order_dept')" />
      <ElTableColumn prop="order_id" :label="getFieldLabel('order_id')" />
      <ElTableColumn prop="order_name" :label="getFieldLabel('order_name')" />
      <ElTableColumn prop="order_source" :label="getFieldLabel('order_source')" />
      <ElTableColumn prop="order_time" :label="getFieldLabel('order_time')" />
      <ElTableColumn prop="order_type" :label="getFieldLabel('order_type')" />
      <ElTableColumn prop="original_patient_id" :label="getFieldLabel('original_patient_id')" />
      <ElTableColumn prop="prescribing_dept" :label="getFieldLabel('prescribing_dept')" />
      <ElTableColumn prop="prescription_date" :label="getFieldLabel('prescription_date')" />
      <ElTableColumn prop="prescription_id" :label="getFieldLabel('prescription_id')" />
      <ElTableColumn prop="route" :label="getFieldLabel('route')" />
      <ElTableColumn prop="specification" :label="getFieldLabel('specification')" />
      <ElTableColumn prop="stop_time" :label="getFieldLabel('stop_time')" />
      <ElTableColumn prop="visit_id" :label="getFieldLabel('visit_id')" />
    </template>
    <template v-else-if="tableName === '基因检测'">
      <ElTableColumn prop="exam_date" :label="getFieldLabel('exam_date')" />
      <ElTableColumn prop="exam_type" :label="getFieldLabel('exam_type')">
        <template  #default="{ row }" >
          {{dictStore.getDictItemLabel("med_exam_type",  row.exam_type)}}
        </template>
      </ElTableColumn>
    </template>
    <template v-else-if="tableName === '免疫组化'">
      <ElTableColumn prop="exam_date" :label="getFieldLabel('exam_date')" />
      <ElTableColumn prop="napsina" :label="getFieldLabel('napsina')" />
      <ElTableColumn prop="p40" :label="getFieldLabel('p40')" />
      <ElTableColumn prop="pdl1_clone" :label="getFieldLabel('pdl1_clone')" />
      <ElTableColumn prop="pdl1_tps_pct" :label="getFieldLabel('pdl1_tps_pct')" />
      <ElTableColumn prop="ttf1" :label="getFieldLabel('ttf1')" />
    </template>
    <template v-else-if="tableName === '病理'">
      <ElTableColumn prop="exam_date" :label="getFieldLabel('exam_date')" />
      <ElTableColumn prop="sampling_site" :label="getFieldLabel('sampling_site')" />
      <ElTableColumn prop="specimen_type" :label="getFieldLabel('specimen_type')" />
    </template>
    <template v-else-if="getIsImage()">
      <ElTableColumn prop="exam_date" :label="getFieldLabel('exam_date')" width="120" />
      <ElTableColumn prop="nodule_no" :label="getFieldLabel('nodule_no')" width="120" />
      <ElTableColumn prop="report_text.body_clean" :label="getFieldLabel('body_clean')">
        <template #default="{ row }" >
          <div class="marked-content" v-html="marked(row?.report_text?.body_clean)"></div>
        </template>
      </ElTableColumn>
    </template>
  </ElTable>

  <el-dialog class="flex flex-col" :bodyClass="'mdDialogDetailBody'" v-model="showFsq" fullscreen>
    <div v-if="showFsq" style="height: 100%">
      <FastqRawView :text="onLoadSample()" colored />
    </div>
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="showFsq = false" type="primary"  plain>关闭</el-button>
      </div>
    </template>
  </el-dialog>
  <Viewer ref="viewer" />
</template>

<script setup lang="ts">
import {computed, ref} from "vue";
import {ElTable, ElTableColumn} from "element-plus";
import {getFieldLabel} from "@/components/medical/field-renderer";
import FastqRawView from "@/components/others/fa-fastq-viewer/components/FastqRawView.vue";
import {marked} from "marked";
import {useDictStore} from "@/store";
import Viewer from "@views/module_medical/viewer/index.vue";

interface Props {
  rows: any[];
  tableName: string;
}
interface TableItem<T = any> {
  tableName: string;
  tableData: T[];
  tableColumn: { prop:string,label:string }[];
}
const dictStore = useDictStore()
const viewer = ref<any>(null)
const showFsq = ref(false);
// const fsq = ref(``);

const props = defineProps<Props>();
function isObjectKey(value:any,key:string){
  if(value instanceof Array){
    return value.length > 0 && typeof value[0] === 'object'
  }
  return (typeof value === 'object' && value !== null && !['report_text','nursing_days','pre_admission','post_admission'].includes(key))
}
const isShowExpand = computed(()=>{
  let bool = false
  const rows = props.rows || []
  rows.find(function (row:any){
    for (const key in row){
      let value = row[key];
      if(isObjectKey(value,key)){
        bool = true
        break;
      }
    }
  })
  return bool
})

function getDateStr(obj: any){
  if(!obj){
    return obj
  }
  if(typeof obj === 'string' && obj.indexOf("{") === 0){
    obj = JSON.parse(obj)
  }
  return obj.days+ getFieldLabel('days') + obj.hours + getFieldLabel('hours') + obj.minutes + getFieldLabel('minutes')
}
function nursingDays(obj:any){
  if(!obj){
    return obj
  }
  if(typeof obj === 'string' && obj.indexOf("{") === 0){
    obj = JSON.parse(obj)
  }
  return getFieldLabel('level_1') + obj.level_1 +"天\n" + getFieldLabel('level_2') + obj.level_2 +'天'
}

const expandTableList = computed(()=>{
  let arr:TableItem[][] = [];

  function processing(arrTable:any,value:any,key:string){
    let valueFirst = value;
    let tableData:any[] = [];

    if(value instanceof Array && value.length > 0){
      valueFirst = value[0]
      tableData = tableData.concat(value)
    } else if(typeof value === 'object'){
      for (let subKey in valueFirst){
        let subValue = valueFirst[subKey]
        if(isObjectKey(subValue,subKey)){
         processing(arrTable,subValue,subKey)
        }
      }
      tableData = [valueFirst]
    }

    let cols = getTableColumn(valueFirst)

    if(cols.length > 0){
      arrTable.push({
        tableName:getFieldLabel(key),
        tableData:tableData,
        tableColumn:cols
      })
    }
  }
  (props.rows || []).forEach(function (row:any,index:number){
    let arrTable:any = [];
    for (const key in row){
      let value = row[key];
      if(isObjectKey(value,key)){
        if(arr[index] === undefined){
          arr[index] = arrTable
        }
        processing(arrTable,value,key)
      }
    }
  });

  return arr;
})
function getIsVisit(){
  let tableName = props.tableName
  return tableName === '就诊' ||
    tableName === '手术' ||
    tableName === '检查'
}
function getIsImage(){
  let tableName = props.tableName
  return tableName === 'CT' ||
    tableName === '影像' ||
    tableName === '超声'
}
function onLoadSample() {
  // 3 条 read：1 对双端 + 1 单端（与 parser.spec.ts fixture 一致）
  const seq = "GATTTGGGGTTCAAAGCAGTATCGATCAAATAGTAAATCCATTTGTTCAACTCACAGTTT";
  const qual = "I".repeat(60);
  const r3seq = "ACGT".repeat(15);
  let arr:any = []
  let tempArr = [
    `@A00582:907:H7255DSX3:1:1101:8196:1063 1:N:0:TAAGGCGA`,
    seq,
    `+`,
    qual,
    `@A00582:907:H7255DSX3:1:1101:8196:1063 2:N:0:TAAGGCGA`,
    seq,
    `+`,
    qual,
    `@A00582:907:H7255DSX3:1:1101:8196:9999`,
    r3seq,
    `+`,
    "I".repeat(r3seq.length),
  ]

  for (let i = 0; i <41;i++){
    arr = arr.concat(tempArr)
  }
  arr.push(".....")
  arr.push(".....")
  arr.push(".....")
  arr.push(".....")
  arr.push(".....")
  for (let i = 0; i <41;i++){
    arr = arr.concat(tempArr)
  }
  return arr.join("\n")
}

function getTableColumn(obj:any){
  let arr = []
  for (const key in obj){
    let value = obj[key];
    if(key.indexOf("_") !== 0 && !['review_status','pat_local_id'].includes(key) && !isObjectKey(value,key)){
      arr.push({
        prop:key,
        label:getFieldLabel(key)
      })
    }
  }
  return arr
}

function ctToggle(){
  if(viewer?.value){
    viewer?.value.open({
      file_type:'dcm',
      file_id:1
    })
  }
}
function fsqToggle(){
  showFsq.value = true
}
onBeforeMount(async ()=>{
  await dictStore.getDict(['med_exam_type'])
})
</script>
<style>
.mdDialogDetailBody{
  height: calc(100% - 80px);
}
.marked-content p + p{
  margin-top: 10px;
}
</style>
