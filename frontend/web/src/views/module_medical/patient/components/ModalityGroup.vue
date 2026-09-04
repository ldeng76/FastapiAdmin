<template>
  <div v-if="rows.length === 0">
    <ElEmpty :description="`暂无${tableName}`" />
  </div>
  <div v-else style="height: 100%">
      <ModalityGroupTable :tableName="tableName" :rows="rows"></ModalityGroupTable>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { ElEmpty } from "element-plus";
import { type ModalityRow } from "@/api/module_medical/patient";
import ModalityGroupTable from "@views/module_medical/patient/components/ModalityGroupTable.vue";
import { getFieldLabel } from "@/components/medical/field-renderer";

// 定义 props
const props = defineProps({
  rows: { type: Array as () => ModalityRow[], default: () => [] },
  name : { type: String, default: '' }
});
const tableName = computed(function (){
  return getFieldLabel(props.name)
})

</script>
