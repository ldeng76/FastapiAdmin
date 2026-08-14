<!--
  业务渲染：数组 → ElTable（诊断 / 临床文档等）。
  由 FieldRenderer 在 schema.type === 'table' 时调用。
-->
<template>
  <div class="json-biz-card">
    <div v-if="showTitle" class="json-biz-title">
      {{ schema.title }}（{{ rows.length }}）
    </div>
    <ElTable :data="rows" border size="small" stripe style="width: 100%">
      <ElTableColumn
        v-for="col in schema.columns"
        :key="col.key"
        :prop="col.key"
        :label="col.label"
        :width="col.width"
        :min-width="col.minWidth"
        :show-overflow-tooltip="false"
      >
        <template #default="{ row }">
          <span v-if="!col.formatter">{{ cellText(row[col.key]) }}</span>
          <component v-else :is="col.formatter(row[col.key], row)" />
        </template>
      </ElTableColumn>
    </ElTable>
  </div>
</template>

<script setup lang="ts">
import { ElTable, ElTableColumn } from "element-plus";
import type { TableSchema } from "./field-schemas";

defineOptions({ name: "DiagnosesTableCard" });

withDefaults(
  defineProps<{
    rows: Record<string, unknown>[];
    schema: TableSchema;
    /** 是否显示卡片标题；由 FieldRenderer.showTitle 透传 */
    showTitle?: boolean;
  }>(),
  { showTitle: true },
);

function cellText(v: unknown): string {
  if (v === null || v === undefined || v === "") return "-";
  if (typeof v === "boolean") return v ? "是" : "否";
  return String(v);
}
</script>

<style scoped>
.json-biz-card {
  margin: 0;
}
.json-biz-title {
  font-weight: 600;
  font-size: 13px;
  color: var(--el-text-color-regular);
  margin-bottom: 8px;
}
</style>
