<template>
  <ElEmpty v-if="rows.length === 0" :description="`暂无${tableName}`" />
  <ModalityGroupTable v-else :tableName="tableName" :rows="rows"></ModalityGroupTable>
</template>

<script setup lang="ts">
import { ElEmpty} from "element-plus";
import { type ModalityRow} from "@/api/module_medical/patient";
import ModalityGroupTable from "@views/module_medical/patient/components/ModalityGroupTable.vue";
import {getFieldLabel} from "@/components/medical/field-renderer";

// 定义 props
 const props = defineProps({
  rows: { type: Array as () => ModalityRow[], default: () => [] },
  name : { type: String, default: '' }
});
const tableName = computed(function (){
  return getFieldLabel(props.name)
})

</script>

<style scoped>
.record-card {
  margin-bottom: 12px;
}
</style>
