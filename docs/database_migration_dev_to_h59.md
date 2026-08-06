# 数据库迁移指南：dev → h59

> **适用范围**：将本地开发数据库（dev, PG18）的全部数据迁移到 h59 服务器（PG15, 192.168.1.59）
> **最后更新**：2026-07-29
> **配套脚本**：`scripts/migrate_dev_to_h59.sh`
> **依赖前置**：本机 `~/.ssh/config` 中存在 `Host h59` 别名（root@192.168.1.59 免密登录）

> 备注：h59 与 h42 指向同一台物理主机（192.168.1.59），区别仅在 SSH 别名。
> 本指南与 `docs/database_migration_dev_to_h42.md` 内容高度重叠，仅在目标 DB / 应用账号 / 工具链（h59 用本机 /usr/bin）上做了修正。

---

## 环境信息

| 项目 | dev（源） | h59（目标） |
|---|---|---|
| 主机 | 127.0.0.1 | 192.168.1.59（SSH 别名 `h59`） |
| 端口 | 5432 | 5432 |
| PostgreSQL | 18.0 (Windows) | 15.18 (Linux/EL7) |
| 数据库 | postgres | postgres |
| Schema | lnrs | lnrs |
| 超级用户 | postgres / admin@pwd | postgres / admin@pwd |
| 应用用户 | lnrs / lnrs_pwd（见 `backend/env/.env.h42:31-32`） | lnrs / lnrs_pwd |
| pg_dump 路径 | `C:\Program Files\PostgreSQL\18\bin`（仅重新导出时用） | `/usr/bin/pg_restore`（PG15 自带） |

---

## 已缓存的导出

仓库当前缓存了一份由本机 dev (PG18) 在 **2026-07-25 08:35:59** 导出的 custom 格式 dump：

```
backend/lnrs_migration_20260725_083559.pdump   (447K, schema=lnrs, 1251 个 TOC 条目)
```

`scripts/migrate_dev_to_h59.sh` 默认直接使用这份 dump，无需再导出即可恢复。

如需重新导出（在 dev 上跑）：

```bash
PGPASSWORD=admin@pwd "/c/Program Files/PostgreSQL/18/bin/pg_dump.exe" \
  -h 127.0.0.1 -p 5432 -U postgres -d postgres \
  --schema=lnrs -Fc --no-owner --no-privileges \
  -f backend/lnrs_migration_$(date +%Y%m%d_%H%M%S).pdump
```

---

## 标准操作脚本

将以下内容保存为 `scripts/migrate_dev_to_h59.sh`，在 Git Bash（本机）执行：

```bash
#!/bin/bash
# 详细见仓库 scripts/migrate_dev_to_h59.sh
```

### 用法示例

```bash
# 在本机 Git Bash 里（推荐）

# 1. 默认行为：复用仓库里已缓存的 dump，直接 scp + 远程恢复
./scripts/migrate_dev_to_h59.sh

# 2. 强制重新从 dev 导出再恢复（dump 时间戳会变）
RE_EXPORT=1 ./scripts/migrate_dev_to_h59.sh

# 3. 用指定的 dump 文件恢复
DUMP_FILE=backend/lnrs_migration_xxx.pdump ./scripts/migrate_dev_to_h59.sh

# 4. 覆盖默认凭据（推荐通过环境变量注入，不要改脚本）
SUPER_PWD='<your_super_pwd>' APP_PWD='<your_app_pwd>' \
  ./scripts/migrate_dev_to_h59.sh
```

### 脚本步骤

| 步骤 | 动作 | 跑在哪 |
|---|---|---|
| 0 | 校验 dump 文件存在并打印大小；测试 SSH 别名 `h59` 可达 | 本机 |
| 1 | （可选 `RE_EXPORT=1`）本机 `pg_dump -Fc` 重新导出 dev | 本机 |
| 2 | `scp` 把 dump 推送到 `h59:/tmp/lnrs_migration_<时间戳>.pdump` | 本机 → h59 |
| 3 | h59 上 `DROP SCHEMA lnrs CASCADE` + 重建 + 授权 | h59 |
| 4 | h59 上 `pg_restore -Fc --no-owner`；过滤 `transaction_timeout` 与「模式已存在」 | h59 |
| 5 | h59 上对 schema 内所有表/序列/函数 `GRANT ALL` 给 `lnrs` | h59 |
| 6 | h59 上以应用用户 `lnrs` 登录，对核心业务表 `count(*)` 验证 | h59 |

---

## 与 h42/h125 脚本的关键差异

| 项 | h42/h125 | h59 |
|---|---|---|
| 脚本跑在哪 | Git Bash 直连目标机 | Git Bash → scp + ssh h59 远程跑 |
| 目标端工具 | 本机 `pg_restore.exe`（远程需安装 PG） | h59 自带 `/usr/bin/pg_restore`（PG15） |
| 数据库 | h125: `lnrs` / h42: `postgres` | `postgres`（与 `.env.h42` 对齐） |
| 应用用户 | h125: `lnrs_pwd_2026` / h42: `lnrs_pwd` | `lnrs_pwd` |
| 鉴权 | 直连 psql/pg_restore | 通过 SSH 别名 `h59` 走免密 |

---

## 关键经验教训（与 dev → h42 一致）

### 1. PG18 → PG15 不兼容
- **问题**：`pg_dump --schema=lnrs --no-owner` 的 plain SQL 会在目标端写 `SET transaction_timeout = 0;`
- **解决**：用 `pg_dump -Fc` 输出 custom 格式 → `pg_restore` 读文件，绕开 SET 语句

### 2. 管道传输 custom 格式会坏
- **问题**：`pg_dump -Fc | pg_restore` 直传会损坏 binary
- **解决**：必须经过文件（pdump）中转，跨主机用 `scp`

### 3. h59 lnrs 用户无 DDL 权限
- lnrs 用户仅有 `LOGIN` + 基本权限，没有 `CREATEDB`/`SUPERUSER`
- 必须用 postgres 超级用户执行 `DROP/CREATE SCHEMA` 与 `pg_restore`
- 恢复后必须再 `GRANT ALL` 一次（恢复写的是 postgres 拥有的对象）

### 4. pg_restore 遇到已存在表会失败
- 必须先 `DROP SCHEMA lnrs CASCADE`，再恢复，避免 COPY 数据落到空表产生 "0 行"假象

### 5. SSH 别名不可用
- 脚本默认走 `h59` 别名；如果没配，会在「步骤 0」打印 ERROR 并退出，不会半途失败
- 配置方法见 `~/.ssh/config`：

  ```sshconfig
  Host h59
      HostName 192.168.1.59
      User root
      Port 22
      IdentityFile ~/.ssh/id_rsa
      IdentitiesOnly yes
      PreferredAuthentications publickey
      PasswordAuthentication no
  ```

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

> 实际行数请以脚本 Step 6 在 h59 上的 `count(*)` 输出为准。

---

## 快速检查清单

- [ ] 已确认 dev 数据完整（执行导出前 `SELECT count(*)` 抽查）
- [ ] 导出用 `-Fc` custom 格式（不是 plain SQL）
- [ ] `~/.ssh/config` 已有 `Host h59` 别名且 root 免密登录可用
- [ ] 远程 dump 走 `scp`，不靠管道直传
- [ ] 恢复前 `DROP SCHEMA lnrs CASCADE`（h59 目标库 `postgres`）
- [ ] 恢复后对 schema 内对象重新 `GRANT ALL` 给 `lnrs`
- [ ] 用 `lnrs`（非 superuser）验证查询正常
- [ ] 保留 `backend/lnrs_migration_*.pdump` 至少一个迁移周期作为备份

---

## 注意事项

1. **dump 文件即备份**：每次迁移生成的 `.pdump` 文件保留，可作为 dev 数据库的时间点备份
2. **迁移窗口**：`phi_audit` 约 275 万行，`pg_restore` 约需 3~5 分钟，请在 h59 低峰期执行
3. **外键依赖**：dump 文件内已按依赖顺序排列，无需手动排序
4. **序列值**：`pg_dump` 包含 `SEQUENCE SET`，恢复后序列值与 dev 一致
5. **敏感配置**：dump 内含 demo 数据，不含敏感业务数据；恢复后请按 `docs/敏感环境变量与配置项审计.md`
   重新评估 h59 的凭据与默认密钥是否仍使用占位值（h59 与 h42 同主机，请同步处理）。

---

## 常见错误速查

| 错误信息 | 原因 | 解决 |
|---|---|---|
| `ssh-copy-id: command not found`（PowerShell） | 在原生 PowerShell 下执行 | 改用 Git Bash |
| `Permission denied (publickey)` | `~/.ssh/config` 中无 `Host h59` 别名或 authorized_keys 未配 | 参考 `~/.ssh/config` 段落补全 |
| `transaction_timeout` 不认可 | PG18→PG15 不兼容 | 用 `-Fc` 文件格式中转 |
| `input file is too short` | 管道传 binary 损坏 | 用文件中转，别管道 |
| `关系不存在`（查询时） | lnrs 用户无权限 | Step 5 重新 GRANT |
| `模式已存在` | 未先 DROP SCHEMA | 先 DROP 再恢复 |
| `权限不够`（CREATE SCHEMA） | lnrs 用户无 DDL 权限 | 用 postgres 超级用户 |
| 数据为 0 但表很大 | pg_restore 遇到已存在表，COPY 失败 | DROP SCHEMA 后重做 |
| `connection to server ... Connection refused` | h59 端 pg 未监听远程 | h59 脚本走 `127.0.0.1`，无需远程监听 |