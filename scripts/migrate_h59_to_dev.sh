#!/bin/bash
# ============================================================
# 反向同步脚本：h59 (192.168.1.59, PG15) → dev (本机 PG18)
#
# 将 h59 上 postgres 库的 lnrs schema 全量同步到本机 postgres 库
# 的 lnrs schema（先 DROP 原 schema 再恢复，目标端数据会全部清空）。
# 与 scripts/migrate_dev_to_h59.sh 方向相反，经验教训一致：
#   - 必须用 pg_dump -Fc custom 格式经文件中转（scp），不能管道直传；
#   - 必须先 DROP SCHEMA lnrs CASCADE 再 pg_restore，否则数据落到旧表；
#   - 恢复后必须重新 GRANT 给应用用户 lnrs。
#   - PG15 dump → PG18 restore 属低版本导高版本，完全兼容
#     （无 dev→h59 方向的 transaction_timeout 问题）。
#
# 使用方法（Git Bash，本机执行）：
#   ./scripts/migrate_h59_to_dev.sh
#   KEEP_REMOTE_DUMP=1 ./scripts/migrate_h59_to_dev.sh   # 保留 h59 上的临时 dump
#
# 环境变量可覆盖（默认值见下方 “---- 连接参数”）：
#   H59_HOST / H59_DB / H59_SCHEMA
#   DEV_HOST / DEV_PORT / DEV_DB
#   SUPER_PWD / APP_USER / APP_PWD
#   PG_BIN / PG_DATA（本机 PG18 的 bin 目录与数据目录）
# ============================================================
set -euo pipefail

# ---- 本机路径 ------------------------------------------------------------
PG_BIN="${PG_BIN:-/c/Program Files/PostgreSQL/18/bin}"
PG_DATA="${PG_DATA:-C:/Program Files/PostgreSQL/18/data}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# SSH 别名（在 ~/.ssh/config 中定义，root@192.168.1.59 免密）
H59_HOST="${H59_HOST:-h59}"
H59_TMP_DIR="${H59_TMP_DIR:-/tmp}"

# ---- 连接参数 ------------------------------------------------------------
# 源：h59 端 PG15（本机监听 5432，DB = postgres，schema = lnrs）
H59_PG_PORT=5432
H59_DB="${H59_DB:-postgres}"
H59_SCHEMA="${H59_SCHEMA:-lnrs}"

# 目标：本机 dev PG18
DEV_HOST="${DEV_HOST:-127.0.0.1}"
DEV_PORT="${DEV_PORT:-5432}"
DEV_DB="${DEV_DB:-postgres}"

SUPER_PWD="${SUPER_PWD:-admin@pwd}"
APP_USER="${APP_USER:-lnrs}"
APP_PWD="${APP_PWD:-lnrs_pwd}"

TS="$(date +%Y%m%d_%H%M%S)"
REMOTE_DUMP="$H59_TMP_DIR/lnrs_migration_h59_${TS}.pdump"
LOCAL_DUMP="$REPO_ROOT/backend/lnrs_migration_h59_${TS}.pdump"

psql_local() {
  PGPASSWORD="$SUPER_PWD" "$PG_BIN/psql.exe" -h "$DEV_HOST" -p "$DEV_PORT" -U postgres -d "$DEV_DB" "$@"
}

psql_h59() {
  ssh "$H59_HOST" "PGPASSWORD='$SUPER_PWD' psql -h 127.0.0.1 -p $H59_PG_PORT -U postgres -d $H59_DB $*"
}

# ---- 步骤 0：前置检查 ----------------------------------------------------
echo "=== SSH 连通性测试 ==="
if ! ssh -o BatchMode=yes -o ConnectTimeout=5 "$H59_HOST" 'echo OK' >/dev/null 2>&1; then
  echo "ERROR: 无法免密 SSH 到 $H59_HOST，请先确认 ~/.ssh/config 与 192.168.1.59 上的 authorized_keys" >&2
  exit 1
fi
echo "       SSH OK -> $H59_HOST"

echo "=== 本机 PG 连接测试 ==="
if ! psql_local -tAc "SELECT 1;" >/dev/null 2>&1; then
  echo "       本机 PG 未启动，尝试 pg_ctl 启动（$PG_DATA）..."
  "$PG_BIN/pg_ctl.exe" -D "$PG_DATA" -l "$TEMP/pg18.log" -w start
  if ! psql_local -tAc "SELECT 1;" >/dev/null 2>&1; then
    echo "ERROR: 本机 PG 启动后仍无法连接，请检查 $TEMP/pg18.log 与 data 目录权限" >&2
    exit 1
  fi
fi
echo "       本机 PG OK ($DEV_HOST:$DEV_PORT/$DEV_DB)"

# ---- 步骤 1：在 h59 上导出 ------------------------------------------------
echo "=== Step 1: 在 $H59_HOST 上 pg_dump（custom 格式，含结构+数据） ==="
ssh "$H59_HOST" \
  "PGPASSWORD='$SUPER_PWD' pg_dump -h 127.0.0.1 -p $H59_PG_PORT -U postgres -d $H59_DB \
     --schema='$H59_SCHEMA' -Fc --no-owner --no-privileges \
     -f '$REMOTE_DUMP' && ls -lh '$REMOTE_DUMP'"

# ---- 步骤 2：scp 拉回本机 -------------------------------------------------
echo "=== Step 2: scp 拉回本机 $LOCAL_DUMP ==="
mkdir -p "$REPO_ROOT/backend"
scp -q "$H59_HOST:$REMOTE_DUMP" "$LOCAL_DUMP"
ls -lh "$LOCAL_DUMP" | awk '{print "       size:", $5}'

# ---- 步骤 3：本机清理目标 schema ------------------------------------------
echo "=== Step 3: 本机清空目标 schema（$DEV_DB.$H59_SCHEMA，CASCADE） ==="
psql_local -c "DROP SCHEMA IF EXISTS $H59_SCHEMA CASCADE; \
               CREATE SCHEMA $H59_SCHEMA AUTHORIZATION postgres; \
               GRANT ALL ON SCHEMA $H59_SCHEMA TO $APP_USER;"

# ---- 步骤 4：本机 pg_restore ----------------------------------------------
echo "=== Step 4: 本机 pg_restore ==="
PGPASSWORD="$SUPER_PWD" "$PG_BIN/pg_restore.exe" \
  -h "$DEV_HOST" -p "$DEV_PORT" -U postgres -d "$DEV_DB" \
  --no-owner --no-privileges \
  "$LOCAL_DUMP" 2>&1 \
  | grep -Ev '模式.*已经存在|schema .* already exists' || true

# ---- 步骤 5：本机重新授权 --------------------------------------------------
echo "=== Step 5: 授权应用用户 $APP_USER ==="
psql_local -c "GRANT ALL ON ALL TABLES    IN SCHEMA $H59_SCHEMA TO $APP_USER; \
               GRANT ALL ON ALL SEQUENCES IN SCHEMA $H59_SCHEMA TO $APP_USER; \
               GRANT ALL ON ALL FUNCTIONS IN SCHEMA $H59_SCHEMA TO $APP_USER;"

# ---- 步骤 6：源/目标全表 count(*) 对比验证 ---------------------------------
echo "=== Step 6: 验证（源/目标逐表 count(*) 对比） ==="
# 以源端表清单为准，动态拼 UNION ALL，两端各跑一遍后 diff
TABLE_LIST="$(ssh "$H59_HOST" "PGPASSWORD='$SUPER_PWD' psql -h 127.0.0.1 -p $H59_PG_PORT -U postgres -d $H59_DB -tAc \"SELECT tablename FROM pg_tables WHERE schemaname='$H59_SCHEMA' ORDER BY 1;\"")"
if [[ -z "$TABLE_LIST" ]]; then
  echo "ERROR: 源端 $H59_HOST 上 $H59_SCHEMA schema 无表" >&2
  exit 1
fi

COUNT_SQL=""
while IFS= read -r t; do
  COUNT_SQL+="SELECT '$t' AS tbl, count(*) FROM $H59_SCHEMA.\"$t\" UNION ALL "
done <<< "$TABLE_LIST"
COUNT_SQL="${COUNT_SQL% UNION ALL };"

# 本机 Windows psql 输出为 CRLF，远端为 LF；统一去掉 \r 与行尾空白后再比较
SRC_COUNTS="$(psql_h59 "-tAc \"$COUNT_SQL\"" | tr -d '\r' | sed -e 's/[[:space:]]*$//')"
DST_COUNTS="$(psql_local -tAc "$COUNT_SQL" | tr -d '\r' | sed -e 's/[[:space:]]*$//')"

echo "$SRC_COUNTS" | awk '{printf "  src  %-32s %s\n", $1, $2}'
if [[ "$SRC_COUNTS" == "$DST_COUNTS" ]]; then
  echo "       行数对比：源/目标完全一致 ✔"
else
  echo "ERROR: 源/目标行数不一致：" >&2
  diff <(echo "$SRC_COUNTS") <(echo "$DST_COUNTS") >&2 || true
  exit 1
fi

# ---- 步骤 7：以应用用户身份验证只读 ----------------------------------------
echo "=== Step 7: 以应用用户 $APP_USER 登录抽查 ==="
PGPASSWORD="$APP_PWD" "$PG_BIN/psql.exe" -h "$DEV_HOST" -p "$DEV_PORT" -U "$APP_USER" -d "$DEV_DB" \
  -tAc "SELECT count(*) FROM $H59_SCHEMA.sys_user;" | awk '{print "       sys_user rows:", $1}'

# ---- 收尾 -----------------------------------------------------------------
if [[ "${KEEP_REMOTE_DUMP:-0}" != "1" ]]; then
  ssh "$H59_HOST" "rm -f '$REMOTE_DUMP'"
fi
echo ""
echo "=== 完成 ==="
echo "  本地 dump: $LOCAL_DUMP（保留，可作为 h59 数据的时间点备份）"
[[ "${KEEP_REMOTE_DUMP:-0}" == "1" ]] && echo "  h59  dump: $REMOTE_DUMP（已保留）" \
                                     || echo "  h59  临时 dump 已清理"
echo "  本机 $DEV_DB.$H59_SCHEMA 已全量重建（表数：$(echo "$TABLE_LIST" | wc -l)）"
