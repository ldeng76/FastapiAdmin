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
          <FaTableHeaderLeft :perm-create="['module_medical:hospital:create']" @add="openCreateDialog" />
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
  </div>
</template>

<script setup lang="ts">
import { computed, h, onMounted, ref } from "vue";

import { ElButton, ElCard, ElTag, ElTooltip } from "element-plus";
import type { SearchFormItem } from "@/components/forms/fa-search-bar/index.vue";
import type { ColumnOption } from "@/types/component";
import FaSearchBar from "@/components/forms/fa-search-bar/index.vue";
import FaTable from "@/components/tables/fa-table/index.vue";
import FaTableHeader from "@/components/tables/fa-table-header/index.vue";
import FaTableHeaderLeft from "@/components/tables/fa-table-header-left/index.vue";

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
              // 触发导入（仅 mapping_configured / data_imported）
              IMPORTABLE_STATUSES.includes(row.lifecycle_status) && hasAuth("module_medical:hospital:import")
                ? h(ElButton, { type: "primary", link: true, onClick: () => handleTriggerImport(row) }, () => "导入")
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
