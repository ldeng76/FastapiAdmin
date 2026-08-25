#!/bin/bash
# ============================================================
# 定向增量同步：dev (本机 PG18) → h59 (192.168.1.59, PG15)
# 范围：珠江 0814 + CT 首导 + CT 正文修复 + ct0820 切换 共 5 个 batch：
#   - 25f41209-...-5e71fb992ebe  0814 patient 导入
#   - 2f5e131c-...-c1b5e6c5f4f8  全量 CT 首导
#   - 3a2baddf-...-1bcab52f1743  CT 正文修复重跑
#   - d65bff4e-...-e58bcfd821f5  (0719 sample 修复)
#   - 4ba87bae-...-f0a87b8d9437  ct0820 切换 (nodule_imaging 100% 重合 + body_clean/detail_json 全部刷新)
# 同步范围与 0814 脚本一致（patient / exam CT / report_text / exam_detail / phi_audit / med_dict_mapping）。
# 与 migrate_dev_to_h59.sh（全量 DROP+restore）的区别：
#   - 不 DROP schema、不删除目标端任何行，全部 ON CONFLICT upsert；
#   - 行级过滤，只搬运本次导入的足迹（可重复执行，幂等）。
#
# 使用方法（Git Bash，本机执行）：
#   ./scripts/migrate_dev_to_h59_zhujiang_ct0820.sh
#   BATCH_IDS='<uuid1>,<uuid2>' ./scripts/...   # 同步其他批次
#   KEEP_FILES=1 ./scripts/...                  # 保留两端临时文件
# ============================================================
set -euo pipefail

# ---- 批次定义（本次导入足迹） ----------------------------------------------
# 珠江 CT 系列共 5 个 batch（含 0814 patient / 全量 CT 首导 / CT 正文修复 / ct0820 切换）。
# 重跑会刷新 report_text.body_clean、exam_detail.created_batch_id 与
# patient.last_seen_batch_id，故同步范围必须包含全部相关批次。
# 复用本脚本同步新批次时，用 BATCH_IDS 覆盖（逗号分隔 UUID 列表）。
BATCH_IDS="${BATCH_IDS:-25f41209-8fdc-48af-a8f4-5e71fb992ebe,2f5e131c-0e0c-4d49-806b-c1b5e6c5f4f8,3a2baddf-0961-4555-b8e6-1bcab52f1743,d65bff4e-ff72-4ef9-986c-e58bcfd821f5,4ba87bae-5607-4fd1-b3c1-f0a87b8d9437}"
CENTER="${CENTER:-zhujiang}"
IN_LIST=""
IFS=',' read -ra _BIDS <<< "$BATCH_IDS"
for _b in "${_BIDS[@]}"; do
  [[ -n "$IN_LIST" ]] && IN_LIST+=","
  IN_LIST+="'$_b'"
done

# ---- 连接参数（与 migrate_dev_to_h59.sh 一致） ------------------------------
PG_BIN="${PG_BIN:-/c/Program Files/PostgreSQL/18/bin}"
DEV_HOST=127.0.0.1
DEV_PORT=5432
DEV_DB="${DEV_DB:-postgres}"
SUPER_PWD="${SUPER_PWD:-admin@pwd}"
H59_HOST="${H59_HOST:-h59}"
H59_PG_PORT=5432
H59_DB="${H59_DB:-postgres}"

TS="$(date +%Y%m%d_%H%M%S)"
# Windows TEMP 转 C:/ 正斜杠形式，psql \copy 兼容
LOCAL_DIR="$(cygpath -m "$TEMP")/lnrs_h59_sync_$TS"
REMOTE_DIR="/tmp/lnrs_h59_sync_$TS"

psql_local() {
  PGPASSWORD="$SUPER_PWD" PGCLIENTENCODING=UTF8 "$PG_BIN/psql.exe" \
    -h "$DEV_HOST" -p "$DEV_PORT" -U postgres -d "$DEV_DB" "$@"
}
psql_h59() {
  ssh "$H59_HOST" "PGPASSWORD='$SUPER_PWD' PGCLIENTENCODING=UTF8 psql \
    -h 127.0.0.1 -p $H59_PG_PORT -U postgres -d $H59_DB $*"
}

# ---- 步骤 0：前置检查 ------------------------------------------------------
echo "=== 前置检查 ==="
ssh -o BatchMode=yes -o ConnectTimeout=5 "$H59_HOST" 'echo "       SSH OK -> '"$H59_HOST"'"'
psql_local -tAc "SELECT 1;" >/dev/null && echo "       dev PG OK"
psql_h59 "-tAc 'SELECT 1;'" >/dev/null && echo "       h59 PG OK"
mkdir -p "$LOCAL_DIR"

# ---- 步骤 1：dev 过滤导出（CSV） -------------------------------------------
echo "=== Step 1: dev 导出相关行 → $LOCAL_DIR ==="
cat > "$LOCAL_DIR/export.sql" <<EOF
\set ON_ERROR_STOP on
\copy (SELECT * FROM lnrs.lnrs_anon_ingest_batch WHERE batch_id IN ($IN_LIST)) TO '$LOCAL_DIR/ingest_batch.csv' WITH (FORMAT csv)
\copy (SELECT * FROM lnrs.lnrs_anon_patient WHERE center_code='$CENTER') TO '$LOCAL_DIR/patient.csv' WITH (FORMAT csv)
\copy (SELECT * FROM lnrs.lnrs_anon_exam WHERE center_code='$CENTER' AND exam_type='CT') TO '$LOCAL_DIR/exam.csv' WITH (FORMAT csv)
\copy (SELECT * FROM lnrs.lnrs_anon_report_text WHERE anon_exam_id IN (SELECT anon_exam_id FROM lnrs.lnrs_anon_exam WHERE center_code='$CENTER' AND exam_type='CT')) TO '$LOCAL_DIR/report_text.csv' WITH (FORMAT csv)
\copy (SELECT * FROM lnrs.lnrs_anon_exam_detail WHERE created_batch_id IN ($IN_LIST)) TO '$LOCAL_DIR/exam_detail.csv' WITH (FORMAT csv)
\copy (SELECT * FROM lnrs.lnrs_anon_phi_audit WHERE batch_id IN ($IN_LIST)) TO '$LOCAL_DIR/phi_audit.csv' WITH (FORMAT csv)
\copy (SELECT * FROM lnrs.med_dict_mapping WHERE hospital_id=(SELECT id FROM lnrs.med_hospital WHERE code='$CENTER')) TO '$LOCAL_DIR/dict_mapping.csv' WITH (FORMAT csv)
EOF
psql_local -f "$LOCAL_DIR/export.sql"
ls -lh "$LOCAL_DIR"/*.csv | awk '{printf "       %-18s %s\n", $9, $5}'

# ---- 步骤 2：scp 到 h59 ----------------------------------------------------
echo "=== Step 2: scp → $H59_HOST:$REMOTE_DIR ==="
ssh "$H59_HOST" "mkdir -p '$REMOTE_DIR'"
scp -q "$LOCAL_DIR"/*.csv "$H59_HOST:$REMOTE_DIR/"

# ---- 步骤 3：h59 upsert（单事务，FK 顺序） ---------------------------------
echo "=== Step 3: h59 定向 upsert ==="
cat > "$LOCAL_DIR/sync.sql" <<EOF
\set ON_ERROR_STOP on
BEGIN;

CREATE TEMP TABLE st_batch   (LIKE lnrs.lnrs_anon_ingest_batch INCLUDING DEFAULTS);
CREATE TEMP TABLE st_patient (LIKE lnrs.lnrs_anon_patient      INCLUDING DEFAULTS);
CREATE TEMP TABLE st_exam    (LIKE lnrs.lnrs_anon_exam         INCLUDING DEFAULTS);
CREATE TEMP TABLE st_report  (LIKE lnrs.lnrs_anon_report_text  INCLUDING DEFAULTS);
CREATE TEMP TABLE st_detail  (LIKE lnrs.lnrs_anon_exam_detail  INCLUDING DEFAULTS);
CREATE TEMP TABLE st_audit   (LIKE lnrs.lnrs_anon_phi_audit    INCLUDING DEFAULTS);
CREATE TEMP TABLE st_dictmap (LIKE lnrs.med_dict_mapping       INCLUDING DEFAULTS);

\copy st_batch   FROM '$REMOTE_DIR/ingest_batch.csv'  WITH (FORMAT csv)
\copy st_patient FROM '$REMOTE_DIR/patient.csv'       WITH (FORMAT csv)
\copy st_exam    FROM '$REMOTE_DIR/exam.csv'          WITH (FORMAT csv)
\copy st_report  FROM '$REMOTE_DIR/report_text.csv'   WITH (FORMAT csv)
\copy st_detail  FROM '$REMOTE_DIR/exam_detail.csv'   WITH (FORMAT csv)
\copy st_audit   FROM '$REMOTE_DIR/phi_audit.csv'     WITH (FORMAT csv)
\copy st_dictmap FROM '$REMOTE_DIR/dict_mapping.csv'  WITH (FORMAT csv)

-- 1. batch（patient/exam 的 FK 依赖，必须最先）
INSERT INTO lnrs.lnrs_anon_ingest_batch SELECT * FROM st_batch
ON CONFLICT (batch_id) DO NOTHING;

-- 2. patient：新行插入；旧行刷新人口学/稳定属性 + last_seen（保留 created_batch_id）
INSERT INTO lnrs.lnrs_anon_patient SELECT * FROM st_patient
ON CONFLICT (patient_id) DO UPDATE SET
  birth_date         = EXCLUDED.birth_date,
  sex                = EXCLUDED.sex,
  ethnicity          = EXCLUDED.ethnicity,
  smoking_status     = EXCLUDED.smoking_status,
  abo_blood_type     = EXCLUDED.abo_blood_type,
  rh_blood_type      = EXCLUDED.rh_blood_type,
  native_place       = EXCLUDED.native_place,
  first_nodule_date  = EXCLUDED.first_nodule_date,
  bmi                = EXCLUDED.bmi,
  patient_meta       = EXCLUDED.patient_meta,
  last_seen_batch_id = EXCLUDED.last_seen_batch_id,
  deleted_at         = EXCLUDED.deleted_at,
  deleted_reason     = EXCLUDED.deleted_reason,
  deleted_batch_id   = EXCLUDED.deleted_batch_id;

-- 3. exam：刷新 last_seen/exam_date（exam_type/created_batch_id 保留首值，与引擎语义一致）
INSERT INTO lnrs.lnrs_anon_exam SELECT * FROM st_exam
ON CONFLICT (anon_exam_id) DO UPDATE SET
  patient_id         = EXCLUDED.patient_id,
  exam_date          = EXCLUDED.exam_date,
  last_seen_batch_id = EXCLUDED.last_seen_batch_id;

-- 4. report_text：刷新正文与清洗状态（created_batch_id 保留首值）
INSERT INTO lnrs.lnrs_anon_report_text SELECT * FROM st_report
ON CONFLICT (anon_exam_id) DO UPDATE SET
  body_clean         = EXCLUDED.body_clean,
  pii_replaced_count = EXCLUDED.pii_replaced_count,
  clean_method       = EXCLUDED.clean_method,
  llm_model          = EXCLUDED.llm_model,
  review_status      = EXCLUDED.review_status;

-- 5. exam_detail：刷新 JSONB 内容
INSERT INTO lnrs.lnrs_anon_exam_detail SELECT * FROM st_detail
ON CONFLICT (anon_exam_id, detail_type, detail_ordinal) DO UPDATE SET
  detail_json       = EXCLUDED.detail_json,
  created_batch_id  = EXCLUDED.created_batch_id;

-- 6. phi_audit：append-only，先删本批次旧行再原样插入（audit_id 与 dev 对齐，可重复执行）
DELETE FROM lnrs.lnrs_anon_phi_audit WHERE batch_id IN ($IN_LIST);
INSERT INTO lnrs.lnrs_anon_phi_audit SELECT * FROM st_audit;

-- 7. 字典映射：新增 0011 种子的 29 行，已有行不动
INSERT INTO lnrs.med_dict_mapping SELECT * FROM st_dictmap
ON CONFLICT DO NOTHING;

-- 8. 序列校准（patient 发号 + phi_audit audit_id，防止 h59 后续导入撞号）
SELECT setval('lnrs.lnrs_anon_patient_seq',
              (SELECT max(substring(patient_id from 4)::bigint) FROM lnrs.lnrs_anon_patient));
SELECT setval('lnrs.lnrs_anon_phi_audit_audit_id_seq',
              (SELECT max(audit_id) FROM lnrs.lnrs_anon_phi_audit));

COMMIT;
EOF
scp -q "$LOCAL_DIR/sync.sql" "$H59_HOST:$REMOTE_DIR/sync.sql"
psql_h59 "-v ON_ERROR_STOP=1 -f '$REMOTE_DIR/sync.sql'"

# ---- 步骤 4：两端逐项计数对比验证 -------------------------------------------
echo "=== Step 4: 验证（dev vs h59，同一过滤条件） ==="
# 标签不含空格（awk 显示用）；ORDER BY 保证两端行序一致；
# 序列只验证 >= max(patient 序号)（dev 端可能有探测性 nextval 空洞，等值比较会误报）
VERIFY_SQL="SELECT 'batch_list', count(*) FROM lnrs.lnrs_anon_ingest_batch WHERE batch_id IN ($IN_LIST) UNION ALL \
SELECT 'patient_$CENTER', count(*) FROM lnrs.lnrs_anon_patient WHERE center_code='$CENTER' UNION ALL \
SELECT 'exam_${CENTER}_ct', count(*) FROM lnrs.lnrs_anon_exam WHERE center_code='$CENTER' AND exam_type='CT' UNION ALL \
SELECT 'report_ct', count(*) FROM lnrs.lnrs_anon_report_text WHERE anon_exam_id IN (SELECT anon_exam_id FROM lnrs.lnrs_anon_exam WHERE center_code='$CENTER' AND exam_type='CT') UNION ALL \
SELECT 'detail_list', count(*) FROM lnrs.lnrs_anon_exam_detail WHERE created_batch_id IN ($IN_LIST) UNION ALL \
SELECT 'phi_list', count(*) FROM lnrs.lnrs_anon_phi_audit WHERE batch_id IN ($IN_LIST) UNION ALL \
SELECT 'dictmap_$CENTER', count(*) FROM lnrs.med_dict_mapping WHERE hospital_id=(SELECT id FROM lnrs.med_hospital WHERE code='$CENTER') UNION ALL \
SELECT 'seq_ge_max', ((SELECT last_value FROM lnrs.lnrs_anon_patient_seq) >= (SELECT max(substring(patient_id from 4)::bigint) FROM lnrs.lnrs_anon_patient))::int \
ORDER BY 1;"

DEV_COUNTS="$(psql_local -tAc "$VERIFY_SQL" | tr -d '\r' | sed -e 's/[[:space:]]*$//')"
H59_COUNTS="$(psql_h59 "-tAc \"$VERIFY_SQL\"" | tr -d '\r' | sed -e 's/[[:space:]]*$//')"

echo "$DEV_COUNTS" | awk '{printf "  dev  %-20s %s\n", $1, $2}'
echo "$H59_COUNTS" | awk '{printf "  h59  %-20s %s\n", $1, $2}'
if [[ "$DEV_COUNTS" == "$H59_COUNTS" ]]; then
  echo "       行数对比：dev/h59 完全一致 ✔"
else
  echo "ERROR: dev/h59 行数不一致：" >&2
  diff <(echo "$DEV_COUNTS") <(echo "$H59_COUNTS") >&2 || true
  exit 1
fi

# ---- 收尾 -----------------------------------------------------------------
if [[ "${KEEP_FILES:-0}" != "1" ]]; then
  ssh "$H59_HOST" "rm -rf '$REMOTE_DIR'"
  rm -rf "$LOCAL_DIR"
  echo "       两端临时文件已清理（KEEP_FILES=1 可保留）"
fi
echo ""
echo "=== 完成 ==="
echo "  h59 postgres.lnrs 已增量同步珠江 0814+CT 批次（未触碰其他表/行）"
