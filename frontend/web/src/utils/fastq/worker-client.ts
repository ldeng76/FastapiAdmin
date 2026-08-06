/**
 * FASTQ 解析 Worker 客户端封装
 * 暴露 useFastqParser() 供 Vue 组件组合式调用
 */
import { ref, onBeforeUnmount } from "vue";
import type { ParseOptions, ParseResult } from "./types";
import FastqWorker from "@/workers/fastq-parser.worker?worker";

/** 解析 worker 状态 */
export type ParserStatus = "idle" | "running" | "success" | "error";

export interface UseFastqParser {
  parse: (text: string, opts?: ParseOptions) => Promise<ParseResult>;
  status: ReturnType<typeof ref<ParserStatus>>;
  result: ReturnType<typeof ref<ParseResult | null>>;
  error: ReturnType<typeof ref<string | null>>;
  terminate: () => void;
}

/**
 * 在 Worker 中解析 FASTQ 文本。
 * 用法：
 *   const { parse, status, result, error, terminate } = useFastqParser();
 *   onBeforeUnmount(terminate);
 *   await parse(text);
 */
export function useFastqParser(): UseFastqParser {
  // 懒创建：首次 parse() 时再 new Worker
  let worker: Worker | null = null;
  const status = ref<ParserStatus>("idle");
  const result = ref<ParseResult | null>(null);
  const error = ref<string | null>(null);

  function ensureWorker(): Worker {
    if (!worker) worker = new FastqWorker();
    return worker;
  }

  function parse(text: string, opts?: ParseOptions): Promise<ParseResult> {
    return new Promise((resolve, reject) => {
      const w = ensureWorker();
      status.value = "running";
      error.value = null;
      const onMessage = (e: MessageEvent) => {
        w.removeEventListener("message", onMessage);
        const { ok, result: r, error: errMsg } = e.data || {};
        if (ok) {
          result.value = r;
          status.value = "success";
          resolve(r);
        } else {
          error.value = errMsg;
          status.value = "error";
          reject(new Error(errMsg));
        }
      };
      const onError = (ev: ErrorEvent) => {
        w.removeEventListener("message", onMessage);
        w.removeEventListener("error", onError);
        error.value = ev.message;
        status.value = "error";
        reject(new Error(ev.message));
      };
      w.addEventListener("message", onMessage, { once: true });
      w.addEventListener("error", onError, { once: true });
      w.postMessage({ text, opts });
    });
  }

  function terminate() {
    if (worker) {
      worker.terminate();
      worker = null;
      status.value = "idle";
    }
  }

  // 默认在调用方组件 unmount 时自动清理（组合式 API 友好）
  onBeforeUnmount(terminate);

  return { parse, status, result, error, terminate };
}
