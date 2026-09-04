<template>
  <el-container class="files-container">
    <el-aside width="250px" style="margin-right: 10px;">
      <ElCard class="fa-table-card" :bodyStyle="{overflow: 'auto'}" style="height: 100% ;margin-top : 0;">
         <el-collapse :expand-icon-position="'left'" :model-value="['examType','fileType']">
          <el-collapse-item title="模态类型" name="examType">
            <el-checkbox-group v-model="selectedExamType">
              <el-checkbox class="checkbox-block" v-for="item in dictStore.getDictArray('med_exam_type')" :key="item.dict_value" :label="item.dict_label" :value="item.dict_value" border />
            </el-checkbox-group>
          </el-collapse-item>
          <el-collapse-item title="文件类型" name="fileType">
            <el-checkbox-group v-model="selectedFileType">
              <el-checkbox class="checkbox-block" v-for="item in fileTypeDict" :key="item.dict_value" :label="item.dict_label" :value="item.dict_value" border />
            </el-checkbox-group>
          </el-collapse-item>
        </el-collapse>
      </ElCard>
    </el-aside>
    <el-main style="padding: 0">
      <ElCard class="fa-table-card" style="height: 100%;margin-top : 0">
        <div style="display: flex;align-items: center;justify-content: center;font-size: 20px">
          总计<strong> <FaCountTo :target="statisticsCount.file_count || 0" separator="," :duration="!statisticsCount.file_count || statisticsCount.file_count <10 ? 0 :1000" /></strong> 文件
          <FaSvgIcon icon="ri:file-user-fill" style="font-size: 24px;margin-left: 15px" /><strong><FaCountTo :target="statisticsCount.patient_count || 0 " :duration="!statisticsCount.patient_count || statisticsCount.patient_count <10 ? 0 :1000" separator="," /></strong> 患者
          <FaSvgIcon icon="ri:hard-drive-2-fill" style="font-size: 24px;margin-left: 15px" /><span v-html="fileSize(statisticsCount.total_size_bytes,true)"></span>
        </div>
        <FaTable
          :loading="loading"
          :data="data"
          :columns="columns"
          :header-cell-style="{ backgroundColor: '#f5f7fa' }"
          border
          :pagination="pagination"
          @pagination:size-change="handleSizeChange"
          @pagination:current-change="handleCurrentChange"
        />
      </ElCard>
    </el-main>
  </el-container>
  <Viewer ref="viewer" />
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
const selectedFileType= ref([])
const fileTypeDict = ref<any>([])
const statisticsCount = ref<StatisticsCount>({})
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
watch([selectedExamType,selectedFileType],function (arr){
  let examType = arr[0]
  let fileType = arr[1]
  let params = {
    exam_type:examType.toString(),
    file_type:fileType.toString()
  }
  getData(params)
  FilesApi.statistics(params).then(function (res){
    statisticsCount.value = res
  })
})
const {
  columns,
  data,
  loading,
  pagination,
  handleSizeChange,
  handleCurrentChange,
  getData
} = useTable({
  core: {
    apiFn: FilesApi.list,
    apiParams: { page_no: 1, page_size: 30 },
    columnsFactory: (): ColumnOption<FilesTable>[] => [
      {
        prop: "patient_id",
        label: "患者ID"
      },
      {
        prop: "file_name",
        label: "文件名"
      },
      {
        prop: "exam_type",
        label: "模态类型",
        minWidth: 80,
        formatter(row){
          return dictStore.getDictItemLabel("med_exam_type",row.exam_type)
        }
      },
      {
        prop: "file_type",
        label: "文件类型",
        minWidth: 80
      },
      {
        prop: "file_size",
        label: "文件大小",
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
  fileTypeDict.value = await FilesApi.getFileType()
  statisticsCount.value = await FilesApi.statistics()
})

</script>
<style scoped>
.files-container{
  height: 100%;
}
.checkbox-block{
  display: flex;
  width: 100%;
}
.checkbox-block +.checkbox-block{
  margin-top: 10px;
}
</style>
