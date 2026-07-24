<!-- 医院管理 · 主列表页：多中心数据注册、Schema 映射、ETL 导入、上下线 -->
<template>
  <div class="fa-full-height">
    <!-- 搜索栏 -->
    <FaSearchBar
      v-show="showSearchBar"
      v-model="searchForm"
      :items="searchItems"
      :is-expand="false"
      :show-expand="true"
      :show-reset="true"
      :show-search="true"
      @search="handleSearch"
      @reset="onResetSearch"
    />

    <ElCard shadow="hover" class="fa-table-card" :style="{ 'margin-top': showSearchBar ? '12px' : '0' }">
      <FaTableHeader v-model:columns="columnChecks" v-model:showSearchBar="showSearchBar" :loading="loading" @refresh="refreshData">
        <template #left>
          <ElSpace>
            <FaTableHeaderLeft :perm-create="['module_medical:hospital:create']" @add="openCreateDialog" />
            <ElButton
              v-if="hasAuth('module_medical:dict_mapping:create')"
              type="warning"
              plain
              :icon="Upload"
              @click="openDictMappingImport"
            >
              批量导入选项映射
            </ElButton>
            <ElButton
              v-if="hasAuth('module_medical:dict_mapping:query')"
              type="primary"
              plain
              :icon="Download"
              :loading="dictMappingExportLoading"
              @click="handleDictMappingExport"
            >
              导出选项映射
            </ElButton>
          </ElSpace>
        </template>
      </FaTableHeader>

      <FaTable
        :loading="loading"
        :data="data"
        :columns="columns"
        :pagination="pagination"
        @pagination:size-change="handleSizeChange"
        @pagination:current-change="handleCurrentChange"
      />
    </ElCard>

    <!-- 注册向导 -->
    <HospitalCreateDialog v-model="createDialogVisible" @success="onCreateSuccess" />

    <!-- 数据概览面板 -->
    <DataOverviewPanel
      v-model="overviewDialogVisible"
      :hospital-id="overviewHospitalId"
      @online="refreshData"
      @offline="refreshData"
    />

    <!-- 映射编辑器 -->
    <MappingEditor
      v-model="mappingDialogVisible"
      :hospital-id="mappingHospitalId"
      :template-code="mappingTemplateCode"
    />

    <!-- 导入管理器 -->
    <ImportManager
      v-model="importDialogVisible"
      :hospital-id="importHospitalId"
      @completed="refreshData"
    />

    <!-- 选项映射批量导入 -->
    <FaImportDialog
      v-model="dictMappingImportVisible"
      title="批量导入选项映射"
      note="每个 sheet 对应一家医院（sheet 名 = center_code），表头三列：dict_type | raw_label | dict_value"
      :content-config="dictMappingImportConfig"
      :loading="dictMappingImportLoading"
      @upload="handleDictMappingImport"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, ref } from "vue";

import { ElButton, ElCard, ElMessage, ElMessageBox, ElSpace, ElTag, ElTooltip } from "element-plus";
import { Upload, Download } from "@element-plus/icons-vue";
import type { SearchFormItem } from "@/components/forms/fa-search-bar/index.vue";
import type { ColumnOption } from "@/types/component";
import type { IContentConfig } from "@/components/modal/types";
import FaSearchBar from "@/components/forms/fa-search-bar/index.vue";
import FaTable from "@/components/tables/fa-table/index.vue";
import FaTableHeader from "@/components/tables/fa-table-header/index.vue";
import FaTableHeaderLeft from "@/components/tables/fa-table-header-left/index.vue";
import FaImportDialog from "@/components/modal/fa-import-dialog/index.vue";

import HospitalAPI from "@/api/module_medical/hospital";
import { LIFECYCLE_STATUS_META, type HospitalLifecycleStatus, type HospitalTable } from "@/types/module_medical/hospital";

import { useAuth } from "@/hooks/core/useAuth";
import { useTable } from "@/hooks/core/useTable";

import DataOverviewPanel from "./components/DataOverviewPanel.vue";
import HospitalCreateDialog from "./components/HospitalCreateDialog.vue";
import ImportManager from "./components/ImportManager.vue";
import MappingEditor from "./components/MappingEditor.vue";

defineOptions({ name: "MedicalHospital", inheritAttrs: false });

const { hasAuth } = useAuth();

// 允许触发导入的状态
const IMPORTABLE_STATUSES: string[] = ["mapping_configured", "data_imported"];

// ─── 搜索 ───────────────────────────────────────────────────
interface HospitalSearchForm {
  name: string;
  code: string;
  lifecycle_status: "" | HospitalLifecycleStatus;
}
const searchForm = ref<HospitalSearchForm>({ name: "", code: "", lifecycle_status: "" });
const showSearchBar = ref(true);

const statusOptions = computed(() => [
  { label: "全部", value: "" },
  ...Object.entries(LIFECYCLE_STATUS_META).map(([value, meta]) => ({ label: meta.label, value })),
]);

const searchItems: SearchFormItem[] = [
  { key: "name", label: "医院名称", type: "input", placeholder: "模糊搜索", span: 6 },
  { key: "code", label: "医院编码", type: "input", placeholder: "模糊搜索", span: 6 },
  { key: "lifecycle_status", label: "状态", type: "select", options: [], span: 6 },
];

function handleSearch() {
  replaceSearchParams({
    name: searchForm.value.name || undefined,
    code: searchForm.value.code || undefined,
    lifecycle_status: searchForm.value.lifecycle_status || undefined,
  });
  getData();
}

function onResetSearch() {
  searchForm.value = { name: "", code: "", lifecycle_status: "" };
  resetSearchParams();
  getData();
}

// ─── 表格 ───────────────────────────────────────────────────
const {
  columns,
  columnChecks,
  data,
  loading,
  pagination,
  getData,
  replaceSearchParams,
  resetSearchParams,
  handleSizeChange,
  handleCurrentChange,
  refreshData,
} = useTable<typeof HospitalAPI.listHospital>({
  core: {
    apiFn: HospitalAPI.listHospital,
    apiParams: { page_no: 1, page_size: 10 },
    columnsFactory: (): ColumnOption<HospitalTable>[] => [
      { type: "globalIndex", width: 56, label: "序号" },
      { prop: "code", label: "编码", minWidth: 120, showOverflowTooltip: true },
      { prop: "name", label: "名称", minWidth: 160, showOverflowTooltip: true },
      {
        prop: "lifecycle_status",
        label: "状态",
        width: 120,
        align: "center",
        formatter: (row) => {
          const meta = LIFECYCLE_STATUS_META[row.lifecycle_status] || { label: row.lifecycle_status, type: "info" as const };
          return h(ElTag, { type: meta.type, effect: "dark", size: "small" }, () => meta.label);
        },
      },
      { prop: "last_import_rows", label: "数据行数", width: 110, align: "right", formatter: (row) => (row.last_import_rows ? row.last_import_rows.toLocaleString() : "-") },
      {
        prop: "last_import_time",
        label: "最近导入",
        width: 170,
        formatter: (row) => (row.last_import_time ? row.last_import_time.replace("T", " ").slice(0, 19) : "-"),
      },
      {
        prop: "__operation__",
        label: "操作",
        minWidth: 260,
        align: "left",
        formatter: (row) =>
          h(
            "div",
            { class: "operation-cell" },
            [
              // 数据预览
              h(ElButton, { type: "primary", link: true, onClick: () => handlePreviewData(row) }, () => "数据概览"),
              // 编辑映射（registered/mapping_configured/data_imported 允许；LIVE 需下线）
              hasAuth("module_medical:hospital:mapping:edit")
                ? h(
                    ElButton,
                    {
                      type: "primary",
                      link: true,
                      disabled: row.lifecycle_status === "live",
                      onClick: () => handleEditMappings(row),
                    },
                    () =>
                      row.lifecycle_status === "live"
                        ? h(ElTooltip, { content: "请先下线后再编辑映射", placement: "top" }, { default: () => "编辑映射" })
                        : "编辑映射",
                  )
                : null,
              // 上线 / 下线
              row.lifecycle_status === "data_imported" && hasAuth("module_medical:hospital:online")
                ? h(ElButton, { type: "success", link: true, onClick: () => handleGoOnline(row) }, () => "上线")
                : null,
              row.lifecycle_status === "live" && hasAuth("module_medical:hospital:offline")
                ? h(ElButton, { type: "warning", link: true, onClick: () => handleGoOffline(row) }, () => "下线")
                : null,
              // 触发 anon 数据导入（仅 mapping_configured / data_imported）
              IMPORTABLE_STATUSES.includes(row.lifecycle_status) && hasAuth("module_medical:hospital:import:anon")
                ? h(
                    ElButton,
                    { type: "primary", link: true, onClick: () => handleTriggerImport(row) },
                    () => "导入匿名数据",
                  )
                : null,
            ].filter(Boolean),
          ),
      },
    ],
  },
});

// ─── 注册向导 ───────────────────────────────────────────────
const createDialogVisible = ref(false);

function openCreateDialog() {
  createDialogVisible.value = true;
}

function onCreateSuccess() {
  refreshData();
}

// ─── 子组件状态 ─────────────────────────────────────────────
const overviewDialogVisible = ref(false);
const overviewHospitalId = ref(0);
const mappingDialogVisible = ref(false);
const mappingHospitalId = ref(0);
const mappingTemplateCode = ref<string>("");
const importDialogVisible = ref(false);
const importHospitalId = ref(0);

// ─── 操作处理 ───────────────────────────────────────────────
function handlePreviewData(row: HospitalTable) {
  overviewHospitalId.value = row.id;
  overviewDialogVisible.value = true;
}

function handleEditMappings(row: HospitalTable) {
  mappingHospitalId.value = row.id;
  mappingTemplateCode.value = "";
  mappingDialogVisible.value = true;
}

async function handleGoOnline(row: HospitalTable) {
  try {
    await HospitalAPI.goOnline(row.id);
    refreshData();
  } catch {
    // 错误已由 axios 拦截器处理
  }
}

async function handleGoOffline(row: HospitalTable) {
  try {
    await HospitalAPI.goOffline(row.id);
    refreshData();
  } catch {
    // 错误已由 axios 拦截器处理
  }
}

function handleTriggerImport(row: HospitalTable) {
  importHospitalId.value = row.id;
  importDialogVisible.value = true;
}

// ─── 选项映射 Excel 批量导入 ────────────────────────────────
const dictMappingImportVisible = ref(false);
const dictMappingImportLoading = ref(false);
const dictMappingImportConfig: IContentConfig = {
  permPrefix: "module_medical:dict_mapping",
  // FaImportDialog 仅消费 permPrefix + importTemplate；indexAction/cols 为满足 IContentConfig 必填的占位
  indexAction: async () => ({}),
  cols: [],
  importTemplate: () => HospitalAPI.downloadDictMappingTemplate(),
};

function openDictMappingImport() {
  dictMappingImportVisible.value = true;
}

async function handleDictMappingImport(formData: FormData) {
  dictMappingImportLoading.value = true;
  try {
    const res = await HospitalAPI.importDictMapping(formData);
    const msg = res.data?.data || "导入完成";
    dictMappingImportVisible.value = false;
    // 结果可能含跳过的无效数据明细，用多行消息框展示
    if (msg.includes("跳过") || msg.includes("\n")) {
      ElMessageBox.alert(msg.replace(/\n/g, "<br/>"), "导入结果", {
        dangerouslyUseHTMLString: true,
        type: "warning",
      });
    } else {
      ElMessage.success(msg);
    }
  } catch {
    // 错误已由拦截器处理
  } finally {
    dictMappingImportLoading.value = false;
  }
}

// ─── 选项映射 Excel 导出 ────────────────────────────────────
const dictMappingExportLoading = ref(false);

async function handleDictMappingExport() {
  dictMappingExportLoading.value = true;
  try {
    const res = await HospitalAPI.exportDictMapping();
    const blob = new Blob([res.data as any], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;charset=utf-8",
    });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "医院选项映射导出.xlsx";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
    ElMessage.success("导出成功");
  } catch {
    // 错误已由拦截器处理
  } finally {
    dictMappingExportLoading.value = false;
  }
}

onMounted(() => {
  // 初始数据加载由 useTable 自动完成
});
</script>

<style scoped>
:deep(.operation-cell) {
  display: flex;
  gap: 8px;
  flex-wrap: nowrap;
  align-items: center;
}
</style>
