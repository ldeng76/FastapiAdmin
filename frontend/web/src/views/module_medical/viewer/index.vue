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
  file_id?:number | null
}
const props = defineProps<params>()

function open(obj:params){
  let file_id = obj && obj.file_id || props.file_id
  let file_type = obj && obj.file_type || props.file_type
  loading.value = ElLoading.service()
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
