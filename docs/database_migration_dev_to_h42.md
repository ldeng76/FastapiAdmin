# 数据库迁移指南：dev → h42

> **适用范围**：将本地开发数据库（dev, PG18）的全部数据迁移到 h42 服务器（PG15）
> **最后更新**：2026-07-23

---

## 环境信息

| 项目 | dev（源） | h42（目标） |
|---|---|---|
| 主机 | 127.0.0.1 | 192.168.1.59 |
| 端口 | 5432 | 5432 |
| PostgreSQL | 18.0 (Windows) | 15.18 (Linux/EL7) |
| 数据库 | postgres | postgres |
| Schema | lnrs | lnrs |
| 超级用户 | postgres / admin@pwd | postgres / admin@pwd |
| 应用用户 | lnrs / lnrs_pwd | lnrs / lnrs_pwd |
| pg_dump 路径 | `C:\Program Files\PostgreSQL\18\bin` | — |

---

## 标准操作脚本

将以下内容保存为 `scripts/migrate_dev_to_h42.sh`，在 Git Bash 中执行：

```bash
#!/bin/bash
# ============================================================
# 标准迁移脚本：dev (PG18) → h42 (PG15)
# 使用方法：Git Bash 中执行 ./scripts/migrate_dev_to_h42.sh
# ============================================================
set -e

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
PGPASSWORD="$SUPER_PWD" "$PG_BIN/pg_restore.exe" \
  -h $H42_HOST -p $H42_PORT -U postgres -d postgres \
  --no-owner --no-privileges \
  "$DUMP_FILE"

echo "=== Step 4: 授权应用用户 ==="
PGPASSWORD="$SUPER_PWD" "$PG_BIN/psql.exe" \
  -h $H42_HOST -p $H42_PORT -U postgres -d postgres \
  -c "GRANT ALL ON ALL TABLES IN SCHEMA lnrs TO $APP_USER; GRANT ALL ON ALL SEQUENCES IN SCHEMA lnrs TO $APP_USER; GRANT ALL ON ALL FUNCTIONS IN SCHEMA lnrs TO $APP_USER;"

echo "=== Step 5: 验证 ==="
PGPASSWORD="$APP_PWD" "$PG_BIN/psql.exe" \
  -h $H42_HOST -p $H42_PORT -U $APP_USER -d postgres \
  -c "SELECT 'patient' as tbl, count(*) FROM lnrs.lnrs_anon_patient UNION ALL SELECT 'exam', count(*) FROM lnrs.lnrs_anon_exam UNION ALL SELECT 'phi_audit', count(*) FROM lnrs.lnrs_anon_phi_audit UNION ALL SELECT 'report_text', count(*) FROM lnrs.lnrs_anon_report_text;"

echo "=== 完成，dump 文件保留在: $DUMP_FILE ==="
```

---

## 关键经验教训

### 1. PG18 → PG15 不兼容
- **问题**：`pg_restore` 连 PG15 会生成 `SET transaction_timeout = 0;`，PG15 不认识
- **解决**：用 `pg_dump -Fc` 导出 custom 格式 dump 文件，再用 `pg_restore` 从文件恢复到 h42（custom 格式恢复时不生成 SET 语句）

### 2. 管道传输 binary 必坏
- **问题**：`pg_dump -Fc | pg_restore` 管道直传会损坏 binary 数据
- **报错**：`pg_restore: error: input file is too short (read 0, expected 5)`
- **解决**：必须经过文件中转，不能管道直传 custom 格式

### 3. `--data-only` dump 内含 TRUNCATE
- **问题**：`pg_dump --data-only` 生成的 dump 开头有 `TRUNCATE ... CASCADE`
- **教训**：恢复前先备份目标库，或确认目标库可清空
- **建议**：使用完整 dump（不含 `--data-only`），恢复时先 DROP SCHEMA

### 4. h42 lnrs 用户无 CREATE SCHEMA 权限
- lnrs 用户没有 CREATEDB / CREATEROLE / SUPERUSER 权限
- 需要 postgres 超级用户执行 DDL 和 DROP/CREATE SCHEMA
- 恢复后必须重新授权

### 5. pg_restore 遇到已存在的表会失败
- 恢复前必须 `DROP SCHEMA lnrs CASCADE`，确保目标 schema 干净
- 否则 COPY 数据无法写入已存在的表，导致 0 行

---

## 快速检查清单

- [ ] 导出前确认 dev 数据完整（`SELECT count(*)` 各表）
- [ ] 导出用 `-Fc` custom 格式（不是 plain SQL）
- [ ] 导出/恢复均用 postgres 超级用户
- [ ] 恢复前 `DROP SCHEMA lnrs CASCADE`（h42 目标）
- [ ] 恢复后重新 `GRANT ALL` 给 lnrs 用户
- [ ] 验证 lnrs 用户能正常查询（非 superuser）
- [ ] 保留 dump 文件至少一次迁移周期（作为备份）

---

## 常见错误速查

| 错误信息 | 原因 | 解决 |
|---|---|---|
| `transaction_timeout` 不认可 | PG18→PG15 不兼容 | 用 `-Fc` 文件格式中转 |
| `input file is too short` | 管道传 binary 损坏 | 用文件中转，别管道 |
| `关系不存在`（查询时） | lnrs 用户无权限/未授权 | 重新 GRANT |
| `模式已存在` | 未先 DROP SCHEMA | 先 DROP 再恢复 |
| `权限不够`（CREATE SCHEMA） | lnrs 用户无 DDL 权限 | 用 postgres 超级用户 |
| 数据为 0 但表很大 | pg_restore 遇到已存在表，COPY 失败 | DROP SCHEMA 后重新恢复 |

---

## 数据量参考（2026-07-23）

| 表 | 行数 | 备注 |
|---|---|---|
| lnrs_anon_patient | 129,297 | 病人主表 |
| lnrs_anon_exam | 194,082 | 检查主表 |
| lnrs_anon_report_text | 194,082 | 报告文本 |
| lnrs_anon_phi_audit | 2,750,105 | PHI 审计（最大表） |
| lnrs_anon_ingest_batch | 27 | 导入批次 |
| sys_user | 5 | 用户表 |
| sys_menu | 211 | 菜单表 |
| 其余 sys_/med_/gen_/task_ 表 | 数十~数百 | 系统配置、业务宽表 |

---

## 注意事项

1. **dump 文件即备份**：每次迁移生成的 `.pdump` 文件保留，可作为 dev 数据库的时间点备份
2. **迁移窗口**：phi_audit 表 275 万行，pg_restore 约需 3~5 分钟，请在低峰期执行
3. **外键依赖**：dump 文件内已按依赖顺序排列，无需手动排序
4. **序列值**：pg_dump 包含 SEQUENCE SET，恢复后序列值与 dev 一致
