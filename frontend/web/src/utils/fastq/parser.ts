/**
 * FASTQ 纯函数解析器
 * 依据 docs/adr/FASTQ 结构化展示初稿.md §4.1/§4.2/§4.3/§4.4
 *
 * 设计要点：
 * 1. 纯函数，无副作用（除 console.warn 用于异常质量分告警）
 * 2. 单次扫描，按 4 行一组处理，支持 \n 与 \r\n
 * 3. 校验失败 → 跳过该组 + 收集 error，不中断整体解析
 * 4. 派生字段（avgQuality/q20Pct/q30Pct）在解析阶段一次性算好
 * 5. 文件尾不足 4 行 → 作为 error 收集并终止
 */

import type {
  FastqPairEnd,
  FastqParseError,
  FastqRecord,
  FastqStats,
  ParseOptions,
  ParseResult,
} from "./types";

/** 推荐的 Phred+33 偏移量 */
const DEFAULT_PHRED_OFFSET = 33;

/** 单 read 异常质量上限（Phred+33 下 ASCII 最大 126，约 Q93） */
const ABNORMAL_QUALITY_MAX = 93;

/** 单 read 异常质量下限（负数视为异常） */
const ABNORMAL_QUALITY_MIN = 0;

/** 截断 raw error 文本长度 */
const ERROR_RAW_MAX = 200;

/**
 * 提取第一段作为 Read ID。
 * 依据 §4.5 验收：Read ID = rawHeader 第一段（按空格切分）。
 */
export function readIdOf(rawHeader: string): string {
  const sp = rawHeader.indexOf(" ");
  return sp >= 0 ? rawHeader.slice(0, sp) : rawHeader;
}

/**
 * 提取双端信息（pairEnd + pairKey）。
 * 依据 §4.4：
 * - 优先匹配 "1:N:0:" / "2:N:0:"（Illumina 经典格式）
 * - 回退匹配 " /1" / " /2"（legacy CASAVA 格式）
 * - pairKey = 将该模式替换为 "PAIR:" 后的 rawHeader
 */
export function pairKeyOf(rawHeader: string): { pairEnd: FastqPairEnd; pairKey: string } {
  let pairEnd: FastqPairEnd = 0;
  let pairKey = rawHeader;

  // Illumina 经典：包含 "1:N:0:" / "2:N:0:"
  // 用一个扫描同时识别并替换
  const illuminaR1 = rawHeader.includes("1:N:0:");
  const illuminaR2 = rawHeader.includes("2:N:0:");
  if (illuminaR1 && !illuminaR2) {
    pairEnd = 1;
    pairKey = rawHeader.replace("1:N:0:", "PAIR:");
  } else if (illuminaR2 && !illuminaR1) {
    pairEnd = 2;
    pairKey = rawHeader.replace("2:N:0:", "PAIR:");
  } else if (illuminaR1 && illuminaR2) {
    // 两个都出现：按第一次出现的类型设 pairEnd，再统一替换
    const idx1 = rawHeader.indexOf("1:N:0:");
    const idx2 = rawHeader.indexOf("2:N:0:");
    pairEnd = idx1 < idx2 ? 1 : 2;
    pairKey = rawHeader.replace(/[12]:N:0:/, "PAIR:");
  } else {
    // CASAVA legacy：末尾 "/1" 或 "/2"（可无前导空格）
    if (/\/1$/.test(rawHeader)) {
      pairEnd = 1;
      pairKey = rawHeader.replace(/\/1$/, "/PAIR:");
    } else if (/\/2$/.test(rawHeader)) {
      pairEnd = 2;
      pairKey = rawHeader.replace(/\/2$/, "/PAIR:");
    }
  }

  return { pairEnd, pairKey };
}

/**
 * 把一行质量字符串按 Phred 偏移转换为整数数组。
 * 异常值（< 0 或 > 93）保留原 ASCII 编码值。
 * 依据 §4.3。
 */
export function phredScores(qual: string, offset: number = DEFAULT_PHRED_OFFSET): number[] {
  const out: number[] = new Array(qual.length);
  for (let i = 0; i < qual.length; i++) {
    const code = qual.charCodeAt(i);
    out[i] = code - offset;
  }
  return out;
}

/**
 * 计算一组质量分对应的统计信息。
 * - avgQuality: 简单算术平均
 * - q20Pct: ≥ 20 的占比（0~100）
 * - q30Pct: ≥ 30 的占比（0~100）
 * - abnormalQualityCount: < 0 或 > 93 的数量
 *
 * 空数组 → 全为 0（不返回 NaN，避免下游排序/过滤出锅）。
 */
export function qualityStats(scores: number[]) {
  if (scores.length === 0) {
    return { avgQuality: 0, q20Pct: 0, q30Pct: 0, abnormalQualityCount: 0 };
  }
  let sum = 0;
  let q20 = 0;
  let q30 = 0;
  let abn = 0;
  for (let i = 0; i < scores.length; i++) {
    const s = scores[i];
    sum += s;
    if (s >= 20) q20++;
    if (s >= 30) q30++;
    if (s < ABNORMAL_QUALITY_MIN || s > ABNORMAL_QUALITY_MAX) abn++;
  }
  return {
    avgQuality: sum / scores.length,
    q20Pct: (q20 * 100) / scores.length,
    q30Pct: (q30 * 100) / scores.length,
    abnormalQualityCount: abn,
  };
}

/**
 * 校验 4 行组并解析为 FastqRecord。
 * 返回 { record, error? }：成功 record 有值；失败 error 有值。
 */
export function parseLineGroup(
  header: string,
  seq: string,
  plus: string,
  qual: string,
  idx: number,
  opts: ParseOptions = {},
): { record?: FastqRecord; error?: FastqParseError } {
  const offset = opts.phredOffset ?? DEFAULT_PHRED_OFFSET;

  if (!header.startsWith("@")) {
    return { error: { lineNo: 0, reason: "第 1 行必须以 @ 开头", raw: clip(header) } };
  }
  if (!plus.startsWith("+")) {
    return { error: { lineNo: 0, reason: "第 3 行必须以 + 开头", raw: clip(plus) } };
  }
  if (seq.length !== qual.length) {
    return {
      error: {
        lineNo: 0,
        reason: `序列长度(${seq.length})与质量字符串长度(${qual.length})不一致`,
        raw: clip(`${header}\n${seq}\n${plus}\n${qual}`),
      },
    };
  }
  if (seq.length === 0) {
    return { error: { lineNo: 0, reason: "空序列", raw: clip(seq) } };
  }

  const rawHeader = header.slice(1); // 去 @
  const qualityScores = phredScores(qual, offset);
  const stats = qualityStats(qualityScores);
  const { pairEnd, pairKey } = pairKeyOf(rawHeader);

  // 异常质量分告警（按 §4.3，保留原值不抛错）
  if (stats.abnormalQualityCount > 0) {
    // 单次解析中超过 50% 异常才 warn，避免 100k reads 日志风暴
    if (stats.abnormalQualityCount * 2 > seq.length) {
      console.warn(
        `[fastq-parser] read #${idx} header="${rawHeader}" 有 ${stats.abnormalQualityCount}/${seq.length} 个异常质量分`,
      );
    }
  }

  const record: FastqRecord = {
    idx,
    rawHeader,
    readId: readIdOf(rawHeader),
    sequence: seq,
    qualityString: qual,
    qualityScores,
    length: seq.length,
    pairEnd,
    pairKey,
    avgQuality: stats.avgQuality,
    q20Pct: stats.q20Pct,
    q30Pct: stats.q30Pct,
    abnormalQualityCount: stats.abnormalQualityCount,
  };
  return { record };
}

function clip(s: string): string {
  return s.length > ERROR_RAW_MAX ? `${s.slice(0, ERROR_RAW_MAX)}…` : s;
}

/**
 * 计算结果集的汇总统计。
 * - pairCount: pairKey 相同 + pairEnd 同时存在 1 和 2 的对数
 * - singletons: pairEnd === 0 的 read 数
 * - avgReadLen: 所有 read 长度的平均
 */
export function calcStats(records: FastqRecord[], errorCount: number, elapsedMs: number): FastqStats {
  if (records.length === 0) {
    return { total: 0, pairCount: 0, singletons: 0, avgReadLen: 0, errorCount, elapsedMs };
  }
  // 按 pairKey 分组，记录每组内出现过的 pairEnd 集合
  const groupEnds = new Map<string, Set<FastqPairEnd>>();
  let singletons = 0;
  let lenSum = 0;
  for (const r of records) {
    if (r.pairEnd === 0) singletons++;
    if (!groupEnds.has(r.pairKey)) groupEnds.set(r.pairKey, new Set());
    groupEnds.get(r.pairKey)!.add(r.pairEnd);
    lenSum += r.length;
  }
  let pairCount = 0;
  for (const ends of groupEnds.values()) {
    if (ends.has(1) && ends.has(2)) pairCount++;
  }
  return {
    total: records.length,
    pairCount,
    singletons,
    avgReadLen: lenSum / records.length,
    errorCount,
    elapsedMs,
  };
}

/**
 * 主入口：解析一整段 FASTQ 文本。
 * 性能：100k reads（4 行/条 ≈ 40 万行）应在 ~1s 内完成。
 */
export function parseFastq(text: string, opts: ParseOptions = {}): ParseResult {
  const t0 = performance.now();
  const maxRecords = opts.maxRecords ?? Infinity;
  const maxLines = opts.maxLines ?? 4_000_000;

  const records: FastqRecord[] = [];
  const errors: FastqParseError[] = [];

  // 按 \n 切，丢弃尾部 \r
  const lines = text.split(/\r?\n/);
  const total = lines.length;
  const limit = Math.min(total, maxLines);

  let i = 0;
  let idx = 0;
  // 跳过可能的前置空行（容错：很多测序文件结尾有空行）
  while (i < limit && lines[i] === "") i++;

  for (; i + 3 < limit + 1 && records.length < maxRecords; ) {
    // 4 行一组
    const startLine = i + 1; // 1-based
    const header = lines[i];
    const seq = lines[i + 1];
    const plus = lines[i + 2];
    const qual = lines[i + 3];

    // 4 行都为空 → 跳过整组
    if (header === "" && seq === "" && plus === "" && qual === "") {
      i += 4;
      continue;
    }

    const { record, error } = parseLineGroup(header, seq, plus, qual, idx, opts);
    if (record) {
      records.push(record);
      idx++;
    } else if (error) {
      errors.push({ ...error, lineNo: startLine });
    }
    i += 4;
  }

  // 检查尾部剩余行：若存在非空残留，说明文件不完整
  if (records.length < maxRecords) {
    for (let j = i; j < limit; j++) {
      if (lines[j] !== "") {
        errors.push({
          lineNo: j + 1,
          reason: "文件末尾残留不完整记录（不足 4 行）",
          raw: clip(lines[j]),
        });
        break;
      }
    }
  }

  // 截断提示
  if (maxRecords !== Infinity && records.length >= maxRecords && i + 4 <= limit) {
    errors.push({
      lineNo: 0,
      reason: `已达到 maxRecords=${maxRecords} 上限，后续记录已截断`,
      raw: "",
    });
  }

  const elapsedMs = performance.now() - t0;
  const stats = calcStats(records, errors.length, elapsedMs);
  return { records, errors, stats };
}
