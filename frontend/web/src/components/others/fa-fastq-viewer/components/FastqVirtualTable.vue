<!-- FASTQ · 虚拟滚动表格（RecycleScroller） -->
<template>
  <div class="fastq-vt">
    <!-- 表头 -->
    <div class="fastq-vt-header">
      <div class="col col-idx">#</div>
      <div class="col col-id">Read ID</div>
      <div class="col col-len">长度</div>
      <div class="col col-q">Q30 / 平均</div>
      <div class="col col-pair">双端</div>
      <div class="col col-seq">序列预览（前 {{ PREVIEW_LEN }}bp）</div>
      <div class="col col-heat">质量</div>
    </div>

    <!-- 虚拟滚动列表 -->
    <RecycleScroller
      class="fastq-vt-scroller"
      :items="items"
      :item-size="ROW_H"
      key-field="idx"
      v-slot="{ item, index }"
    >
      <div class="fastq-row" @click="toggle(item.idx)">
        <div class="col col-idx">{{ index + 1 }}</div>
        <div class="col col-id" :title="item.rawHeader">{{ item.readId }}</div>
        <div class="col col-len">{{ item.length }}</div>
        <div class="col col-q">
          <span class="q30">{{ item.q30Pct.toFixed(0) }}%</span>
          <span class="avg">Q{{ item.avgQuality.toFixed(1) }}</span>
        </div>
        <div class="col col-pair">
          <FastqPairBadge :pair-end="item.pairEnd" />
        </div>
        <div class="col col-seq">
          <FastqBaseSpan
            v-for="(b, i) in previewSeq(item.sequence)"
            :key="i"
            :base="b"
            :quality="item.qualityScores[i]"
          />
          <span v-if="item.length > PREVIEW_LEN" class="ellipsis">…</span>
        </div>
        <div class="col col-heat">
          <FastqQualityHeatBar :scores="item.qualityScores" :compact="true" />
        </div>
      </div>
      <FastqExpandedPanel v-if="expanded.has(item.idx)" :record="item" />
    </RecycleScroller>
  </div>
</template>

<script setup lang="ts">
/**
 * 虚拟滚动表格：
 * - 表头 36px + 行 44px
 * - 行点击展开/收起 FastqExpandedPanel
 * - 序列预览仅前 50bp（每个 span），控制 DOM 节点数
 * - 质量列用 FastqQualityHeatBar（compact 模式）
 */
import { ref } from "vue";
import { RecycleScroller } from "vue-virtual-scroller";
import "vue-virtual-scroller/dist/vue-virtual-scroller.css";
import type { FastqRecord } from "@/utils/fastq/types";
import { PREVIEW_LEN } from "../constants/colors";
import FastqBaseSpan from "./FastqBaseSpan.vue";
import FastqQualityHeatBar from "./FastqQualityHeatBar.vue";
import FastqPairBadge from "./FastqPairBadge.vue";
import FastqExpandedPanel from "./FastqExpandedPanel.vue";

defineProps<{ items: FastqRecord[] }>();

const ROW_H = 44;
const expanded = ref(new Set<number>());

function toggle(idx: number) {
  if (expanded.value.has(idx)) expanded.value.delete(idx);
  else expanded.value.add(idx);
  // 触发响应式（Set 需要重新赋值才被检测）
  expanded.value = new Set(expanded.value);
}

function previewSeq(seq: string): string {
  return seq.length > PREVIEW_LEN ? seq.slice(0, PREVIEW_LEN) : seq;
}
</script>

<style scoped>
.fastq-vt {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  background: var(--el-fill-color-blank);
  overflow: hidden;
}
.fastq-vt-header,
.fastq-row {
  display: grid;
  grid-template-columns:
    50px /* idx */
    1.4fr /* id */
    80px /* len */
    110px /* q */
    80px /* pair */
    2fr /* seq */
    120px; /* heat */
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  font-size: 12px;
}
.fastq-vt-header {
  height: 36px;
  background: var(--el-fill-color-light);
  font-weight: 600;
  color: var(--el-text-color-regular);
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.fastq-vt-scroller {
  height: 60vh;
}
.fastq-row {
  height: 44px;
  border-bottom: 1px solid var(--el-border-color-extra-light);
  cursor: pointer;
  transition: background 0.15s;
  overflow: hidden;
}
.fastq-row:hover {
  background: var(--el-fill-color-light);
}
.col {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.col-id {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}
.col-q {
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}
.col-q .q30 {
  color: #2e8b57;
  font-weight: 600;
}
.col-q .avg {
  color: var(--el-text-color-secondary);
  font-size: 10px;
}
.col-seq {
  font-family: ui-monospace, monospace;
  overflow: hidden;
}
.ellipsis {
  color: var(--el-text-color-secondary);
  margin-left: 2px;
}
</style>
