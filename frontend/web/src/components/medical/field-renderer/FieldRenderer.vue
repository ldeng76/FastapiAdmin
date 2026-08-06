<!--
  字段渲染调度器：按 keyName 选业务渲染策略，未命中走兜底。
  - schema.type === 'table' → DiagnosesTableCard
  - schema.type === 'kv'    → KeyValueCard
  - object/array 未声明 schema → FaJsonPretty（折叠 JSON 树）
  - 空数组 / 空 dict → emptyHint 灰色提示
  - 标量 / null / 空 → 普通文本
-->
<template>
  <!-- 空数组 → 兜底提示 -->
  <span
    v-if="Array.isArray(value) && value.length === 0"
    class="field-empty"
  >
    {{ emptyHint }}
  </span>
  <!-- 空 dict → 兜底提示 -->
  <span
    v-else-if="isEmptyPlainObject(value)"
    class="field-empty"
  >
    {{ emptyHint }}
  </span>
  <DiagnosesTableCard
    v-else-if="schema?.type === 'table' && Array.isArray(value)"
    :rows="value as Record<string, unknown>[]"
    :schema="schema"
    :show-title="showTitle"
    class="field-block"
  />
  <KeyValueCard
    v-else-if="schema?.type === 'kv' && isPlainObject(value)"
    :data="value as Record<string, unknown>"
    :schema="schema"
    :show-title="showTitle"
    class="field-block"
  />
  <FaJsonPretty
    v-else-if="isObjectOrArray"
    :value="value as string | number | boolean | Record<string, unknown> | unknown[]"
    height="240px"
    class="field-block"
  />
  <span v-else class="field-scalar">{{ formatScalar(value) }}</span>
</template>

<script setup lang="ts">
import { computed } from "vue";
import FaJsonPretty from "@/components/others/fa-json-pretty/index.vue";
import DiagnosesTableCard from "./DiagnosesTableCard.vue";
import KeyValueCard from "./KeyValueCard.vue";
import { getFieldSchema } from "./field-schemas";

defineOptions({ name: "FieldRenderer" });

const props = withDefaults(
  defineProps<{
    /** 字段 key（用于查业务 schema） */
    keyName: string;
    /** 字段值（任意类型） */
    value: unknown;
    /**
     * 是否显示卡片标题。
     * - true（默认）：独立 section 使用（顶部 extRows），保留"诊断 / 病史"等语义标题
     * - false：嵌在 ElDescriptionsItem 里调用时，DescriptionsItem label 已提供语义，避免双重标题
     */
    showTitle?: boolean;
    /** 空数组 / 空 dict 兜底提示文案 */
    emptyHint?: string;
  }>(),
  {
    showTitle: true,
    emptyHint: "暂无记录",
  },
);

const schema = computed(() => getFieldSchema(props.keyName));

const isObjectOrArray = computed(() => {
  const v = props.value;
  return v !== null && v !== undefined && typeof v === "object";
});

function isPlainObject(v: unknown): boolean {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

function isEmptyPlainObject(v: unknown): boolean {
  return (
    v !== null && typeof v === "object" && !Array.isArray(v) && Object.keys(v).length === 0
  );
}

/** 标量格式化（与原 detail.vue formatValue 标量分支一致） */
function formatScalar(v: unknown): string {
  if (v === null || v === undefined || v === "") return "-";
  if (typeof v === "boolean") return v ? "是" : "否";
  const s = String(v);
  return s.length > 200 ? `${s.slice(0, 200)}…（共 ${s.length} 字）` : s;
}
</script>

<style scoped>
/**
 * 表格 / KV 卡 / 折叠 JSON 树都是"独占整行"的渲染块，
 * 在 ElDescriptionsItem 的窄列里会撑爆旁列。这里强制块级 + 100% 宽，
 * 让调用方通过 :span="column" 把它放到整行上。
 */
.field-block {
  display: block;
  width: 100%;
  min-width: 0;
}
.field-scalar {
  color: var(--el-text-color-primary);
}
/**
 * 空数组 / 空 dict 的兜底提示。
 * 与 KeyValueCard.vue 的 .kv-empty 风格对齐：灰色 + 小字 + 8px 内边距。
 */
.field-empty {
  display: inline-block;
  color: var(--el-text-color-placeholder);
  font-size: 13px;
  padding: 8px 0;
}
</style>
