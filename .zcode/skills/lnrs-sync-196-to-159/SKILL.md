---
name: lnrs-sync-196-to-159
description: 将 lnrs 项目 10.12.196.3 (h196_3) 上 lnrs_anon_ 前缀的表反向同步到 192.168.1.59 (h42 库)，支持 --limit N 每表按主键取前 N 行抽样，或 --by-center N 按医院抽样 (衍生表沿 FK 闭包自动跟随)。用户要求"把 h196_3 的 lnrs_anon_* 表同步/搬回 1.59"、"反向同步脱敏表"、"抽样同步 N 条"、"每家医院抽 N 个患者同步"时使用。脚本在 DROP 前自动备份 1.59 已有目标表到 /data/lnrs_backup。
trigger:
  - 用户要求把 h196_3 / 10.12.196.3 的 lnrs_anon_ 表数据同步/搬回 192.168.1.59 或 1.59
  - 用户提及 196.3 -> 1.59 方向的反向数据搬运（与 lnrs-sync-159-to-196 相反方向）
  - "抽样同步 N 条" / "每表只同步 N 行" / "limit N 同步 lnrs_anon 表"
  - "按医院抽样" / "每家医院抽 N 个患者" / "随机抽样患者同步"
---

<!-- skill 同步副本：.zcode/skills/lnrs-sync-196-to-159/ 与 .claude/skills/lnrs-sync-196-to-159/ 内容须保持一致（harness 同时扫描两侧）；修改任一侧请同步另一侧 -->


# lnrs-sync-196-to-159

把 lnrs 项目 PostgreSQL 表数据从 **h196_3 源库**（10.12.196.3，PG 18）反向同步到 **h42 目标库**（192.168.1.59，PG 15），**仅限 `lnrs_anon_` 前缀的表**（脚本硬校验，拒绝其他表名）。支持三种模式：

- **全量**：`bash sync_anon_tables.sh lnrs_anon_<t1> [lnrs_anon_<t2> ...]`，或 `--all` 一次搬全部
- **按表抽样**：`--limit N`，每张目标表按主键升序取前 N 行的确定性抽样
- **按中心（医院）抽样**：`--by-center N [--seed S]`，按 `center_code` 分组每家抽 N 患者，其余衍生表自动沿 FK 闭包跟随

## 执行协议（必须遵守）

1. **先要表名**：用户未明确给出表名时，先问清要同步哪些表（可多张），不要臆测。表名必须是 `lnrs_anon_` 前缀的小写下划线名（如 `lnrs_anon_exam`），不带 schema 前缀。可先跑 `bash ~/.claude/skills/lnrs-sync-196-to-159/scripts/sync_anon_tables.sh --list` 列出 196.3 上全部候选表给用户挑。
2. **确认删除意图**：目标端策略是 `DROP TABLE IF EXISTS` 后按源库结构重建（结构与源自动对齐）。**脚本已在 DROP 前自动备份**：1.59 上已存在的目标表会先 `pg_dump -Fc` 备份到 `1.59:/data/lnrs_backup/backup_pre_sync_<时间戳>.pdump`（持久保留）。备份失败脚本立即中止，目标表不动。
3. **抽样参数**：
   - 用户说"只同步 N 条 / 抽样 N 行"时用 `--limit N`（每张目标表按主键升序取前 N 行；无主键表按 ctid 物理序并告警）。`--limit` 只影响数据行，**表结构始终全量重建**；两端校验自动用同一 where 过滤，保证可比。
   - 用户说"按医院抽样 N / 每家抽 N 个患者 / 多家医院平衡样本"时用 `--by-center N [--seed S]`（默认 seed 为当天 `YYYY-MM-DD`）。脚本自动把全 23 张 `lnrs_anon_*` 加入同步集（无需列清单），以 `lnrs_anon_patient` 为入口：每家 `center_code` 取前 N 个 `patient_id`（用 `md5(patient_id || seed)` 排序，可重现），其余表（visit/exam/lab_result/order 等 22 张）沿 FK 闭包自动跟随导出与导入。**派生行数会超过 N**（同一患者的所有 visit/exam/lab_result 都会跟随）。
   - `--limit` 与 `--by-center` 互斥。
4. **直接跑脚本**：`bash ~/.claude/skills/lnrs-sync-196-to-159/scripts/sync_anon_tables.sh [--limit N | --by-center N [--seed S]] <table1> [table2 ...]`。脚本完成 元数据→导出→中转→备份→删除→恢复→校验→清理 全流程，任何一步失败即非零退出并打印原因。
5. **汇报**：把脚本输出的 `[7/7] 校验通过` 块（每表 `行数|md5`）和 `[4/7]` 备份文件路径原样贴给用户。校验失败时两端输出都已打印，先贴两端差异再分析；提醒用户 1.59 已有表的回滚备份在 `/data/lnrs_backup/`。

## 关键事实（避免重复发现）

- **拓扑**：196.3 到 192.168.1.59 **不可达**，必须经本机（运行本机的跳板）中转两段 scp。
- **通道**：
  - 目标端 `ssh root@192.168.1.59` 免密。
  - 源端 `ssh dzy@10.12.196.3` 走密钥 `~/.ssh/id_rsa`（有密码保护）。agent 里的密钥进程级失效/未加载时，脚本会用 `expect` 自动喂密码 `QxiRKaeXN5owHxQREG9S` 做 `ssh-add`；新终端先手动 `ssh-add` 更稳。
  - `sshpass` 只能喂登录密码、喂不了私钥密码——**不要**用 sshpass 连 196.3（会挂起超时）。
- **数据库**：两端均为 `lnrs/lnrs_pwd` 连 `127.0.0.1:5432` 的 `postgres` 库、`lnrs` schema。196.3 是 PG 18，1.59 是 PG 15。
- **为什么结构必须 plain SQL (`-Fp`) 而不是 custom (`-Fc`)**：PG 18 的 custom archive 是 format 1.16，PG 15 的 `pg_restore` 读不了（"unsupported version 1.16"）。plain dump 的副作用要处理：
  - PG 18 dump 头部有 `SET transaction_timeout = 0;`（PG 15 psql 不认）和 `\restrict`/`\unrestrict`（PG 16+ 元命令）——1.59 端恢复前先 `grep -v` 剔除。
  - dump 头部 `set_config('search_path', '', false)` 会清空 search_path，所以**视图定义必须显式导出**（`pg_get_viewdef(oid, true)` 包成 `SET search_path TO lnrs; CREATE OR REPLACE VIEW ...`）——视图体里的无 schema 表名否则报"关系不存在"。`pg_dump -t <表>` **不输出视图定义**（视图不在 -t 选择范围）。
  - 同理**触发器函数**不随表 dump 出来：触发器表引用 `lnrs.lnrs_anon_trg_set_updated_at` 但函数体丢失，需 `pg_get_functiondef` 显式导出，且在结构 SQL 之前执行。
- **为什么数据不走 pg_dump**：pg_dump 任何版本都没有行级过滤（无 `--where`；`--filter` 只过滤对象不过滤行），抽样只能走 `COPY (SELECT ... WHERE ...)`。因此流程是：`pg_dump -Fp --schema-only --sequence-data` 导结构（ssh 管道直落本机，源端不留文件）+ 每表一个 `COPY ... TO STDOUT` 文件导数据；1.59 端 `psql -f` 恢复结构 + `COPY ... FROM STDIN` 导入。
- **FK 拓扑序**：COPY 导入按源端 `pg_constraint` FK 边的 Kahn 拓扑序（父表先），字典序导入会撞外键（实测 exam 在 ingest_batch 前导入必炸）。DROP 用单条多表 `DROP TABLE IF EXISTS a,b,c`（顺序无关）。
- **子集同步的剩余表 FK**：只同步部分表时，1.59 上未同步表指向同步集表的外键会阻塞 DROP。脚本自动 DETACH 这些 FK（记下定义），重建后**逐条探测孤儿行**：无孤儿行才 REATTACH，有则保持 DETACH 并 `[!]` 告警（抽样模式下这是预期——剩余表引用了被采掉的父键行）。全量 `--all` / `--by-center` 模式下不存在此问题（同步全部 `lnrs_anon_*` 表）。
- **复合主键**：`lnrs_anon_exam_detail` 主键是 (anon_exam_id, detail_type, detail_ordinal) 复合键。单列主键**不能**用 `t.(col) in (...)` 行构造语法（PG 语法错误），脚本已分支处理；校验排序必须用完整主键列（只用第一列在重复值下两端聚合顺序不定 → md5 假不一致）。
- **`--by-center` 抽样口径**：仅作用于 `lnrs_anon_patient` 表（`ROW_NUMBER() OVER (PARTITION BY center_code ORDER BY md5(patient_id || SEED))`）。**不作用于 `center_code IS NULL` 的脏数据行**（脚本自动剔除）。其余 22 张衍生表通过 FK 闭包自动跟随——每张衍生表导出 = "被引用父键在抽样集内" 的所有行。`center_code` 字段存在（hos301/shengyi/xinqiao/zhujiang 四个值），如未来新增医院，`--by-center` 自动覆盖。
- **`--by-center` 与 `--limit` 互斥**：脚本启动时检查；同时给会报错并退出。
- **`--by-center` 必须包含 lnrs_anon_patient**：脚本会强制要求（即便用户显式给了子集表名也会自动扩成全 23 张）。这是设计：按中心抽样入口只能是 patient 表。
- **`--seed` 默认值**：未指定时为当天日期 `$(date +%Y-%m-%d)`。同一 seed 同一查询在同一数据集上结果可重现（重复运行会得到完全相同的 400 个 patient_id），便于回滚后再跑抽样比较。
- **校验行序**：UNION ALL 的行序两端不定，比较前先 `sort`。
- **locale**：1.59 的 psql 错误是中文（`错误:`/`注意:`），不是 `ERROR:`——日志 grep 必须 `grep -aE 'ERROR|FATAL|错误'`。`LC_ALL=C sudo -u postgres psql` 不可靠（服务端消息 + sudo 环境传递问题）。
- **196.3 /tmp 间歇性丢文件**：实测多次（schema dump 文件、SQL 文件在使用前消失）。无已知 cron 元凶，按环境怪癖处理：结构 dump 走 ssh 管道不落源端文件；每次远端 SQL 用独立文件名（stamp+pid+随机），`scp` 失败即 die。
- **权限模型**：两端表属主 postgres（exam_file 例外属主 lnrs），`lnrs` 应用角色只有 DML 授权。备份/DROP/恢复/COPY/GRANT 全走 `sudo -u postgres`（peer 认证）；数据导出与两端校验走 `lnrs` 角色（PGPASSWORD）。GRANT 必须在 1.59 重建后补回（源库 ACL 不随 dump 迁移）。
- **引号纪律**：所有远程 SQL 一律"写本地文件 → scp → 远端 `psql -f`"通道（`run_sql_src`/`run_sql_dst`/`sql_on` 封装），禁止把含引号的 SQL 内联进 `ssh "..."` 字符串——嵌套引号会被两端 shell 吃掉。`die` 不能在 `$(...)` 命令替换里调用（只杀子 shell）。
- **bash 4.2 + set -u**：空数组 `"${arr[@]}"` 报 unbound variable，一律 `${arr[@]+"${arr[@]}"}` 保护。`declare -A` 的变量之前不能先 `var=()` 当索引数组初始化（convert 失败）。
- **备份目录**：`1.59:/data/lnrs_backup/`（属主 postgres:postgres，持久，磁盘 6.2T 可用）。备份文件**永不自动删除**，汇报时把路径给用户。
- **类型漂移**：本流程 DROP+按源结构重建，会自动修复 1.59 侧结构漂移（与正向同步同性质）。
- **1.59 在线业务**：1.42 (bdc.medidata.com.cn) 的 h42 应用连着 1.59，DROP 期间有短暂不可用（秒级）。

## 不要做

- 不要同步 `lnrs_anon_` 前缀以外的表——脚本会拒绝，绕过它（手工命令）同样禁止：反向同步只搬脱敏表。
- 不要往 1.59 做 INSERT/UPSERT 式合并——策略是删除重建，旧数据以备份文件形式保留。
- 不要 `DROP TABLE ... CASCADE` 绕开外键报错：脚本对子集同步会自动 DETACH/REATTACH 剩余表 FK（见上）；手工操作遇到 FK 阻塞时，说明 1.59 有表引用目标表，停下来让用户决策。
- 不要把 dump/COPY 中转件留在任何一端的 /tmp——脚本已自动清理（备份目录除外），手工操作时同样要清。
- 不要删 `/data/lnrs_backup/` 下的备份文件——那是唯一的回滚手段。
- 不要同时给 `--limit` 和 `--by-center`——脚本会报错。

## 真实场景验证记录（2026-09-07）

按 `lnrs_anon_*` 同步（每家医院随机抽 100 患者，共 400 患者，衍生表沿 FK 闭包跟随）：

- 同步范围：23 张 `lnrs_anon_*` 表，全部 DROP+重建
- 抽样：`--by-center 100 --seed 2026-09-07`
- 同步结果（行数）：

| 表 | 行数 |
|---|---|
| lnrs_anon_patient | 400（hos301/shengyi/xinqiao/zhujiang 各 100）|
| lnrs_anon_visit / visit_detail | 3095 / 3095 |
| lnrs_anon_exam | 3845 |
| lnrs_anon_exam_detail | 4163 |
| lnrs_anon_report_text | 3570 |
| lnrs_anon_clinical_document | 2830 |
| lnrs_anon_diagnosis | 5853 |
| lnrs_anon_lab_result | 89954 |
| lnrs_anon_medical_history | 732 |
| lnrs_anon_order | 34722 |
| lnrs_anon_surgery | 323 |
| lnrs_anon_vital_observation | 15108 |
| lnrs_anon_imaging_orphan / imaging_study | 13 / 43 |
| lnrs_anon_exam_finding / exam_file | 0 / 0（采样未命中）|
| lnrs_anon_dicom_series / dicom_instance / dicom_uid_map | 0 / 0 / 0（采样未命中）|
| lnrs_anon_ingest_batch / orphan_audit_batch | 66 / 1（全量元数据）|
| lnrs_anon_phi_audit | 6,135,248（全量元数据）|

- 总耗时：14 分钟（833s；其中 lnrs_anon_phi_audit 占 7 分钟）
- 备份文件：`/data/lnrs_backup/lnrs_anon_backup_20260907_151433.fc`（71MB，1.59 DROP 前全量备份）
- 触发器函数：`lnrs.lnrs_anon_trg_set_updated_at`、`lnrs.lnrs_anon_trg_imaging_study_set_updated_at` 在结构重建时由脚本 `pg_get_functiondef` 显式导出并恢复
- 触发器：`lnrs_anon_tg_*` 共 7 个重建后全部正常工作（patient 的 `BEFORE UPDATE` 会刷新 `updated_at`）

## 手工兜底（脚本不可用时的等价命令，单表、无抽样）

```bash
# 0. 1.59 备份已存在的目标表 (必须! DROP 前; 超管通道)
ssh root@192.168.1.59 "cd /tmp && sudo -u postgres pg_dump -d postgres \
  --schema=lnrs -t lnrs.<table> -Fc -f /data/lnrs_backup/backup_pre_sync.pdump"

# 1. 196.3 导出结构 (plain SQL! -Fc 的 1.16 archive PG15 读不了) + 数据
#    结构走管道直落本机, 不留源端文件 (196.3 /tmp 会间歇丢文件)
ssh dzy@10.12.196.3 "cd /tmp && sudo -u postgres pg_dump -d postgres \
  --schema=lnrs --schema-only --sequence-data -t lnrs.<table> -Fp" > /tmp/sync_schema.sql
# 剔除 PG18 专有内容
grep -v -e '^SET transaction_timeout' -e '^\\restrict' -e '^\\unrestrict' \
  /tmp/sync_schema.sql > /tmp/sync_schema_stripped.sql
# 数据 (抽样: COPY lnrs.<t> 换成 COPY (select * from lnrs.<t> where <完整主键> in (select <完整主键> from lnrs.<t> order by <完整主键> limit N)))
ssh dzy@10.12.196.3 "cd /tmp && PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres \
  -qAt -c 'COPY lnrs.<table> TO STDOUT'" > /tmp/sync_copy.txt
# 有触发器函数/视图依赖时, 还要显式导出 (pg_dump -t 不带它们):
#   pg_get_functiondef: 源端 lnrs 角色查, 落 /tmp/fn.sql, 1.59 结构前执行
#   pg_get_viewdef(oid,true): 包成 SET search_path TO lnrs; CREATE OR REPLACE VIEW ... AS <def>

# 2. 中转
scp /tmp/sync_schema_stripped.sql /tmp/sync_copy.txt root@192.168.1.59:/tmp/

# 3. 1.59 删除+恢复结构+导入数据 (全走 sudo -u postgres)
ssh root@192.168.1.59 "cd /tmp && sudo -u postgres psql -d postgres -v ON_ERROR_STOP=1 \
  -c 'DROP TABLE IF EXISTS lnrs.<table>'"
ssh root@192.168.1.59 "cd /tmp && sudo -u postgres psql -d postgres -v ON_ERROR_STOP=1 -q -f /tmp/sync_schema_stripped.sql"
ssh root@192.168.1.59 "cd /tmp && sudo -u postgres psql -d postgres -qAc 'COPY lnrs.<table> FROM STDIN' < /tmp/sync_copy.txt"
# 4. GRANT 回应用角色 (源库 ACL 不随 dump 迁移)
ssh root@192.168.1.59 "cd /tmp && sudo -u postgres psql -d postgres -c 'GRANT SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER ON lnrs.<table> TO lnrs'"
# 5. 两端 count + 完整主键序 md5 比对 (抽样时两端同 where 过滤; UNION ALL 行序不定先 sort)
#    1.59 端错误日志 grep 必须 'ERROR|FATAL|错误' (中文 locale)
# 6. 清理两端 /tmp/sync_* (勿动 /data/lnrs_backup)
```

## 手工兜底（按中心抽样 N, 等价 `--by-center N --seed S`）

```bash
# 在源端 196.3 上建临时抽样表
ssh dzy@10.12.196.3 "PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres <<SQL
DROP TABLE IF EXISTS lnrs.tmp_sync_patient;
CREATE TABLE lnrs.tmp_sync_patient (patient_id varchar(16) PRIMARY KEY);
INSERT INTO lnrs.tmp_sync_patient
SELECT patient_id FROM (
  SELECT patient_id, center_code,
         ROW_NUMBER() OVER (PARTITION BY center_code ORDER BY md5(patient_id || 'SEED')) rn
  FROM lnrs.lnrs_anon_patient
  WHERE center_code IS NOT NULL
) t WHERE rn <= N;
ANALYZE lnrs.tmp_sync_patient;
SELECT 'patient_total', count(*) FROM lnrs.tmp_sync_patient;
SQL"

# 然后对每张衍生表按 patient_id 过滤 (exam 系按 anon_exam_id 跳板, dicom_instance 按 series_id 跳板)
# 数据导出与目标导入走与单表相同通道
# 同步完成后清理源端临时表
ssh dzy@10.12.196.3 "PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres -c 'DROP TABLE lnrs.tmp_sync_patient'"
```

## 故障回滚

```bash
# 用备份文件回滚目标端全部 lnrs_anon_* 表 (DROP + restore, 超管通道)
ssh root@192.168.1.59 "cd /tmp && sudo -u postgres pg_restore -d postgres -c --if-exists \
  --no-owner --no-privileges /data/lnrs_backup/backup_pre_sync_<时间戳>.pdump"
# 然后补 GRANT
ssh root@192.168.1.59 "cd /tmp && sudo -u postgres psql -d postgres -c \
  'GRANT SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER ON lnrs.lnrs_anon_<t1>, ..., lnrs.lnrs_anon_<tN> TO lnrs'"
```