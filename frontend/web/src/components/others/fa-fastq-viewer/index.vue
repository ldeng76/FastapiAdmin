<!-- FASTQ · 结构化展示 Viewer（主入口） -->
<template>
  <div class="fa-fastq-viewer">
    <ElCollapse v-model="activePanels">
      <ElCollapseItem title="导入 FASTQ 文本" name="upload">
        <FastqUploadPanel @parsed="onParsed" @load-sample="onLoadSample" />
      </ElCollapseItem>
    </ElCollapse>

    <ElAlert
      v-if="parseError"
      :title="`解析失败：${parseError}`"
      type="error"
      :closable="false"
      show-icon
      class="mt-8"
    />

    <ElAlert
      v-else-if="parseResult && parseResult.errors.length > 0"
      :title="`解析完成，${parseResult.records.length} 条成功，${parseResult.errors.length} 条因格式错误已跳过`"
      type="warning"
      :closable="true"
      show-icon
      class="mt-8"
      @close="dismissed = true"
    />

    <template v-if="parseResult && parseResult.records.length">
      <FastqToolbar
        v-model:search="search"
        v-model:viewMode="viewMode"
        v-model:sortBy="sortBy"
        v-model:pairFilter="pairFilter"
        v-model:minAvgQuality="minAvgQuality"
        :stats="parseResult.stats"
        class="mt-8"
      />

      <ElEmpty v-if="filteredRecords.length === 0" description="未找到匹配的 FASTQ 记录" />
      <FastqVirtualTable v-else-if="viewMode === 'structured'" :items="filteredRecords" />
      <FastqRawView v-else :text="rawText" />
    </template>
    <ElEmpty
      v-else-if="!loading"
      description="请上传或粘贴 FASTQ 文本以开始解析"
      class="mt-12"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * FASTQ Viewer 主入口。
 * - 接收无 prop，自管所有状态
 * - 解析走 Web Worker（utils/fastq/worker-client.ts）
 * - 搜索/排序/过滤在客户端完成
 * - 集成测试：见 utils/fastq/__tests__/parser.spec.ts
 */
import { ref, computed, watch } from "vue";
import { ElCollapse, ElCollapseItem, ElAlert, ElEmpty, ElMessage } from "element-plus";
import { useFastqParser } from "@/utils/fastq/worker-client";
import type {
  FastqPairFilter,
  FastqRecord,
  FastqSortKey,
  FastqViewMode,
  ParseResult,
} from "@/utils/fastq/types";
import FastqUploadPanel from "./components/FastqUploadPanel.vue";
import FastqToolbar from "./components/FastqToolbar.vue";
import FastqVirtualTable from "./components/FastqVirtualTable.vue";
import FastqRawView from "./components/FastqRawView.vue";

defineOptions({ name: "FaFastqViewer", inheritAttrs: false });

const activePanels = ref<string[]>(["upload"]);
const rawText = ref("");
const parseResult = ref<ParseResult | null>(null);
const parseError = ref<string | null>(null);
const loading = ref(false);
const dismissed = ref(false);

// 视图/过滤状态
const search = ref("");
const viewMode = ref<FastqViewMode>("structured");
const sortBy = ref<FastqSortKey>("id");
const pairFilter = ref<FastqPairFilter>("all");
const minAvgQuality = ref(0);

const { parse } = useFastqParser();

async function onParsed(text: string) {
  rawText.value = text;
  parseError.value = null;
  dismissed.value = false;
  loading.value = true;
  try {
    // 性能预警：> 50 万行
    const lineCount = (text.match(/\n/g) || []).length;
    if (lineCount > 500_000) {
      ElMessage.warning(`输入包含 ${lineCount} 行，可能影响解析与渲染性能`);
    }
    const r = await parse(text);
    parseResult.value = r;
    if (r.records.length === 0) {
      ElMessage.warning("未解析出任何有效 read，请检查格式");
    } else {
      ElMessage.success(
        `解析完成：${r.records.length} 条 / ${r.errors.length} 错误 / ${r.stats.elapsedMs.toFixed(0)}ms`,
      );
    }
  } catch (err: any) {
    parseError.value = err?.message ?? String(err);
  } finally {
    loading.value = false;
  }
}

function onLoadSample() {
  // 3 条 read：1 对双端 + 1 单端（与 parser.spec.ts fixture 一致）
  const seq = "GATTTGGGGTTCAAAGCAGTATCGATCAAATAGTAAATCCATTTGTTCAACTCACAGTTT";
  const qual = "I".repeat(60);
  const r3seq = "ACGT".repeat(15);
  const sample = [
    `@A00582:907:H7255DSX3:1:1101:8196:1063 1:N:0:TAAGGCGA`,
    seq,
    `+`,
    qual,
    `@A00582:907:H7255DSX3:1:1101:8196:1063 2:N:0:TAAGGCGA`,
    seq,
    `+`,
    qual,
    `@A00582:907:H7255DSX3:1:1101:8196:9999`,
    r3seq,
    `+`,
    "I".repeat(r3seq.length),
  ].join("\n");
  onParsed(sample);
}

// 过滤 + 排序
const filteredRecords = computed<FastqRecord[]>(() => {
  const r = parseResult.value?.records ?? [];
  if (r.length === 0) return [];
  const q = search.value.trim();
  const minQ = minAvgQuality.value;
  const pf = pairFilter.value;
  const sb = sortBy.value;
  const filtered: FastqRecord[] = [];
  for (let i = 0; i < r.length; i++) {
    const rec = r[i];
    if (minQ > 0 && rec.avgQuality < minQ) continue;
    if (pf === "singleton" && rec.pairEnd !== 0) continue;
    if (pf === "r1" && rec.pairEnd !== 1) continue;
    if (pf === "r2" && rec.pairEnd !== 2) continue;
    if (q) {
      // 跨 readId / pairKey / sequence 任意子串命中
      if (
        rec.readId.indexOf(q) < 0 &&
        rec.pairKey.indexOf(q) < 0 &&
        rec.sequence.indexOf(q) < 0
      ) {
        continue;
      }
    }
    filtered.push(rec);
  }
  // 排序：先 pairKey（让 R1/R2 相邻），再 sortBy
  filtered.sort((a, b) => {
    const pk = a.pairKey < b.pairKey ? -1 : a.pairKey > b.pairKey ? 1 : 0;
    if (pk !== 0) return pk;
    switch (sb) {
      case "length":
        return a.length - b.length;
      case "avgQuality":
        return b.avgQuality - a.avgQuality;
      case "pairKey":
        return a.pairEnd - b.pairEnd;
      case "id":
      default:
        return a.readId < b.readId ? -1 : a.readId > b.readId ? 1 : 0;
    }
  });
  return filtered;
});

// 当 pairFilter 改变时自动重排
watch([pairFilter, sortBy], () => {
  // filteredRecords 是 computed，会自动重算
});
</script>

<style scoped>
.fa-fastq-viewer {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.mt-8 {
  margin-top: 8px;
}
.mt-12 {
  margin-top: 12px;
}
</style>
