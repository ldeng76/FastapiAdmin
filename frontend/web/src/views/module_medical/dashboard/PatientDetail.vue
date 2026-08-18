<template>
  <el-row :gutter="10" class="h-full patientDetail">
    <el-col :span="4" class="overflow-y-auto">
      <el-collapse expand-icon-position="left" class="patientDetail-collapse" v-model="activeNames">
        <el-collapse-item title="CT" name="ct" class="pl-2 pr-2">
          <el-table class="patientDetail-collapse-table" :row-class-name="tableRowClassName" :data="[
              {fileName:'0100_000001_1.3.46.670589.33.1.63896480002311796600001.5635762842026550517',type:'dicom'},
              {fileName:'case_5.nii',type:'nii'},
            ]">
            <el-table-column prop="fileName">
              <template #default="{ row: row }:{row : FileName}">
                <div style="cursor: pointer" @click="seeImage(row,row.type)">{{ row.fileName }}</div>
              </template>
            </el-table-column>
          </el-table>
        </el-collapse-item>
        <el-collapse-item title="病理" name="svs" class="pl-2 pr-2">
          <el-table class="patientDetail-collapse-table" :row-class-name="tableRowClassName" :data="[{fileName:'B1229048-2.svs',type :'svs'}]">
            <el-table-column prop="fileName">
              <template #default="{ row: row }:{row : FileName}">
                <div style="cursor: pointer" @click="seeImage(row,'svs')">{{ row.fileName }}</div>
              </template>
            </el-table-column>
          </el-table>
        </el-collapse-item>
      </el-collapse>
    </el-col>
    <el-col :span="20">
      <div class="flex flex-col h-full">
        <ElDescriptions class="patientDetail-elDescriptions" :column="6" border>
          <ElDescriptionsItem label="患者编号">{{ data?.patient_id }}</ElDescriptionsItem>
          <ElDescriptionsItem label="性别">{{ getDictLabel('med_sex',data?.sex ) }}</ElDescriptionsItem>
          <ElDescriptionsItem label="出生日期">{{ data?.birth_date }}</ElDescriptionsItem>
          <ElDescriptionsItem label="年龄">{{ data?.age }}</ElDescriptionsItem>
          <ElDescriptionsItem label="籍贯">{{ data?.native_place }}</ElDescriptionsItem>
          <ElDescriptionsItem label="吸烟情况">{{ getDictLabel('med_smoking_status', data?.smoking_status) }}</ElDescriptionsItem>
          <ElDescriptionsItem label="ABO血型">{{ getDictLabel('med_blood_type_abo', data?.abo_blood_type) }}</ElDescriptionsItem>
          <ElDescriptionsItem label="RH血型">{{ getDictLabel('med_blood_type_rh', data?.rh_blood_type)  }}</ElDescriptionsItem>
          <ElDescriptionsItem label="BMI">{{ data?.bmi }}</ElDescriptionsItem>
          <ElDescriptionsItem label="首次发现结节日期">{{ data?.first_nodule_date }}</ElDescriptionsItem>
        </ElDescriptions>
        <div class="flex-1">
          <iframe v-if="currImageType == 'dicom'" @load="closeLoading" class="border-0 w-full h-full p-0 m-0" src="/api/v1/medical/dicom/viewer?StudyInstanceUIDs=1.3.12.2.1107.5.4.3.123456789012345.19950922.121803.6"></iframe>
          <iframe v-if="currImageType == 'nii'" @load="closeLoading" class="border-0 w-full h-full p-0 m-0" src="/api/v1/static/niftiViewer.html"></iframe>
          <iframe v-if="currImageType == 'svs'" @load="closeLoading" class="border-0 w-full h-full p-0 m-0" src="/api/v1/static/svsViewer.html"></iframe>
        </div>
      </div>
    </el-col>
  </el-row>
</template>
<script setup lang="ts">
import {ElDescriptions, ElDescriptionsItem} from "element-plus";
import {ref ,onMounted} from 'vue';
import { ElLoading } from 'element-plus'
import {PatientListItem} from "@/types/module_medical/hospital.ts";
const loadingInstance = ref()
defineProps<{
  data:PatientListItem | undefined,
  getDictLabel:(key:string,value:any) => string
}>()
interface FileName {
  fileName: string
  type: string
}
const activeNames = ref(['ct','svs'])
const currImageType = ref()
function seeImage(row : any,type : string){
  if(type !== currImageType.value){
    loadingInstance.value = ElLoading.service()
    currImageType.value = type
  }
}
function tableRowClassName({row}:{row :FileName}){
  if(row.type === currImageType.value){
    return 'success-row'
  }
  return ''
}

function closeLoading(){
  if(loadingInstance.value != null){
    loadingInstance.value.close()
  }
}
onMounted(function (){
  seeImage({},'dicom')
})
</script>
<style>
.patientDetail-collapse-table .success-row{
  --el-table-tr-bg-color: rgb(231 255 223)
}
</style>
<style scoped>
.patientDetail{
  font-size: 16px;

}
.patientDetail-collapse{
  border: 1px solid var(--el-collapse-border-color);
  --el-collapse-border-color:#ccc;
}
.patientDetail-collapse-table{
  --el-table-border-color: #ccc;
}
.patientDetail-elDescriptions{
   --el-border-color-lighter: #ccc;
}
</style>
