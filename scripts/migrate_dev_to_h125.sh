#!/bin/bash
# ============================================================
# 标准迁移脚本：dev (本机 PG18) → h125 (10.12.118.125 PG18)
#
# 执行位置：开发机（Windows + Git Bash），通过 SSH 免密远程操作 h125。
#   ssh 免密别名：backend-10-12-118-125 （~/.ssh/config 已配置）
#
# 设计要点：
#   - 本机 pg_dump 导出 dev 的 lnrs schema（custom 格式，含结构+数据）
#   - scp 把 dump 文件传到 h125 的临时目录
#   - ssh 远程执行：DROP+CREATE schema → pg_restore → GRANT → 验证
#   - 默认复用仓库内已存在的 dev 导出：backend/lnrs_migration_20260725_083559.pdump；
#     RE_EXPORT=1 则重新导出并写到 backend/lnrs_migration_<时间戳>.pdump。
#
# 使用方法（在开发机 Git Bash 里执行）：
#   ./scripts/migrate_dev_to_h125.sh                       # 复用现有 dump 导入 h125
#   RE_EXPORT=1 ./scripts/migrate_dev_to_h125.sh           # 先重新从 dev 导出再导入
#   DUMP_FILE=backend/lnrs_migration_xxx.pdump ./scripts/migrate_dev_to_h125.sh
#   KEEP_REMOTE_DUMP=0 ./scripts/migrate_dev_to_h125.sh    # 导入后删除 h125 上的 dump（默认保留）
#
#  验证：ssh backend-10-12-118-125 'PGPASSWORD=lnrs_pwd_2026 /home/dzy/pg18/bin/psql -h 127.0.0.1 -U lnrs -d lnrs -c "SELECT count(*) FROM lnrs.lnrs_anon_patient;"'
#
# 连接参数（均可用环境变量覆盖）：
#   - dev:  127.0.0.1:5432, postgres/admin@pwd, db=postgres
#   - h125: 通过 SSH 别名 backend-10-12-118-125，PG 本机 127.0.0.1:5432，
#           postgres/admin@pwd（超级用户），lnrs/lnrs_pwd_2026（应用用户），db=lnrs
#
# 注意：
#   - pg_restore 在 PG15 上会报 "transaction_timeout"，属正常现象，已过滤。
#   - pg_restore 会报 "模式 lnrs 已存在"（因 Step 2 已创建），属正常现象，已过滤。
#   - 必须先在 h125 上 DROP SCHEMA lnrs CASCADE，再用超级用户恢复，否则 COPY 会落到空表。
#
# ============================================================
set -euo pipefail

# ---- 路径与导出文件 -------------------------------------------------------
# 开发机本机 PG 18（用于 pg_dump 导出 dev）
PG_BIN="${PG_BIN:-/c/Program Files/PostgreSQL/18/bin}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEFAULT_DUMP="$REPO_ROOT/backend/lnrs_migration_20260725_083559.pdump"

# 重新导出（如需）
if [[ "${RE_EXPORT:-0}" == "1" ]]; then
  DUMP_FILE="$REPO_ROOT/backend/lnrs_migration_$(date +%Y%m%d_%H%M%S).pdump"
else
  DUMP_FILE="${DUMP_FILE:-$DEFAULT_DUMP}"
fi

# ---- 连接参数（dev：本机） ------------------------------------------------
DEV_HOST="${DEV_HOST:-127.0.0.1}"
DEV_PORT="${DEV_PORT:-5432}"
DEV_DB="${DEV_DB:-postgres}"
SUPER_PWD="${SUPER_PWD:-admin@pwd}"   # postgres 超级用户密码（dev 与 h125 相同）

# ---- 连接参数（h125：远程，经 SSH） ---------------------------------------
# SSH 免密别名（~/.ssh/config 已配好，免密登录到 h125 的 dzy 用户）
SSH_ALIAS="${SSH_ALIAS:-backend-10-12-118-125}"
# h125 上 PG bin 路径（PG18 装在 dzy 用户主目录下）
REMOTE_PG_BIN="${REMOTE_PG_BIN:-/home/dzy/pg18/bin}"
# h125 上临时存放 dump 的目录（dzy 可写）
REMOTE_TMP_DIR="${REMOTE_TMP_DIR:-/tmp}"
# h125 上 PG 连接（PG 监听本机 5432，postgres/lnrs 均可 TCP 连 127.0.0.1）
REMOTE_PG_HOST="${REMOTE_PG_HOST:-127.0.0.1}"
REMOTE_PG_PORT="${REMOTE_PG_PORT:-5432}"
REMOTE_APP_USER="${REMOTE_APP_USER:-lnrs}"
REMOTE_APP_PWD="${REMOTE_APP_PWD:-lnrs_pwd_2026}"
REMOTE_APP_DB="${REMOTE_APP_DB:-lnrs}"
# 导入后是否保留 h125 上的 dump 文件（1=保留，0=删除）
KEEP_REMOTE_DUMP="${KEEP_REMOTE_DUMP:-1}"

DUMP_BASENAME="$(basename "$DUMP_FILE")"
REMOTE_DUMP_PATH="$REMOTE_TMP_DIR/$DUMP_BASENAME"

# 远程执行 SQL（postgres 超级用户）。
# 用法（从 stdin 读取 SQL，SQL 内部可自由使用单引号字面量）：
#   remote_psql_super <<'SQL'
#   DROP SCHEMA IF EXISTS lnrs CASCADE;
#   SQL
# 实现要点：SQL 通过 stdin 管道喂给远程 psql -f -，完全不经过远程 shell 解析，
# 彻底避免层层引号/变量转义陷阱。连接参数（密码/host 等）仍走远程命令行，
# 但这些值都是脚本常量，不含特殊字符。
remote_psql_super() {
  ssh "$SSH_ALIAS" \
    "PGPASSWORD='$SUPER_PWD' '$REMOTE_PG_BIN/psql' -h '$REMOTE_PG_HOST' -p '$REMOTE_PG_PORT' -U postgres -d '$REMOTE_APP_DB' -v ON_ERROR_STOP=1 -f -"
}

# 远程执行 SQL（lnrs 应用用户，验证用）。用法同上。
remote_psql_app() {
  ssh "$SSH_ALIAS" \
    "PGPASSWORD='$REMOTE_APP_PWD' '$REMOTE_PG_BIN/psql' -h '$REMOTE_PG_HOST' -p '$REMOTE_PG_PORT' -U '$REMOTE_APP_USER' -d '$REMOTE_APP_DB' -v ON_ERROR_STOP=1 -f -"
}

# ---- Step 1: 导出 dev（本机） ---------------------------------------------
if [[ "${RE_EXPORT:-0}" == "1" ]]; then
  echo "=== Step 1: 从 dev 重新导出（本机 pg_dump，custom 格式，含结构+数据） ==="
  echo "    $DUMP_FILE"
  PGPASSWORD="$SUPER_PWD" "$PG_BIN/pg_dump.exe" \
    -h "$DEV_HOST" -p "$DEV_PORT" -U postgres -d "$DEV_DB" \
    --schema=lnrs -Fc --no-owner --no-privileges \
    -f "$DUMP_FILE"
  echo "    Dump 完成: $(ls -lh "$DUMP_FILE" | awk '{print $5}')"
else
  echo "=== Step 1: 跳过重新导出，复用现有 dump ==="
  if [[ ! -f "$DUMP_FILE" ]]; then
    echo "ERROR: 找不到 dump 文件：$DUMP_FILE" >&2
    echo "       若需要重新导出，请使用 RE_EXPORT=1 $0" >&2
    exit 1
  fi
  ls -lh "$DUMP_FILE" | awk '{print "       size:", $5}'
fi

# ---- Step 2: 传输 dump 到 h125（scp） ------------------------------------
echo "=== Step 2: 传输 dump 到 h125（scp → $REMOTE_DUMP_PATH） ==="
scp -q "$DUMP_FILE" "$SSH_ALIAS:$REMOTE_DUMP_PATH"
echo "    传输完成"

# ---- Step 3: 清理 h125 目标 schema ---------------------------------------
echo "=== Step 3: 清理 h125 目标 schema（DROP + CREATE lnrs） ==="
remote_psql_super <<SQL
DROP SCHEMA IF EXISTS lnrs CASCADE;
CREATE SCHEMA lnrs AUTHORIZATION postgres;
GRANT ALL ON SCHEMA lnrs TO $REMOTE_APP_USER;
SQL

# ---- Step 4: 恢复到 h125（远程 pg_restore） -------------------------------
echo "=== Step 4: 恢复到 h125（远程 pg_restore） ==="
echo "    （'transaction_timeout' 与 '模式 lnrs 已存在' 警告属正常现象，已过滤）"
ssh "$SSH_ALIAS" \
  "PGPASSWORD='$SUPER_PWD' '$REMOTE_PG_BIN/pg_restore' -h '$REMOTE_PG_HOST' -p '$REMOTE_PG_PORT' -U postgres -d '$REMOTE_APP_DB' --no-owner --no-privileges '$REMOTE_DUMP_PATH'" 2>&1 \
  | grep -Ev "transaction_timeout|模式.*已经存在|schema .* already exists" || true

# ---- Step 5: 授权应用用户 -------------------------------------------------
echo "=== Step 5: 授权应用用户 $REMOTE_APP_USER ==="
remote_psql_super <<SQL
GRANT ALL ON ALL TABLES IN SCHEMA lnrs TO $REMOTE_APP_USER;
GRANT ALL ON ALL SEQUENCES IN SCHEMA lnrs TO $REMOTE_APP_USER;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA lnrs TO $REMOTE_APP_USER;
SQL

# ---- Step 6: 验证（以应用用户 lnrs 登录） ---------------------------------
echo "=== Step 6: 验证（以应用用户 $REMOTE_APP_USER 登录 h125） ==="
remote_psql_app <<'SQL'
SELECT 'lnrs_anon_patient'      AS tbl, count(*) FROM lnrs.lnrs_anon_patient
UNION ALL SELECT 'lnrs_anon_exam',        count(*) FROM lnrs.lnrs_anon_exam
UNION ALL SELECT 'lnrs_anon_visit_detail',count(*) FROM lnrs.lnrs_anon_visit_detail
UNION ALL SELECT 'lnrs_anon_lab_result',  count(*) FROM lnrs.lnrs_anon_lab_result
UNION ALL SELECT 'lnrs_anon_order',       count(*) FROM lnrs.lnrs_anon_order
UNION ALL SELECT 'lnrs_anon_phi_audit',   count(*) FROM lnrs.lnrs_anon_phi_audit
UNION ALL SELECT 'lnrs_anon_report_text', count(*) FROM lnrs.lnrs_anon_report_text
UNION ALL SELECT 'lnrs_anon_ingest_batch',count(*) FROM lnrs.lnrs_anon_ingest_batch
UNION ALL SELECT 'sys_user',              count(*) FROM sys_user
UNION ALL SELECT 'sys_menu',              count(*) FROM sys_menu;
SQL

# ---- Step 7: 清理远程临时 dump（可选） ------------------------------------
if [[ "$KEEP_REMOTE_DUMP" == "0" ]]; then
  echo "=== Step 7: 删除 h125 上的临时 dump（KEEP_REMOTE_DUMP=0） ==="
  ssh "$SSH_ALIAS" "rm -f '$REMOTE_DUMP_PATH'"
  echo "    已删除 $REMOTE_DUMP_PATH"
else
  echo "=== Step 7: 保留 h125 上的 dump（$REMOTE_DUMP_PATH，KEEP_REMOTE_DUMP=1） ==="
fi

echo "=== 完成 ==="
echo "    本机 dump 文件: $DUMP_FILE"
echo "    h125 dump 文件: $REMOTE_DUMP_PATH"
