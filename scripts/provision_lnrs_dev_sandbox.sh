#!/usr/bin/env bash
# 重建测试沙箱库 lnrs_dev（同 PG 实例上的独立数据库）。
#
# 用途：pytest 里所有**写库**测试在此库上运行，真库永不被测试触碰。
# 背景：2026-09-20 事故 —— 测试用真中心名清理 batch，级联删掉 168,260 行 dicom_series。
#      复盘 docs/etl2/findings/incident-20260920-test-cascade-delete.md
#
# 为什么是「独立数据库」而不是「独立 schema」：
#   代码里有 470 处硬编码 `lnrs.` 前缀（Python 177 + SQL 293），会绕过 search_path。
#   在独立数据库里 `lnrs` 是另一个同名 schema → 硬编码原样生效且指向沙箱。
#   schema 方案要重写 470 处，且每新增一处就静默漏出沙箱。
#
# 内容：
#   1) 结构 —— 以 **live 库为准**（pg_dump --schema-only），不是以 DDL 文件为准：
#      live 与 backend/sql/postgres/0006 的外键集已分叉（见复盘 §3.1）。
#   2) 参考数据 —— 字典 / 中心注册 / 菜单 / 用户等**小表**全量复制；
#      医学数据表（lnrs_anon_*）**不复制**（空表，测试自建数据）。
#
# 用法：
#   bash scripts/provision_lnrs_dev_sandbox.sh          # 重建（会 DROP 现有 lnrs_dev）
#   bash scripts/provision_lnrs_dev_sandbox.sh --keep   # 已存在则跳过
#
# 前置：需要 postgres 超管（lnrs 角色无 CREATE DATABASE 权限）。
set -euo pipefail

SRC_HOST=127.0.0.1
SRC_PORT=5432
SRC_DB=postgres
APP_USER=lnrs
APP_PWD=lnrs_pwd
SUPER_USER=postgres
SUPER_PWD=admin@pwd

SANDBOX_DB=lnrs_dev
TMP_SQL=$(mktemp -d)/lnrs_dev.sql

KEEP=0
[ "${1:-}" = "--keep" ] && KEEP=1

psql_super() { PGPASSWORD="$SUPER_PWD" psql -h "$SRC_HOST" -p "$SRC_PORT" -U "$SUPER_USER" "$@"; }
psql_app()   { PGPASSWORD="$APP_PWD"   psql -h "$SRC_HOST" -p "$SRC_PORT" -U "$APP_USER"   "$@"; }

echo "[1/6] 检查是否已存在 $SANDBOX_DB"
exists=$(psql_super -d "$SRC_DB" -tAc "SELECT 1 FROM pg_database WHERE datname='$SANDBOX_DB'")
if [ -n "$exists" ]; then
  if [ "$KEEP" = "1" ]; then
    echo "      $SANDBOX_DB 已存在，--keep 指定跳过。"; exit 0
  fi
  echo "      DROP 现有 $SANDBOX_DB"
  psql_super -d "$SRC_DB" -q -c "DROP DATABASE IF EXISTS $SANDBOX_DB;"
fi

echo "[2/6] CREATE DATABASE $SANDBOX_DB"
psql_super -d "$SRC_DB" -q -c "CREATE DATABASE $SANDBOX_DB OWNER $SUPER_USER;"

echo "[3/6] 建 schema + 扩展（与 live 同 schema 归属）"
psql_super -d "$SANDBOX_DB" -q -v ON_ERROR_STOP=1 -c "
CREATE SCHEMA lnrs AUTHORIZATION $SUPER_USER;
CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA lnrs;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements WITH SCHEMA lnrs;"

echo "[4/6] 结构：从 live 库 pg_dump --schema-only（剥掉 CREATE SCHEMA 行）"
PGPASSWORD="$APP_PWD" pg_dump -h "$SRC_HOST" -p "$SRC_PORT" -U "$APP_USER" -d "$SRC_DB" \
  --schema=lnrs --schema-only --no-owner --no-privileges \
  | sed '/^CREATE SCHEMA lnrs;$/d' > "$TMP_SQL"
psql_super -d "$SANDBOX_DB" -q -v ON_ERROR_STOP=1 -f "$TMP_SQL" >/dev/null

echo "[5/6] 参考数据：小表全量（排除医学数据表与临时/备份表）"
PGPASSWORD="$APP_PWD" pg_dump -h "$SRC_HOST" -p "$SRC_PORT" -U "$APP_USER" -d "$SRC_DB" \
  --schema=lnrs --data-only --no-owner \
  --exclude-table='lnrs.lnrs_anon_*' \
  --exclude-table='lnrs.verify_*' \
  --exclude-table='lnrs.lnrs_tmp_*' \
  --exclude-table='lnrs.*_bak_*' \
  --exclude-table='lnrs.p_*_bak_*' \
  --exclude-table='lnrs._*' \
  --exclude-table='lnrs.gen_demo*' \
  --exclude-table='lnrs.sys_log' \
  --exclude-table='lnrs.apscheduler_jobs' \
  > "${TMP_SQL}.data"
psql_super -d "$SANDBOX_DB" -q -v ON_ERROR_STOP=1 \
  -c "SET session_replication_role = replica;" \
  -f "${TMP_SQL}.data" >/dev/null

echo "[6/6] 授权给 $APP_USER"
psql_super -d "$SANDBOX_DB" -q -v ON_ERROR_STOP=1 -c "
GRANT CONNECT ON DATABASE $SANDBOX_DB TO $APP_USER;
GRANT USAGE, CREATE ON SCHEMA lnrs TO $APP_USER;
GRANT ALL ON ALL TABLES    IN SCHEMA lnrs TO $APP_USER;
GRANT ALL ON ALL SEQUENCES IN SCHEMA lnrs TO $APP_USER;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA lnrs TO $APP_USER;
ALTER DEFAULT PRIVILEGES IN SCHEMA lnrs GRANT ALL ON TABLES    TO $APP_USER;
ALTER DEFAULT PRIVILEGES IN SCHEMA lnrs GRANT ALL ON SEQUENCES TO $APP_USER;
ALTER DEFAULT PRIVILEGES IN SCHEMA lnrs GRANT ALL ON FUNCTIONS TO $APP_USER;"

echo
echo "完成。校验："
psql_app -d "$SANDBOX_DB" -c "
SELECT 'tables'      k, COUNT(*)::text v FROM pg_tables WHERE schemaname='lnrs'
UNION ALL SELECT 'views',      COUNT(*)::text FROM pg_views WHERE schemaname='lnrs'
UNION ALL SELECT 'FKs',        COUNT(*)::text FROM pg_constraint c JOIN pg_class r ON r.oid=c.conrelid
                                       JOIN pg_namespace n ON n.oid=r.relnamespace
                                       WHERE n.nspname='lnrs' AND c.contype='f'
UNION ALL SELECT 'med_hospital',   COUNT(*)::text FROM lnrs.med_hospital
UNION ALL SELECT 'sys_dict_data',  COUNT(*)::text FROM lnrs.sys_dict_data
UNION ALL SELECT 'lnrs_anon_patient（应为 0，医学数据不复制）', COUNT(*)::text FROM lnrs.lnrs_anon_patient;"
echo
echo "跑写库测试：cd backend && ENVIRONMENT=test uv run pytest tests/anon_etl/"
