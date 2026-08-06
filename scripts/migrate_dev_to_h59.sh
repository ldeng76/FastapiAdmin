#!/bin/bash
# ============================================================
# 标准迁移脚本：dev (PG18) → h59 (192.168.1.59, PG15)
#
# 与 scripts/migrate_dev_to_h42.sh 的差异：
#   - 目标机 = h59（与 h42 同主机 192.168.1.59，但 SSH 别名是 h59；
#     脚本默认通过 ~/.ssh/config 中的 "h59" 别名走免密登录）。
#   - 应用数据库 = postgres（与 .env.h42 一致）；schema = lnrs。
#   - h59 端 PostgreSQL 15 自带 /usr/bin/{psql,pg_dump,pg_restore}，无需额外安装。
#   - dev → h59 走两步：本地 scp dump 到 h59 /tmp/ → ssh h59 执行 pg_restore。
#
# 使用方法（Git Bash，本机执行）：
#   ./scripts/migrate_dev_to_h59.sh                     # 复用仓库内已缓存的 dev dump
#   RE_EXPORT=1 ./scripts/migrate_dev_to_h59.sh        # 先重新从 dev 导出再推送
#   DUMP_FILE=backend/lnrs_migration_xxx.pdump \
#     ./scripts/migrate_dev_to_h59.sh                   # 用指定的 dump 文件
#
# 注意（与 dev → h42/h125 已知问题一致）：
#   - pg_restore 在 PG15 上会报 "transaction_timeout"，属正常现象，已过滤。
#   - pg_restore 会报 "模式 lnrs 已存在"（因 Step 2 已创建），属正常现象，已过滤。
#   - 必须先在 h59 上 DROP SCHEMA lnrs CASCADE，再用超级用户恢复，否则 COPY 会落到空表。
# ============================================================
set -euo pipefail

# ---- 本机路径 ------------------------------------------------------------
# 本机 PG 18（仅在 RE_EXPORT=1 时使用）
PG_BIN="/c/Program Files/PostgreSQL/18/bin"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEFAULT_DUMP="$REPO_ROOT/backend/lnrs_migration_20260725_083559.pdump"

# SSH 别名（在 ~/.ssh/config 中定义，root@192.168.1.59 免密）
H59_HOST="${H59_HOST:-h59}"
# h59 上的临时工作目录（脚本结束后可手工清理）
H59_TMP_DIR="${H59_TMP_DIR:-/tmp}"

# ---- 连接参数 ------------------------------------------------------------
DEV_HOST=127.0.0.1
DEV_PORT=5432
SUPER_PWD="${SUPER_PWD:-admin@pwd}"

# h59 端 PG15：本机监听 5432，DB = postgres，schema = lnrs
H59_PG_PORT=5432
H59_DB="${H59_DB:-postgres}"
H59_SCHEMA="${H59_SCHEMA:-lnrs}"

# 应用用户（与 .env.h42:31-32 对齐）
APP_USER="${APP_USER:-lnrs}"
APP_PWD="${APP_PWD:-lnrs_pwd}"

# ---- dump 文件选择 -------------------------------------------------------
if [[ "${RE_EXPORT:-0}" == "1" ]]; then
  LOCAL_DUMP="$REPO_ROOT/backend/lnrs_migration_$(date +%Y%m%d_%H%M%S).pdump"
else
  LOCAL_DUMP="${DUMP_FILE:-$DEFAULT_DUMP}"
fi
LOCAL_DUMP_ABS="$(cd "$(dirname "$LOCAL_DUMP")" && pwd)/$(basename "$LOCAL_DUMP")"
REMOTE_DUMP="$H59_TMP_DIR/lnrs_migration_$(date +%Y%m%d_%H%M%S).pdump"

# ---- 步骤 0：前置检查 ----------------------------------------------------
echo "=== 本机 dump 文件: $LOCAL_DUMP_ABS ==="
if [[ ! -f "$LOCAL_DUMP_ABS" ]]; then
  echo "ERROR: 找不到 dump 文件：$LOCAL_DUMP_ABS" >&2
  echo "       若需要重新导出，请使用 RE_EXPORT=1 $0" >&2
  exit 1
fi
ls -lh "$LOCAL_DUMP_ABS" | awk '{print "       size:", $5}'

echo "=== SSH 连通性测试 ==="
if ! ssh -o BatchMode=yes -o ConnectTimeout=5 "$H59_HOST" 'echo OK' >/dev/null 2>&1; then
  echo "ERROR: 无法免密 SSH 到 $H59_HOST，请先确认 ~/.ssh/config 与 192.168.1.59 上的 authorized_keys" >&2
  exit 1
fi
echo "       SSH OK -> $H59_HOST"

# ---- 步骤 1：（可选）重新从 dev 导出 -------------------------------------
if [[ "${RE_EXPORT:-0}" == "1" ]]; then
  echo "=== Step 1: 从 dev 重新导出（custom 格式，含结构+数据） ==="
  PGPASSWORD="$SUPER_PWD" "$PG_BIN/pg_dump.exe" \
    -h "$DEV_HOST" -p "$DEV_PORT" -U postgres -d postgres \
    --schema="$H59_SCHEMA" -Fc --no-owner --no-privileges \
    -f "$LOCAL_DUMP_ABS"
  LOCAL_DUMP_ABS="$(cd "$(dirname "$LOCAL_DUMP_ABS")" && pwd)/$(basename "$LOCAL_DUMP_ABS")"
  echo "Dump: $(ls -lh "$LOCAL_DUMP_ABS" | awk '{print $5}')"
else
  echo "=== Step 1: 跳过重新导出，复用现有 dump ==="
fi

# ---- 步骤 2：scp 到 h59 --------------------------------------------------
echo "=== Step 2: scp dump 到 $H59_HOST:$REMOTE_DUMP ==="
scp -q "$LOCAL_DUMP_ABS" "$H59_HOST:$REMOTE_DUMP"
ssh "$H59_HOST" "ls -lh $REMOTE_DUMP"

# ---- 步骤 3：在 h59 上 DROP SCHEMA + 重建 --------------------------------
echo "=== Step 3: 在 $H59_HOST 上清理目标 schema（postgres.$H59_SCHEMA） ==="
ssh "$H59_HOST" \
  "PGPASSWORD='$SUPER_PWD' psql -h 127.0.0.1 -p $H59_PG_PORT -U postgres -d $H59_DB \
     -c \"DROP SCHEMA IF EXISTS $H59_SCHEMA CASCADE; \
         CREATE SCHEMA $H59_SCHEMA AUTHORIZATION postgres; \
         GRANT ALL ON SCHEMA $H59_SCHEMA TO $APP_USER;\""

# ---- 步骤 4：在 h59 上 pg_restore -----------------------------------------
echo "=== Step 4: 在 $H59_HOST 上 pg_restore ==="
echo "（'transaction_timeout' 与 '模式 lnrs 已存在' 警告属正常现象，已过滤）"
ssh "$H59_HOST" \
  "PGPASSWORD='$SUPER_PWD' pg_restore \
     -h 127.0.0.1 -p $H59_PG_PORT -U postgres -d $H59_DB \
     --no-owner --no-privileges \
     '$REMOTE_DUMP' 2>&1 \
   | grep -Ev 'transaction_timeout|模式.*已经存在|schema .* already exists' || true"

# ---- 步骤 5：在 h59 上重新授权 --------------------------------------------
echo "=== Step 5: 在 $H59_HOST 上授权应用用户 $APP_USER ==="
ssh "$H59_HOST" \
  "PGPASSWORD='$SUPER_PWD' psql -h 127.0.0.1 -p $H59_PG_PORT -U postgres -d $H59_DB \
     -c \"GRANT ALL ON ALL TABLES    IN SCHEMA $H59_SCHEMA TO $APP_USER; \
         GRANT ALL ON ALL SEQUENCES IN SCHEMA $H59_SCHEMA TO $APP_USER; \
         GRANT ALL ON ALL FUNCTIONS IN SCHEMA $H59_SCHEMA TO $APP_USER;\""

# ---- 步骤 6：在 h59 上以应用用户身份 count(*) 验证 ------------------------
echo "=== Step 6: 验证（以应用用户 $APP_USER 登录，count(*) 抽查） ==="
ssh "$H59_HOST" \
  "PGPASSWORD='$APP_PWD' psql -h 127.0.0.1 -p $H59_PG_PORT -U $APP_USER -d $H59_DB \
     -c \"SELECT 'lnrs_anon_patient'      AS tbl, count(*) FROM $H59_SCHEMA.lnrs_anon_patient \
   UNION ALL SELECT 'lnrs_anon_exam',         count(*) FROM $H59_SCHEMA.lnrs_anon_exam \
   UNION ALL SELECT 'lnrs_anon_phi_audit',    count(*) FROM $H59_SCHEMA.lnrs_anon_phi_audit \
   UNION ALL SELECT 'lnrs_anon_report_text',  count(*) FROM $H59_SCHEMA.lnrs_anon_report_text \
   UNION ALL SELECT 'lnrs_anon_ingest_batch', count(*) FROM $H59_SCHEMA.lnrs_anon_ingest_batch \
   UNION ALL SELECT 'sys_user',               count(*) FROM $H59_SCHEMA.sys_user \
   UNION ALL SELECT 'sys_menu',               count(*) FROM $H59_SCHEMA.sys_menu;\""

# ---- 收尾 ---------------------------------------------------------------
echo ""
echo "=== 完成 ==="
echo "  本地 dump: $LOCAL_DUMP_ABS"
echo "  h59  dump: $REMOTE_DUMP  （如不再需要可执行 ssh h59 'rm $REMOTE_DUMP'）"
echo "  h59  schema 已重建于 postgres.$H59_SCHEMA"