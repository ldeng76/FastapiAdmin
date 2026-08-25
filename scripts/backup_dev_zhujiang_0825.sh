#!/bin/bash
# ============================================================
# 备份脚本（Linux 适配版）：dev (h196_3, 127.0.0.1:5432) → /tmp/lnrs_backup_zhujiang_0825_<TS>/
#
# 用途：
#   在导入 zhujiang 0825 批次之前，备份 dev 端 lnrs schema 的 4 张表。
#   范围比 ct0820 版（backup_dev_zhujiang_ct.sh）更宽：
#     report_text / exam_detail 按 center_code='zhujiang' 全部 exam_type
#     （除 CT 97k 刷外，本批还有 Pathology 39 条、Genetic 12 条 sample 原位刷新）。
#   可在导入失败时回滚 / 重跑。
#
# 备份范围：
#   1. lnrs_anon_report_text (按 exam JOIN 过滤: center_code='zhujiang', 全部 exam_type)
#   2. lnrs_anon_exam_detail (按 exam JOIN 过滤；不用 batch_id 以避免漏 0719 重跑行)
#   3. lnrs_anon_phi_audit   (按 ingest_batch.center_code='zhujiang' 的全部 batch 过滤)
#   4. lnrs_anon_patient     (center_code='zhujiang' 全量)
#
# 为什么不备份 lnrs_anon_exam？
#   导入对 exam 表只做 last_seen_batch_id + exam_date 刷新（不重建）。
#   一旦回滚时把 exam 也回退，会破坏真实病人信息；FK CASCADE
#   还会把 finding/series/uid_map/report/detail 全部级联炸掉。
#
# 与 Windows 版 (backup_dev_zhujiang_ct.sh) 的差异：
#   - PG_BIN 默认 /usr/bin（psql 18.4），不再用 psql.exe / cygpath
#   - 连接用户 lnrs（PGPASSWORD=lnrs_pwd），不再用 postgres 超级用户
#   - 备份目录 /tmp/lnrs_backup_zhujiang_0825_<TS>（可用 BACKUP_ROOT 覆盖）
#   - 过滤条件去掉 exam_type='CT'，改为全部 exam_type
#
# 使用方法（Linux，本机执行）：
#   ./scripts/backup_dev_zhujiang_0825.sh
#   # 自定义（可选）：
#   BACKUP_ROOT=/home/dzy/wk/lnrs_backup_tmp DEV_HOST=127.0.0.1 ./scripts/backup_dev_zhujiang_0825.sh
#
# 输出：
#   BACKUP_DIR 绝对路径、4 表「库内 count vs CSV 行数」对照表、md5 清单、耗时与磁盘占用。
# ============================================================
set -euo pipefail

# ---- 本机路径 ------------------------------------------------------------
PG_BIN="${PG_BIN:-/usr/bin}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ---- 连接参数 ------------------------------------------------------------
DEV_HOST="${DEV_HOST:-127.0.0.1}"
DEV_PORT="${DEV_PORT:-5432}"
DEV_DB="${DEV_DB:-postgres}"
DEV_USER="${DEV_USER:-lnrs}"
DEV_PWD="${DEV_PWD:-lnrs_pwd}"

# ---- 过滤参数 ------------------------------------------------------------
CENTER="${CENTER:-zhujiang}"

# ---- 输出目录（Linux：POSIX 路径，直接用）--------------------------------
TS="$(date +%Y%m%d_%H%M%S)"
BACKUP_ROOT="${BACKUP_ROOT:-/tmp}"
BACKUP_DIR="${BACKUP_ROOT}/lnrs_backup_${CENTER}_0825_$TS"

START_TS=$(date +%s)

psql_local() {
  PGPASSWORD="$DEV_PWD" PGCLIENTENCODING=UTF8 "$PG_BIN/psql" \
    -h "$DEV_HOST" -p "$DEV_PORT" -U "$DEV_USER" -d "$DEV_DB" "$@"
}

# ---- Step 0：前置检查 ----------------------------------------------------
echo "=== 前置检查 ==="
psql_local -tAc "SELECT 1;" >/dev/null
echo "       PG OK ($DEV_HOST:$DEV_PORT/$DEV_DB, user=$DEV_USER)"

mkdir -p "$BACKUP_DIR"
echo "       备份目录: $BACKUP_DIR"

# ---- Step 1：拍 phi_audit 的 batch 集合快照（动态，避免遗漏未来重跑）-----
echo "=== Step 1: 拍 phi_audit 的 batch 集合快照 ==="
psql_local -tAc "
  SELECT batch_id FROM lnrs.lnrs_anon_ingest_batch
  WHERE center_code = '$CENTER'
  ORDER BY started_at;" > "$BACKUP_DIR/phi_audit_backup_batches.txt"
# psql 个别平台输出 CRLF，统一去掉 \r
tr -d '\r' < "$BACKUP_DIR/phi_audit_backup_batches.txt" > "$BACKUP_DIR/phi_audit_backup_batches.tmp"
mv "$BACKUP_DIR/phi_audit_backup_batches.tmp" "$BACKUP_DIR/phi_audit_backup_batches.txt"
N_BATCHES=$(wc -l < "$BACKUP_DIR/phi_audit_backup_batches.txt")
echo "       中心 $CENTER 现有 batch: $N_BATCHES 个"
head -5 "$BACKUP_DIR/phi_audit_backup_batches.txt" | awk '{print "       样例 batch:", $0}'

# ---- Step 2：导出 4 张表到 CSV（\copy 单行调用，规避多行解析问题）--------
# 注意：psql \copy 不支持跨行的 SQL 字符串，必须单行 \copy 整段。
# 这里用 psql -c 单行调用 4 次（每张表一次）。
BATCHES_INLINE=$(tr '\n' ',' < "$BACKUP_DIR/phi_audit_backup_batches.txt" | sed "s/,$//" | sed "s/,/','/g")
BACKUP_POSIX="$BACKUP_DIR"

echo "=== Step 2: 导出 4 张表到 CSV ==="

# 2.1 report_text（按 exam JOIN 过滤；report_text 不带 center_code；全部 exam_type）
RT_COPY=$(psql_local -tA -c "\copy (SELECT rt.* FROM lnrs.lnrs_anon_report_text rt WHERE rt.anon_exam_id IN (SELECT anon_exam_id FROM lnrs.lnrs_anon_exam WHERE center_code='$CENTER')) TO '$BACKUP_POSIX/report_text.csv' WITH (FORMAT csv, HEADER true)" 2>&1 | grep -oE 'COPY [0-9]+' | grep -oE '[0-9]+' || true)
RT_COPY=${RT_COPY:-0}

# 2.2 exam_detail（按 exam JOIN 过滤；不用 batch_id 以避免漏 0719 重跑行；全部 exam_type）
ED_COPY=$(psql_local -tA -c "\copy (SELECT ed.* FROM lnrs.lnrs_anon_exam_detail ed WHERE ed.anon_exam_id IN (SELECT anon_exam_id FROM lnrs.lnrs_anon_exam WHERE center_code='$CENTER')) TO '$BACKUP_POSIX/exam_detail.csv' WITH (FORMAT csv, HEADER true)" 2>&1 | grep -oE 'COPY [0-9]+' | grep -oE '[0-9]+' || true)
ED_COPY=${ED_COPY:-0}

# 2.3 phi_audit（按 ingest_batch.center_code 过滤；动态 batch IN）
PA_COPY=$(psql_local -tA -c "\copy (SELECT pa.* FROM lnrs.lnrs_anon_phi_audit pa WHERE pa.batch_id IN ('$BATCHES_INLINE')) TO '$BACKUP_POSIX/phi_audit.csv' WITH (FORMAT csv, HEADER true)" 2>&1 | grep -oE 'COPY [0-9]+' | grep -oE '[0-9]+' || true)
PA_COPY=${PA_COPY:-0}

# 2.4 patient（center_code 全量）
PT_COPY=$(psql_local -tA -c "\copy (SELECT * FROM lnrs.lnrs_anon_patient WHERE center_code='$CENTER') TO '$BACKUP_POSIX/patient.csv' WITH (FORMAT csv, HEADER true)" 2>&1 | grep -oE 'COPY [0-9]+' | grep -oE '[0-9]+' || true)
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
                            WHERE center_code='$CENTER');")
ED_DB=$(psql_local -tAc "
  SELECT count(*) FROM lnrs.lnrs_anon_exam_detail ed
  WHERE ed.anon_exam_id IN (SELECT anon_exam_id FROM lnrs.lnrs_anon_exam
                            WHERE center_code='$CENTER');")
# phi_audit 行数：把 batch 集合以 PG 数组形式传入，避免 shell 转义陷阱
BATCHES_PGARR="{"$(tr '\n' ',' < "$BACKUP_DIR/phi_audit_backup_batches.txt" | sed 's/,$//')"}"
PA_DB=$(psql_local -tAc "
  SELECT count(*) FROM lnrs.lnrs_anon_phi_audit pa
  WHERE pa.batch_id = ANY('$BATCHES_PGARR'::uuid[]);")
PT_DB=$(psql_local -tAc "
  SELECT count(*) FROM lnrs.lnrs_anon_patient WHERE center_code='$CENTER';")

match() { if [[ "$1" == "$2" ]]; then echo "OK"; else echo "MISMATCH"; fi; }

echo ""
echo "  表名          | 库内 count | CSV 行数  | 一致?"
echo "  --------------+------------+-----------+---------"
printf "  %-14s | %-10s | %-9s | %s\n" "report_text" "$RT_DB" "$RT_CSV" "$(match "$RT_CSV" "$RT_DB")"
printf "  %-14s | %-10s | %-9s | %s\n" "exam_detail" "$ED_DB" "$ED_CSV" "$(match "$ED_CSV" "$ED_DB")"
printf "  %-14s | %-10s | %-9s | %s\n" "phi_audit"   "$PA_DB" "$PA_CSV" "$(match "$PA_CSV" "$PA_DB")"
printf "  %-14s | %-10s | %-9s | %s\n" "patient"     "$PT_DB" "$PT_CSV" "$(match "$PT_CSV" "$PT_DB")"
echo ""

if [[ "$RT_CSV" != "$RT_DB" || "$ED_CSV" != "$ED_DB" || "$PA_CSV" != "$PA_DB" || "$PT_CSV" != "$PT_DB" ]]; then
  echo "ERROR: 行数不一致，备份不完整，拒绝继续" >&2
  exit 1
fi

# ---- Step 4：md5 落盘 ----------------------------------------------------
echo "=== Step 4: 落 md5 校验 ==="
md5sum "$BACKUP_DIR"/*.csv > "$BACKUP_DIR/checksums.md5"
cat "$BACKUP_DIR/checksums.md5" | awk '{printf "       %s  %s\n", $1, $2}'

# ---- 完成 ----------------------------------------------------------------
ELAPSED=$(( $(date +%s) - START_TS ))
USAGE=$(du -sh "$BACKUP_DIR" | awk '{print $1}')

echo ""
echo "=== 完成 ==="
echo "  备份目录: $BACKUP_DIR"
echo "  备份范围: $CENTER / 全部 exam_type / phi_audit 覆盖 $N_BATCHES 个 batch"
echo "    - report_text : $RT_CSV 行"
echo "    - exam_detail : $ED_CSV 行"
echo "    - phi_audit   : $PA_CSV 行"
echo "    - patient     : $PT_CSV 行"
echo "  耗时: ${ELAPSED}s   磁盘占用: $USAGE"
echo ""
echo "  下一步（导入 zhujiang 0825，由主线执行）："
echo "    cd backend && PYTHONPATH=. ./.venv/bin/python -m app.plugin.module_medical.hospital.anon_etl \\"
echo "      --centers $CENTER --data-root ../data_zj0825"
echo ""
echo "  失败时回滚：用 $BACKUP_DIR 下 4 个 CSV 把对应行删后灌回（不动 lnrs_anon_exam）。"
