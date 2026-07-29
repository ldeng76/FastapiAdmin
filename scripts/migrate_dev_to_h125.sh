#!/bin/bash
# ============================================================
# 标准迁移脚本：dev (PG18) → h125 (本机 PG，本机监听 5432)
#
# 设计要点：
#   - 与 scripts/migrate_dev_to_h42.sh 风格保持一致（pg_dump -Fc / 文件中转 / DROP+CREATE / pg_restore / GRANT / 验证）。
#   - 默认复用仓库内已存在的 dev 导出：backend/lnrs_migration_20260725_083559.pdump；
#     若设 RE_EXPORT=1 则重新导出并写到 backend/lnrs_migration_<时间戳>.pdump。
#   - h125 端运行 PostgreSQL（账户信息见 backend/env/.env.h125：USER=lnrs / PWD=lnrs_pwd_2026 / DB=lnrs）。
#   - 因脚本预期在 h125 (10.12.118.125) 上以 postgres 超级用户执行，
#     PG_BIN 与连接 host 默认走本机；如需从本机远程执行，修改 H125_HOST/SUPER_PWD 后即可。
#
# 使用方法（推荐在 h125 服务器本机 Git Bash 里执行）：
#   ./scripts/migrate_dev_to_h125.sh                    # 复用现有 dump
#   RE_EXPORT=1 ./scripts/migrate_dev_to_h125.sh       # 先重新从 dev 导出再导入
#   DUMP_FILE=backend/lnrs_migration_xxx.pdump ./scripts/migrate_dev_to_h125.sh
#
# 注意（与 dev → h42 已知问题一致）：
#   - pg_restore 在 PG15 上会报 "transaction_timeout"，属正常现象，已过滤。
#   - pg_restore 会报 "模式 lnrs 已存在"（因 Step 2 已创建），属正常现象，已过滤。
#   - 必须先在 h125 上 DROP SCHEMA lnrs CASCADE，再用超级用户恢复，否则 COPY 会落到空表。
# ============================================================
set -euo pipefail

# ---- 路径与导出文件 -------------------------------------------------------
# 本机 PG 18（如从 h125 远程到 dev，请改为对应路径并拷 dump 过去）
PG_BIN="/c/Program Files/PostgreSQL/18/bin"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEFAULT_DUMP="$REPO_ROOT/backend/lnrs_migration_20260725_083559.pdump"

# 重新导出（如需）
if [[ "${RE_EXPORT:-0}" == "1" ]]; then
  DUMP_FILE="$REPO_ROOT/backend/lnrs_migration_$(date +%Y%m%d_%H%M%S).pdump"
else
  DUMP_FILE="${DUMP_FILE:-$DEFAULT_DUMP}"
fi

# ---- 连接参数 --------------------------------------------------------------
DEV_HOST=127.0.0.1
DEV_PORT=5432

# h125 端：脚本预期在 10.12.118.125 上以 postgres 超级用户本机执行；
# 若你在开发机上远程执行，请改为 10.12.118.125
H125_HOST="${H125_HOST:-127.0.0.1}"
H125_PORT="${H125_PORT:-5432}"

SUPER_PWD="${SUPER_PWD:-admin@pwd}"
APP_USER="${APP_USER:-lnrs}"
APP_PWD="${APP_PWD:-lnrs_pwd_2026}"
APP_DB="${APP_DB:-lnrs}"

# ---- 步骤 -----------------------------------------------------------------
echo "=== dump 文件: $DUMP_FILE ==="
if [[ ! -f "$DUMP_FILE" ]]; then
  echo "ERROR: 找不到 dump 文件：$DUMP_FILE" >&2
  echo "       若需要重新导出，请使用 RE_EXPORT=1 $0" >&2
  exit 1
fi
ls -lh "$DUMP_FILE" | awk '{print "       size:", $5}'

if [[ "${RE_EXPORT:-0}" == "1" ]]; then
  echo "=== Step 1: 从 dev 重新导出（custom 格式，含结构+数据） ==="
  PGPASSWORD="$SUPER_PWD" "$PG_BIN/pg_dump.exe" \
    -h "$DEV_HOST" -p "$DEV_PORT" -U postgres -d postgres \
    --schema=lnrs -Fc --no-owner --no-privileges \
    -f "$DUMP_FILE"
  echo "Dump: $(ls -lh "$DUMP_FILE" | awk '{print $5}')"
else
  echo "=== Step 1: 跳过重新导出，复用现有 dump ==="
fi

echo "=== Step 2: 清理 h125 目标 schema（lnrs.$APP_DB） ==="
PGPASSWORD="$SUPER_PWD" "$PG_BIN/psql.exe" \
  -h "$H125_HOST" -p "$H125_PORT" -U postgres -d "$APP_DB" \
  -c "DROP SCHEMA IF EXISTS lnrs CASCADE; CREATE SCHEMA lnrs AUTHORIZATION postgres; GRANT ALL ON SCHEMA lnrs TO $APP_USER;"

echo "=== Step 3: 恢复到 h125（自定义 schema = postgres 默认 search_path） ==="
echo "（'transaction_timeout' 与 '模式 lnrs 已存在' 警告属正常现象，已过滤）"
PGPASSWORD="$SUPER_PWD" "$PG_BIN/pg_restore.exe" \
  -h "$H125_HOST" -p "$H125_PORT" -U postgres -d "$APP_DB" \
  --no-owner --no-privileges \
  "$DUMP_FILE" 2>&1 \
  | grep -Ev "transaction_timeout|模式.*已经存在|schema .* already exists" || true

echo "=== Step 4: 授权应用用户 $APP_USER ==="
PGPASSWORD="$SUPER_PWD" "$PG_BIN/psql.exe" \
  -h "$H125_HOST" -p "$H125_PORT" -U postgres -d "$APP_DB" \
  -c "GRANT ALL ON ALL TABLES IN SCHEMA lnrs TO $APP_USER; \
      GRANT ALL ON ALL SEQUENCES IN SCHEMA lnrs TO $APP_USER; \
      GRANT ALL ON ALL FUNCTIONS IN SCHEMA lnrs TO $APP_USER;"

echo "=== Step 5: 验证（以应用用户 lnrs 登录） ==="
PGPASSWORD="$APP_PWD" "$PG_BIN/psql.exe" \
  -h "$H125_HOST" -p "$H125_PORT" -U "$APP_USER" -d "$APP_DB" \
  -c "SELECT 'lnrs_anon_patient'    AS tbl, count(*) FROM lnrs.lnrs_anon_patient \
   UNION ALL SELECT 'lnrs_anon_exam',       count(*) FROM lnrs.lnrs_anon_exam \
   UNION ALL SELECT 'lnrs_anon_phi_audit',  count(*) FROM lnrs.lnrs_anon_phi_audit \
   UNION ALL SELECT 'lnrs_anon_report_text',count(*) FROM lnrs.lnrs_anon_report_text \
   UNION ALL SELECT 'lnrs_anon_ingest_batch',count(*) FROM lnrs.lnrs_anon_ingest_batch \
   UNION ALL SELECT 'sys_user',             count(*) FROM lnrs.sys_user \
   UNION ALL SELECT 'sys_menu',             count(*) FROM lnrs.sys_menu;"

echo "=== 完成，dump 文件保留在: $DUMP_FILE ==="
