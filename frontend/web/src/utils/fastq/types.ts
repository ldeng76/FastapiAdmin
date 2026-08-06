/**
 * FASTQ 结构化展示 · 类型定义
 * 依据 docs/adr/FASTQ 结构化展示初稿.md §4.2/§4.3/§4.4 描述
 */

/** 碱基类型（只识别 A/T/C/G/N，其它字符按 N 处理） */
export type FastqBase = "A" | "T" | "C" | "G" | "N";

/** 双端标识：1 = R1, 2 = R2, 0 = 单端或未知 */
export type FastqPairEnd = 0 | 1 | 2;

/** 单条 read 解析结果 */
export interface FastqRecord {
  /** 唯一索引（在 records 数组中的下标，便于 key-field） */
  idx: number;
  /** 原始 header（去掉开头的 @） */
  rawHeader: string;
  /** Read ID（rawHeader 第一段，空格分隔） */
  readId: string;
  /** 碱基序列 */
  sequence: string;
  /** 原始质量字符串 */
  qualityString: string;
  /** 转换后的质量分数数组（Phred+33） */
  qualityScores: number[];
  /** 序列长度 */
  length: number;
  /** 双端标识 */
  pairEnd: FastqPairEnd;
  /** 双端配对键（1:N:0:/2:N:0: 替换为 PAIR: 占位符后的字符串） */
  pairKey: string;
  // ── 派生字段（解析阶段一次性算好，渲染直接用） ──
  /** 平均质量分（NaN 表示 qualityScores 为空） */
  avgQuality: number;
  /** Q≥20 占比（0~100） */
  q20Pct: number;
  /** Q≥30 占比（0~100） */
  q30Pct: number;
  /** 异常质量分（负数 或 > 93）的数量 */
  abnormalQualityCount: number;
}

/** 解析错误 */
export interface FastqParseError {
  /** 4 行组在原文中的起始行号（1-based） */
  lineNo: number;
  /** 错误原因 */
  reason: string;
  /** 涉及到的原始文本（≤ 200 字，超出截断） */
  raw: string;
}

/** 解析统计 */
export interface FastqStats {
  /** 成功解析的 read 数 */
  total: number;
  /** 双端对数（pairKey 相同 + pairEnd 同时存在 1 和 2 的对数） */
  pairCount: number;
  /** 单端 read 数（pairEnd === 0） */
  singletons: number;
  /** 平均 read 长度 */
  avgReadLen: number;
  /** 错误数 */
  errorCount: number;
  /** 解析耗时（ms） */
  elapsedMs: number;
}

/** 解析结果 */
export interface ParseResult {
  records: FastqRecord[];
  errors: FastqParseError[];
  stats: FastqStats;
}

/** 解析选项 */
export interface ParseOptions {
  /** Phred 偏移量，默认 33（Sanger/Phred+33） */
  phredOffset?: number;
  /** 最大解析记录数（超过则截断并标记 truncated），默认 Infinity */
  maxRecords?: number;
  /** 单次扫描的最大行数（防止异常大文件），默认 4_000_000 */
  maxLines?: number;
}

/** 排序键 */
export type FastqSortKey = "id" | "length" | "avgQuality" | "pairKey";

/** 视图模式 */
export type FastqViewMode = "structured" | "raw";

/** 配对过滤 */
export type FastqPairFilter = "all" | "singleton" | "r1" | "r2";
