<!--
  DICOM 影像查看器（cornerstone3D stack viewport）

  能力：
  - 滚轮逐层翻看（StackScroll），支持序列内任意张数流式加载
  - 调窗宽窗位：左键拖拽实时调节 + 肺窗/纵隔窗/骨窗/脑窗预设
  - 缩放/平移：滚轮缩放、右键拖拽平移
  - 测量：长度(mm)、角度、探针(显示鼠标处 HU 值)、矩形 ROI 统计
  - 多序列切换

  数据流：后端 /medical/dicom/instances/{sop_uid} 返回原始 .dcm 字节 →
  前端 cornerstone dicom-image-loader (wadouri) 浏览器端解码 →
  保留 HU 值 → 支持调窗/带物理单位测量。

  关键点：
  - wadouri 的 XHR 默认不带 Authorization，通过 dicomImageLoader.internal.setOptions
    注入 beforeSend 钩子补上 token。
  - viewport 容器必须有显式高度，否则 canvas 黑屏。
  - 组件卸载必须 destroy renderingEngine + toolGroup，防 WebGL 内存泄漏。
-->
<template>
  <div class="dicom-viewer">
    <!-- 左侧：序列选择 -->
    <div class="viewer-sidebar">
      <div class="sidebar-title">序列列表</div>
      <div
        v-for="s in seriesList"
        :key="s.series_uid"
        class="series-item"
        :class="{ active: s.series_uid === activeSeriesUid }"
        @click="selectSeries(s.series_uid)"
      >
        <div class="series-desc">{{ s.series_description || "(未命名序列)" }}</div>
        <div class="series-meta">
          <ElTag size="small" effect="plain">{{ s.modality || "?" }}</ElTag>
          <span>{{ s.instance_count }} 张</span>
          <span v-if="s.slice_thickness">{{ s.slice_thickness }}mm</span>
        </div>
      </div>
      <ElEmpty v-if="!seriesList.length" description="暂无序列" :image-size="60" />
    </div>

    <!-- 中间：影像 viewport -->
    <div class="viewer-main">
      <div
        ref="viewportRef"
        class="viewport-container"
        v-loading="loadingImage"
        element-loading-text="加载影像..."
      >
        <div class="viewport-overlay" v-if="currentInstance">
          <div class="overlay-tl">
            <div>{{ studyInfo?.patient_name || "" }}</div>
            <div>{{ studyInfo?.study_description || "" }}</div>
          </div>
          <div class="overlay-tr">
            <div>{{ activeSeries?.series_description || "" }}</div>
            <div>{{ activeSeries?.slice_thickness ? activeSeries.slice_thickness + "mm" : "" }}</div>
          </div>
          <div class="overlay-bl">
            <div>层 {{ currentInstance.index }} / {{ instanceCount }}</div>
            <div v-if="currentInstance.position_z != null">
              Z: {{ currentInstance.position_z.toFixed(1) }} mm
            </div>
          </div>
          <div class="overlay-br">
            <div>WW {{ Math.round(windowWidth) }} / WL {{ Math.round(windowCenter) }}</div>
          </div>
        </div>
      </div>

      <!-- 工具栏 -->
      <div class="viewer-toolbar">
        <div class="toolbar-group">
          <span class="group-label">窗位</span>
          <ElButton size="small" @click="applyPreset('lung')">肺窗</ElButton>
          <ElButton size="small" @click="applyPreset('mediastinum')">纵隔</ElButton>
          <ElButton size="small" @click="applyPreset('bone')">骨窗</ElButton>
          <ElButton size="small" @click="applyPreset('brain')">脑窗</ElButton>
          <ElButton size="small" @click="applyPreset('default')">默认</ElButton>
        </div>
        <div class="toolbar-divider" />
        <div class="toolbar-group">
          <span class="group-label">操作</span>
          <ElButton
            size="small"
            :type="activeTool === 'WindowLevel' ? 'primary' : 'default'"
            @click="setActiveTool('WindowLevel')"
          >调窗</ElButton>
          <ElButton
            size="small"
            :type="activeTool === 'Zoom' ? 'primary' : 'default'"
            @click="setActiveTool('Zoom')"
          >缩放</ElButton>
          <ElButton
            size="small"
            :type="activeTool === 'Pan' ? 'primary' : 'default'"
            @click="setActiveTool('Pan')"
          >平移</ElButton>
        </div>
        <div class="toolbar-divider" />
        <div class="toolbar-group">
          <span class="group-label">测量</span>
          <ElButton
            size="small"
            :type="activeTool === 'Length' ? 'primary' : 'default'"
            @click="setActiveTool('Length')"
          >长度</ElButton>
          <ElButton
            size="small"
            :type="activeTool === 'Angle' ? 'primary' : 'default'"
            @click="setActiveTool('Angle')"
          >角度</ElButton>
          <ElButton
            size="small"
            :type="activeTool === 'Probe' ? 'primary' : 'default'"
            @click="setActiveTool('Probe')"
          >探针</ElButton>
          <ElButton
            size="small"
            :type="activeTool === 'RectangleROI' ? 'primary' : 'default'"
            @click="setActiveTool('RectangleROI')"
          >ROI</ElButton>
        </div>
        <div class="toolbar-divider" />
        <div class="toolbar-group">
          <ElButton size="small" @click="resetView">重置</ElButton>
          <ElButton size="small" type="danger" plain @click="clearMeasurements">清除标注</ElButton>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch, nextTick } from "vue";
import { ElButton, ElTag, ElEmpty, ElMessage } from "element-plus";
import {
  RenderingEngine,
  Types as CsTypes,
  init as initCore,
  Enums as CsEnums,
  eventTarget,
  getRenderingEngine,
  imageLoader,
} from "@cornerstonejs/core";
import {
  init as initTools,
  addTool,
  ToolGroupManager,
  Enums as ToolEnums,
  annotation as toolsAnnotation,
  WindowLevelTool,
  ZoomTool,
  PanTool,
  StackScrollTool,
  LengthTool,
  AngleTool,
  ProbeTool,
  RectangleROITool,
} from "@cornerstonejs/tools";

// MouseBindings 在 Enums 命名空间下
const { MouseBindings } = ToolEnums;
import dicomImageLoader from "@cornerstonejs/dicom-image-loader";

/** 最小 ToolGroup 接口（仅声明用到的方法），避免全 any 丢失类型保护 */
interface IToolGroup {
  addTool: (name: string) => void;
  addToolInstance: (name: string, instanceId: string) => void;
  addViewport: (viewportId: string, engineId: string) => void;
  setToolActive: (name: string, opts?: { bindings?: Array<{ mouseButton: number }> }) => void;
  setToolPassive: (name: string) => void;
  destroy: () => void;
}
import DicomAPI, {
  type DicomStudy,
  type DicomSeries,
  type DicomInstance,
} from "@/api/module_medical/dicom";
import { Auth } from "@/utils/auth";

const props = defineProps<{
  /** 初始 Study ID（目录名） */
  studyId?: string;
}>();

// cornerstone 全局只初始化一次（跨多次开关弹窗）
let cornerstoneInited = false;

// 运行时实例
const ENGINE_ID = "dicom-engine";
const TOOLGROUP_ID = "dicom-toolgroup";
const VIEWPORT_ID = "dicom-viewport";
let renderingEngine: RenderingEngine | null = null;
let toolGroup: IToolGroup = null;

// 数据状态
const seriesList = ref<DicomSeries[]>([]);
const activeSeriesUid = ref<string>("");
const instanceList = ref<DicomInstance[]>([]);
const studyInfo = ref<DicomStudy | null>(null);
const currentInstance = ref<DicomInstance | null>(null);
const loadingImage = ref(false);
const activeTool = ref<string>("WindowLevel");
const windowWidth = ref(0);
const windowCenter = ref(0);

const viewportRef = ref<HTMLDivElement | null>(null);
const instanceCount = computed(() => instanceList.value.length);
const activeSeries = computed(
  () => seriesList.value.find((s) => s.series_uid === activeSeriesUid.value) || null,
);

// 窗位预设（WW / WL）
const WINDOW_PRESETS: Record<string, { ww: number; wc: number }> = {
  lung: { ww: 1600, wc: -600 },
  mediastinum: { ww: 400, wc: 40 },
  bone: { ww: 1500, wc: 400 },
  brain: { ww: 80, wc: 40 },
};

// 工具名 → 注册类
const TOOL_CLASSES: Record<string, any> = {
  WindowLevel: WindowLevelTool,
  Zoom: ZoomTool,
  Pan: PanTool,
  StackScroll: StackScrollTool,
  Length: LengthTool,
  Angle: AngleTool,
  Probe: ProbeTool,
  RectangleROI: RectangleROITool,
};

// ===================================================================== //
// 初始化
// ===================================================================== //
function ensureCornerstoneInited() {
  if (cornerstoneInited) return;
  initCore();
  initTools();
  // wadouri 加载器注册（dicom scheme → dicom-image-loader）
  dicomImageLoader.init({
    // 注入 Authorization 头：wadouri 的 XHR 默认不带 token
    beforeSend: () => {
      const token = Auth.getAccessToken();
      return token ? { Authorization: `Bearer ${token}` } : ({} as Record<string, string>);
    },
  });
  cornerstoneInited = true;
}

function registerTools() {
  Object.values(TOOL_CLASSES).forEach((ToolClass) => {
    try {
      addTool(ToolClass);
    } catch (e) {
      // 重复注册会抛错，忽略
    }
  });
}

function createToolGroup() {
  if (toolGroup) return toolGroup;
  toolGroup = ToolGroupManager.createToolGroup(TOOLGROUP_ID);
  if (!toolGroup) return null;
  // 把所有工具加进 toolgroup
  Object.keys(TOOL_CLASSES).forEach((name) => toolGroup!.addTool(name));
  // 默认工具绑定
  // 左键 = 当前激活工具（WindowLevel/Length 等）
  // 滚轮 = 翻层（始终）
  toolGroup.addToolInstance("StackScroll", "stackScrollMouseWheel");
  toolGroup.setToolActive("stackScrollMouseWheel", {
    bindings: [{ mouseButton: MouseBindings.Wheel }],
  });
  // 右键 = 平移（始终）
  toolGroup.setToolActive("Pan", {
    bindings: [{ mouseButton: MouseBindings.Secondary }],
  });
  // 中键 = 缩放（始终）
  toolGroup.setToolActive("Zoom", {
    bindings: [{ mouseButton: MouseBindings.Auxiliary }],
  });
  return toolGroup;
}

/** 构建 imageId：wadouri scheme + 后端文件接口。
 * 必须用绝对 URL：cornerstone 的 wadouri loader 用 XMLHttpRequest，
 * 相对路径在某些浏览器/worker 场景下无法正确解析，导致请求不发。
 * 前端经 vite proxy（/api/v1 → 后端），故 origin 用当前页面 origin 即可。
 * 可通过 VITE_DICOM_API_BASE 覆盖，便于在不同部署/反代路径下调整。
 */
const DICOM_API_BASE =
  (import.meta.env.VITE_DICOM_API_BASE as string) ||
  `${window.location.origin}/api/v1/medical/dicom/instances`;

function buildImageId(sopUid: string): string {
  return `wadouri:${DICOM_API_BASE}/${encodeURIComponent(sopUid)}`;
}

// ===================================================================== //
// 数据加载
// ===================================================================== //
async function loadStudy() {
  if (!props.studyId) return;
  loadingImage.value = true;
  try {
    // NOTE: 当前全量拉 studies 再前端过滤；后端若新增 GET /dicom/studies/{studyId}
    // 可改为单点查询以减少传输量。
    const [studyRes, seriesRes] = await Promise.all([
      DicomAPI.listStudies(),
      DicomAPI.listSeries(props.studyId),
    ]);
    const studies = studyRes.data?.data || [];
    studyInfo.value = studies.find((s) => s.study_id === props.studyId) || studies[0] || null;
    seriesList.value = (seriesRes.data?.data || []).filter(
      // 仅显示 CT 轴位序列（有窗宽窗位的可阅片序列），跳过截图/无窗序列可选
      (s) => s.instance_count > 0,
    );
    if (seriesList.value.length) {
      // 默认选张数最多的序列（通常是薄层主序列）
      const main = [...seriesList.value].sort((a, b) => b.instance_count - a.instance_count)[0];
      await selectSeries(main.series_uid);
    }
  } catch (e: any) {
    ElMessage.error("加载 Study 数据失败：" + (e?.message || e));
  } finally {
    loadingImage.value = false;
  }
}

async function selectSeries(seriesUid: string, force = false) {
  if (!force && seriesUid === activeSeriesUid.value && instanceList.value.length) return;
  activeSeriesUid.value = seriesUid;
  loadingImage.value = true;
  try {
    const res = await DicomAPI.listInstances(seriesUid);
    instanceList.value = res.data?.data || [];
    if (!instanceList.value.length) {
      ElMessage.warning("该序列无可用切片");
      return;
    }
    await renderStack();
  } catch (e: any) {
    ElMessage.error("加载切片失败：" + (e?.message || e));
  } finally {
    loadingImage.value = false;
  }
}

// ===================================================================== //
// 渲染
// ===================================================================== //
async function renderStack() {
  if (!viewportRef.value || !instanceList.value.length) return;

  ensureCornerstoneInited();
  registerTools();

  // 清理旧 engine（切 series / 重新渲染时）
  destroyEngine();

  renderingEngine = new RenderingEngine(ENGINE_ID);
  createToolGroup();

  const viewportInput: CsTypes.PublicViewportInput = {
    viewportId: VIEWPORT_ID,
    type: CsEnums.ViewportType.STACK,
    element: viewportRef.value,
  };
  renderingEngine.setViewports([viewportInput]);

  const viewport = renderingEngine.getViewport(VIEWPORT_ID) as any;
  if (!viewport) return;

  // toolgroup 绑定到 viewport
  toolGroup?.addViewport(VIEWPORT_ID, ENGINE_ID);

  // 构建 imageId 列表（已按 Z 轴排序）
  const imageIds = instanceList.value.map((i) => buildImageId(i.sop_uid));

  // stack 模式：设 imageIds，自动按需加载
  await viewport.setStack(imageIds, 0);

  // 默认激活调窗工具
  setActiveTool("WindowLevel");

  // 应用默认窗位（取切片的 window width/center）
  const first = instanceList.value[0];
  if (first?.window_width && first?.window_center) {
    windowWidth.value = first.window_width;
    windowCenter.value = first.window_center;
    applyWindowToViewport(first.window_width, first.window_center);
  }

  // 翻层事件：更新当前层信息
  viewport.element.addEventListener(CsEnums.Events.STACK_VIEWPORT_SCROLL, onStackScroll);
  // 窗位改变事件
  eventTarget.addEventListener(CsEnums.Events.VOI_MODIFIED, onVoiModified);

  // 立即渲染首张
  renderingEngine.renderViewports([VIEWPORT_ID]);

  // 初始 currentInstance
  updateCurrentInstance(viewport);
  // 预取相邻层（流畅翻看）
  prefetchNeighbors(viewport);

  // 开发期暴露 viewport 便于联调（生产构建会被 tree-shake 掉 if 块）
  if (import.meta.env.DEV) (window as any).__cv = viewport;
}

function onStackScroll(evt: any) {
  const viewport = renderingEngine?.getViewport(VIEWPORT_ID) as any;
  if (!viewport) return;
  updateCurrentInstance(viewport);
  prefetchNeighbors(viewport);
}

function updateCurrentInstance(viewport: any) {
  const idx = viewport.getCurrentImageIdIndex?.() ?? 0;
  currentInstance.value = instanceList.value[idx] || null;
}

function prefetchNeighbors(viewport: any) {
  // cornerstone 默认会按需加载当前层；这里触发相邻层预取以提升体验
  const idx = viewport.getCurrentImageIdIndex?.() ?? 0;
  const imageIds = instanceList.value.map((i) => buildImageId(i.sop_uid));
  const neighbors = [imageIds[idx + 1], imageIds[idx + 2], imageIds[idx - 1]].filter(Boolean);
  neighbors.forEach((id: string) => {
    try {
      // 异步预取，不阻塞渲染
      imageLoader.loadImage(id).catch(() => {});
    } catch {
      /* ignore */
    }
  });
}

function onVoiModified(evt: any) {
  const { volumeId, range } = evt.detail || {};
  if (!range) return;
  // voiRange.lower/upper → 反推 WW/WL：WL=(upper+lower)/2, WW=(upper-lower)
  if (range.lower != null && range.upper != null) {
    windowCenter.value = (range.upper + range.lower) / 2;
    windowWidth.value = range.upper - range.lower;
  }
}

// ===================================================================== //
// 工具与窗位操作
// ===================================================================== //
// 先把所有可绑定到鼠标左键的工具置为 passive，避免 setActiveTool 后多工具同时响应左键
const PRIMARY_TOOLS = [
  "WindowLevel",
  "Zoom",
  "Pan",
  "Length",
  "Angle",
  "Probe",
  "RectangleROI",
];

function setActiveTool(toolName: string) {
  if (!toolGroup) return;
  PRIMARY_TOOLS.forEach((name) => {
    if (name !== toolName) toolGroup!.setToolPassive(name);
  });
  activeTool.value = toolName;
  // 左键绑定到激活工具
  toolGroup.setToolActive(toolName, {
    bindings: [{ mouseButton: MouseBindings.Primary }],
  });
}

function applyPreset(preset: string) {
  if (preset === "default") {
    const first = instanceList.value[0];
    if (first?.window_width && first?.window_center) {
      applyWindowToViewport(first.window_width, first.window_center);
    }
    return;
  }
  const p = WINDOW_PRESETS[preset];
  if (p) applyWindowToViewport(p.ww, p.wc);
}

function applyWindowToViewport(ww: number, wc: number) {
  const viewport = renderingEngine?.getViewport(VIEWPORT_ID) as any;
  if (!viewport) return;
  const lower = wc - ww / 2;
  const upper = wc + ww / 2;
  viewport.setProperties({ voiRange: { lower, upper } });
  windowWidth.value = ww;
  windowCenter.value = wc;
  renderingEngine?.renderViewports([VIEWPORT_ID]);
}

function resetView() {
  const viewport = renderingEngine?.getViewport(VIEWPORT_ID) as any;
  if (!viewport) return;
  viewport.resetProperties?.();
  viewport.resetCamera?.();
  const first = instanceList.value[0];
  if (first?.window_width && first?.window_center) {
    applyWindowToViewport(first.window_width, first.window_center);
  } else {
    renderingEngine?.renderViewports([VIEWPORT_ID]);
  }
}

function clearMeasurements() {
  // 仅清除绑定到当前 viewport element 的标注，避免影响其他实例
  const element = viewportRef.value;
  const annots = toolsAnnotation.state.getAllAnnotations?.() || [];
  annots
    .filter((a: any) => !element || a.metadata?.element === element)
    .forEach((a: any) => {
      toolsAnnotation.state.removeAnnotation?.(a.annotationUID);
    });
  renderingEngine?.renderViewports([VIEWPORT_ID]);
}

// ===================================================================== //
// 生命周期清理（防 WebGL 内存泄漏）
// ===================================================================== //
function destroyEngine() {
  // 移除事件
  const vp = renderingEngine?.getViewport(VIEWPORT_ID);
  vp?.element?.removeEventListener(CsEnums.Events.STACK_VIEWPORT_SCROLL, onStackScroll);
  eventTarget.removeEventListener(CsEnums.Events.VOI_MODIFIED, onVoiModified);
  // 销毁 engine（含 viewport + canvas）
  const existing = getRenderingEngine(ENGINE_ID);
  if (existing) {
    existing.destroy();
  }
  renderingEngine = null;
  // toolgroup 销毁
  if (toolGroup) {
    try {
      toolGroup.destroy?.();
    } catch {
      /* ignore */
    }
    toolGroup = null;
  }
}

onMounted(async () => {
  await nextTick();
  await loadStudy();
});

onBeforeUnmount(() => {
  destroyEngine();
});

// studyId 变化时重新加载
watch(
  () => props.studyId,
  (val) => {
    if (val) loadStudy();
  },
);
</script>

<style scoped>
.dicom-viewer {
  display: flex;
  width: 100%;
  height: 100%;
  background: #0a0a0a;
  color: #e0e0e0;
  overflow: hidden;
}

/* 左侧序列栏 */
.viewer-sidebar {
  width: 220px;
  flex-shrink: 0;
  background: #1a1a1a;
  border-right: 1px solid #333;
  overflow-y: auto;
  padding: 8px;
}
.sidebar-title {
  font-size: 13px;
  color: #909399;
  padding: 4px 8px 10px;
  border-bottom: 1px solid #2a2a2a;
  margin-bottom: 8px;
}
.series-item {
  padding: 10px 8px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s;
  margin-bottom: 4px;
}
.series-item:hover {
  background: #2a2a2a;
}
.series-item.active {
  background: #2d4a7a;
}
.series-desc {
  font-size: 13px;
  margin-bottom: 6px;
  word-break: break-all;
}
.series-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #a0a0a0;
  flex-wrap: wrap;
}

/* 中间主区 */
.viewer-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

/* viewport 容器：必须有显式高度，否则 canvas 黑屏 */
.viewport-container {
  flex: 1;
  position: relative;
  min-height: 0;
  background: #000;
}

/* 四角叠层信息 */
.viewport-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
  color: #ffe082;
  font-size: 12px;
  text-shadow: 0 0 3px #000;
  line-height: 1.5;
}
.overlay-tl {
  position: absolute;
  top: 8px;
  left: 10px;
}
.overlay-tr {
  position: absolute;
  top: 8px;
  right: 10px;
  text-align: right;
}
.overlay-bl {
  position: absolute;
  bottom: 8px;
  left: 10px;
}
.overlay-br {
  position: absolute;
  bottom: 8px;
  right: 10px;
  text-align: right;
}

/* 工具栏 */
.viewer-toolbar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  padding: 8px 12px;
  background: #1a1a1a;
  border-top: 1px solid #333;
}
.toolbar-group {
  display: flex;
  align-items: center;
  gap: 4px;
}
.group-label {
  font-size: 12px;
  color: #909399;
  margin-right: 2px;
  white-space: nowrap;
}
.toolbar-divider {
  width: 1px;
  height: 20px;
  background: #333;
  margin: 0 6px;
}

/* element-plus 按钮在深色背景下保持可读 */
.viewer-toolbar :deep(.el-button) {
  margin-left: 0;
}
</style>
