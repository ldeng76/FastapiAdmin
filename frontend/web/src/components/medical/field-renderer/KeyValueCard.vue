<!--
  业务渲染：dict → 分层卡片（病史 / 病案首页 / 人口学 等）。
  - 一级 key 是 dict → 子项网格（嵌套层）
  - 一级 key 是数组 → 简短摘要 + 兜底走 FaJsonPretty
  - 一级 key 是长字符串 → 自动折叠 + 展开/收起按钮
-->
<template>
  <div class="json-biz-card kv-card">
    <div v-if="showTitle" class="json-biz-title">{{ schema.title }}</div>

    <div v-if="entries.length === 0" class="kv-empty">无内容</div>

    <div
      v-for="(item, idx) in entries"
      :key="idx"
      class="kv-block"
      :class="{ 'kv-nested': item.kind === 'nested' }"
    >
      <div class="kv-label">{{ item.label }}</div>
      <div class="kv-value">
        <!-- 嵌套 dict → 子层网格 -->
        <div v-if="item.kind === 'nested'" class="kv-subgrid">
          <div
            v-for="(sub, j) in item.children"
            :key="j"
            class="kv-subitem"
          >
            <span class="kv-sublabel">{{ sub.label }}</span>
            <span class="kv-subvalue">{{ sub.value }}</span>
          </div>
        </div>

        <!-- 数组 → 简短摘要 + 兜底 JSON 折叠 -->
        <div v-else-if="item.kind === 'array'" class="kv-array">
          <span class="kv-array-summary">{{ item.summary }}</span>
          <FaJsonPretty
            :value="item.raw as string | number | boolean | Record<string, unknown> | unknown[]"
            height="160px"
          />
        </div>

        <!-- 长文本 → 折叠展示 -->
        <div v-else-if="item.kind === 'long-text'" class="kv-longtext">
          <div class="kv-text" :class="{ collapsed: !item.expanded }">
            {{ item.value }}
          </div>
          <button class="kv-toggle" type="button" @click="toggle(idx)">
            {{ item.expanded ? "收起" : "展开" }}
          </button>
        </div>

        <!-- 普通文本 -->
        <span v-else>{{ item.value }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import FaJsonPretty from "@/components/others/fa-json-pretty/index.vue";
import { getFieldLabel } from "./field-labels";
import type { KvSchema } from "./field-schemas";

defineOptions({ name: "KeyValueCard" });

const props = withDefaults(
  defineProps<{
    data: Record<string, unknown>;
    schema: KvSchema;
    /** 是否显示卡片标题；由 FieldRenderer.showTitle 透传 */
    showTitle?: boolean;
  }>(),
  { showTitle: true },
);

/** 长文本阈值：超过则启用展开/收起按钮 */
const LONG_THRESHOLD = (): number => props.schema.longTextThreshold ?? 120;

/** 单个条目 */
type Entry =
  | { kind: "scalar"; label: string; value: string }
  | { kind: "long-text"; label: string; value: string; expanded: boolean }
  | { kind: "nested"; label: string; children: { label: string; value: string }[] }
  | { kind: "array"; label: string; summary: string; raw: unknown };

/** 顶层顺序：先按 schema.labelMap 的顺序，未声明的 key 追加在末尾 */
const orderedKeys = computed(() => {
  const known = Object.keys(props.schema.labelMap ?? {});
  const unknown = Object.keys(props.data).filter((k) => !known.includes(k));
  return [...known, ...unknown];
});

const entries = computed<Entry[]>(() => {
  const map = props.schema.labelMap ?? {};
  const out: Entry[] = [];
  for (const key of orderedKeys.value) {
    const raw = props.data[key];
    if (raw === null || raw === undefined || raw === "") continue;
    const label = map[key] ?? getFieldLabel(key);

    if (Array.isArray(raw)) {
      const summary = `${raw.length} 条`;
      out.push({ kind: "array", label, summary, raw });
      continue;
    }

    if (typeof raw === "object") {
      // 嵌套 dict → 子层网格（仅展示一层）
      const children: { label: string; value: string }[] = [];
      for (const [ck, cv] of Object.entries(raw as Record<string, unknown>)) {
        if (cv === null || cv === undefined || cv === "") continue;
        if (typeof cv === "object") continue; // 嵌套太深交给 FaJsonPretty
        children.push({ label: getFieldLabel(ck), value: scalarText(cv) });
      }
      if (children.length === 0) continue;
      out.push({ kind: "nested", label, children });
      continue;
    }

    const text = scalarText(raw);
    if (text.length > LONG_THRESHOLD()) {
      out.push({ kind: "long-text", label, value: text, expanded: false });
    } else {
      out.push({ kind: "scalar", label, value: text });
    }
  }
  return out;
});

function scalarText(v: unknown): string {
  if (v === true) return "是";
  if (v === false) return "否";
  return String(v);
}

/** 切换长文本展开/收起（就地修改 entries[idx]，触发响应式） */
function toggle(idx: number): void {
  const item = entries.value[idx];
  if (item.kind === "long-text") {
    item.expanded = !item.expanded;
  }
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
.kv-empty {
  color: var(--el-text-color-placeholder);
  font-size: 13px;
  padding: 8px 0;
}
.kv-block {
  display: grid;
  /* 130px 给"数据来源/现病史/既往史"等 4 字 label 留足；
     minmax(0, 1fr) 防止 value 被长文本撑爆（grid 子项默认 min-content 会让容器溢出） */
  grid-template-columns: 130px minmax(0, 1fr);
  gap: 8px 12px;
  padding: 6px 0;
  border-bottom: 1px dashed var(--el-border-color-lighter);
  font-size: 13px;
  align-items: start;
}
.kv-block:last-child {
  border-bottom: none;
}
.kv-block.kv-nested {
  grid-template-columns: 130px minmax(0, 1fr);
}
.kv-label {
  color: var(--el-text-color-regular);
  font-weight: 500;
}
.kv-value {
  color: var(--el-text-color-primary);
  word-break: break-word;
}
.kv-subgrid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 4px 16px;
  padding: 4px 8px;
  background-color: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
}
.kv-subitem {
  display: flex;
  gap: 6px;
  font-size: 12px;
}
.kv-sublabel {
  color: var(--el-text-color-regular);
  flex-shrink: 0;
}
.kv-sublabel::after {
  content: "：";
  color: var(--el-text-color-placeholder);
}
.kv-subvalue {
  color: var(--el-text-color-primary);
}
.kv-longtext {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.kv-text {
  white-space: pre-wrap;
  line-height: 1.6;
}
.kv-text.collapsed {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}
.kv-toggle {
  align-self: flex-start;
  background: none;
  border: none;
  padding: 0;
  color: var(--el-color-primary);
  font-size: 12px;
  cursor: pointer;
}
.kv-toggle:hover {
  text-decoration: underline;
}
.kv-array {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.kv-array-summary {
  font-size: 12px;
  color: var(--el-text-color-regular);
}
</style>
