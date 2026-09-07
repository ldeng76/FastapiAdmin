#!/usr/bin/env bash
# 省医 2026-09 全量批次导入 runner：每 run = 独立 staging 子目录 + 单事务 + 1 条 ingest_batch。
# 用法: ./scripts/shengyi_import_r1.sh [起始run标签, 默认 R1]
# 前置: staging 已生成于 data_shengyi202609/shengyi/
set -uo pipefail

cd "$(dirname "$0")/../backend"
ROOT=../data_shengyi202609
STAGE=$ROOT/shengyi
LOGDIR=/tmp/shengyi_import
mkdir -p "$LOGDIR"

declare -A RUNS=(
  [R1]="patient visit_record"
  [R2]="pahology_specimen imaging_report ultrasound_report ecg_report genetic_report"
  [R3]="surgery_record"
  [R4]="lab_result_p1"
  [R5]="lab_result_p2"
  [R6]="lab_result_p3"
  [R7]="lab_result_p4"
  [R8]="drug_order"
  [R9]="no_drug_order"
  [R10]="outp_order anesthesia_order"
  [R11]="diagnosis diagnosis_inpatient"
  [R12]="clinical_document"
  [R13]="medical_history"
  [R14]="nursing_observation"
  [R15]="icu_observation anesthesia_observation"
)
ORDER=(R1 R2 R3 R4 R5 R6 R7 R8 R9 R10 R11 R12 R13 R14 R15)

START="${1:-R1}"
started=0
for tag in "${ORDER[@]}"; do
  if [ "$tag" = "$START" ]; then started=1; fi
  [ "$started" = 1 ] || continue
  files="${RUNS[$tag]}"
  dir="$ROOT/import_${tag}"
  mkdir -p "$dir/shengyi"
  for f in $files; do
    [ -f "$STAGE/$f.parquet" ] || { echo "[$tag] 缺少 staging: $f.parquet"; exit 1; }
    ln -f "$STAGE/$f.parquet" "$dir/shengyi/$f.parquet"
  done
  echo "===== [$tag] $(date +%H:%M:%S) $files =====" | tee -a "$LOGDIR/summary.log"
  log="$LOGDIR/${tag}.log"
  PYTHONPATH="" ENVIRONMENT=dev uv run python -m app.plugin.module_medical.hospital.anon_etl \
    --centers shengyi --data-root "$dir" > "$log" 2>&1
  rc=$?
  echo "[$tag] EXIT=$rc $(date +%H:%M:%S)" | tee -a "$LOGDIR/summary.log"
  if [ $rc -ne 0 ]; then
    echo "[$tag] 失败, 停止后续 run。日志: $log" | tee -a "$LOGDIR/summary.log"
    exit $rc
  fi
done
echo "===== 全部 run 完成 =====" | tee -a "$LOGDIR/summary.log"
