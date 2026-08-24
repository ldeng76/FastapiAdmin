<template>
  <el-container class="files-container">
    <el-aside width="200px" style="border-right: 1px solid var(--el-collapse-border-color);">
      <el-collapse :expand-icon-position="'left'" :model-value="['examType','fileType']" style="padding:0 10px;">
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
    </el-aside>
    <el-main>
      <div class="fa-full-height" style="height: 100%">
        <FaTable
          :loading="loading"
          :data="data"
          :columns="columns"
          :height="'100%'"
          :header-cell-style="{ backgroundColor: '#f5f7fa' }"
          border
          :pagination="pagination"
          @pagination:size-change="handleSizeChange"
          @pagination:current-change="handleCurrentChange"
        />
      </div>
    </el-main>
  </el-container>
  <Viewer ref="viewer" />
</template>
<script setup lang="ts">
import {useDictStore} from "@/store";
import {h, ref, watch} from 'vue';
import {useTable} from "@/hooks";
import type {ColumnOption} from "@/types";
import FilesApi,{FilesTable} from "@api/module_medical/files.ts";
import {ElButton} from "element-plus";
import Viewer from "@views/module_medical/viewer/index.vue";
const viewer = ref<any>(null)
const selectedExamType = ref([])
const selectedFileType= ref([])
const fileTypeDict = ref([
  {dict_value:"dicom",dict_label:"DICOM"},
  {dict_value:"svs",dict_label:"SVS"},
  {dict_value:"nii",dict_label:"NII"},
])
function fileSize(sizeBytes:number | undefined) {

  if (!sizeBytes) {
    throw new Error("文件大小值异常");
  }

  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  let size = sizeBytes;
  let index = 0;

  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index++;
  }

  return size.toFixed(2) + ' ' + units[index];
}
const dictStore = useDictStore();
watch([selectedExamType,selectedFileType],function (arr){
  let examType = arr[0]
  let fileType = arr[1]
  getData({
    exam_type:examType.toString(),
    file_type:fileType.toString()
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
</script>
<style scoped>
.files-container{
  background-color: #fff;
}
.checkbox-block{
  display: flex;
  width: 100%;
}
.checkbox-block +.checkbox-block{
  margin-top: 10px;
}
</style>
