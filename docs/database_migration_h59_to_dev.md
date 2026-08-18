# 数据库反向同步指南：h59 → dev

> **适用范围**：将 h59 服务器（192.168.1.59, PG15）postgres 库的 `lnrs` schema 全量同步到本机 dev（PG18）postgres 库的 `lnrs` schema（目标端先清空再恢复）
> **最后更新**：2026-08-14
> **配套脚本**：`scripts/migrate_h59_to_dev.sh`
> **依赖前置**：本机 `~/.ssh/config` 中存在 `Host h59` 别名（root@192.168.1.59 免密登录）

---

## 环境信息

| 项目 | h59（源） | dev（目标） |
|---|---|---|
| 主机 | 192.168.1.59（SSH 别名 `h59`） | 127.0.0.1 |
| 端口 | 5432 | 5432 |
| PostgreSQL | 15.18 (Linux/EL7) | 18.0 (Windows) |
| 数据库 | postgres | postgres |
| Schema | lnrs | lnrs |
| 超级用户 | postgres / admin@pwd | postgres / admin@pwd |
| 应用用户 | lnrs / lnrs_pwd | lnrs / lnrs_pwd |
| 工具 | h59 自带 `/usr/bin/{psql,pg_dump}`（PG15） | `C:\Program Files\PostgreSQL\18\bin` |

> 方向说明：与 `scripts/migrate_dev_to_h59.sh`（dev → h59）相反。PG15 dump → PG18 restore 属低版本导高版本，完全兼容，**没有** dev→h59 方向的 `transaction_timeout` 问题。

---

## 用法

```bash
# Git Bash 本机执行（默认：同步后清理 h59 上的临时 dump，本地 dump 保留）
./scripts/migrate_h59_to_dev.sh

# 保留 h59 上的临时 dump
KEEP_REMOTE_DUMP=1 ./scripts/migrate_h59_to_dev.sh

# 覆盖默认凭据（推荐环境变量注入，不要改脚本）
SUPER_PWD='<your_super_pwd>' APP_PWD='<your_app_pwd>' ./scripts/migrate_h59_to_dev.sh
```

## 脚本步骤

| 步骤 | 动作 | 跑在哪 |
|---|---|---|
| 0 | SSH 别名 `h59` 可达测试；本机 PG 连接测试（未启动则自动 `pg_ctl -w start`） | 本机 |
| 1 | h59 上 `pg_dump -Fc --schema=lnrs --no-owner --no-privileges` 导出 | h59 |
| 2 | `scp` 拉回本机 `backend/lnrs_migration_h59_<时间戳>.pdump` | h59 → 本机 |
| 3 | 本机 `DROP SCHEMA lnrs CASCADE` + 重建 + 授权 schema | 本机 |
| 4 | 本机 `pg_restore -Fc --no-owner`（「模式已存在」警告属预期，已过滤） | 本机 |
| 5 | 本机对 schema 内所有表/序列/函数 `GRANT ALL` 给 `lnrs` | 本机 |
| 6 | 以源端表清单为准，源/目标逐表 `count(*)` 对比，不一致则报错退出 | 两端 |
| 7 | 以应用用户 `lnrs` 登录本机抽查 `sys_user` | 本机 |

## 验证结果参考（2026-08-14 首次同步）

- 51 张表全部同步，源/目标逐表行数完全一致
- 核心表行数：`sys_user` 6、`sys_menu` 203、`sys_log` 303、`lnrs_anon_patient` 16、`lnrs_anon_exam` 81、`lnrs_anon_report_text` 81、`lnrs_anon_phi_audit` 214、`med_dict_mapping` 55
- dump 大小约 506K

## 关键经验教训

1. **必须 `-Fc` custom 格式经文件中转**（scp 拉回本机），管道直传会损坏 binary。
2. **必须先 `DROP SCHEMA lnrs CASCADE` 再 restore**，否则 COPY 会落到旧表产生假象。
3. **恢复后必须重新 `GRANT ALL`**：restore 以 postgres 身份写入，应用用户 `lnrs` 需要重新授权。
4. **pg_restore 报 1 个已忽略错误**（`CREATE SCHEMA lnrs` 已存在，因步骤 3 已建），属预期。
5. **源/目标行数对比必须先去掉 `\r`**：本机 Windows psql 输出是 CRLF，h59 是 LF，直接字符串比较会误报不一致（脚本已处理）。
6. **本机 PG18 服务常处于停止状态**：脚本会在连接失败时自动 `pg_ctl -D "C:/Program Files/PostgreSQL/18/data" -w start`，无需管理员权限。
7. `backend/*.pdump` 已被 `.gitignore` 忽略，保留在本地作为 h59 数据的时间点备份。

## 与 dev → h59 脚本的关键差异

| 项 | dev → h59 | h59 → dev（本脚本） |
|---|---|---|
| dump 在哪跑 | 本机 `pg_dump.exe`（PG18） | h59 上 `/usr/bin/pg_dump`（PG15） |
| 传输方向 | scp 推送到 h59 /tmp | scp 拉回本机 backend/ |
| 版本兼容 | PG18 dump → PG15，有 `transaction_timeout` 问题 | PG15 dump → PG18，无兼容问题 |
| 目标端启动 | h59 常驻 | 本机 PG 服务可能停止，脚本自动拉起 |
| 验证 | 固定 7 张核心表 count | 全部表动态生成 count，源/目标 diff |
