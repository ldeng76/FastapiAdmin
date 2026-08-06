/**
 * 医学模块字段渲染器：统一导出。
 *
 * 用法：
 *   import FieldRenderer from "@/components/medical/field-renderer";
 *   <FieldRenderer key-name="diagnoses" :value="row.diagnoses" />
 */

export { default as FieldRenderer } from "./FieldRenderer.vue";
export { FIELD_SCHEMAS, getFieldSchema } from "./field-schemas";
export { FIELD_LABELS, getFieldLabel } from "./field-labels";
export type { FieldSchema, TableSchema, KvSchema, TableColumn } from "./field-schemas";

import FieldRenderer from "./FieldRenderer.vue";
export default FieldRenderer;
