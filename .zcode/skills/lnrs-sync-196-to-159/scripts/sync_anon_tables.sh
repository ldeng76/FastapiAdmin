#!/bin/bash
# ============================================================
# lnrs 表反向同步: 10.12.196.3 (h196_3 源库, PG 18) -> 192.168.1.59 (h42 目标库, PG 15)
# 只允许 lnrs_anon_ 前缀的表。
#
# 拓扑: 196.3 到 192.168.1.59 不可达，必须经本机中转:
#   196.3 上 [sudo -u postgres] pg_dump -Fp --schema-only (表+依赖序列setval, 经 ssh 管道直落本机)
#          + 触发器函数 pg_get_functiondef + 依赖视图 pg_get_viewdef 显式导出
#          + [lnrs 角色] COPY 数据 (抽样时 where 过滤, 含 FK 闭包行)
#     --scp--> 本机 --scp--> 1.59
#   1.59 上 [sudo -u postgres] 备份已有对象(-Fc) -> (子集同步: DETACH 剩余表 FK)
#          -> DROP(视图/表/序列) -> psql 恢复结构(先触发器函数, 后表, 后视图)
#          -> COPY 导入(FK 拓扑序) -> GRANT 回 lnrs 角色 -> (REATTACH 无孤儿行的 FK)
#          -> 两端 count+md5 校验 -> 清理
#
# 版本屏障 (重要): PG18 的 custom archive (format 1.16) 无法被 PG15 pg_restore 读取
#   ("unsupported version 1.16"), 所以 18 -> 15 结构导出必须用 plain SQL (-Fp);
#   plain 文件里 PG18 专有 GUC "SET transaction_timeout" 在 1.59 端先剔除再执行。
#   备份是 1.59 自己 dump 自己 (15->15), 仍用 -Fc。
#
# 权限模型: 两端的 lnrs_anon_* 表属主都是 postgres 角色, lnrs 应用角色只有普通
#   DML 授权。因此:
#   - 结构 dump / 备份 / DROP / pg_restore / COPY 导入 / GRANT 全部走
#     "root 免密 ssh + sudo -u postgres" (peer 本地 socket 认证, 超管, 免密码)
#   - 数据导出和两端校验用 lnrs 角色 (PGPASSWORD) 模拟应用视角
#   两台跳板机 (196.3 dzy / 1.59 root) 都有免密 sudo, 已验证。
#
# 为什么数据不走 pg_dump: pg_dump 任何版本都没有行级过滤 (无 --where, --filter
#   只过滤对象), 抽样只能走 COPY (SELECT ... WHERE ...)。
#
# 同步闭包: DROP 某表会被 1.59 上依赖它的对象阻塞。脚本自动收集:
#   - 依赖视图 (pg_depend deptype='o'): 确认源端同名视图存在后纳入闭包,
#     源端没有 = schema 漂移, 停下让用户决策
#   - 依赖序列 (pg_depend deptype='a') + 触发器函数: 进结构 dump, 重建时恢复
#   - FK 约束: 随表走, 不单独处理
#
# 用法:
#   ./sync_anon_tables.sh --list                    # 列出 196.3 上所有 lnrs_anon_* 表
#   ./sync_anon_tables.sh <table1> [table2 ...]     # 全量同步 (表名带 lnrs_anon_ 前缀, 不带 schema)
#   ./sync_anon_tables.sh --all                     # 同步全部 lnrs_anon_* 表
#   ./sync_anon_tables.sh --limit N <table1> [...]   # 每表按主键顺序取前 N 行 (确定性抽样)
#   ./sync_anon_tables.sh --by-center N [--seed S]   # 按 center_code 分组每家抽 N 患者 (其余表沿 FK 闭包)
#                                              (要求 lnrs_anon_patient 在表集; SEED 默认当天日期)

#
# 备份: DROP 前 1.59 上已存在的对象会先 pg_dump -Fc 备份到
#   1.59:/data/lnrs_backup/backup_pre_sync_<时间戳>.pdump (持久保留, 永不自动删除)
#
# 引号纪律: 所有远程 SQL 走 "写本地文件 -> scp -> 远端 psql -f" 通道
#   (run_sql_src/run_sql_dst/sql_on 封装), 禁止把含引号的 SQL 内联进 ssh "..." 字符串。
# ============================================================
set -euo pipefail

SRC="dzy@10.12.196.3"      # 源库服务器 (h196_3): ssh 密钥 ~/.ssh/id_rsa (有密码保护), dzy 有免密 sudo
DST="root@192.168.1.59"    # 目标库服务器 (h42): 免密 ssh root, root 有免密 sudo
DB_USER="lnrs"             # 应用角色
DB_PWD="lnrs_pwd"
DB_NAME="postgres"
DB_HOST="127.0.0.1"
SCHEMA="lnrs"
PREFIX="lnrs_anon_"
KEY_PWD='QxiRKaeXN5owHxQREG9S'   # ~/.ssh/id_rsa 私钥密码
BACKUP_DIR="/data/lnrs_backup"   # 1.59 上 DROP 前备份的持久目录 (须 postgres 可写)
STAMP="$(date +%Y%m%d%H%M%S)"
RND="$$"   # 本进程 pid; 远端 SQL 文件按 (stamp, pid, 随机) 命名, 杜绝并发实例
               # 共用 /var/tmp/lnrs_sync_sql.sql 互相删文件

die() { echo "ERROR: $*" >&2; exit 1; }

# ---------- 远端 SQL 通道 (文件通道, 杜绝引号问题; psql -f 一律 ON_ERROR_STOP) ----------
# 每次调用用独立远端路径 (R_REMOTE), 避免并发实例竞争
R_REMOTE=""
_new_rremote() { R_REMOTE="/var/tmp/lnrs_sync_${STAMP}_${RND}_$RANDOM.sql"; }
run_sql_src() { # $1=本地sql文件 -> 196.3 上 lnrs 角色执行, 输出 psql -At 结果
  local sqlf="$1"
  _new_rremote
  scp -o BatchMode=yes "$sqlf" "$SRC:$R_REMOTE" >/dev/null || die "scp 到源端失败 (并发实例或网络问题)"
  ssh -o BatchMode=yes "$SRC" \
    "PGPASSWORD=$DB_PWD psql -h $DB_HOST -p 5432 -U $DB_USER -d $DB_NAME -qAt -v ON_ERROR_STOP=1 -f $R_REMOTE; rc=\$?; rm -f $R_REMOTE; exit \$rc"
}
run_sql_dst() { # $1=本地sql文件 -> 1.59 上 sudo -u postgres (超管) 执行
  local sqlf="$1"
  _new_rremote
  scp -o BatchMode=yes "$sqlf" "$DST:$R_REMOTE" >/dev/null || die "scp 到 1.59 失败 (并发实例或网络问题)"
  ssh -o BatchMode=yes "$DST" \
    "cd /tmp && sudo -u postgres psql -d $DB_NAME -qAt -v ON_ERROR_STOP=1 -f $R_REMOTE; rc=\$?; rm -f $R_REMOTE; exit \$rc"
}
# sql_on <src|dst> <SQL文本>: 经临时文件通道执行并回显结果; 失败时向 stderr 打印并返回 1
# 注意: 调用处若用 $(...) 捕获, die/exit 只杀子 shell, 需用 || 链式处理
sql_on() {
  local which="$1" sql="$2" f
  f="$(mktemp /tmp/lnrs_sync_adhoc.XXXXXX.sql)"
  chmod 644 "$f"    # mktemp 默认 0600, scp 过去 postgres 用户读不了
  printf '%s\n' "$sql" > "$f"
  if [ "$which" = "src" ]; then out="$(run_sql_src "$f")"; else out="$(run_sql_dst "$f")"; fi
  local rc=$?
  rm -f "$f"
  [ $rc -eq 0 ] || { echo "远端 SQL 失败 (rc=$rc): $sql" >&2; return 1; }
  printf '%s\n' "$out"
}

# ---------- SSH 通道自检 ----------
ssh -o BatchMode=yes -o ConnectTimeout=8 "$DST" true </dev/null 2>/dev/null \
  || die "无法免密 ssh 到 $DST (root)"
ssh -o BatchMode=yes "$DST" "sudo -n true" </dev/null 2>/dev/null \
  || die "$DST 上 root 无免密 sudo (目标端超管通道不可用)"
ssh -o BatchMode=yes "$SRC" "sudo -n true" </dev/null 2>/dev/null \
  || die "$SRC 上无免密 sudo (源端超管通道不可用)"
if ! ssh -o BatchMode=yes -o ConnectTimeout=8 "$SRC" true </dev/null 2>/dev/null; then
  command -v expect >/dev/null 2>&1 || die "无法免密 ssh 到 $SRC 且无 expect，请手动 ssh-add ~/.ssh/id_rsa"
  echo "[*] 196.3 不可达，尝试经 expect 将 ~/.ssh/id_rsa 加载进 ssh-agent..."
  expect -c "set timeout 20; spawn ssh-add /home/dzy/.ssh/id_rsa
expect {\"passphrase\" {send \"$KEY_PWD\r\"; exp_continue}; eof}" >/dev/null 2>&1 || true
  ssh -o BatchMode=yes -o ConnectTimeout=8 "$SRC" true </dev/null 2>/dev/null \
    || die "加载密钥后仍无法 ssh 到 $SRC"
fi

# ---------- 参数解析 ----------
LIMIT=0; TABLES=(); ALL=0; BY_CENTER=0; SEED=""

while [ $# -gt 0 ]; do
  case "$1" in
    --list)
      sql_on src "select relname from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='$SCHEMA' and c.relkind='r' and relname like '$PREFIX%' order by relname" \
        || die "无法查询表清单"
      exit 0 ;;
    --all) ALL=1 ;;
    --limit)
      shift; [ $# -ge 1 ] || die "--limit 需要数值参数"
      [[ "$1" =~ ^[1-9][0-9]*$ ]] || die "--limit 必须是正整数: $1"
      LIMIT="$1" ;;
    --by-center)
      shift; [ $# -ge 1 ] || die "--by-center 需要数值参数"
      [[ "$1" =~ ^[1-9][0-9]*$ ]] || die "--by-center 必须是正整数: $1"
      BY_CENTER="$1" ;;
    --seed)
      shift; [ $# -ge 1 ] || die "--seed 需要字符串参数"
      SEED="$1" ;;
    -h|--help)
      grep '^# ' "$0" | sed 's/^# //'; exit 0 ;;
    -*) die "未知选项: $1" ;;
    *) TABLES+=("$1") ;;
  esac
  shift
done

# --limit 与 --by-center 互斥检查 (放在 while 循环后, 任意顺序都生效)
if [ "$LIMIT" -gt 0 ] && [ "$BY_CENTER" -gt 0 ]; then
  die "--limit 与 --by-center 互斥, 二选一"
fi

if [ "$ALL" -eq 1 ] || [ "$BY_CENTER" -gt 0 ]; then
  mapfile -t TABLES < <(sql_on src "select relname from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='$SCHEMA' and c.relkind='r' and relname like '$PREFIX%' order by relname")
fi

[ ${#TABLES[@]} -gt 0 ] || [ "$BY_CENTER" -gt 0 ] || die "用法: $0 [--list] [--all] [--limit N | --by-center N [--seed S]] <table1> [table2 ...]  (表名需带 $PREFIX 前缀, 或用 --all/--by-center)"


# ---------- 表名校验 (强制 lnrs_anon_ 前缀) ----------
targs=(); drop_list=(); table_names=(); grant_list=()
for t in "${TABLES[@]}"; do
  [[ "$t" =~ ^${PREFIX}[a-z0-9_]*$ ]] || die "表名必须以 $PREFIX 开头且为小写下划线: $t"
  targs+=("-t" "$SCHEMA.$t")
  drop_list+=("$SCHEMA.$t")
  grant_list+=("$SCHEMA.$t")
  table_names+=("$t")
done

# --by-center 强制要求 lnrs_anon_patient 在表集 (作为抽样入口表)
if [ "$BY_CENTER" -gt 0 ]; then
  has_patient=0
  for t in "${table_names[@]}"; do [ "$t" = "${PREFIX}patient" ] && has_patient=1; done
  [ "$has_patient" -eq 1 ] || die "--by-center 要求 lnrs_anon_patient 在待同步表集中 (入口表)"
  : "${SEED:=$(date +%Y-%m-%d)}"
  echo "[i] --by-center 抽样: 每家医院前 $BY_CENTER 患者, seed='$SEED'"
fi

# ---------- 同步闭包: 依赖视图 / 序列 / 触发器函数 ----------
view_list=(); view_kinds=(); seq_list=(); trig_fns=()
# 1. 源端依赖待同步表的视图 (权威闭包): plain dump 不会自动带上, 需 pg_get_viewdef 显式导出
#    (在 1.59 端检测会在目标端视图缺失时漏闭包, 不可靠)
dep_file="/tmp/lnrs_sync_deps_${STAMP}.sql"
{
  echo "select distinct c.relname, c.relkind::text from pg_depend d join pg_rewrite r on r.oid=d.objid join pg_class c on c.oid=r.ev_class join pg_namespace n on n.oid=c.relnamespace where c.relkind in ('v','m') and n.nspname='$SCHEMA' and d.refclassid='pg_class'::regclass and d.refobjid in ("
  first=1
  for t in "${table_names[@]}"; do
    if [ $first -eq 1 ]; then first=0; else echo "union"; fi
    echo "  select c.oid from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='$SCHEMA' and c.relname='$t'"
  done
  echo "  )"
  echo "order by 1"
} > "$dep_file"
chmod 644 "$dep_file"
deps="$(run_sql_src "$dep_file")" || die "查询源端依赖视图失败"
rm -f "$dep_file"
if [ -n "$deps" ]; then
  while IFS='|' read -r depname depkind; do
    [ -z "$depname" ] && continue
    view_list+=("$depname"); view_kinds+=("$depkind")
    echo "      [i] 依赖$([ "$depkind" = v ] && echo 视图 || echo 物化视图)纳入同步闭包: $depname (源端导出, 1.59 先 DROP 再重建)"
  done <<< "$deps"
fi
# 1b. 目标端安全网: 1.59 上依赖待同步表的视图必须已在闭包里 (否则 DROP 表会被阻塞)
dep_file="/tmp/lnrs_sync_depsdst_${STAMP}.sql"
{
  echo "select distinct c.relname from pg_depend d join pg_rewrite r on r.oid=d.objid join pg_class c on c.oid=r.ev_class join pg_namespace n on n.oid=c.relnamespace where c.relkind in ('v','m') and n.nspname='$SCHEMA' and d.refclassid='pg_class'::regclass and d.refobjid in ("
  first=1
  for t in "${table_names[@]}"; do
    if [ $first -eq 1 ]; then first=0; else echo "union"; fi
    echo "  select c.oid from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='$SCHEMA' and c.relname='$t'"
  done
  echo "  )"
  echo "order by 1"
} > "$dep_file"
chmod 644 "$dep_file"
dst_deps="$(run_sql_dst "$dep_file")" || die "查询 1.59 依赖视图失败"
rm -f "$dep_file"
if [ -n "$dst_deps" ]; then
  while read -r depname; do
    [ -z "$depname" ] && continue
    in_list=0
    for v in "${view_list[@]}"; do [ "$v" = "$depname" ] && in_list=1; done
    [ $in_list -eq 1 ] || die "1.59 上视图 $depname 依赖待同步表但源端无此视图 -- schema 漂移, 请人工决策"
  done <<< "$dst_deps"
fi
# 2. 依赖序列 (源端查 deptype='a'): 重建后必须 setval, 否则序列归零撞主键
#    in_list: 生成 'a','b','c' 形式的 SQL IN 列表 (逗号分隔, 无尾逗号)
in_list() { local first=1 x; for x in "$@"; do if [ $first -eq 1 ]; then first=0; else printf ","; fi; printf "'%s'" "$x"; done; }
#    预先构造逗号分隔的 IN 列表 (两处查询共用)
IN_TBL="$(in_list "${table_names[@]}")"
# 2. 依赖序列 (源端查 deptype='a'): 重建后必须 setval, 否则序列归零撞主键
seq_file="/tmp/lnrs_sync_seqs_${STAMP}.sql"
{
  echo "select c.relname from pg_depend d join pg_class c on c.oid=d.objid join pg_class t on t.oid=d.refobjid join pg_namespace n on n.oid=c.relnamespace where d.deptype='a' and c.relkind='S' and n.nspname='$SCHEMA' and t.relname in ($IN_TBL) order by 1"
} > "$seq_file"
chmod 644 "$seq_file"
seqs="$(run_sql_src "$seq_file")" || die "查询源端依赖序列失败"
rm -f "$seq_file"
if [ -n "$seqs" ]; then
  mapfile -t seq_list <<< "$seqs"
  echo "      [i] 依赖序列纳入结构 dump (含 setval): ${seq_list[*]}"
fi
# 3. 触发器函数 (源端查 pg_trigger): 恢复时 CREATE TRIGGER 依赖函数存在
trig_file="/tmp/lnrs_sync_trig_${STAMP}.sql"
{
  echo "select distinct p.proname from pg_trigger tg join pg_class t on t.oid=tg.tgrelid join pg_proc p on p.oid=tg.tgfoid join pg_namespace n on n.oid=t.relnamespace where n.nspname='$SCHEMA' and not tg.tgisinternal and t.relname in ($IN_TBL) order by 1"
} > "$trig_file"
chmod 644 "$trig_file"
trigs="$(run_sql_src "$trig_file")" || die "查询源端触发器函数失败"
rm -f "$trig_file"
if [ -n "$trigs" ]; then
  mapfile -t trig_fns <<< "$trigs"
  echo "      [i] 触发器函数纳入同步闭包: ${trig_fns[*]}"
fi

# 源端查 FK 边 child|parent|condef (condef 为源端原始定义文本, 用于抽样模式的 where 展开)
# bash 4.2 + set -u: 空数组一律 ${arr[@]+"${arr[@]}"} 保护
declare -A parents_map
fk_defs=""   # 每行: child|parent|condef
fk_file="/tmp/lnrs_sync_fkedges_${STAMP}.sql"
printf 'select cc.relname || '\''|'\'' || f.relname || '\''|'\'' || pg_get_constraintdef(c.oid) from pg_constraint c join pg_class cc on cc.oid=c.conrelid join pg_class f on f.oid=c.confrelid join pg_namespace n on n.oid=cc.relnamespace where c.contype='\''f'\'' and n.nspname='\''%s'\'' and cc.relname in (%s) and f.relname in (%s) order by 1;\n' "$SCHEMA" "$IN_TBL" "$IN_TBL" > "$fk_file"
chmod 644 "$fk_file"
edges="$(run_sql_src "$fk_file")" || die "查询 FK 依赖边失败"
rm -f "$fk_file"
if [ -n "$edges" ]; then
  while IFS='|' read -r child parent condef; do
    [ -z "$child" ] && continue
    fk_defs="${fk_defs}${child}|${parent}|${condef}
"
    case " ${parents_map[$child]:-} " in
      *" $parent "*) : ;;
      *) parents_map[$child]="${parents_map[$child]:-} $parent" ;;
    esac
  done <<< "$edges"
fi
topo_order=()
while :; do
  prev=${#topo_order[@]}
  for cand in "${table_names[@]}"; do
    already=0
    for o in ${topo_order[@]+"${topo_order[@]}"}; do [ "$o" = "$cand" ] && { already=1; break; }; done
    [ $already -eq 1 ] && continue
    blocked=0
    for p in ${parents_map[$cand]:-}; do
      pdone=0
      for o in ${topo_order[@]+"${topo_order[@]}"}; do [ "$o" = "$p" ] && { pdone=1; break; }; done
      [ $pdone -eq 0 ] && { blocked=1; break; }
    done
    [ $blocked -eq 0 ] && topo_order+=("$cand")
  done
  [ ${#topo_order[@]} -ge ${#table_names[@]} ] && break
  [ ${#topo_order[@]} -gt $prev ] || die "FK 依赖出现环, 无法确定导入顺序"
done
echo "      [i] FK 拓扑导入顺序: ${topo_order[*]}"

# ---------- Step 1: 源端表存在性 + 抽样 where 子句 (FK 定点迭代) ----------
# 全量模式: where_map 全空, 各表整表导出/校验。
# 抽样模式: S(t) = "PK 前 N 行" ∪ 各 FK 边 (子 t 父 p) 的 p."fcol" in (select fcol from t where C(t));
#   C(t) 依赖 C(child), 沿 FK 图迭代至不动点 (叶子表先定型), 保证:
#   每个子表行引用的父键必然在父表导出集内 (FK 不炸), 且两端 (源/目标) 用同一 C(t) 导出与校验。
#   注意: 实际导出行数可能 > N (FK 闭包行)。
declare -A pk_map
for t in "${table_names[@]}"; do
  sql_on src "select 1 from pg_class where oid='$SCHEMA.$t'::regclass" > "/tmp/lnrs_sync_chk_${STAMP}" \
    || die "源端 (196.3) 不存在表 $SCHEMA.$t"
  pk_map[$t]="$(sql_on src "select string_agg(a.attname, ',' order by a.attnum) from pg_index i join pg_class c on c.oid=i.indrelid join pg_attribute a on a.attrelid=c.oid and a.attnum=any(i.indkey) and a.attnum>0 where c.oid='$SCHEMA.$t'::regclass and c.relnamespace='$SCHEMA'::regnamespace and i.indisprimary")"
done
rm -f "/tmp/lnrs_sync_chk_${STAMP}"
declare -A where_map
if [ "$BY_CENTER" -gt 0 ]; then
  # --by-center 模式: 仅 lnrs_anon_patient 表用 ROW_NUMBER OVER (PARTITION BY center_code) 抽样,
  #   其余表 (visit/exam/lab_result/order 等) 由 FK 闭包迭代自动填入 where_map (沿 fk_defs 走)
  t="${PREFIX}patient"
  pk="${pk_map[$t]:-}"
  if [ -n "$pk" ]; then
    IFS=',' read -ra PKC <<< "$pk"
    keycol="\"${PKC[0]}\""
    where_map[$t]="($t.$keycol in (select patient_id FROM (SELECT patient_id, ROW_NUMBER() OVER (PARTITION BY center_code ORDER BY md5(patient_id || '$SEED')) AS rn FROM $SCHEMA.$t WHERE center_code IS NOT NULL) t WHERE rn <= $BY_CENTER))"
  else
    die "$SCHEMA.$t 无主键, --by-center 要求 patient_id 是主键"
  fi
else
  # --limit 模式: 每表独立按 PK 前 N 行
  for t in "${table_names[@]}"; do
    pk="${pk_map[$t]:-}"
    if [ -n "$pk" ]; then
      IFS=',' read -ra PKC <<< "$pk"
      keycol=""
      for c in "${PKC[@]}"; do
        if [ -z "$keycol" ]; then keycol="\"$c\""; else keycol+=", \"$c\""; fi
      done
      if [ ${#PKC[@]} -eq 1 ]; then
        where_map[$t]="($t.$keycol in (select $keycol from $SCHEMA.$t order by $keycol limit $LIMIT))"
      else
        where_map[$t]="($t.($keycol) in (select $keycol from $SCHEMA.$t order by $keycol limit $LIMIT))"
      fi
    else
      echo "      [!] $SCHEMA.$t 无主键, 按 ctid 物理序取样 (期间若发生表重写, 抽样集可能漂移)"
      where_map[$t]="($t.ctid in (select ctid from $SCHEMA.$t order by ctid limit $LIMIT))"
    fi
  done
fi

  # FK 闭包: 逆拓扑序处理, 每处理子表 t 时把 "父表列 in (select 子表列 from t where C(t))" 追加进父表条件
  #   (t 在拓扑序中位于其父之前 = 其所有子表已处理完, C(t) 已定型)
  n=${#topo_order[@]}
  for ((k=n-1; k>=0; k--)); do
    t="${topo_order[$k]}"
    while IFS='|' read -r child parent condef; do
      [ -z "$child" ] && continue
      [ "$child" = "$t" ] || continue
      # 解析子表 FK 列: FOREIGN KEY (col1[, col2...])
      ck="$(printf '%s' "$condef" | sed -n 's/.*FOREIGN KEY[[:space:]]*(\([^)]*\)).*/\1/p')"
      read -ra CC <<< "$ck"
      # 复合键逐列 or 展开 (取超集: 行数可能略多, 但两端同一条件, 校验一致, FK 必然满足)
      extra=""
      for c in ${CC[@]+"${CC[@]}"}; do
        extra="$extra or $parent.\"$c\" in (select \"$c\" from $SCHEMA.$child where ${where_map[$child]})"
      done
      where_map[$parent]="${where_map[$parent]%)}$extra)"
    done <<< "$fk_defs"
  done

echo "[1/7] 源端表确认存在 (196.3): ${table_names[*]}"
if [ "$LIMIT" -gt 0 ]; then
  echo "      抽样: 每表 PK 前 $LIMIT 行 + FK 闭包行 (实际行数可能 > N; 两端同条件, 校验可比)"
elif [ "$BY_CENTER" -gt 0 ]; then
  echo "      按中心抽样: 每家医院前 $BY_CENTER 患者 (seed='$SEED'); 其余表沿 FK 闭包跟随"
fi

# ---------- Step 2: 196.3 结构导出 (plain SQL; 超管) + 数据导出 (lnrs 角色 COPY) ----------
# 注意: 18 -> 15 不能用 -Fc (PG18 custom 1.16 archive 无法被 PG15 pg_restore 读取),
#       只能 plain SQL; 恢复端需剔除 PG18 专有 GUC (SET transaction_timeout)
dump_targs=("${targs[@]}")
SCHEMA_SQL="/tmp/lnrs_sync_schema_${STAMP}.sql"
# 结构 plain SQL 经 ssh 管道直接落本机 (源端不留结构文件, 避免源端 /tmp 间歇性清理/占用导致 scp 失败)
ssh -o BatchMode=yes "$SRC" "cd /tmp && sudo -u postgres pg_dump -d $DB_NAME --schema=$SCHEMA --schema-only --sequence-data ${dump_targs[*]} -Fp" > "$SCHEMA_SQL" 2> "/tmp/lnrs_sync_dumperr_${STAMP}.log" \
  || die "pg_dump 结构失败: $(head -3 /tmp/lnrs_sync_dumperr_${STAMP}.log | tr '\n' ' ')"
rm -f "/tmp/lnrs_sync_dumperr_${STAMP}.log"
head -2 "$SCHEMA_SQL" | grep -q "PostgreSQL database dump" || die "pg_dump 输出异常 (非 plain dump 文件): $(head -1 "$SCHEMA_SQL" | cut -c1-80)"
# 触发器函数 / 视图: pg_dump -t 按表名选对象, 不输出函数和视图定义 (plain 模式实测),
#   必须用 pg_get_functiondef / pg_get_viewdef 显式导出, 恢复时先执行
if [ ${#trig_fns[@]} -gt 0 ]; then
  for f in "${trig_fns[@]}"; do
    sql_on src "select pg_get_functiondef(p.oid) from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='$SCHEMA' and p.proname='$f'" > "/tmp/lnrs_sync_fn_${f}.sql" \
      || die "提取触发器函数 $f 定义失败"
    printf ';\n' >> "/tmp/lnrs_sync_fn_${f}.sql"
  done
fi
if [ ${#view_list[@]} -gt 0 ]; then
  for i in "${!view_list[@]}"; do
    v="${view_list[$i]}"
    if [ "${view_kinds[$i]}" = "m" ]; then
      die "物化视图 $v 依赖待同步表, 本脚本不支持重建 (需 REFRESH), 请人工决策"
    fi
    sql_on src "select pg_get_viewdef(c.oid, true) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='$SCHEMA' and c.relname='$v' and c.relkind='v'" > "/tmp/lnrs_sync_viewdef_${v}.sql" \
      || die "提取视图 $v 定义失败"
    # 视图定义里的基表多为不带 schema 前缀, 单独 psql -f 时默认 search_path 未必命中 $SCHEMA,
    #   显式 SET 保证解析正确
    printf 'SET search_path TO %s;\nCREATE OR REPLACE VIEW %s.%s AS\n%s;\n' "$SCHEMA" "$SCHEMA" "$v" "$(cat "/tmp/lnrs_sync_viewdef_${v}.sql")" > "/tmp/lnrs_sync_view_${v}.sql"
  done
fi
for t in "${table_names[@]}"; do
  if [ "$LIMIT" -gt 0 ]; then
    printf 'COPY (select * from %s.%s where %s) TO STDOUT;\n' "$SCHEMA" "$t" "${where_map[$t]}" > "/tmp/lnrs_sync_exp_${t}.sql"
  else
    printf 'COPY %s.%s TO STDOUT;\n' "$SCHEMA" "$t" > "/tmp/lnrs_sync_exp_${t}.sql"
  fi
  chmod 644 "/tmp/lnrs_sync_exp_${t}.sql"
  _new_rremote
  scp -o BatchMode=yes "/tmp/lnrs_sync_exp_${t}.sql" "$SRC:$R_REMOTE" >/dev/null || die "scp 导出 SQL 到源端失败"
  ssh -o BatchMode=yes "$SRC" \
    "PGPASSWORD=$DB_PWD psql -h $DB_HOST -p 5432 -U $DB_USER -d $DB_NAME -qAt -f $R_REMOTE > /tmp/lnrs_sync_${STAMP}_${t}.copy; rc=\$?; rm -f $R_REMOTE; exit \$rc" \
    || die "COPY 导出 $SCHEMA.$t 失败"
  rm -f "/tmp/lnrs_sync_exp_${t}.sql"
done
echo "[2/7] 源端结构+数据导出完成 (196.3)"

# ---------- Step 3: 经本机中转 (结构 SQL + 触发器函数 SQL + COPY 数据) ----------
DATA_DIR="/tmp/lnrs_sync_data_${STAMP}"
mkdir -p "$DATA_DIR"
if [ ${#trig_fns[@]} -gt 0 ]; then
  for f in "${trig_fns[@]}"; do scp -o BatchMode=yes "/tmp/lnrs_sync_fn_${f}.sql" "$DST:/tmp/lnrs_sync_fn_${f}.sql" >/dev/null || die "scp 函数 $f 本机 -> 1.59 失败"; done
fi
if [ ${#view_list[@]} -gt 0 ]; then
  for v in "${view_list[@]}"; do scp -o BatchMode=yes "/tmp/lnrs_sync_view_${v}.sql" "$DST:/tmp/lnrs_sync_view_${v}.sql" >/dev/null || die "scp 视图 $v 本机 -> 1.59 失败"; done
fi
for t in "${table_names[@]}"; do
  scp -o BatchMode=yes "$SRC:/tmp/lnrs_sync_${STAMP}_${t}.copy" "$DATA_DIR/${t}.copy" >/dev/null || die "scp 数据 $t 196.3 -> 本机失败"
done
ssh -o BatchMode=yes "$DST" "mkdir -p /tmp/lnrs_sync_data_${STAMP}" >/dev/null
scp -o BatchMode=yes "$SCHEMA_SQL" "$DST:/tmp/lnrs_sync_schema_${STAMP}.sql" >/dev/null || die "scp 结构 本机 -> 1.59 失败"
scp -o BatchMode=yes "$DATA_DIR/"*.copy "$DST:/tmp/lnrs_sync_data_${STAMP}/" >/dev/null || die "scp 数据 本机 -> 1.59 失败"
echo "[3/7] 结构 SQL + ${#table_names[@]} 个数据文件已中转至 1.59"

# ---------- Step 4: 1.59 备份已存在的对象 (DROP 前必做; 全新对象则跳过) ----------
existing=(); existing_targs=()
for name in "${table_names[@]}" ${view_list[@]+"${view_list[@]}"}; do
  sql_on dst "select 1 from pg_class where oid='$SCHEMA.$name'::regclass" > "/tmp/lnrs_sync_chk_${STAMP}" \
    || { rm -f "/tmp/lnrs_sync_chk_${STAMP}"; continue; }   # 1.59 上无此对象 = 新对象, 无需备份
  if [ -s "/tmp/lnrs_sync_chk_${STAMP}" ]; then
    existing+=("$name")
    existing_targs+=("-t" "$SCHEMA.$name")
  fi
  rm -f "/tmp/lnrs_sync_chk_${STAMP}"
done
BACKUP_FILE=""
if [ ${#existing[@]} -gt 0 ]; then
  BACKUP_FILE="$BACKUP_DIR/backup_pre_sync_${STAMP}.pdump"
  ssh -o BatchMode=yes "$DST" \
    "cd /tmp && mkdir -p $BACKUP_DIR && sudo -u postgres pg_dump -d $DB_NAME --schema=$SCHEMA ${existing_targs[*]} -Fc -f $BACKUP_FILE && ls -la $BACKUP_FILE" \
    || die "1.59 备份失败, 中止 (目标对象未做任何改动)"
  echo "[4/7] 1.59 已有对象已备份: ${existing[*]}"
  echo "      备份文件: $BACKUP_FILE (持久保留, 不要删除)"
else
  echo "[4/7] 1.59 无已存在的目标对象 (均为新对象), 跳过备份"
fi
# 子集同步: 1.59 上剩余表的 FK 指向同步集内的表时会阻塞 DROP。
#   先 DETACH (记下约束定义), 重建后再 REATTACH (定义来自 1.59 自身, 可直接重放)。
ORPHAN_DEFS="/tmp/lnrs_sync_orphans_${STAMP}.txt"
rm -f "$ORPHAN_DEFS"
IN_SYNC="$(in_list "${table_names[@]}")"
orphan_file="/tmp/lnrs_sync_orphansql_${STAMP}.sql"
printf 'select cc.relname || '\''|'\'' || c.conname || '\''|'\'' || pg_get_constraintdef(c.oid) from pg_constraint c join pg_class cc on cc.oid=c.conrelid join pg_class f on f.oid=c.confrelid join pg_namespace n on n.oid=cc.relnamespace where c.contype='\''f'\'' and n.nspname='\''%s'\'' and cc.relname not in (%s) and f.relname in (%s) order by 1;\n' "$SCHEMA" "$IN_SYNC" "$IN_SYNC" > "$orphan_file"
chmod 644 "$orphan_file"
orphans="$(run_sql_dst "$orphan_file")"
rm -f "$orphan_file"
detach_file="/tmp/lnrs_sync_detach_${STAMP}.sql"
: > "$detach_file"
if [ -n "$orphans" ]; then
  # 每条约束: DETACH 行 + 孤儿行探测 (child 行按全部 FK 列 join 不到 parent 即孤儿) + REATTACH 行
  i=0
  while IFS='|' read -r child cname condef; do
    [ -z "$child" ] && continue
    i=$((i+1))
    ckc="$(printf '%s' "$condef" | sed -n 's/^FOREIGN KEY[[:space:]]*(\([^)]*\)).*/\1/p')"
    parent_cols="$(printf '%s' "$condef" | sed -n 's/.*REFERENCES[[:space:]]*\([^[:space:]]*\)(\([^)]*\)).*/\1|\2/p')"
    [ -n "$parent_cols" ] || die "无法解析 FK 定义: $condef"
    par="${parent_cols%%|*}"
    pcc="${parent_cols#*|}"
    on=""
    IFS=',' read -ra KC <<< "$ckc"
    IFS=',' read -ra PC <<< "$pcc"
    [ ${#KC[@]} -eq ${#PC[@]} ] || die "无法解析复合 FK 列: $condef"
    for k in "${!KC[@]}"; do
      [ -n "$on" ] && on="$on and "
      on="$on a.${KC[$k]} = b.${PC[$k]}"
    done
    printf '%s|%s\n' "$child" "$cname" >> "$ORPHAN_DEFS"
    printf 'ALTER TABLE %s.%s DROP CONSTRAINT %s;\n' "$SCHEMA" "$child" "$cname" >> "$detach_file"
    printf 'select count(*) from %s.%s a left join %s b on %s where b.%s is null;\n' \
      "$SCHEMA" "$child" "$par" "$on" "${PC[0]}" > "/tmp/lnrs_sync_orphchk_${STAMP}_${i}.sql"
    printf 'ALTER TABLE %s.%s ADD CONSTRAINT %s %s;\n' "$SCHEMA" "$child" "$cname" "$condef" > "/tmp/lnrs_sync_reattach_${STAMP}_${i}.sql"
    chmod 644 "/tmp/lnrs_sync_orphchk_${STAMP}_${i}.sql" "/tmp/lnrs_sync_reattach_${STAMP}_${i}.sql"
  done <<< "$orphans"
  run_sql_dst "$detach_file" >/dev/null || die "DETACH 1.59 剩余表 FK 失败"
  echo "      [i] 子集同步: 已临时 DETACH $i 条 1.59 剩余表指向同步集的 FK (重建后逐条检查, 无孤儿行则自动恢复)"
  ORPHAN_COUNT=$i
else
  ORPHAN_COUNT=0
fi


# ---------- Step 5: 1.59 删除目标对象 (先视图后表后序列; 超管通道) ----------
{
  vi=0; for v in ${view_list[@]+"${view_list[@]}"}; do if [ "${view_kinds[$vi]}" = "m" ]; then printf 'DROP MATERIALIZED VIEW IF EXISTS %s;\n' "$SCHEMA.$v"; else printf 'DROP VIEW IF EXISTS %s;\n' "$SCHEMA.$v"; fi; vi=$((vi+1)); done
  printf 'DROP TABLE IF EXISTS %s;\n' "$(IFS=,; echo "${drop_list[*]}")"
  for s in ${seq_list[@]+"${seq_list[@]}"}; do printf 'DROP SEQUENCE IF EXISTS %s;\n' "$SCHEMA.$s"; done
} > "/tmp/lnrs_sync_drop_${STAMP}.sql"
chmod 644 "/tmp/lnrs_sync_drop_${STAMP}.sql"
run_sql_dst "/tmp/lnrs_sync_drop_${STAMP}.sql" >/dev/null || die "1.59 删除目标对象失败 (若被外键引用会报错，需人工决策是否 CASCADE)"
echo "[5/7] 1.59 目标对象已删除 (视图/表/序列)"

# ---------- Step 6: 1.59 恢复结构 (plain SQL) + COPY 数据 + GRANT (超管通道) ----------
# 恢复顺序: 触发器函数 -> 结构 SQL (表/序列 setval/索引/约束/触发器) -> 视图 (引用基表)
# 剔除 PG18 专有 GUC 'SET transaction_timeout' 和 PG16+ 元命令 \restrict/\unrestrict
# 错误行抓取兼容中英文 locale (grep 同时匹配 ERROR/FATAL/错误)
ssh -o BatchMode=yes "$DST" \
  "cd /tmp && grep -v -e '^SET transaction_timeout' -e '^\\\\restrict' -e '^\\\\unrestrict' /tmp/lnrs_sync_schema_${STAMP}.sql > /tmp/lnrs_sync_schema_stripped_${STAMP}.sql && ls -la /tmp/lnrs_sync_schema_stripped_${STAMP}.sql" \
  || die "剔除不兼容 GUC/元命令失败"
for f in ${trig_fns[@]+"${trig_fns[@]}"}; do
  ssh -o BatchMode=yes "$DST" \
    "cd /tmp && sudo -u postgres psql -d $DB_NAME -v ON_ERROR_STOP=1 -q -f /tmp/lnrs_sync_fn_${f}.sql" \
    || die "重建触发器函数 $f 失败"
done
ssh -o BatchMode=yes "$DST" \
  "cd /tmp && LC_ALL=C sudo -u postgres psql -d $DB_NAME -v ON_ERROR_STOP=1 -q -f /tmp/lnrs_sync_schema_stripped_${STAMP}.sql 2>/tmp/lnrs_sync_restore.log; rc=\$?; grep -aE 'ERROR|FATAL|错误' /tmp/lnrs_sync_restore.log | head -20 || true; rm -f /tmp/lnrs_sync_restore.log; exit \$rc" \
  || die "结构恢复失败 (详见上方错误行)"
for v in ${view_list[@]+"${view_list[@]}"}; do
  ssh -o BatchMode=yes "$DST" \
    "cd /tmp && sudo -u postgres psql -d $DB_NAME -v ON_ERROR_STOP=1 -q -f /tmp/lnrs_sync_view_${v}.sql" \
    || die "重建视图 $v 失败"
done
# COPY 导入按 FK 拓扑序 (父表先), 避免外键违反
for t in ${topo_order[@]+"${topo_order[@]}"}; do
  ssh -o BatchMode=yes "$DST" \
    "cd /tmp && sudo -u postgres psql -d $DB_NAME -qAc 'COPY $SCHEMA.$t FROM STDIN' < /tmp/lnrs_sync_data_${STAMP}/${t}.copy" \
    || die "COPY 导入 $SCHEMA.$t 失败"
done
# 重建后对象属主为 postgres 且无任何授权 (源库默认 ACL 不随 dump 迁移), 必须把应用角色权限加回来
{
  printf 'GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON %s TO %s;\n' \
    "$(IFS=,; echo "${grant_list[*]}")" "$DB_USER"
  for v in ${view_list[@]+"${view_list[@]}"}; do printf 'GRANT SELECT ON %s TO %s;\n' "$SCHEMA.$v" "$DB_USER"; done
  for f in ${trig_fns[@]+"${trig_fns[@]}"}; do printf 'GRANT EXECUTE ON FUNCTION %s TO %s;\n' "$SCHEMA.$f" "$DB_USER"; done
} > "/tmp/lnrs_sync_grant_${STAMP}.sql"
chmod 644 "/tmp/lnrs_sync_grant_${STAMP}.sql"
run_sql_dst "/tmp/lnrs_sync_grant_${STAMP}.sql" >/dev/null || die "GRANT 回 $DB_USER 角色失败"
# 恢复子集同步时 DETACH 的剩余表 FK: 逐条先探测孤儿行, 无孤儿行才 REATTACH
#   (抽样模式下同步集只是源库子集, 剩余表引用被采掉父键的行属预期, 保持 DETACH 并告警)
reattached=0
skipped=0
i=0
if [ "$ORPHAN_COUNT" -gt 0 ]; then
while IFS='|' read -r child cname; do
  [ -z "$child" ] && continue
  i=$((i+1))
  orph="$(run_sql_dst "/tmp/lnrs_sync_orphchk_${STAMP}_${i}.sql")" || die "孤儿行探测失败 ($child -> $cname)"
  if [ "$orph" = "0" ]; then
    run_sql_dst "/tmp/lnrs_sync_reattach_${STAMP}_${i}.sql" >/dev/null || die "REATTACH $cname 失败"
    reattached=$((reattached+1))
  else
    skipped=$((skipped+1))
    echo "      [!] 约束 $cname ($child -> 同步集) 有 $orph 行孤儿引用, 保持 DETACH -- 抽样模式下属预期, 全量模式请人工核对"
  fi
  rm -f "/tmp/lnrs_sync_orphchk_${STAMP}_${i}.sql" "/tmp/lnrs_sync_reattach_${STAMP}_${i}.sql"
done < "$ORPHAN_DEFS"
fi
if [ "$ORPHAN_COUNT" -gt 0 ]; then
  echo "      [i] 1.59 剩余表 FK 处理完成: 恢复 $reattached 条, 保持 DETACH $skipped 条 (共 $ORPHAN_COUNT 条)"
fi
rm -f "$detach_file" "$ORPHAN_DEFS"
echo "[6/7] pg_restore 结构 + COPY 数据导入 + GRANT $DB_USER 完成 (1.59)"
VERIFY_SQL=""
for t in "${table_names[@]}"; do
  pk="${pk_map[$t]:-}"
  cols="$(sql_on src "select string_agg(attname, ',' order by attnum) from pg_attribute where attrelid='$SCHEMA.$t'::regclass and attnum>0 and not attisdropped")"
  [ -n "$cols" ] || die "无法读取 $SCHEMA.$t 列清单"
  s_expr=""
  IFS=',' read -ra C <<< "$cols"
  for c in "${C[@]}"; do
    if [ -z "$s_expr" ]; then s_expr="coalesce($c::text,'')"; else s_expr+="||'|'||coalesce($c::text,'')"; fi
  done
  if [ -n "$pk" ]; then
    order_expr="$pk"          # 主键列排序, 跨机确定
  else
    order_expr="s"            # 无主键: 按行内容排序 (跨机结果仍可比)
  fi
  if [ "$LIMIT" -gt 0 ]; then filter="where ${where_map[$t]}"; else filter=""; fi
  if [ -n "$VERIFY_SQL" ]; then VERIFY_SQL+="
union all
"; fi
  VERIFY_SQL+="select '$t', count(*), md5(coalesce(string_agg(s, chr(1) order by $order_expr), '')) from (select $s_expr as s$([ -n "$pk" ] && echo ", $pk") from $SCHEMA.$t $filter) x"
done
echo "$VERIFY_SQL" > "/tmp/lnrs_sync_verify_${STAMP}.sql"
out_src="$(run_sql_src "/tmp/lnrs_sync_verify_${STAMP}.sql")" || die "源端校验 SQL 失败"
out_dst="$(run_sql_dst "/tmp/lnrs_sync_verify_${STAMP}.sql")" || die "目标端校验 SQL 失败 (GRANT 未生效或权限不足)"
# 两端各自执行 UNION ALL 的行序不定, 排序后比较
out_src="$(printf '%s\n' "$out_src" | sort)"
out_dst="$(printf '%s\n' "$out_dst" | sort)"
if [ "$out_src" = "$out_dst" ] && [ -n "$out_src" ]; then
  echo "[7/7] 校验通过, 两端一致:$([ "$LIMIT" -gt 0 ] && echo " (抽样每表 $LIMIT 行)")"
  echo "$out_src" | sed 's/^/      /'
else
  echo "===== 源端 (196.3) =====" ; echo "$out_src"
  echo "===== 目标端 (1.59) =====" ; echo "$out_dst"
  die "两端校验不一致 (1.59 已有对象备份在: $BACKUP_FILE)"
fi

# ---------- 清理 (备份文件持久保留, 只清中转件) ----------
ssh -o BatchMode=yes "$SRC" "rm -f /tmp/lnrs_sync_schema_${STAMP}.sql /tmp/lnrs_sync_${STAMP}_*.copy" >/dev/null 2>&1 || true
ssh -o BatchMode=yes "$DST" "rm -rf /tmp/lnrs_sync_schema_${STAMP}.sql /tmp/lnrs_sync_schema_stripped_${STAMP}.sql /tmp/lnrs_sync_fn_*.sql /tmp/lnrs_sync_data_${STAMP}" >/dev/null 2>&1 || true
rm -rf "$SCHEMA_SQL" "$DATA_DIR" "/tmp/lnrs_sync_fn_"*.sql "/tmp/lnrs_sync_drop_${STAMP}.sql" "/tmp/lnrs_sync_grant_${STAMP}.sql" "/tmp/lnrs_sync_verify_${STAMP}.sql" "/tmp/lnrs_sync_exp_"*.sql
if [ "$LIMIT" -gt 0 ]; then SUMMARY="抽样 每表 $LIMIT 行"; elif [ "$BY_CENTER" -gt 0 ]; then SUMMARY="按中心 每家 $BY_CENTER 行 (seed=$SEED)"; else SUMMARY="全量"; fi
echo "同步完成: ${table_names[*]}  (196.3 -> 1.59, $SUMMARY)"
