<!-- 映射规则编辑器：表格内联编辑 + 全量替换 -->
<template>
  <FaDialog
    v-model="visible"
    title="编辑字段映射规则"
    width="1100px"
    dialog-class="crud-embed-dialog"
    modal-class="crud-embed-dialog"
    :confirm-loading="submitLoading"
    @cancel="handleCancel"
    @confirm="handleSubmit"
  >
    <div class="mapping-editor-toolbar">
      <ElButton type="primary" :icon="Plus" @click="handleAddRule">新增规则</ElButton>
      <ElButton :icon="RefreshRight" @click="handleReload">重新加载</ElButton>
      <ElButton type="success" :icon="Download" @click="handleApplyTemplate">应用模板</ElButton>
      <span class="rule-count">共 {{ rules.length }} 条规则</span>
    </div>

    <ElTable :data="rules" border stripe max-height="60vh" style="width: 100%">
      <ElTableColumn prop="src_table" label="源表" width="140">
        <template #default="{ row }">
          <ElInput v-model="row.src_table" placeholder="源表名" size="small" />
        </template>
      </ElTableColumn>
      <ElTableColumn prop="src_field" label="源字段" width="140">
        <template #default="{ row }">
          <ElInput v-model="row.src_field" placeholder="源字段名" size="small" />
        </template>
      </ElTableColumn>
      <ElTableColumn prop="tgt_table" label="目标表" width="140">
        <template #default="{ row }">
          <ElInput v-model="row.tgt_table" placeholder="med_xxx" size="small" />
        </template>
      </ElTableColumn>
      <ElTableColumn prop="tgt_field" label="目标字段" width="140">
        <template #default="{ row }">
          <ElInput v-model="row.tgt_field" placeholder="目标字段名" size="small" />
        </template>
      </ElTableColumn>
      <ElTableColumn prop="transform_type" label="转换类型" width="120">
        <template #default="{ row }">
          <ElSelect v-model="row.transform_type" size="small" style="width: 100%">
            <ElOption label="重命名" value="rename" />
            <ElOption label="常量" value="constant" />
            <ElOption label="表达式" value="expression" />
          </ElSelect>
        </template>
      </ElTableColumn>
      <ElTableColumn prop="transform_value" label="转换值" min-width="160">
        <template #default="{ row }">
          <ElInput
            v-model="row.transform_value"
            :placeholder="row.transform_type === 'rename' ? '重命名无需填写' : '常量值或函数名'"
            :disabled="row.transform_type === 'rename'"
            size="small"
          />
        </template>
      </ElTableColumn>
      <ElTableColumn prop="sort" label="顺序" width="80">
        <template #default="{ row }">
          <ElInputNumber v-model="row.sort" :min="0" size="small" style="width: 100%" />
        </template>
      </ElTableColumn>
      <ElTableColumn label="规则操作" width="90">
        <template #default="{ $index }">
          <ElButton type="danger" link size="small" @click="handleDeleteRule($index)">删除</ElButton>
        </template>
      </ElTableColumn>
    </ElTable>

    <template #footer>
      <ElButton @click="handleCancel">取消</ElButton>
      <ElButton type="primary" :loading="submitLoading" @click="handleSubmit">保存</ElButton>
    </template>
  </FaDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";

import { ElButton, ElInput, ElInputNumber, ElMessage, ElOption, ElSelect, ElTable, ElTableColumn } from "element-plus";
import { Download, Plus, RefreshRight } from "@element-plus/icons-vue";

import FaDialog from "@/components/modal/fa-dialog/index.vue";
import HospitalAPI from "@/api/module_medical/hospital";
import type { MappingRuleRow } from "@/types/module_medical/hospital";

const props = defineProps<{
  modelValue: boolean;
  hospitalId: number;
  templateCode?: string;
}>();
const emit = defineEmits<{ "update:modelValue": [boolean] }>();

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit("update:modelValue", val),
});

const rules = ref<MappingRuleRow[]>([]);
const submitLoading = ref(false);

// 空规则模板
function emptyRule(): MappingRuleRow {
  return {
    src_table: "",
    src_field: "",
    tgt_table: "med_",
    tgt_field: "",
    transform_type: "rename",
    transform_value: null,
    description: null,
    sort: rules.value.length,
  };
}

async function loadRules() {
  try {
    const res = await HospitalAPI.listMappings(props.hospitalId);
    rules.value = res.data?.data || [];
  } catch {
    rules.value = [];
  }
}

function handleAddRule() {
  rules.value.push(emptyRule());
}

function handleDeleteRule(index: number) {
  rules.value.splice(index, 1);
}

function handleReload() {
  loadRules();
}

async function handleApplyTemplate() {
  if (!props.templateCode) {
    ElMessage.warning("未指定模板编码");
    return;
  }
  try {
    const res = await HospitalAPI.applyTemplate(props.hospitalId, props.templateCode);
    rules.value = res.data?.data || [];
    ElMessage.success("模板应用成功");
  } catch {
    // 错误已由拦截器处理
  }
}

async function handleSubmit() {
  // 校验必填字段
  for (const rule of rules.value) {
    if (!rule.src_table || !rule.src_field || !rule.tgt_table || !rule.tgt_field) {
      ElMessage.warning("请填写完整的源表/源字段/目标表/目标字段");
      return;
    }
  }
  submitLoading.value = true;
  try {
    await HospitalAPI.replaceMappings(props.hospitalId, {
      rules: rules.value.map((r, i) => ({
        src_table: r.src_table,
        src_field: r.src_field,
        tgt_table: r.tgt_table,
        tgt_field: r.tgt_field,
        transform_type: r.transform_type,
        transform_value: r.transform_value || null,
        description: r.description || null,
        sort: i,
      })),
    });
    ElMessage.success("映射规则已更新");
    visible.value = false;
  } finally {
    submitLoading.value = false;
  }
}

function handleCancel() {
  visible.value = false;
}

watch(visible, (val) => {
  if (val) {
    loadRules();
  }
});
</script>

<style scoped>
.mapping-editor-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.rule-count {
  margin-left: auto;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
