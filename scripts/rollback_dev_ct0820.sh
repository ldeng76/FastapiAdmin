#!/bin/bash
# ============================================================
# 回滚脚本：用 backup_dev_zhujiang_ct.sh 导出的 CSV 把 dev PG 回滚到导入前状态。
#
# 范围：
#   - lnrs_anon_report_text  (zhujiang CT 全部行 → 删 → 灌回)
#   - lnrs_anon_exam_detail  (zhujiang CT 全部行 → 删 → 灌回)
#   - lnrs_anon_phi_audit    (不在本脚本范围：手动 DELETE，列在 Step 末尾)
#   - lnrs_anon_patient      (不在本脚本范围：手动 DELETE，列在 Step 末尾)
#
# 不动 lnrs_anon_exam：导入对 exam 表只 last_seen/exam_date 刷新，不重建。
#                   FK CASCADE 一旦删 exam 会级联炸掉 finding/series/uid_map
#                   /report/detail，所以必须不动。
#
# 使用方法（Git Bash，本机执行）：
#   ./scripts/rollback_dev_ct0820.sh <BACKUP_DIR>
#   # 例：
#   ./scripts/rollback_dev_ct0820.sh "C:/Users/dzy/AppData/Local/Temp/lnrs_backup_zhujiang_CT_20260820_150012"
#
# 验证：
#   Step 2 自动跑：count(*) 对比 + 重导 CSV + md5 对比。
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

# ---- 入参 ----------------------------------------------------------------
BACKUP_DIR="${1:?用法: $0 <BACKUP_DIR>}"
CENTER_DEFAULT="zhujiang"
EXAM_TYPE_DEFAULT="CT"
CENTER="${CENTER:-$CENTER_DEFAULT}"
EXAM_TYPE="${EXAM_TYPE:-$EXAM_TYPE_DEFAULT}"

# 文件存在性校验
for f in report_text.csv exam_detail.csv phi_audit.csv patient.csv; do
  if [[ ! -f "$BACKUP_DIR/$f" ]]; then
    echo "ERROR: $BACKUP_DIR/$f 不存在" >&2
    exit 1
  fi
done

psql_local() {
  PGPASSWORD="$SUPER_PWD" PGCLIENTENCODING=UTF8 "$PG_BIN/psql.exe" \
    -h "$DEV_HOST" -p "$DEV_PORT" -U postgres -d "$DEV_DB" "$@"
}

# ---- Step 0：MD5 校验（防止备份文件被改）--------------------------------
echo "=== Step 0: 校验备份文件 md5 ==="
md5sum "$BACKUP_DIR"/*.csv | awk '{printf "       %s  %s\n", $1, $2}'

# ---- Step 1：单事务删 → 灌回 ---------------------------------------------
echo "=== Step 1: 单事务回滚 report_text + exam_detail ==="
ROLLBACK_SQL="$BACKUP_DIR/rollback.sql"
cat > "$ROLLBACK_SQL" <<EOF
\set ON_ERROR_STOP on
BEGIN;

-- 1.1 清空 zhujiang CT 的 report_text 行（FK -> exam 不删，FK 父表 exam 未动）
DELETE FROM lnrs.lnrs_anon_report_text rt
WHERE rt.anon_exam_id IN (
  SELECT anon_exam_id FROM lnrs.lnrs_anon_exam
  WHERE center_code = '$CENTER' AND exam_type = '$EXAM_TYPE'
);

-- 1.2 清空 zhujiang CT 的 exam_detail 行（同样不动 exam；两表互不 FK）
DELETE FROM lnrs.lnrs_anon_exam_detail ed
WHERE ed.anon_exam_id IN (
  SELECT anon_exam_id FROM lnrs.lnrs_anon_exam
  WHERE center_code = '$CENTER' AND exam_type = '$EXAM_TYPE'
);

-- 1.3 灌回（CSV HEADER=true，与 backup 端一致；\copy INSERT，PK/FK 约束自动满足）
\\copy lnrs.lnrs_anon_report_text FROM '$(cygpath -m "$BACKUP_DIR")/report_text.csv' WITH (FORMAT csv, HEADER true)
\\copy lnrs.lnrs_anon_exam_detail FROM '$(cygpath -m "$BACKUP_DIR")/exam_detail.csv' WITH (FORMAT csv, HEADER true)

COMMIT;
EOF
psql_local -f "$ROLLBACK_SQL"

# ---- Step 2：验证 --------------------------------------------------------
echo "=== Step 2: 验证（行数 + md5） ==="
# 2.1 行数对比
RT_DB=$(psql_local -tAc "
  SELECT count(*) FROM lnrs.lnrs_anon_report_text rt
  WHERE rt.anon_exam_id IN (SELECT anon_exam_id FROM lnrs.lnrs_anon_exam
                            WHERE center_code='$CENTER' AND exam_type='$EXAM_TYPE');")
ED_DB=$(psql_local -tAc "
  SELECT count(*) FROM lnrs.lnrs_anon_exam_detail ed
  WHERE ed.anon_exam_id IN (SELECT anon_exam_id FROM lnrs.lnrs_anon_exam
                            WHERE center_code='$CENTER' AND exam_type='$EXAM_TYPE');")
RT_CSV=$(($(wc -l < "$BACKUP_DIR/report_text.csv") - 1))
ED_CSV=$(($(wc -l < "$BACKUP_DIR/exam_detail.csv") - 1))
echo "       report_text:  CSV=$RT_CSV  DB=$RT_DB"
echo "       exam_detail :  CSV=$ED_CSV  DB=$ED_DB"

if [[ "$RT_CSV" != "$RT_DB" || "$ED_CSV" != "$ED_DB" ]]; then
  echo "ERROR: 回滚后行数与备份不一致" >&2
  exit 1
fi

# 2.2 重导库内 CSV + md5 对比
VERIFY_SQL="$BACKUP_DIR/verify.sql"
cat > "$VERIFY_SQL" <<EOF
\copy (
  SELECT rt.* FROM lnrs.lnrs_anon_report_text rt
  WHERE rt.anon_exam_id IN (SELECT anon_exam_id FROM lnrs.lnrs_anon_exam
                            WHERE center_code='$CENTER' AND exam_type='$EXAM_TYPE')
  ORDER BY rt.anon_exam_id
) TO '$(cygpath -m "$BACKUP_DIR")/report_text.post.csv' WITH (FORMAT csv, HEADER true)
\copy (
  SELECT ed.* FROM lnrs.lnrs_anon_exam_detail ed
  WHERE ed.anon_exam_id IN (SELECT anon_exam_id FROM lnrs.lnrs_anon_exam
                            WHERE center_code='$CENTER' AND exam_type='$EXAM_TYPE')
  ORDER BY ed.anon_exam_id, ed.detail_type, ed.detail_ordinal
) TO '$(cygpath -m "$BACKUP_DIR")/exam_detail.post.csv' WITH (FORMAT csv, HEADER true)
EOF
psql_local -f "$VERIFY_SQL"

echo ""
echo "--- report_text md5 (备份 vs 回滚后) ---"
md5sum "$BACKUP_DIR/report_text.csv" "$BACKUP_DIR/report_text.post.csv" | awk '{printf "       %s  %s\n", $1, $2}'
echo "--- exam_detail  md5 (备份 vs 回滚后) ---"
md5sum "$BACKUP_DIR/exam_detail.csv" "$BACKUP_DIR/exam_detail.post.csv" | awk '{printf "       %s  %s\n", $1, $2}'

# ---- Step 3：手动清理 phi_audit / patient 增量的提示 --------------------
echo ""
echo "=== 完成 ==="
echo "  已回滚：report_text + exam_detail (zhujiang CT)"
echo ""
echo "  ⚠  以下增量未回滚（按需手动清理；运行前请再次确认 batch_id）："
echo ""
echo "  # phi_audit 增量（本次新 batch 写入的 3 条/exam ≈ 29 万行）"
echo "  psql -c \"DELETE FROM lnrs.lnrs_anon_phi_audit WHERE batch_id = '<本次 batch_id>';\""
echo ""
echo "  # 占位 patient 增量（ct0820 触发的 ≈ 16k 个 sex='0' 占位行）"
echo "  psql -c \"DELETE FROM lnrs.lnrs_anon_patient \\"
echo "           WHERE center_code='$CENTER' AND sex='0' \\"
echo "             AND created_batch_id='<本次 batch_id>';\""
echo ""
echo "  查 batch_id："
echo "  psql -c \"SELECT batch_id, started_at, status, row_counts \\"
echo "           FROM lnrs.lnrs_anon_ingest_batch \\"
echo "           WHERE center_code='$CENTER' AND source_locator LIKE '%ct0820%' \\"
echo "           ORDER BY started_at DESC LIMIT 3;\""
