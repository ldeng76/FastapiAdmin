#!/bin/bash
# ============================================================
# 标准迁移脚本：dev (PG18) → h42 (PG15)
# 使用方法：Git Bash 中执行 ./scripts/migrate_dev_to_h42.sh
#
# 注意：
#   - pg_restore 会报 "transaction_timeout" 错误（PG15 不支持），属正常现象，可忽略
#   - pg_restore 会报 "模式 lnrs 已存在"（因为 Step 2 已创建），属正常现象，可忽略
# ============================================================

PG_BIN="/c/Program Files/PostgreSQL/18/bin"
DUMP_FILE="backend/lnrs_migration_$(date +%Y%m%d_%H%M%S).pdump"

DEV_HOST=127.0.0.1
DEV_PORT=5432
H42_HOST=192.168.1.59
H42_PORT=5432
SUPER_PWD=admin@pwd
APP_USER=lnrs
APP_PWD=lnrs_pwd

echo "=== Step 1: 从 dev 导出（custom 格式，含结构+数据） ==="
PGPASSWORD="$SUPER_PWD" "$PG_BIN/pg_dump.exe" \
  -h $DEV_HOST -p $DEV_PORT -U postgres -d postgres \
  --schema=lnrs -Fc --no-owner --no-privileges \
  -f "$DUMP_FILE"
echo "Dump: $(ls -lh $DUMP_FILE | awk '{print $5}')"

echo "=== Step 2: 清理 h42 目标 schema ==="
PGPASSWORD="$SUPER_PWD" "$PG_BIN/psql.exe" \
  -h $H42_HOST -p $H42_PORT -U postgres -d postgres \
  -c "DROP SCHEMA IF EXISTS lnrs CASCADE; CREATE SCHEMA lnrs AUTHORIZATION postgres; GRANT ALL ON SCHEMA lnrs TO $APP_USER;"

echo "=== Step 3: 恢复到 h42 ==="
echo "（'transaction_timeout' 和 '模式已存在' 错误属正常现象，可忽略）"
PGPASSWORD="$SUPER_PWD" "$PG_BIN/pg_restore.exe" \
  -h $H42_HOST -p $H42_PORT -U postgres -d postgres \
  --no-owner --no-privileges \
  "$DUMP_FILE" 2>&1 | grep -v "transaction_timeout" | grep -v "模式.*已经存在"

echo "=== Step 4: 授权应用用户 ==="
PGPASSWORD="$SUPER_PWD" "$PG_BIN/psql.exe" \
  -h $H42_HOST -p $H42_PORT -U postgres -d postgres \
  -c "GRANT ALL ON ALL TABLES IN SCHEMA lnrs TO $APP_USER; GRANT ALL ON ALL SEQUENCES IN SCHEMA lnrs TO $APP_USER; GRANT ALL ON ALL FUNCTIONS IN SCHEMA lnrs TO $APP_USER;"

echo "=== Step 5: 验证 ==="
PGPASSWORD="$APP_PWD" "$PG_BIN/psql.exe" \
  -h $H42_HOST -p $H42_PORT -U $APP_USER -d postgres \
  -c "SELECT 'patient' as tbl, count(*) FROM lnrs.lnrs_anon_patient UNION ALL SELECT 'exam', count(*) FROM lnrs.lnrs_anon_exam UNION ALL SELECT 'phi_audit', count(*) FROM lnrs.lnrs_anon_phi_audit UNION ALL SELECT 'report_text', count(*) FROM lnrs.lnrs_anon_report_text UNION ALL SELECT 'ingest_batch', count(*) FROM lnrs.lnrs_anon_ingest_batch;"

echo "=== 完成，dump 文件保留在: $DUMP_FILE ==="
