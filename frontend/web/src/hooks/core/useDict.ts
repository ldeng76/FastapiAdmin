/**
 * useDict —— 字典 value↔label 翻译的统一入口。
 *
 * 在 `dict.store.ts`（缓存 + localStorage 持久化）之上的薄封装，
 * 收敛三种显示场景：表单下拉 options、表格列 formatter、详情/Tag。
 *
 * ## 主要功能
 *
 * - `label(type, value)`：value → label 纯文本，支持逗号多值，空值显示 "—"
 * - `item(type, value)`：value → 完整字典项（给 DictTag 取 list_class / css_class）
 * - `options(type)`：直接喂 `el-select` 的 options 数组
 *
 * ## 用法
 *
 * ```ts
 * const { label, options } = useDict("sys_notice_type");
 * // 表格 formatter
 * formatter: (row) => label("sys_notice_type", row.notice_type)
 * // 表单下拉
 * <el-option v-for="d in options('sys_notice_type')" ... />
 * ```
 *
 * @module useDict
 * @see docs/dict-value-label-display-design.md
 */
import { useDictStoreHook } from "@/store/modules/dict.store";
import type { DictDataTable } from "@/api/module_system/dict";

/** 多值分隔符：DB 约定逗号串存多选，如 "1,2" */
const MULTI_VALUE_SEP = ",";

export function useDict(...types: string[]) {
  const store = useDictStoreHook();

  // 进入页面时按需拉取（store 内部已去重 + localStorage 持久化）
  if (types.length > 0) {
    store.getDict(types).catch((error: unknown) => {
      // 拉取失败不阻塞渲染，但开发环境保留上下文，便于定位接口或权限问题
      if (import.meta.env.DEV) {
        console.warn("[useDict] failed to load dictionary", { types, error });
      }
    });
  }

  /**
   * value → label（纯文本）
   * - 空值 → "—"
   * - 多值 "1,2" → "标签1,标签2"
   * - 未匹配 → 回退原 value（调试可见）
   */
  function label(type: string, value: string | null | undefined): string {
    if (value === null || value === undefined || value === "") return "—";
    const v = String(value);
    const lookup = (seg: string): string => findItem(type, seg)?.dict_label ?? seg;
    if (v.includes(MULTI_VALUE_SEP)) {
      return v
        .split(MULTI_VALUE_SEP)
        .map((seg) => lookup(seg.trim()))
        .join(MULTI_VALUE_SEP);
    }
    return lookup(v);
  }

  /** value → 完整字典项（找不到返回 undefined） */
  function item(type: string, value: string | null | undefined): DictDataTable | undefined {
    if (value === null || value === undefined || value === "") return undefined;
    return findItem(type, String(value));
  }

  /** 按 dict_value 精确查找字典项（不经过 store.getDictLabel 的 union 返回） */
  function findItem(type: string, value: string): DictDataTable | undefined {
    return store.dictData[type]?.find((d) => d.dict_value === value);
  }

  /** 给 el-select 直接用：[{dict_value, dict_label}] */
  function options(type: string): Array<{ dict_value: string; dict_label: string }> {
    return store.getDictArray(type);
  }

  return { label, item, options };
}
