# 数据库迁移指南：dev → h125

> **适用范围**：将本地开发数据库（dev, PG18）的全部数据迁移到 h125 服务器（PG15, 10.12.118.125）
> **最后更新**：2026-07-25
> **配套脚本**：`scripts/migrate_dev_to_h125.sh`

---

## 环境信息

| 项目 | dev（源） | h125（目标） |
|---|---|---|
| 主机 | 127.0.0.1 | 10.12.118.125（本机执行默认走 127.0.0.1） |
| 端口 | 5432 | 5432 |
| PostgreSQL | 18.0 (Windows) | 15.x (Linux) |
| 数据库 | postgres | lnrs |
| Schema | lnrs | lnrs |
| 超级用户 | postgres / admin@pwd | postgres / admin@pwd |
| 应用用户 | lnrs | lnrs / lnrs_pwd_2026（见 `backend/env/.env.h125`） |
| pg_dump 路径 | `C:\Program Files\PostgreSQL\18\bin` | — |

> 复用 `docs/database_migration_dev_to_h42.md` 中已沉淀的经验：custom 格式文件中转、先
> `DROP SCHEMA` 再恢复、PG18 → PG15 的 `transaction_timeout` 与 "模式已存在" 警告可忽略。

---

## 已缓存的导出

仓库当前缓存了一份由本机 dev (PG18) 在 **2026-07-25 08:35:59** 导出的 custom 格式 dump：

```
backend/lnrs_migration_20260725_083559.pdump   (447K, schema=lnrs, 1251 个 TOC 条目)
```

`scripts/migrate_dev_to_h125.sh` 默认直接使用这份 dump，无需再导出即可恢复。

如需重新导出（在 dev 上跑）：

```bash
PGPASSWORD=admin@pwd "/c/Program Files/PostgreSQL/18/bin/pg_dump.exe" \
  -h 127.0.0.1 -p 5432 -U postgres -d postgres \
  --schema=lnrs -Fc --no-owner --no-privileges \
  -f backend/lnrs_migration_$(date +%Y%m%d_%H%M%S).pdump
```

---

## 标准操作脚本

将以下内容保存为 `scripts/migrate_dev_to_h125.sh`，推荐在 h125 服务器本机的 Git Bash 中执行：

```bash
#!/bin/bash
# 详细见仓库 scripts/migrate_dev_to_h125.sh
```

### 用法示例

```bash
# 在 h125 服务器上（推荐）

# 1. 默认行为：复用仓库里已缓存的 dump 直接恢复
./scripts/migrate_dev_to_h125.sh

# 2. 强制重新从 dev 导出再恢复
RE_EXPORT=1 ./scripts/migrate_dev_to_h125.sh

# 3. 用指定的 dump 文件恢复
DUMP_FILE=backend/lnrs_migration_xxx.pdump ./scripts/migrate_dev_to_h125.sh

# 4. 从本机远程连 h125（前提 h125 允许远程超级用户登录）
H125_HOST=10.12.118.125 SUPER_PWD=admin@pwd ./scripts/migrate_dev_to_h125.sh
```

### 脚本步骤

| 步骤 | 动作 |
|---|---|
| 0 | 校验 dump 文件存在并打印大小 |
| 1 | （可选 `RE_EXPORT=1`）重新从 dev 执行 `pg_dump -Fc` |
| 2 | 用 postgres 超级用户 `DROP SCHEMA lnrs CASCADE` 并重建、授权 |
| 3 | `pg_restore` 自定义格式 dump 到 h125；过滤 `transaction_timeout` 与「模式已存在」警告 |
| 4 | 对 schema 内所有表/序列/函数重新 `GRANT ALL` 给 `lnrs` |
| 5 | 以应用用户 `lnrs` 登录，对核心业务表执行 `count(*)` 验证 |

---

## 关键经验教训（与 dev → h42 一致）

### 1. PG18 → PG15 不兼容
- **问题**：`pg_dump --schema=lnrs --no-owner` 的 plain SQL 会在目标端写 `SET transaction_timeout = 0;`
- **解决**：用 `pg_dump -Fc` 输出 custom 格式 → `pg_restore` 读文件，绕开 SET 语句

### 2. 管道传输 custom 格式会坏
- **问题**：`pg_dump -Fc | pg_restore` 直传会损坏 binary
- **解决**：必须经过文件（pdump）中转

### 3. h125 lnrs 用户无 DDL 权限
- lnrs 用户仅有 `LOGIN` + 基本权限，没有 `CREATEDB`/`SUPERUSER`
- 必须用 postgres 超级用户执行 `DROP/CREATE SCHEMA` 与 `pg_restore`
- 恢复后必须再 `GRANT ALL` 一次（恢复写的是 postgres 拥有的对象）

### 4. pg_restore 遇到已存在表会失败
- 必须先 `DROP SCHEMA lnrs CASCADE`，再恢复，避免 COPY 数据落到空表产生 "0 行"假象

---

## 数据量参考（来自 2026-07-23 的 dev 导出，2026-07-25 的 dump 沿用同一份 dev 基线）

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

> 实际行数请以脚本 Step 5 在 h125 上的 `count(*)` 输出为准。

---

## 快速检查清单

- [ ] 已确认 dev 数据完整（执行导出前 `SELECT count(*)` 抽查）
- [ ] 导出用 `-Fc` custom 格式（不是 plain SQL）
- [ ] 导出/恢复均用 postgres 超级用户
- [ ] 恢复前 `DROP SCHEMA lnrs CASCADE`（h125 目标库 `lnrs`）
- [ ] 恢复后对 schema 内对象重新 `GRANT ALL` 给 `lnrs`
- [ ] 用 `lnrs`（非 superuser）验证查询正常
- [ ] 保留 `backend/lnrs_migration_*.pdump` 至少一个迁移周期作为备份

---

## 注意事项

1. **dump 文件即备份**：每次迁移生成的 `.pdump` 文件保留，可作为 dev 数据库的时间点备份
2. **迁移窗口**：`phi_audit` 约 275 万行，`pg_restore` 约需 3~5 分钟，请在 h125 低峰期执行
3. **外键依赖**：dump 文件内已按依赖顺序排列，无需手动排序
4. **序列值**：`pg_dump` 包含 `SEQUENCE SET`，恢复后序列值与 dev 一致
5. **敏感配置**：dump 内含 demo 数据，不含敏感业务数据；恢复后请按 `docs/敏感环境变量与配置项审计.md`
   重新评估 h125 的 `backend/env/.env.h125` 凭据与默认密钥是否仍使用占位值。

---

## 常见错误速查

| 错误信息 | 原因 | 解决 |
|---|---|---|
| `transaction_timeout` 不认可 | PG18→PG15 不兼容 | 用 `-Fc` 文件格式中转 |
| `input file is too short` | 管道传 binary 损坏 | 用文件中转，别管道 |
| `关系不存在`（查询时） | lnrs 用户无权限 | Step 4 重新 GRANT |
| `模式已存在` | 未先 DROP SCHEMA | 先 DROP 再恢复 |
| `权限不够`（CREATE SCHEMA） | lnrs 用户无 DDL 权限 | 用 postgres 超级用户 |
| 数据为 0 但表很大 | pg_restore 遇到已存在表，COPY 失败 | DROP SCHEMA 后重做 |
| `connection to server ... Connection refused` | h125 端 pg 未监听远程 | 默认走 `127.0.0.1`，或让 pg 监听 `0.0.0.0` |
