/// <reference lib="webworker" />
/**
 * FASTQ 解析 Worker
 * 接收字符串文本 → postMessage ParseResult
 * Vite `?worker` 后缀导入后会得到 Worker 构造函数
 */

import { parseFastq } from "@/utils/fastq/parser";
import type { ParseOptions, ParseResult } from "@/utils/fastq/types";

// Worker 上下文
const ctx = self as unknown as DedicatedWorkerGlobalScope;

ctx.onmessage = (e: MessageEvent<{ text: string; opts?: ParseOptions }>) => {
  const { text, opts } = e.data || {};
  try {
    const result: ParseResult = parseFastq(text ?? "", opts);
    ctx.postMessage({ ok: true, result });
  } catch (err: any) {
    ctx.postMessage({ ok: false, error: err?.message ?? String(err) });
  }
};
