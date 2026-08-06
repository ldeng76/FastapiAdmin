<!-- FASTQ · 展开行：全序列 + 质量热力 + 原始 header -->
<template>
  <div class="fastq-expanded">
    <ElDescriptions :column="3" border size="small">
      <ElDescriptionsItem label="Read ID">{{ record.readId }}</ElDescriptionsItem>
      <ElDescriptionsItem label="长度">{{ record.length }} bp</ElDescriptionsItem>
      <ElDescriptionsItem label="平均质量">Q{{ record.avgQuality.toFixed(1) }}</ElDescriptionsItem>
      <ElDescriptionsItem label="Q20 占比">{{ record.q20Pct.toFixed(1) }}%</ElDescriptionsItem>
      <ElDescriptionsItem label="Q30 占比">{{ record.q30Pct.toFixed(1) }}%</ElDescriptionsItem>
      <ElDescriptionsItem label="配对键">
        <span class="pair-key">{{ record.pairKey }}</span>
      </ElDescriptionsItem>
      <ElDescriptionsItem label="原始 header" :span="3">
        <span class="raw-header">{{ record.rawHeader }}</span>
      </ElDescriptionsItem>
    </ElDescriptions>

    <div class="fastq-expanded-block">
      <div class="label">质量热力（与序列一一对应）</div>
      <FastqQualityHeatBar :scores="record.qualityScores" :compact="false" />
    </div>

    <div class="fastq-expanded-block">
      <div class="label">完整序列（{{ record.length }} bp）</div>
      <!-- 短序列用 span；超长切 Canvas 防 DOM 爆炸 -->
      <div v-if="useCanvas" class="canvas-host">
        <canvas ref="canvasRef" :width="canvasWidth" :height="20" />
        <div class="hint">长序列使用 Canvas 渲染（共 {{ record.length }} bp）</div>
      </div>
      <div v-else class="seq-host" :aria-label="`sequence ${record.length}bp`">
        <FastqBaseSpan
          v-for="(b, i) in record.sequence"
          :key="i"
          :base="b"
          :quality="record.qualityScores[i]"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 展开行面板。
 * - < 5000 bp：每个碱基一个 span（带颜色 + 质量背景 + tooltip）
 * - ≥ 5000 bp：Canvas 绘制（fillText + fillStyle）
 */
import { computed, onMounted, ref, watch } from "vue";
import { ElDescriptions, ElDescriptionsItem } from "element-plus";
import type { FastqRecord } from "@/utils/fastq/types";
import { BASE_COLOR, EXPAND_CANVAS_THRESHOLD } from "../constants/colors";
import FastqBaseSpan from "./FastqBaseSpan.vue";
import FastqQualityHeatBar from "./FastqQualityHeatBar.vue";

const props = defineProps<{ record: FastqRecord }>();

const useCanvas = computed(() => props.record.length >= EXPAND_CANVAS_THRESHOLD);
const canvasRef = ref<HTMLCanvasElement | null>(null);
const canvasWidth = computed(() => Math.max(800, props.record.length * 7.2));

function drawCanvas() {
  if (!useCanvas.value) return;
  const cv = canvasRef.value;
  if (!cv) return;
  const ctx = cv.getContext("2d");
  if (!ctx) return;
  ctx.clearRect(0, 0, cv.width, cv.height);
  ctx.font = "12px ui-monospace, monospace";
  ctx.textBaseline = "middle";
  const seq = props.record.sequence;
  const scores = props.record.qualityScores;
  for (let i = 0; i < seq.length; i++) {
    const ch = seq[i].toUpperCase();
    const color = BASE_COLOR[ch] ?? BASE_COLOR.default;
    // 背景
    const q = scores[i];
    ctx.fillStyle =
      q >= 30 ? "rgba(46, 139, 87, 0.35)" : q >= 20 ? "rgba(255, 215, 0, 0.35)" : "rgba(220, 20, 60, 0.35)";
    ctx.fillRect(i * 7.2, 0, 7.2, 20);
    // 字符
    ctx.fillStyle = color;
    ctx.fillText(ch, i * 7.2 + 1, 10);
  }
}

onMounted(drawCanvas);
watch(
  () => props.record.idx,
  () => requestAnimationFrame(drawCanvas),
);
</script>

<style scoped>
.fastq-expanded {
  padding: 12px;
  background: var(--el-fill-color-light);
  border-top: 1px dashed var(--el-border-color-lighter);
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.fastq-expanded-block .label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}
.seq-host {
  font-family: ui-monospace, monospace;
  word-break: break-all;
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 8px;
  max-height: 320px;
  overflow: auto;
}
.canvas-host {
  background: var(--el-fill-color-blank);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 8px;
  overflow-x: auto;
}
.canvas-host .hint {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
.pair-key,
.raw-header {
  font-family: ui-monospace, monospace;
  font-size: 12px;
  word-break: break-all;
}
</style>
