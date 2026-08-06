/**
 * FASTQ Viewer · 颜色与阈值常量
 * 依据 docs/adr/FASTQ 结构化展示初稿.md §5.2/§5.3
 */

/** 碱基配色（与文档 §5.2 一致） */
export const BASE_COLOR: Record<string, string> = {
  A: "#2E8B57", // 绿
  T: "#DC143C", // 红
  C: "#1E90FF", // 蓝
  G: "#FF8C00", // 橙
  N: "#808080", // 灰
  default: "#808080",
};

/** 质量分档位背景色（带 0.35 透明度） */
export function qualityBg(q: number): string {
  if (q >= 30) return "rgba(46, 139, 87, 0.35)"; // 绿
  if (q >= 20) return "rgba(255, 215, 0, 0.35)"; // 黄
  return "rgba(220, 20, 60, 0.35)"; // 红
}

/** 质量分档位纯色（用于标签/边框） */
export const QUALITY_TIER_COLOR: Record<"high" | "mid" | "low", string> = {
  high: "#2E8B57",
  mid: "#DAA520",
  low: "#DC143C",
};

/** 质量分档位（按 Q 分） */
export type QualityTier = "high" | "mid" | "low";
export function qualityTier(q: number): QualityTier {
  if (q >= 30) return "high";
  if (q >= 20) return "mid";
  return "low";
}

/** 配对标识色（按 pairKey HSL 分配） */
export function pairKeyColor(key: string): string {
  // 简易 hash → hue
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) | 0;
  const hue = Math.abs(h) % 360;
  return `hsl(${hue}, 70%, 45%)`;
}

/** 序列预览默认长度（碱基数） */
export const PREVIEW_LEN = 50;

/** 展开行内碱基渲染阈值（超过则切到 Canvas） */
export const EXPAND_CANVAS_THRESHOLD = 5000;
