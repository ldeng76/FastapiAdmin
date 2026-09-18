<template>
  <el-dialog  class="flex flex-col" :bodyClass="'viewerDialogDetailBody'" v-model="showToggle" fullscreen>
    <iframe v-if="showToggle && src" allowfullscreen @load="closeLoading" class="border-0 w-full h-full p-0 m-0" :src="src"></iframe>
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="showToggle = false" type="primary"  plain>关闭</el-button>
      </div>
    </template>
  </el-dialog>
</template>
<script setup lang="ts">
import {ref} from 'vue';
import {ElLoading} from "element-plus";
import FilesApi from "@api/module_medical/files.ts";
const showToggle = ref(false)
const loading = ref()
const src = ref()
interface params {
  file_type?:string,
  file_id?: number | string | null
  anon_exam_id?:string
}
const props = defineProps<params>()

async function open(obj:params){
  let file_id = obj && obj.file_id || props.file_id
  let file_type = obj && obj.file_type || props.file_type
  let anon_exam_id = obj && obj.anon_exam_id || props.anon_exam_id
  loading.value = ElLoading.service()
  if(!file_type || !['nii','svs','dcm'].includes(file_type)){
    closeLoading()
    ElMessage.info('该文件不支持在线预览')
    return
  }
  let query:params = {}
  if(file_id){
     query.file_id = file_id;
  } else if(anon_exam_id){
     query.anon_exam_id = anon_exam_id;
  }
  let res = await FilesApi.getFileCheckExists(query)
  if(!res.exists){
    closeLoading()
    ElMessage.error('文件不存在！')
    return;
  }
  file_id = res.file_id;
  if(file_type === 'nii'){
    src.value = `/api/v1/static/niftiViewer.html?file_id=${file_id}`
    showToggle.value = true
  } else if(file_type === 'svs'){
    src.value = `/api/v1/static/svsViewer.html?file_id=${file_id}`
    showToggle.value = true
  } else if(file_type === 'dcm'){
    FilesApi.getStudyUid(file_id).then(function (res){
      src.value = `/api/v1/medical/dicom/viewer?StudyInstanceUIDs=${res?.data?.data}`
      showToggle.value = true
    }).catch(function (){
       closeLoading()
    })
  }
}

defineExpose({
  open
})
function closeLoading(){
  if( loading.value != null){
    loading.value.close()
  }
}
</script>
<style>
.viewerDialogDetailBody{
  height: calc(100% - 80px);
}
</style>
