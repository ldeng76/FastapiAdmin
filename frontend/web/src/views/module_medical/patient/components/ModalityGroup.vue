<template>
  <ElEmpty v-if="rows.length === 0" :description="`暂无${getFieldLabel(name)}`" />
  <ElCollapse :expand-icon-position="'left'" v-else :model-value="expandedNames">
    <ElCollapseItem
      v-for="(group, index) in groups"
      :key="index"
      :title="`${group.name}（${group.rows.length}）`"
      :name="index.toString()"
    >
       <ModalityGroupTable :tableName="group.name" :rows="group.rows"></ModalityGroupTable>
    </ElCollapseItem>
  </ElCollapse>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { ElEmpty, ElCollapse, ElCollapseItem } from "element-plus";
import { type ModalityRow} from "@/api/module_medical/patient";
import ModalityGroupTable from "@views/module_medical/patient/components/ModalityGroupTable.vue";
import {getFieldLabel} from "@/components/medical/field-renderer";

// 定义 props
const props = defineProps({
  rows: { type: Array as () => ModalityRow[], default: () => [] },
  column: { type: Number, default: 3 },
  name : { type: String, default: '' }
});

// 计算分组数据
const groups = computed(() => {
  const map = new Map<string, ModalityRow[]>();
  for (const r of props.rows) {
    let key = r._table || "其他";
    if(key === 'genetic'){
      key = getFieldLabel("genetic")
    } else if(key === 'pathology'){
      key = getFieldLabel("pathology")
    } else if(key.indexOf('nodule_imaging') === 0 || key === 'imaging_report' || key === 'ultrasound'){
      key = getFieldLabel("imaging")
    } else if(key === 'ihc'){
      key = getFieldLabel("ihc")
    }
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(r);
  }
  return Array.from(map.entries()).map(([name, rows]) => ({ name, rows }));
});

// v-model 绑定的展开面板数组（所有组都展开）
const expandedNames = computed(() => groups.value.map((_, i) => i.toString()));
</script>

<style scoped>
.record-card {
  margin-bottom: 12px;
}
</style>
