/**
 * FASTQ 解析器单测
 * 风格照搬 views/module_system/role/components/__tests__/FaPermissonDrawer.spec.ts
 * 纯逻辑测试，无 Vue 组件挂载
 */

import { describe, it, expect } from "vitest";
import {
  parseFastq,
  parseLineGroup,
  pairKeyOf,
  readIdOf,
  phredScores,
  qualityStats,
  calcStats,
} from "../parser";
import type { FastqRecord } from "../types";

// ---------------------------------------------------------------------------
// 测试夹具：3 条 record（含一对双端 + 一条单端）
// ⚠️ ADR §3 文档示例的 qualityString 长度(58) 与 sequence 长度(60) 不一致，
//    此处使用补齐后的 fixture（质量串 60 字符），保留 ADR 描述的 R1/R2/单端结构。
// ---------------------------------------------------------------------------

const SEQ_60 = "GATTTGGGGTTCAAAGCAGTATCGATCAAATAGTAAATCCATTTGTTCAACTCACAGTTT";
const QUAL_60 = "I".repeat(60); // 60 个 'I'，每位 Q40

const FIXTURE_3_RECORDS = `@A00582:907:H7255DSX3:1:1101:8196:1063 1:N:0:TAAGGCGA
${SEQ_60}
+
${QUAL_60}
@A00582:907:H7255DSX3:1:1101:8196:1063 2:N:0:TAAGGCGA
${SEQ_60}
+
${QUAL_60}
@A00582:907:H7255DSX3:1:1101:8196:9999
ACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGT
+
IIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIII`;

// ---------------------------------------------------------------------------
// 1. pairKeyOf / readIdOf：双端识别与 ID 提取
// ---------------------------------------------------------------------------

describe("pairKeyOf", () => {
  it("R1 头 → pairEnd=1 + pairKey 含 PAIR:", () => {
    const r = pairKeyOf("A00582:907:H7255DSX3:1:1101:8196:1063 1:N:0:TAAGGCGA");
    expect(r.pairEnd).toBe(1);
    expect(r.pairKey).toBe("A00582:907:H7255DSX3:1:1101:8196:1063 PAIR:TAAGGCGA");
  });

  it("R2 头 → pairEnd=2", () => {
    const r = pairKeyOf("A00582:907:H7255DSX3:1:1101:8196:1063 2:N:0:TAAGGCGA");
    expect(r.pairEnd).toBe(2);
    expect(r.pairKey).toBe("A00582:907:H7255DSX3:1:1101:8196:1063 PAIR:TAAGGCGA");
  });

  it("无 pairEnd 标识 → pairEnd=0，pairKey == rawHeader", () => {
    const r = pairKeyOf("A00582:907:H7255DSX3:1:1101:8196:9999");
    expect(r.pairEnd).toBe(0);
    expect(r.pairKey).toBe("A00582:907:H7255DSX3:1:1101:8196:9999");
  });

  it("CASAVA legacy 格式 '/1' / '/2'（无前导空格）", () => {
    const r1 = pairKeyOf("HWI-EAS:1:1:1:1#0/1");
    expect(r1.pairEnd).toBe(1);
    expect(r1.pairKey).toBe("HWI-EAS:1:1:1:1#0/PAIR:");
    const r2 = pairKeyOf("HWI-EAS:1:1:1:1#0/2");
    expect(r2.pairEnd).toBe(2);
  });

  it("同 R1/R2 → pairKey 相同（可配对）", () => {
    const a = pairKeyOf("A00582:907:H7255DSX3:1:1101:8196:1063 1:N:0:TAAGGCGA");
    const b = pairKeyOf("A00582:907:H7255DSX3:1:1101:8196:1063 2:N:0:TAAGGCGA");
    expect(a.pairKey).toBe(b.pairKey);
    expect(a.pairEnd).not.toBe(b.pairEnd);
  });
});

describe("readIdOf", () => {
  it("按空格切分取第一段", () => {
    expect(readIdOf("A00582:907:H7255DSX3:1:1101:8196:1063 1:N:0:TAAGGCGA")).toBe(
      "A00582:907:H7255DSX3:1:1101:8196:1063",
    );
  });
  it("无空格时整体返回", () => {
    expect(readIdOf("SINGLE_READ")).toBe("SINGLE_READ");
  });
});

// ---------------------------------------------------------------------------
// 2. phredScores / qualityStats：质量转换与统计
// ---------------------------------------------------------------------------

describe("phredScores", () => {
  it("Phred+33 转换正确（ASCII 'I'=73 → Q40）", () => {
    expect(phredScores("I")).toEqual([40]);
  });
  it("多个字符按 Phred+33 转换", () => {
    // 'F'=70 → Q37；'I'=73 → Q40
    expect(phredScores("FI")).toEqual([37, 40]);
  });
  it("支持逗号等非字母字符（文档 §3 注）", () => {
    // ','=44 → Q11
    expect(phredScores(",")).toEqual([11]);
  });
  it("异常值（>93）保留原 ASCII 分数（不抛错）", () => {
    // '~'=126 → Q93，正好边界；'}'=125 → Q92
    const scores = phredScores("~}");
    expect(scores[0]).toBe(93);
    expect(scores[1]).toBe(92);
  });
});

describe("qualityStats", () => {
  it("空数组 → 全 0", () => {
    expect(qualityStats([])).toEqual({
      avgQuality: 0,
      q20Pct: 0,
      q30Pct: 0,
      abnormalQualityCount: 0,
    });
  });
  it("avg / Q20 / Q30 / 异常计数", () => {
    // 4 个质量分: 5, 25, 35, 100（异常）；≥20 含 25/35/100 → 75%；≥30 含 35/100 → 50%
    const stats = qualityStats([5, 25, 35, 100]);
    expect(stats.avgQuality).toBeCloseTo(41.25, 2);
    expect(stats.q20Pct).toBeCloseTo(75, 5);
    expect(stats.q30Pct).toBeCloseTo(50, 5);
    expect(stats.abnormalQualityCount).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// 3. parseLineGroup：单组 4 行校验
// ---------------------------------------------------------------------------

describe("parseLineGroup", () => {
  it("正常 4 行 → record", () => {
    const r = parseLineGroup(
      "@A00582:907:H7255DSX3:1:1101:8196:1063 1:N:0:TAAGGCGA",
      "ACGT",
      "+",
      "IIII",
      0,
    );
    expect(r.error).toBeUndefined();
    expect(r.record?.length).toBe(4);
    expect(r.record?.pairEnd).toBe(1);
    expect(r.record?.avgQuality).toBe(40); // 'I'=Q40
  });

  it("第 1 行不以 @ 开头 → error", () => {
    const r = parseLineGroup("NO_AT_SIGN", "ACGT", "+", "IIII", 0);
    expect(r.record).toBeUndefined();
    expect(r.error?.reason).toContain("@");
  });

  it("第 3 行不以 + 开头 → error", () => {
    const r = parseLineGroup("@R", "ACGT", "NO_PLUS", "IIII", 0);
    expect(r.error?.reason).toContain("+");
  });

  it("序列长度与质量串不一致 → error", () => {
    const r = parseLineGroup("@R", "ACGT", "+", "II", 0);
    expect(r.error?.reason).toContain("长度");
  });

  it("空序列 → error", () => {
    const r = parseLineGroup("@R", "", "+", "", 0);
    expect(r.error?.reason).toContain("空");
  });
});

// ---------------------------------------------------------------------------
// 4. parseFastq：端到端解析 + 验收对照
// ---------------------------------------------------------------------------

describe("parseFastq", () => {
  it("验收 §8.1：解析 3 条 record（含一对双端）", () => {
    const r = parseFastq(FIXTURE_3_RECORDS);
    expect(r.errors).toEqual([]);
    expect(r.records.length).toBe(3);

    // 前两条 pairKey 相同
    expect(r.records[0].pairKey).toBe(r.records[1].pairKey);
    expect(r.records[0].pairEnd).toBe(1);
    expect(r.records[1].pairEnd).toBe(2);

    // 第三条单端
    expect(r.records[2].pairEnd).toBe(0);
  });

  it("stats：pairCount=1, singletons=1, total=3", () => {
    const r = parseFastq(FIXTURE_3_RECORDS);
    expect(r.stats.total).toBe(3);
    expect(r.stats.pairCount).toBe(1);
    expect(r.stats.singletons).toBe(1);
    expect(r.stats.errorCount).toBe(0);
  });

  it("支持 \\r\\n 行尾（Windows 文件）", () => {
    const text = FIXTURE_3_RECORDS.replace(/\n/g, "\r\n");
    const r = parseFastq(text);
    expect(r.records.length).toBe(3);
    expect(r.errors).toEqual([]);
  });

  it("文件末尾不足 4 行 → error 收集且不崩溃", () => {
    const text = `${FIXTURE_3_RECORDS}\n@PARTIAL`;
    const r = parseFastq(text);
    expect(r.records.length).toBe(3);
    expect(r.errors.length).toBeGreaterThanOrEqual(1);
    expect(r.errors[0].reason).toContain("不完整");
  });

  it("中间一条格式错误 → 跳过 + error，不影响后续", () => {
    // 单独造 fixture：3 条 read，破坏第 2 条的 @ 头
    const r1 = `@A00582:907:H7255DSX3:1:1101:8196:1063 1:N:0:TAAGGCGA
${SEQ_60}
+
${QUAL_60}`;
    const r2 = `@A00582:907:H7255DSX3:1:1101:8196:1063 2:N:0:TAAGGCGA
${SEQ_60}
+
${QUAL_60}`;
    const r3 = `@A00582:907:H7255DSX3:1:1101:8196:9999
ACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGTACGT
+
IIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIIII`;
    const text = `${r1}\n${r2}\n${r3}`;
    const lines = text.split(/\n/);
    // 第 2 条的 @ 行位于 0-based 索引 4
    lines[4] = "NO_AT_SIGN";
    const r = parseFastq(lines.join("\n"));
    // 第 1 组（line 1-4）成功；第 2 组（line 5-8）因 @ 行非法被跳过；第 3 组（line 9-12）成功
    expect(r.records.length).toBe(2);
    expect(r.errors.length).toBe(1);
    expect(r.errors[0].lineNo).toBe(5);
  });

  it("maxRecords 截断", () => {
    const r = parseFastq(FIXTURE_3_RECORDS, { maxRecords: 2 });
    expect(r.records.length).toBe(2);
    expect(r.errors.some((e) => e.reason.includes("截断"))).toBe(true);
  });

  it("空输入 → 0 records / 0 errors", () => {
    const r = parseFastq("");
    expect(r.records).toEqual([]);
    expect(r.errors).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// 5. calcStats：单端/双端/对数统计
// ---------------------------------------------------------------------------

describe("calcStats", () => {
  it("3 条样本：1 对双端 + 1 单端", () => {
    const r = parseFastq(FIXTURE_3_RECORDS);
    const stats = calcStats(r.records, 0, 1.23);
    expect(stats.pairCount).toBe(1);
    expect(stats.singletons).toBe(1);
    expect(stats.total).toBe(3);
    expect(stats.avgReadLen).toBeGreaterThan(0);
    expect(stats.elapsedMs).toBe(1.23);
  });
  it("全单端 → pairCount=0", () => {
    const text = "@R1\nACGT\n+\nIIII\n@R2\nACGT\n+\nIIII";
    const r = parseFastq(text);
    expect(r.stats.pairCount).toBe(0);
    expect(r.stats.singletons).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// 6. 性能基线：100k reads 解析应 < 2s
// ---------------------------------------------------------------------------

describe("parseFastq 性能", () => {
  it("100k reads 解析耗时 < 3000ms", () => {
    // 生成 100k 条 read 的合成 FASTQ（每条 4 行 100bp）
    const header = (i: number) => `@READ_${i}_1:N:0:LANE`;
    const seq = "A".repeat(100);
    const qual = "I".repeat(100); // Q40
    const lines: string[] = [];
    for (let i = 0; i < 100_000; i++) {
      lines.push(header(i));
      lines.push(seq);
      lines.push("+");
      lines.push(qual);
    }
    const text = lines.join("\n");

    const t0 = performance.now();
    const r = parseFastq(text);
    const elapsed = performance.now() - t0;

    expect(r.records.length).toBe(100_000);
    expect(r.errors.length).toBe(0);
    // 100k × 100bp 应在 3s 内完成（CI 容差）
    expect(elapsed).toBeLessThan(3000);
  }, 10_000);
});

// ---------------------------------------------------------------------------
// 7. 验收 §8.7 搜索：能按 readId 过滤
// ---------------------------------------------------------------------------

describe("搜索场景（仅验证 records 字段足够支持）", () => {
  it("records 数组能直接 substring 搜索 A00582", () => {
    const r = parseFastq(FIXTURE_3_RECORDS);
    const hits = r.records.filter(
      (rec: FastqRecord) =>
        rec.readId.includes("A00582") ||
        rec.pairKey.includes("A00582") ||
        rec.sequence.includes("A00582"),
    );
    expect(hits.length).toBe(3); // 3 条都含 A00582（在 readId 中）
  });
});
