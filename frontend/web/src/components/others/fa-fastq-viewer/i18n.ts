/**
 * FASTQ Viewer · 模块内文案集中管理
 * 通过 useI18n() 注入；如未挂全局 i18n，回退到中文硬编码（dev 友好）。
 * 后续应将 keys 同步到 src/locales/langs/{zh,en}.json。
 */

export const FASTQ_I18N_KEYS = {
  sectionTitle: "fastq.section.title",
  sectionDesc: "fastq.section.desc",
  upload: {
    btn: "fastq.upload.btn",
    dragHint: "fastq.upload.dragHint",
    pasteHint: "fastq.upload.pasteHint",
    fileTypeError: "fastq.upload.fileTypeError",
    tooLarge: "fastq.upload.tooLarge",
    loadError: "fastq.upload.loadError",
  },
  parse: {
    start: "fastq.parse.start",
    done: "fastq.parse.done",
    errorSome: "fastq.parse.errorSome",
  },
  toolbar: {
    search: "fastq.toolbar.search",
    viewStructured: "fastq.toolbar.viewStructured",
    viewRaw: "fastq.toolbar.viewRaw",
    sortBy: "fastq.toolbar.sortBy",
    sortId: "fastq.toolbar.sortId",
    sortLength: "fastq.toolbar.sortLength",
    sortAvg: "fastq.toolbar.sortAvg",
    sortPair: "fastq.toolbar.sortPair",
    pairFilter: "fastq.toolbar.pairFilter",
    pairAll: "fastq.toolbar.pairAll",
    pairSingle: "fastq.toolbar.pairSingle",
    pairR1: "fastq.toolbar.pairR1",
    pairR2: "fastq.toolbar.pairR2",
    minQuality: "fastq.toolbar.minQuality",
    stats: "fastq.toolbar.stats",
  },
  table: {
    colIdx: "fastq.table.colIdx",
    colReadId: "fastq.table.colReadId",
    colLength: "fastq.table.colLength",
    colAvgQ: "fastq.table.colAvgQ",
    colPair: "fastq.table.colPair",
    colSeq: "fastq.table.colSeq",
    colQual: "fastq.table.colQual",
  },
  pair: {
    R1: "fastq.pair.R1",
    R2: "fastq.pair.R2",
    singleton: "fastq.pair.singleton",
  },
  raw: {
    title: "fastq.raw.title",
    empty: "fastq.raw.empty",
  },
  empty: {
    noData: "fastq.empty.noData",
    noMatch: "fastq.empty.noMatch",
  },
  perf: {
    tooLargeWarn: "fastq.perf.tooLargeWarn",
  },
} as const;
