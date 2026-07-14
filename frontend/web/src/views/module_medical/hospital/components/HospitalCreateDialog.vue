<!-- 医院注册向导：基本信息 → 选模板 → 确认 -->
<template>
  <FaDialog
    v-model="visible"
    title="注册医院"
    width="720px"
    dialog-class="crud-embed-dialog"
    modal-class="crud-embed-dialog"
    :confirm-loading="submitLoading"
    @cancel="handleCancel"
    @confirm="handleSubmit"
  >
    <ElSteps :active="currentStep" finish-status="success" simple style="margin-bottom: 20px">
      <ElStep title="基本信息" />
      <ElStep title="选择模板" />
      <ElStep title="确认" />
    </ElSteps>

    <!-- 步骤 1：基本信息 -->
    <FaForm
      v-if="currentStep === 0"
      ref="basicFormRef"
      v-model="formData"
      :items="basicFormItems"
      :rules="basicRules"
      label-suffix=":"
      :label-width="100"
      label-position="right"
      :span="24"
      :show-reset="false"
      :show-submit="false"
    />

    <!-- 步骤 2：选择模板 -->
    <div v-if="currentStep === 1" class="step-template">
      <ElFormItem label="映射模板" prop="template_code">
        <ElSelect
          v-model="formData.template_code"
          placeholder="请选择预置映射模板（可在注册后修改）"
          :loading="templateLoading"
          style="width: 100%"
          @change="onTemplateChange"
        >
          <ElOption v-for="tpl in templateOptions" :key="tpl.code" :label="tpl.name" :value="tpl.code">
            <span>{{ tpl.name }}</span>
            <span style="float: right; color: var(--el-text-color-secondary); font-size: 12px">
              {{ tpl.rule_count }} 条规则
            </span>
          </ElOption>
        </ElSelect>
      </ElFormItem>

      <ElAlert v-if="selectedTemplate" type="info" :closable="false" style="margin-top: 12px">
        <template #title>
          <strong>{{ selectedTemplate.name }}</strong>
        </template>
        <div>{{ selectedTemplate.description }}</div>
        <div style="margin-top: 8px">
          将复制 <strong>{{ selectedTemplate.rule_count }}</strong> 条字段映射规则到新建医院。
        </div>
      </ElAlert>
    </div>

    <!-- 步骤 3：确认 -->
    <div v-if="currentStep === 2" class="step-confirm">
      <FaDescriptions :data="confirmData" :items="confirmItems" :column="2" />

      <ElAlert type="warning" :closable="false" style="margin-top: 16px">
        提交后将自动创建对应租户和初始管理员账号，请妥善记录临时密码（日志输出）。
      </ElAlert>
    </div>

    <!-- 步骤导航按钮（替代 FaDialog 内置的确认/取消） -->
    <template #footer>
      <ElButton v-if="currentStep > 0" @click="currentStep--">上一步</ElButton>
      <ElButton v-if="currentStep < 2" type="primary" @click="handleNext">下一步</ElButton>
      <ElButton v-if="currentStep === 2" type="success" :loading="submitLoading" @click="handleSubmit">提交注册</ElButton>
      <ElButton @click="handleCancel">取消</ElButton>
    </template>
  </FaDialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";

import type { FormInstance, FormItemRule } from "element-plus";
import { ElAlert, ElFormItem, ElMessageBox, ElOption, ElSelect, ElStep, ElSteps } from "element-plus";
import type { SearchFormItem } from "@/components/forms/fa-search-bar/index.vue";

import FaDescriptions from "@/components/others/fa-descriptions/index.vue";
import FaDialog from "@/components/modal/fa-dialog/index.vue";
import FaForm from "@/components/forms/fa-form/index.vue";
import HospitalAPI from "@/api/module_medical/hospital";
import type { HospitalFormData, MappingTemplate } from "@/types/module_medical/hospital";

const props = defineProps<{ modelValue: boolean }>();
const emit = defineEmits<{ "update:modelValue": [boolean]; success: [] }>();

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit("update:modelValue", val),
});

// ─── 表单数据 ───────────────────────────────────────────────
const initialFormData: HospitalFormData = {
  code: "",
  name: "",
  full_name: "",
  contact_name: "",
  contact_phone: "",
  contact_email: "",
  address: "",
  data_dir: "",
  template_code: "",
};
const formData = ref<HospitalFormData>({ ...initialFormData });

const basicFormRef = ref<FormInstance>();

const basicFormItems = [
  { key: "code", label: "医院编码", type: "input", placeholder: "字母数字，如 shengyi", span: 12 },
  { key: "name", label: "医院名称", type: "input", placeholder: "如 广东省人民医院", span: 12 },
  { key: "full_name", label: "医院全称", type: "input", placeholder: "可选", span: 24 },
  { key: "data_dir", label: "数据目录", type: "input", placeholder: "parquet 文件所在路径，如 docs/zhujiang_xinqiao_parq", span: 24 },
  { key: "contact_name", label: "联系人", type: "input", placeholder: "可选", span: 12 },
  { key: "contact_phone", label: "联系电话", type: "input", placeholder: "可选", span: 12 },
  { key: "contact_email", label: "联系邮箱", type: "input", placeholder: "可选", span: 12 },
  { key: "address", label: "机构地址", type: "input", placeholder: "可选", span: 24 },
];

const basicRules: Partial<Record<string, FormItemRule[]>> = {
  code: [
    { required: true, message: "医院编码不能为空", trigger: "blur" },
    { pattern: /^[a-zA-Z0-9]+$/, message: "编码只能包含字母和数字", trigger: "blur" },
  ],
  name: [{ required: true, message: "医院名称不能为空", trigger: "blur" }],
};

// ─── 模板选择 ───────────────────────────────────────────────
const templateOptions = ref<MappingTemplate[]>([]);
const templateLoading = ref(false);
const selectedTemplate = computed(() => templateOptions.value.find((t) => t.code === formData.value.template_code));

async function loadTemplates() {
  templateLoading.value = true;
  try {
    const res = await HospitalAPI.listTemplates();
    templateOptions.value = res.data?.data || [];
  } finally {
    templateLoading.value = false;
  }
}

function onTemplateChange(_code: string) {
  // 预留：可扩展预览模板详情
}

// ─── 确认数据 ───────────────────────────────────────────────
const confirmData = computed(() => ({
  code: formData.value.code,
  name: formData.value.name,
  data_dir: formData.value.data_dir || "—",
  template_code: formData.value.template_code || "空白（注册后手动配置）",
}));

const confirmItems = [
  { label: "医院编码", prop: "code" },
  { label: "医院名称", prop: "name" },
  { label: "数据目录", prop: "data_dir" },
  { label: "预置模板", prop: "template_code" },
];

// ─── 步骤导航 ───────────────────────────────────────────────
const currentStep = ref(0);
const submitLoading = ref(false);

async function handleNext() {
  if (currentStep.value === 0) {
    const valid = await basicFormRef.value?.validate().catch(() => false);
    if (!valid) return;
  }
  currentStep.value++;
}

async function handleSubmit() {
  submitLoading.value = true;
  try {
    await HospitalAPI.createHospital(formData.value);
    ElMessageBox.alert("注册成功！请在后端日志中查看初始管理员用户名和临时密码。", "提示", {
      type: "success",
      confirmButtonText: "确定",
    });
    visible.value = false;
    currentStep.value = 0;
    formData.value = { ...initialFormData };
    emit("success");
  } finally {
    submitLoading.value = false;
  }
}

function handleCancel() {
  visible.value = false;
  currentStep.value = 0;
  formData.value = { ...initialFormData };
}

watch(visible, (val) => {
  if (val) {
    currentStep.value = 0;
    formData.value = { ...initialFormData };
    loadTemplates();
  }
});
</script>
