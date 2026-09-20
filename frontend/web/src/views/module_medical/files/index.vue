<template>
  <el-container v-loading="loading" class="files-container">
    <el-aside width="250px" style="margin-right: 10px;">
      <ElCard class="fa-table-card" :bodyStyle="{overflow: 'auto'}" style="height: 100% ;margin-top : 0;">
         <el-collapse :expand-icon-position="'left'" :model-value="['examType','fileType']">
          <el-collapse-item title="模态类型" name="examType">
            <el-checkbox-group v-model="selectedExamType">
              <div style="max-height: 300px;overflow: auto">
                <!-- issue-28：候选由后端 by_exam_type 驱动（裁剪到 exam 表实际存在的 exam_type，
                     虚胖字典值不再出现）；「全选」与「不选」等价（IN 覆盖全部值域 = 无过滤）。 -->
                <div class="flex justify-between"  v-for="item in examTypeOptions" :key="item.value">
                  <el-checkbox class="file-checkbox" :label="item.label" :value="item.value" />
                  <div class="el-checkbox" style="cursor: default">{{ item.count }}({{ item.percentage }}%)</div>
                </div>
              </div>
            </el-checkbox-group>
          </el-collapse-item>
          <el-collapse-item title="中心" name="fileType">
            <el-checkbox-group v-model="selectedCenterType">
              <div class="flex justify-between"  v-for="item in dictStore.getDictArray('med_center')" :key="item.dict_value">
                <el-checkbox class="file-checkbox" :label="item.dict_label" :value="item.dict_value" />
<!--                <div class="el-checkbox" style="cursor: default">{{ statisticsTypeText(item.dict_value,'by_file_type') }}</div>-->
              </div>
            </el-checkbox-group>
          </el-collapse-item>
        </el-collapse>
      </ElCard>
    </el-aside>
    <el-main style="padding: 0">
      <ElCard class="fa-table-card" style="height: 100%;margin-top : 0">
        <div style="display: flex;align-items: center;justify-content: center;font-size: 16px">
          <FaMenuRouteIcon icon="el-icon-Tickets" class="icon-count" /> 记录：<strong><FaCountTo :target="statisticsCount.record_count || 0" separator="," :duration="getCountDuration(statisticsCount.record_count)" /></strong>

          <el-tooltip placement="top" effect="light"
            content="有影像文件的患者数（影像口径：imaging_study.patient_id 去重）。只统计名下有影像记录的患者，小于「总患者数」。">
            <span style="cursor: help">
              <FaMenuRouteIcon icon="ri:file-user-fill" class="icon-count" />有影像文件的患者数：<strong><FaCountTo :target="statisticsCount.patient_count || 0 " :duration="getCountDuration(statisticsCount.patient_count)" separator="," /></strong>
            </span>
          </el-tooltip>

          <el-tooltip placement="top" effect="light"
            content="总患者数（患者主数据口径）：lnrs_anon_patient 全集（未删除、非占位），与 medicalDashboard「患者总量」同源同值；只随中心筛选变化，不随模态筛选变化。">
            <span style="cursor: help">
              <FaMenuRouteIcon icon="ri:file-user-fill" class="icon-count" />总患者数：<strong><FaCountTo :target="statisticsCount.total_patient_count || 0" separator="," :duration="getCountDuration(statisticsCount.total_patient_count)" /></strong>
            </span>
          </el-tooltip>

          <FaMenuRouteIcon icon="el-icon-Tickets" class="icon-count" />总记录：<strong><FaCountTo :target="statisticsCount.exam_count || 0" separator="," :duration="getCountDuration(statisticsCount.exam_count)" /></strong>

          <el-tooltip placement="top" effect="light"
            content="有检查记录的患者数（exam 口径：lnrs_anon_exam.patient_id 去重）。exam 世界与影像世界几乎不相交（省医 exam∩imaging = 219），故本数与「有影像文件的患者数」互不覆盖，两者均小于「总患者数」。">
            <span style="cursor: help">
              <FaMenuRouteIcon icon="ri:file-user-fill" class="icon-count" />有检查记录的患者数：<strong><FaCountTo :target="statisticsCount.exam_patient_count || 0" separator="," :duration="getCountDuration(statisticsCount.exam_patient_count)" /></strong>
            </span>
          </el-tooltip>

          <el-tooltip placement="top" effect="light"
            content="总文件个数 = Σ imaging_study.sop_count（真实 DICOM 文件数，issue-28）。省医 sop_count 已按 dicom_series.file_count 回填。">
            <span style="cursor: help">
              <FaMenuRouteIcon icon="file" class="icon-count" /> 总文件个数：<strong><FaCountTo :target="statisticsCount.file_count || 0" separator="," :duration="getCountDuration(statisticsCount.file_count)" /></strong>
            </span>
          </el-tooltip>

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
import {computed, h, ref, watch} from 'vue';
import {useTable} from "@/hooks";
import type {ColumnOption} from "@/types";
import FilesApi, {FilesTable, StatisticsCount} from "@api/module_medical/files.ts";
import {ElButton} from "element-plus";
import Viewer from "@views/module_medical/viewer/index.vue";

const viewer = ref<any>(null)
const selectedExamType = ref([])
const selectedFileType = ref([])
const selectedCenterType = ref([])
const sortParams = ref({sort_field:"",sort_order:""})
const fileTypeDict = ref<any>([])
const statisticsCount = ref<StatisticsCount>({})
const loading = ref(false)

function getCountDuration(value?:number){
  return !value || value <10 ? 0 :1000
}
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
// issue-28：模态筛选候选由后端 by_exam_type 驱动 —— 裁剪到 exam 表实际存在的
// exam_type（虚胖字典值不再出现），计数/百分比即 facet，label 已由后端按
// med_exam_type 字典翻译。「全选」与「不选」等价（IN 覆盖全部值域 = 无过滤）。
const examTypeOptions = computed(() => statisticsCount.value.by_exam_type || []);
watch([selectedExamType,selectedFileType,selectedCenterType,sortParams],async function (arr){
  let examType = arr[0]
  let fileType = arr[1]
  let centerType = arr[2]
  let params = {
    exam_type:examType.toString(),
    file_type:fileType.toString(),
    center_type:centerType.toString(),
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
          return dictStore.getDictItemLabel("med_modality",row.exam_type)
        }
      },
      {
        prop: "file_type",
        label: "数据格式",
        sortable :'custom',
        minWidth: 80
      },
      {
        prop: "file_size",
        label: "文件大小",
        sortable :'custom',
        formatter(row){
          return typeof row.file_size === 'number' ? fileSize(row.file_size) : '—'
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
                  file_id:row.id,
                  anon_exam_id:row.anon_exam_id
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
  await dictStore.getDict(['med_modality','med_center'])
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
.file-checkbox{
  --el-checkbox-input-border:1px solid var(--el-checkbox-checked-input-border-color);
}
.icon-count{
  font-size: 24px;
  margin-left: 15px;
}
</style>
