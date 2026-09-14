<template>
  <el-container v-loading="loading" class="files-container">
    <el-aside width="250px" style="margin-right: 10px;">
      <ElCard class="fa-table-card" :bodyStyle="{overflow: 'auto'}" style="height: 100% ;margin-top : 0;">
         <el-collapse :expand-icon-position="'left'" :model-value="['examType','fileType']">
          <el-collapse-item title="模态类型" name="examType">
            <el-checkbox-group v-model="selectedExamType">
              <div class="flex justify-between"  v-for="item in dictStore.getDictArray('med_exam_type')" :key="item.dict_value">
                <el-checkbox :label="item.dict_label" :value="item.dict_value" />
                <div class="el-checkbox" style="cursor: default">{{ statisticsTypeText(item.dict_value,'by_exam_type') }}</div>
              </div>
            </el-checkbox-group>
          </el-collapse-item>
          <el-collapse-item title="文件类型" name="fileType">
            <el-checkbox-group v-model="selectedFileType">
              <div class="flex justify-between"  v-for="item in fileTypeDict" :key="item.dict_value">
                <el-checkbox :label="item.dict_label" :value="item.dict_value" />
                <div class="el-checkbox" style="cursor: default">{{ statisticsTypeText(item.dict_value,'by_file_type') }}</div>
              </div>
            </el-checkbox-group>
          </el-collapse-item>
        </el-collapse>
      </ElCard>
    </el-aside>
    <el-main style="padding: 0">
      <ElCard class="fa-table-card" style="height: 100%;margin-top : 0">
        <div style="display: flex;align-items: center;justify-content: center;font-size: 20px">
          <FaMenuRouteIcon icon="ri:file-user-fill" style="font-size: 24px;margin-left: 15px" /><strong><FaCountTo :target="statisticsCount.patient_count || 0 " :duration="!statisticsCount.patient_count || statisticsCount.patient_count <10 ? 0 :1000" separator="," /></strong> 患者
          <FaMenuRouteIcon icon="el-icon-Tickets" style="font-size: 24px;margin-left: 15px" /><strong><FaCountTo :target="statisticsCount.exam_count || 0" separator="," :duration="!statisticsCount.exam_count || statisticsCount.exam_count <10 ? 0 :1000" /></strong> 记录
          <FaMenuRouteIcon icon="file" style="font-size: 24px;margin-left: 15px" /><strong> <FaCountTo :target="statisticsCount.file_count || 0" separator="," :duration="!statisticsCount.file_count || statisticsCount.file_count <10 ? 0 :1000" /></strong> 文件
          <FaMenuRouteIcon icon="ri:hard-drive-2-fill" style="font-size: 24px;margin-left: 15px" /><span v-html="fileSize(statisticsCount.total_size_bytes,true)"></span>
        </div>
        <FaTable
          :data="data"
          :columns="columns"
          :header-cell-style="{ backgroundColor: '#f5f7fa' }"
          border
          @sort-change="onSortChange"
          :pagination="pagination"
          @pagination:size-change="handleSizeChange"
          @pagination:current-change="handleCurrentChange"
        />
      </ElCard>
    </el-main>
    <Viewer ref="viewer" />
  </el-container>
</template>
<script setup lang="ts">
import {useDictStore} from "@/store";
import {h, ref, watch} from 'vue';
import {useTable} from "@/hooks";
import type {ColumnOption} from "@/types";
import FilesApi, {FilesTable, StatisticsCount} from "@api/module_medical/files.ts";
import {ElButton} from "element-plus";
import Viewer from "@views/module_medical/viewer/index.vue";

const viewer = ref<any>(null)
const selectedExamType = ref([])
const selectedFileType = ref([])
const sortParams = ref({sort_field:"",sort_order:""})
const fileTypeDict = ref<any>([])
const statisticsCount = ref<StatisticsCount>({})
const loading = ref(false)
function fileSize(sizeBytes:number | undefined,isNumStrong = false) {
  if (typeof sizeBytes !== 'number') {
    return sizeBytes
  }
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  let size = sizeBytes;
  let index = 0;

  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index++;
  }

  return (!isNumStrong ? size.toFixed(2) :'<strong>'+size.toFixed(2)+'</strong>') + ' ' + units[index];
}
const dictStore = useDictStore();
function onSortChange({ prop, order }:any){
  if(order){
     order = order.replace("ending","")
  }
  sortParams.value = {
    sort_field:prop,
    sort_order:order
  }
}
function statisticsTypeText(type:string,key:'by_exam_type'|'by_file_type'){
  let text = '0(0%)'
  if(statisticsCount.value[key] instanceof Array){
    let data = statisticsCount.value[key];
    let item = data.find(function (n){ return n.value === type })
    if(item !== undefined){
      text = `${item.count}(${item.percentage}%)`
    }
  }
  return text
}
watch([selectedExamType,selectedFileType,sortParams],async function (arr){
  let examType = arr[0]
  let fileType = arr[1]
  let params = {
    exam_type:examType.toString(),
    file_type:fileType.toString(),
    order_by:'[]'
  }
  if(sortParams.value.sort_field && sortParams.value.sort_order){
    let obj :any = {}
    obj[sortParams.value.sort_field] = sortParams.value.sort_order
    params.order_by = JSON.stringify([obj])
  }
  loading.value = true
  replaceSearchParams(params)
  await getData(params)
  statisticsCount.value = await FilesApi.statistics(params)
  loading.value = false
})

const {
  columns,
  data,
  pagination,
  handleSizeChange,
  handleCurrentChange,
  replaceSearchParams,
  getData
} = useTable({
  transform:{
    dataTransformer(data){
      data.forEach(function (n:any){
        n.file_type = 'dcm'
      })
      return data
    }
  },
  core: {
    apiFn: FilesApi.list,
    apiParams: { page_no: 1, page_size: 30 },
    columnsFactory: (): ColumnOption<FilesTable>[] => [
      {
        prop: "patient_id",
        label: "患者ID",
        sortable :'custom'
      },
      {
        prop: "file_name",
        label: "文件名",
        sortable :'custom'
      },
      {
        prop: "exam_type",
        label: "模态类型",
        minWidth: 80,
        sortable :'custom',
        formatter(row){
          return dictStore.getDictItemLabel("med_exam_type",row.exam_type)
        }
      },
      {
        prop: "file_type",
        label: "文件类型",
        sortable :'custom',
        minWidth: 80
      },
      {
        prop: "file_size",
        label: "文件大小",
        sortable :'custom',
        formatter(row){
          return fileSize(row.file_size)
        }
      },
      {
        label: "操作",
        formatter(row){
          return h(ElButton, {
            size: "small",
            type:"primary",
            onClick(){
              if(viewer?.value){
                viewer?.value.open({
                  file_type:row.file_type,
                  file_id:row.id
                })
              }
            }},
            () => '查看文件'
          )
        }
      }
    ],
  },
});

onBeforeMount(async ()=>{
  await dictStore.getDict(['med_exam_type'])
  loading.value = true
  fileTypeDict.value = await FilesApi.getFileType()
  statisticsCount.value = await FilesApi.statistics()
  loading.value = false
})

</script>
<style scoped>
.files-container{
  height: 100%;
}

</style>
