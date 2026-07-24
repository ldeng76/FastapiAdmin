<!--
  DictTag —— 字典值 → 带颜色 Tag 显示。

  消费 dict.store 里已缓存的字典项，按 dict_value 查 dict_label，
  并把 list_class 映射到 el-tag 的 type，css_class 作为附加 class。

  - 单值：<DictTag type="sys_notice_type" :value="row.notice_type" />
  - 多值：value="1,2" → 渲染多个 Tag
  - 空值/未匹配：回退显示原值或 "—"

  @see docs/dict-value-label-display-design.md
-->
<template>
  <span v-if="values.length" class="fa-dict-tag">
    <template v-for="entry in valueItems" :key="entry.value">
      <ElTag v-if="entry.item" :type="tagType(entry.item)" :class="entry.item.css_class">
        {{ entry.item.dict_label }}
      </ElTag>
      <span v-else class="fa-dict-tag__fallback">{{ entry.value || "—" }}</span>
      <span v-if="entry.index < valueItems.length - 1" class="fa-dict-tag__sep">,</span>
    </template>
  </span>
  <span v-else class="fa-dict-tag__fallback">—</span>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useDict } from "@/hooks/core/useDict";
import type { DictDataTable } from "@/api/module_system/dict";

defineOptions({ name: "FaDictTag", inheritAttrs: false });

interface Props {
  /** 字典类型，如 "sys_notice_type" */
  type: string;
  /** 字典值，支持逗号多值 "1,2"；null/undefined/"" 显示 "—" */
  value?: string | null;
}

const props = defineProps<Props>();

// 声明字典依赖，按需拉取并缓存
const { item } = useDict(props.type);

/** 拆分多值（DB 约定逗号串） */
const values = computed<string[]>(() => {
  if (props.value === null || props.value === undefined || props.value === "") return [];
  return String(props.value)
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s !== "");
});

const valueItems = computed(() =>
  values.value.map((value, index) => ({ value, index, item: item(props.type, value) })),
);

/** list_class 取值即 el-tag type 枚举，非法值回退 undefined（默认色） */
function tagType(row: DictDataTable | undefined) {
  const t = row?.list_class;
  return ["primary", "success", "warning", "danger", "info"].includes(t as string)
    ? (t as "primary" | "success" | "warning" | "danger" | "info")
    : undefined;
}
</script>

<style scoped lang="scss">
.fa-dict-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;

  &__fallback {
    color: var(--el-text-color-secondary);
  }

  &__sep {
    color: var(--el-text-color-secondary);
  }
}
</style>
