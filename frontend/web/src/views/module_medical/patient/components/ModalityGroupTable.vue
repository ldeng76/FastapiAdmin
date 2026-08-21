<template>
  <ElTable :data="rows" border size="small" :header-cell-style="{ backgroundColor: '#eef0ff' }">
    <ElTableColumn type="expand" v-if="isShowExpand">
      <template #default="{ row }" >
        <div v-if="expandTableList[rows.indexOf(row)] !== undefined" style="padding: 20px">
          <ElTable v-for="(table,index) in expandTableList[rows.indexOf(row)]" style="margin-bottom: 20px" border :header-cell-style="{ backgroundColor: '#f5f7fa' }" :key="index" :data="table.tableData" size="small">
            <ElTableColumn v-for="(col,index) in table.tableColumn" :key="index" :prop="col.prop" :label="col.label" />
          </ElTable>
        </div>
      </template>
    </ElTableColumn>
    <ElTableColumn label="操作" width="110" :align="'center'">
      <template #default="{ row }" >
        <ElButton type="primary" size="small">查看原始值</ElButton>
      </template>
    </ElTableColumn>
    <ElTableColumn v-if="tableName === '就诊' || tableName === '手术'" prop="anon_visit_id" :label="getFieldLabel('anon_visit_id')"  width="200" />
    <ElTableColumn v-else prop="anon_exam_id" :label="getFieldLabel('anon_exam_id')"   width="200"  />
    <template v-if="tableName === '就诊'">
      <ElTableColumn prop="visit_ordinal" :label="getFieldLabel('visit_ordinal')" />
    </template>
    <template v-else-if="tableName === '手术'">
      <ElTableColumn prop="surgery_id" :label="getFieldLabel('surgery_id')" />
      <ElTableColumn prop="surgery_date" :label="getFieldLabel('surgery_date')" />
      <ElTableColumn prop="resection_scope" :label="getFieldLabel('resection_scope')" />
      <ElTableColumn prop="surgical_approach" :label="getFieldLabel('surgical_approach')" />
      <ElTableColumn prop="procedure_name" :label="getFieldLabel('procedure_name')" />
    </template>
    <template v-else-if="tableName === '基因'">
      <ElTableColumn prop="exam_date" :label="getFieldLabel('exam_date')" />
      <ElTableColumn prop="exam_type" :label="getFieldLabel('exam_type')" />
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
    <template v-else-if="tableName === '影像' ">
      <ElTableColumn prop="exam_date" :label="getFieldLabel('exam_date')" width="120" />
      <ElTableColumn prop="nodule_no" :label="getFieldLabel('nodule_no')" width="120" />
      <ElTableColumn prop="report_text.body_clean" :label="getFieldLabel('body_clean')" />
    </template>
  </ElTable>
</template>

<script setup lang="ts">
import { computed ,ref ,watch} from "vue";
import {ElTable,ElTableColumn} from "element-plus";
import {getFieldLabel} from "@/components/medical/field-renderer";
interface Props {
  rows: any[];
  tableName: string;
}
interface TableItem<T = any> {
  tableName: string;
  tableData: T[];
  tableColumn: { prop:string,label:string }[];
}
const expandTableList = ref<TableItem[][]>([])
const props = defineProps<Props>();
function isObjectKey(value:any,key:string){
  return typeof value === 'object' && value !== null && !['report_text'].includes(key)
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
  console.log(props.rows ,bool)
  return bool
})

function getTableColumn(obj:any){
  let arr = []
  for (const key in obj){
    if(key.indexOf("_") > 0 && !['review_status'].includes(key)){
      arr.push({
        prop:key,
        label:getFieldLabel(key)
      })
    }
  }
  return arr
}

watch(props.rows,(newRows)=>{
  if(!isShowExpand.value){
    return;
  }
  let arr:TableItem[][] = [];
  newRows.forEach(function (row:any,index:number){
    for (const key in row){
      let value = row[key];
      if(isObjectKey(value,key)){
        if(arr[index] === undefined){
          arr[index] = []
        }
        arr[index].push({
          tableName:key,
          tableData:[value],
          tableColumn:getTableColumn(value)
        })
      }
    }
  })
  expandTableList.value = arr
},{immediate : true})
</script>
