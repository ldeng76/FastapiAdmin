#!/bin/bash
# ============================================================
# 备份脚本：dev (本机 PG18) → $TEMP/lnrs_backup_zhujiang_CT_<TS>/
#
# 用途：
#   在导入 ct0820 之前，备份 dev 端 lnrs schema 的 4 张表，
#   范围：center_code='zhujiang' AND exam_type='CT'。
#   配合 scripts/rollback_dev_ct0820.sh 使用，可在导入后回滚。
#
# 备份范围：
#   1. lnrs_anon_report_text (按 exam JOIN 过滤)
#   2. lnrs_anon_exam_detail  (按 exam JOIN 过滤，不用 batch_id 以避免漏 0719 重跑行)
#   3. lnrs_anon_phi_audit    (按 ingest_batch.center_code='zhujiang' 的全部 batch 过滤)
#   4. lnrs_anon_patient      (center_code='zhujiang' 全量)
#
# 为什么不备份 lnrs_anon_exam？
#   导入对 exam 表只做 last_seen_batch_id + exam_date 刷新（不重建）。
#   一旦回滚时把 exam 也回退，会破坏 0814 真实病人信息。FK CASCADE
#   还会把 finding/series/uid_map/report/detail 全部级联炸掉。
#
# 使用方法（Git Bash，本机执行）：
#   ./scripts/backup_dev_zhujiang_ct.sh
#   CENTER=zhujiang EXAM_TYPE=CT ./scripts/backup_dev_zhujiang_ct.sh
#   # 自定义：
#   CENTER=xinqiao EXAM_TYPE=Pathology ./scripts/backup_dev_zhujiang_ct.sh
#
# 输出：
#   末尾打印 BACKUP_DIR 绝对路径与回滚命令。
# ============================================================
set -euo pipefail

# ---- 本机路径 ------------------------------------------------------------
PG_BIN="${PG_BIN:-/c/Program Files/PostgreSQL/18/bin}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ---- 连接参数 ------------------------------------------------------------
DEV_HOST="${DEV_HOST:-127.0.0.1}"
DEV_PORT="${DEV_PORT:-5432}"
DEV_DB="${DEV_DB:-postgres}"
SUPER_PWD="${SUPER_PWD:-admin@pwd}"

# ---- 过滤参数 ------------------------------------------------------------
CENTER="${CENTER:-zhujiang}"
EXAM_TYPE="${EXAM_TYPE:-CT}"

# ---- 输出目录（Windows TEMP 转正斜杠，供 psql \copy 使用）---------------
TS="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="$(cygpath -m "$TEMP")/lnrs_backup_${CENTER}_${EXAM_TYPE}_$TS"

psql_local() {
  PGPASSWORD="$SUPER_PWD" PGCLIENTENCODING=UTF8 "$PG_BIN/psql.exe" \
    -h "$DEV_HOST" -p "$DEV_PORT" -U postgres -d "$DEV_DB" "$@"
}

# ---- Step 0：前置检查 ----------------------------------------------------
echo "=== 前置检查 ==="
psql_local -tAc "SELECT 1;" >/dev/null
echo "       PG OK ($DEV_HOST:$DEV_PORT/$DEV_DB)"

mkdir -p "$BACKUP_DIR"
echo "       备份目录: $BACKUP_DIR"

# ---- Step 1：拍 phi_audit 的 batch 集合快照（动态，避免遗漏未来重跑）-----
echo "=== Step 1: 拍 phi_audit 的 batch 集合快照 ==="
psql_local -tAc "
  SELECT batch_id FROM lnrs.lnrs_anon_ingest_batch
  WHERE center_code = '$CENTER'
  ORDER BY started_at;" > "$BACKUP_DIR/phi_audit_backup_batches.txt"
# Windows psql 输出 CRLF，需要 tr 去掉 \r
tr -d '\r' < "$BACKUP_DIR/phi_audit_backup_batches.txt" > "$BACKUP_DIR/phi_audit_backup_batches.tmp"
mv "$BACKUP_DIR/phi_audit_backup_batches.tmp" "$BACKUP_DIR/phi_audit_backup_batches.txt"
N_BATCHES=$(wc -l < "$BACKUP_DIR/phi_audit_backup_batches.txt")
echo "       中心 $CENTER 现有 batch: $N_BATCHES 个"
head -5 "$BACKUP_DIR/phi_audit_backup_batches.txt" | awk '{print "       样例 batch:", $0}'

# ---- Step 2：导出 4 张表到 CSV（\copy 单行调用，规避多行解析问题）-----
# 注意：psql \copy 不支持跨行的 SQL 字符串，必须单行 \copy 整段。
# 这里用 psql -c 单行调用 4 次（每张表一次）。
BATCHES_INLINE=$(tr '\n' ',' < "$BACKUP_DIR/phi_audit_backup_batches.txt" | sed "s/,$//" | sed "s/,/','/g")
BACKUP_POSIX="$(cygpath -m "$BACKUP_DIR")"

echo "=== Step 2: 导出 4 张表到 CSV ==="

# 2.1 report_text（按 exam JOIN 过滤；report_text 不带 center_code）
RT_COPY=$(psql_local -tA -c "\copy (SELECT rt.* FROM lnrs.lnrs_anon_report_text rt WHERE rt.anon_exam_id IN (SELECT anon_exam_id FROM lnrs.lnrs_anon_exam WHERE center_code='$CENTER' AND exam_type='$EXAM_TYPE')) TO '$BACKUP_POSIX/report_text.csv' WITH (FORMAT csv, HEADER true)" 2>&1 | grep -oE 'COPY [0-9]+' | grep -oE '[0-9]+')
RT_COPY=${RT_COPY:-0}

# 2.2 exam_detail（按 exam JOIN 过滤；不用 batch_id 以避免漏 0719 重跑行）
ED_COPY=$(psql_local -tA -c "\copy (SELECT ed.* FROM lnrs.lnrs_anon_exam_detail ed WHERE ed.anon_exam_id IN (SELECT anon_exam_id FROM lnrs.lnrs_anon_exam WHERE center_code='$CENTER' AND exam_type='$EXAM_TYPE')) TO '$BACKUP_POSIX/exam_detail.csv' WITH (FORMAT csv, HEADER true)" 2>&1 | grep -oE 'COPY [0-9]+' | grep -oE '[0-9]+')
ED_COPY=${ED_COPY:-0}

# 2.3 phi_audit（按 ingest_batch.center_code 过滤；动态 batch IN）
PA_COPY=$(psql_local -tA -c "\copy (SELECT pa.* FROM lnrs.lnrs_anon_phi_audit pa WHERE pa.batch_id IN ('$BATCHES_INLINE')) TO '$BACKUP_POSIX/phi_audit.csv' WITH (FORMAT csv, HEADER true)" 2>&1 | grep -oE 'COPY [0-9]+' | grep -oE '[0-9]+')
PA_COPY=${PA_COPY:-0}

# 2.4 patient（center_code 全量）
PT_COPY=$(psql_local -tA -c "\copy (SELECT * FROM lnrs.lnrs_anon_patient WHERE center_code='$CENTER') TO '$BACKUP_POSIX/patient.csv' WITH (FORMAT csv, HEADER true)" 2>&1 | grep -oE 'COPY [0-9]+' | grep -oE '[0-9]+')
PT_COPY=${PT_COPY:-0}

ls -lh "$BACKUP_DIR"/*.csv | awk '{printf "       %-40s %s\n", $9, $5}'

# ---- Step 3：行数 + md5 验证 ----------------------------------------------
echo "=== Step 3: 验证（CSV 行数 vs 库内 count(*)） ==="
# CSV 行数直接用 psql COPY 输出的行数（CSV 含 \n 字段，wc -l 不准）
RT_CSV="$RT_COPY"
ED_CSV="$ED_COPY"
PA_CSV="$PA_COPY"
PT_CSV="$PT_COPY"

# 库内行数
RT_DB=$(psql_local -tAc "
  SELECT count(*) FROM lnrs.lnrs_anon_report_text rt
  WHERE rt.anon_exam_id IN (SELECT anon_exam_id FROM lnrs.lnrs_anon_exam
                            WHERE center_code='$CENTER' AND exam_type='$EXAM_TYPE');")
ED_DB=$(psql_local -tAc "
  SELECT count(*) FROM lnrs.lnrs_anon_exam_detail ed
  WHERE ed.anon_exam_id IN (SELECT anon_exam_id FROM lnrs.lnrs_anon_exam
                            WHERE center_code='$CENTER' AND exam_type='$EXAM_TYPE');")
# phi_audit 行数：把 batch 集合以 PG 数组形式传入，避免 shell 转义陷阱
BATCHES_PGARR="{"$(tr '\n' ',' < "$BACKUP_DIR/phi_audit_backup_batches.txt" | sed 's/,$//')"}"
PA_DB=$(psql_local -tAc "
  SELECT count(*) FROM lnrs.lnrs_anon_phi_audit pa
  WHERE pa.batch_id = ANY('$BATCHES_PGARR'::uuid[]);")
PT_DB=$(psql_local -tAc "
  SELECT count(*) FROM lnrs.lnrs_anon_patient WHERE center_code='$CENTER';")

echo "       report_text:  CSV=$RT_CSV  DB=$RT_DB"
echo "       exam_detail :  CSV=$ED_CSV  DB=$ED_DB"
echo "       phi_audit   :  CSV=$PA_CSV  DB=$PA_DB"
echo "       patient     :  CSV=$PT_CSV  DB=$PT_DB"

if [[ "$RT_CSV" != "$RT_DB" || "$ED_CSV" != "$ED_DB" || "$PA_CSV" != "$PA_DB" || "$PT_CSV" != "$PT_DB" ]]; then
  echo "ERROR: 行数不一致，备份不完整，拒绝继续" >&2
  exit 1
fi

# ---- Step 4：md5 落盘 ----------------------------------------------------
echo "=== Step 4: 落 md5 校验 ==="
md5sum "$BACKUP_DIR"/*.csv > "$BACKUP_DIR/checksums.md5"
cat "$BACKUP_DIR/checksums.md5" | awk '{printf "       %s  %s\n", $1, $2}'

# ---- 完成 ----------------------------------------------------------------
echo ""
echo "=== 完成 ==="
echo "  备份目录: $BACKUP_DIR"
echo "  备份范围: $CENTER / $EXAM_TYPE"
echo "    - report_text : $RT_CSV 行"
echo "    - exam_detail : $ED_CSV 行"
echo "    - phi_audit   : $PA_CSV 行（覆盖 $N_BATCHES 个 batch）"
echo "    - patient     : $PT_CSV 行"
echo ""
echo "  下一步（导入 ct0820）："
echo "    cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.plugin.module_medical.hospital.anon_etl \\"
echo "      --centers $CENTER --data-root ../data_ct0820"
echo ""
echo "  失败时回滚："
echo "    ./scripts/rollback_dev_ct0820.sh '$BACKUP_DIR'"
