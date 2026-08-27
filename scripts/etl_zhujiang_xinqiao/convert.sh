#!/usr/bin/env bash
# convert.sh — 珠江-新桥数据 → parquet 编排器
# 用法: bash convert.sh
set -euo pipefail

ROOT=/data/wlx/DATABASE/0605_small/01disk
SRC=$ROOT/_字段与原始数据
OUT=$ROOT/zhujiang_xinqiao_parquet
PRE=$OUT/_preflight
LOG=$OUT/_logs/conversion.log
SCR=/home/dzy/wk/lnrs/scripts/etl_zhujiang_xinqiao

DUCKDB=/home/dzy/.duckdb/cli/latest/duckdb

mkdir -p "$OUT" "$PRE" "$(dirname "$LOG")" "$OUT/_meta"

# 截断日志
: > "$LOG"

log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

log "=========== START  zhujiang_xinqiao parquet conversion ==========="
log "DUCKDB: $($DUCKDB --version 2>&1 || echo 'NOT FOUND')"
log "libreoffice: $(libreoffice --version 2>&1 || echo 'NOT FOUND')"

# ----- A) .xls → .xlsx (preflight) -----
log "--- A) preflight: .xls → .xlsx ---"
for f in "$SRC/精准医学V2_副本.xls" "$SRC/历史病历查询.xls"; do
  if [ ! -f "$f" ]; then
    log "  skip (missing): $f"
    continue
  fi
  base=$(basename "$f" .xls)
  if [ -f "$PRE/$base.xlsx" ]; then
    log "  cached: $PRE/$base.xlsx"
  else
    log "  converting: $f"
    libreoffice --headless --convert-to xlsx --outdir "$PRE" "$f" >>"$LOG" 2>&1 || {
      log "  ERROR: libreoffice failed for $f"; exit 1;
    }
  fi
done

# ----- B) per-table SQL -----
log "--- B) run per-table SQL ---"
for tbl in 01_patient 02_pathology_specimen 03_surgery_record 04_nodule_imaging \
           05_genetic_test 06_ihc_result 07_follow_up; do
  log "  === $tbl ==="
  $DUCKDB < "$SCR/${tbl}.sql" >>"$LOG" 2>&1 || {
    log "  ERROR: $tbl failed (see $LOG for tail)"
    tail -30 "$LOG"
    exit 1
  }
  log "    ok"
done

# ----- C) verify -----
log "--- C) verify ---"
$DUCKDB -box < "$SCR/99_verify.sql" 2>>"$LOG" | tee -a "$LOG" || {
  log "  WARN: verify returned non-zero (informational only)"
}

# ----- D) manifest -----
log "--- D) manifest ---"
python3 "$SCR/make_manifest.py" "$OUT" "$ROOT" 2>>"$LOG" | tee -a "$LOG"

log "=========== DONE ==========="
log "output: $OUT"
ls -la "$OUT" | tee -a "$LOG"
