# 事故复盘 — 测试清理按 `center_code` 级联删除 168,260 行 `dicom_series`

> 日期：2026-09-20
> 严重度：**高**（dev 库主数据被删，视图对外数字归零）
> 状态：已止血 + 已恢复 + 已推送（`3d62256f`）
> 修复提交：`3d62256f`（止血）/ 数据恢复见 §7
> 关联：[issue-7-fix-etl2-cli-and-backfill-series-count.md](../prd/issue-7-fix-etl2-cli-and-backfill-series-count.md)（引入该测试的提交）

---

## 1. 摘要

`backend/tests/anon_etl/test_etl2_cli_defect_fixes.py`（由 issue-7 的提交 `296eb602` 引入）中，
`TestRunCenterSourceKindAuto` 的两个用例用**真实中心名**（`"zhujiang"` / `"shengyi"`）驱动
`run_center`，而用例末尾的清理写成按中心删除：

```python
DELETE FROM lnrs.lnrs_anon_ingest_batch WHERE center_code = :c   # :c = 'zhujiang' / 'shengyi'
```

该用例把 `_create_batch` monkeypatch 成 `fake_create_batch`（**从不写库**），
所以这条 DELETE 删掉的全是**真实 batch**。经外键
`lnrs_anon_dicom_series.created_batch_id → lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE`：

| 表 | 事故前 | 事故后 | 变化 |
|---|---:|---:|---:|
| `lnrs_anon_ingest_batch` | 69 | 9 | **−64** |
| `lnrs_anon_dicom_series` | 201,574 | 33,314 | **−168,260** |

被删的 `dicom_series` 全部属于 zhujiang（86,203）与 shengyi（82,057）；
xinqiao 的 33,314 行因 batch 未被删而幸存。
视图 `lnrs_anon_v_imaging_study_counts` 的 **zhujiang `total_bytes` 由 19 TB 退化为 0**。

**一句话根因**：一个**从不写库**的测试，执行了一条**按真实中心删除**的清理语句。

---

## 2. 时间线

| 时间 | 事件 | 证据 |
|---|---|---|
| 09-20 00:20 | 该测试已在本机跑过（留下合成中心 batch 泄漏） | `ingest_batch.center_code='src_kind_48a6cfd6'`，`started_at=00:20:21` |
| 00:57 | 本次恢复所用的快照被创建 | `/tmp/lnrs_backup/20260920_xinqiao_pre/` |
| 01:56 | xinqiao `dicom_series` 灌库（33,314 行） | `created_at=01:56:41` |
| ~07:45 | 实测 `dicom_series = 201,574`（**尚完好**） | 本会话查询输出 |
| **09:54** | **测试模块被导入/执行（损伤窗口）** | `tests/anon_etl/__pycache__/test_etl2_cli_defect_fixes.cpython-311-pytest-9.0.2.pyc` mtime |
| ~11:00 | 实测 `dicom_series = 33,314`，视图 zhujiang = 0 bytes | 本会话查询输出 |
| 11:12 | 又有一次 pytest 运行 | `backend/.pytest_cache/v/cache/{lastfailed,nodeids}` mtime |
| 11:33 | 恢复前安全备份 | `/tmp/lnrs_backup/20260920_restore_safety_113330/` |
| ~11:36 | 增量恢复完成 | `dicom_series` 回到 201,574 |
| — | 止血提交并推送 | `3d62256f` |

> 精确的删除时刻无法从 `pg_stat_user_tables` 还原（只有累计 `n_tup_del=204,417`，无时间戳）。
> 09:54 是 `.pyc` mtime，只能界定**窗口**，不能确定单次时刻。

---

## 3. 影响面

**直接**：
- zhujiang 86,203 行 `dicom_series`（含 `file_count` / `byte_size` / `series_count`）
- shengyi 82,057 行 `dicom_series`
- 64 行 `ingest_batch`（shengyi 58 + zhujiang 6）

**间接（对外可见）**：
- `/#/medicalFiles` 统计的影像字节数对 zhujiang 归零（PRD 的最终交付物）

**未受影响**（已逐一核对，依据是 live `pg_constraint` 而非 DDL）：
- `lnrs_anon_imaging_study`：唯一 FK 是 `patient_id`；其 `created_batch_id` **无 FK** → 行数不变
  （zhujiang 86,927 / shengyi 82,994）
- `lnrs_anon_patient`：**live 库里该表一个外键都没有**（`pg_constraint` 查 `contype='f'` 返回 0 行），
  只有 `created_batch_id` / `last_seen_batch_id` 的 NOT NULL。无 FK → 无级联 → 未受损
- `lnrs_anon_phi_audit`：**无 FK**（实测 `pg_constraint` 查不到外键）→ 未受损
  （4,909,326 行 > 备份的 3,840,626）
- shengyi 的 `imaging_study.created_batch_id` 全为 NULL —— **不是本次损伤**，
  备份（00:57）里本来就是全 NULL

### 3.1 ⚠ 附带发现：DDL 文件与 live schema 已分叉

`backend/sql/postgres/0006-anonymized-schema-lnrs.sql` **声明了**这些 FK：

```sql
-- 0006 第 122-123 行（lnrs_anon_patient）
created_batch_id   UUID NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
last_seen_batch_id UUID NOT NULL REFERENCES lnrs.lnrs_anon_ingest_batch(batch_id) ON DELETE CASCADE,
-- 同样写法还出现在 exam(165-166) / report_text(186) / exam_finding(203)
```

但 live dev 库实测：**指向 `ingest_batch` 的 FK 只有 `dicom_series` 一条**。

**这不是本次事故的原因，但它是一个未爆的雷**：

> 若在**按 DDL 建的新环境**上跑同一个测试，`DELETE FROM ingest_batch WHERE center_code='zhujiang'`
> 会沿 0006 声明的 FK 级联删掉 **patient / exam / report_text / exam_finding** ——
> 即整条业务链，而不只是 `dicom_series`。**同一个 bug 在 DDL 环境上是灾难级的。**

**教训**：判断「删一批 batch 会连带删掉什么」**必须查 live `pg_constraint`**，
不能读 DDL 文件。DDL 是意图，live schema 是事实；两者已经不一致。

（附带地：`dicom_series` 的另一条 FK 是 `anon_exam_id → lnrs_anon_exam ON DELETE CASCADE` ——
删 exam 同样会级联删 `dicom_series`，这是第二条爆雷路径。）

---

## 4. 根因

### 4.1 直接原因

```python
def test_dicom_series_only_center_uses_dicom_dir(self, tmp_path):
    asyncio.run(self._body(tmp_path, "zhujiang", "dicom_dir", dicom_series_only=True))
def test_full_parquet_center_uses_csv_report(self, tmp_path):
    asyncio.run(self._body(tmp_path, "shengyi", "csv_report"))
```

真实中心名是**必要的** —— `run_center` 要用它查 `_CENTER_PARQUET_SPECS` 来决定 `source_kind`
（`dicom_series_only=True` → `dicom_dir`；含 parquet spec → `csv_report`），
换成合成名会让用例因「specs 为空」而以**错误理由**通过。

问题不在中心名，在于**清理用了中心名**。`_create_batch` 被替换为：

```python
async def fake_create_batch(db, *, center_code, data_dir, source_kind):
    captured["source_kind"] = source_kind
    return str(uuid.uuid4())          # ← 不写库
```

既然没有创建任何行，`DELETE ... WHERE center_code = :c` 删的**只能是别人的行**。
这是一个**语义上必然错误**的语句，不是边界情况。

### 4.2 为什么这个测试能对着真库跑（问题 1）

**因为它连接的「dev 库」就是真库，且没有任何隔离层。**

```python
def _pg_available() -> bool:
    if os.getenv("ENVIRONMENT") != "dev":
        return False
    conn = await asyncpg.connect(
        host="127.0.0.1", port=5432, user="lnrs",
        password="lnrs_pwd", database="postgres",      # ← 与生产 ETL 同一库
    )
```

逐项核对：

| 隔离手段 | 是否存在 |
|---|---|
| 独立测试数据库 | ❌ 无（全仓 grep `TEST_DATABASE` / `lnrs_test` 无命中） |
| 独立 schema | ❌ 无（测试直接写 `lnrs.*`） |
| 每用例事务回滚 | ❌ 无（用例自己 `await session.commit()`） |
| 全局 DB fixture | ❌ 无（`tests/conftest.py` 只有 session 级 `test_client`） |
| 测试数据种子隔离 | ❌ 无（用例直接在真表上 `DELETE`/`INSERT`） |

而且这不是孤例 —— **6 个测试文件直接开 `async_db_session()` 写真库**：

```
tests/anon_etl/test_anon_patient_placeholder.py        db_session=4  write=3
tests/anon_etl/test_dicom_series_count.py              db_session=8  write=3
tests/anon_etl/test_etl2_cli_defect_fixes.py           db_session=8  write=1   ← 本次
tests/anon_etl/test_etl_smoke.py                       db_session=4  write=0
tests/anon_etl/test_shengyi_placeholder_backfill.py    db_session=4  write=2
tests/test_files_statistics.py                         db_session=2  write=0
```

**所以「测试能对真库跑」不是这个 bug 的偶然条件，而是这个仓库的默认工作方式。**
这个测试只是第一个把「删除」写成了按业务键（而不是按自己创建的主键）的。

### 4.3 `@skipif(not PG_READY)` 的设计缺口（问题 2）

这个装饰器**看起来像安全网，实际是反向的**：

```python
PG_READY = _pg_available()
@pytest.mark.skipif(not PG_READY, reason=SKIP_REASON)
```

**缺口 1 —— 它是可用性门，不是安全性门。**
它跳过的是「PG **不在**」的场景，也就是**唯一安全的场景**；它放行的是「PG **在**」的场景，
也就是**唯一危险的场景**。装饰器的语义恰好把测试**只在能造成伤害时启用**。

**缺口 2 —— skip reason 的措辞强化了错误的安全感。**

```
SKIP_REASON = "需要 ENVIRONMENT=dev 且本地 PG（lnrs:lnrs_pwd@127.0.0.1:5432/postgres）"
```

读起来像「这是环境依赖声明」，读者会推断「环境不对就跳过，所以安全」——
但真实语义是「环境对的时候会写真库」。**它把危险说成了依赖。**

**缺口 3 —— 它让破坏性路径在 CI 中永远不被执行。**
`.gitlab-ci.yml` **只有 `deploy` stage（手动触发），没有任何 test stage**：

```yaml
stages:
  - deploy
deploy_production:
  stage: deploy
  when: manual
  script: [ bash /home/dzy/wk/lnrs/deploy-ci.sh ]
```

CI 里没有 PG → `PG_READY=False` → 这些用例在 CI 中**永远 skip**。
于是这个 bug 在 CI 视角下**不存在**，只能靠人在本机跑到才暴露。
**「测试在 CI 里永远跳过」本身就等于「测试不存在」。**

**缺口 4 —— `_pg_available()` 是逐文件复制的。**
同一份实现被复制进至少 2 个文件（`test_etl2_cli_defect_fixes.py`、
`test_dicom_series_count.py` 注释自述「同款 _pg_available 守卫」）。
没有单一位置可以修，也无法保证下一个新测试文件会带上守卫 —— 本次这个文件就是新加的。

### 4.4 放大因素（为什么没被更早发现）

**放大 1 —— 第二个用例一直失败在断言之前。**
`TestRunCenterSourceKindAuto._body` 缺少 `await async_engine.dispose()` 收尾，
导致同文件第二个用例（shengyi）报
`RuntimeError: ... got Future attached to a different loop`。
失败点在 `_body` 中段，**断言从未执行** → 用例「红着」，但红的原因与数据无关，
没人会去想它是否在删数据。

**放大 2 —— 第一个用例「绿着」，而破坏性 DELETE 就在它的成功路径上。**
`test_dicom_series_only_center_uses_dicom_dir`（zhujiang）PASSED。
一条删掉 86,203 行的语句，被一次 **PASSED** 掩盖。

**放大 3 —— 级联把「删 64 行」放大成「删 168,260 行」。**
`ingest_batch` 看起来只是元数据表（64 行），但它是
`dicom_series.created_batch_id` 的 CASCADE 父表。**删 64 行的操作造成 168,260 行的损失。**

**放大 4 —— 一个「零漂移」检查被空集骗成了绿灯。**
issue-13 的 `verify_no_drift` 报「跨中心零漂移 + xinqiao 非 anon_exam_id 列 checksum 通过」。
「跨中心」集合当时已经空了 → 空集上任何一致性检查都通过。
**这是本次事故里第二个「空集假象」**（第一个是我误读 `series_count IS NULL = 0` 为「已回填」）。

---

## 5. 修复

提交 `3d62256f`，三处改动：

1. **清理改为按自己拿到的 `batch_id` 删**
   ```python
   text("DELETE FROM lnrs.lnrs_anon_ingest_batch WHERE batch_id = :b"),
   {"b": result["batch_id"]},
   ```
   `fake_create_batch` 未写库时是 no-op；将来若不再 fake，也只删自己创建的那一行。

2. **加回归守卫**（行为断言，不是文本断言）
   ```python
   assert remaining_batches == baseline_batches, (
       f"测试改变了 {center} 的真实 batch 行数"
       f"（{baseline_batches} → {remaining_batches}）——"
       "清理必须按 batch_id，不能按 center_code"
   )
   ```
   跑 `run_center` **前后**各数一次该中心的真实 batch 行数。
   任何人重新引入按 `center_code` 的删除，**无论写成什么语法**，都会立刻变红。

3. **补 `await async_engine.dispose()`** —— 修掉 §4.4 放大 1，让第二个用例真正跑到断言。

**验证**：
- `pytest tests/anon_etl/test_etl2_cli_defect_fixes.py` → **7 passed**（此前 1 failed）
- 跑前/跑后 `ingest_batch` / `dicom_series` / `imaging_study` / `patient` **四表计数零差异**
- 同类缺陷**全仓扫描**：只有这一个文件中招
  （其余 `DELETE ... WHERE center_code` 用合成中心 `ph_bak_*` / `ph_cols_*`；
  `test_xinqiao_study_extend.py` 不写库；`test_dicom_series_count.py:339` 只读）

---

## 6. 数据恢复

**恢复源**：`/tmp/lnrs_backup/20260920_xinqiao_pre/`（00:57，灌 xinqiao **之前**的快照）

| 步骤 | 做法 |
|---|---|
| 安全备份 | `pg_dump` 当前三表 → `/tmp/lnrs_backup/20260920_restore_safety_113330/` |
| 载入 staging | `CREATE TABLE lnrs._restore_X (LIKE lnrs.lnrs_anon_X)` + 备份 `.sql` 改写表名载入 |
| 缺口分析 | 缺失 64 batch + 168,260 dicom_series；`imaging_study` 无需恢复 |
| 增量插入 | 先父表 `ingest_batch`，再子表 `dicom_series`；均 `WHERE NOT EXISTS` 且保留原 `series_id` |
| 前置校验 | staging 与 live 的 `series_id` 交集 **0**、`dicom_study_uid` 交集 **0** → 可原样保留 id |
| 清理 | `DROP TABLE lnrs._restore_*` |

**顺带修了一个潜在 bug**：`lnrs_anon_dicom_series_series_id_seq` 的 `last_value=239,035`
**落后于**表 `MAX(series_id)=272,348` → 任何后续插入都会撞主键（第一次恢复正是因此失败）。
已 `setval` 至 272,348，试发号 272,349 ✓。

**恢复后验证**：

| 检查 | 结果 |
|---|---|
| `dicom_series` 总行数 | **201,574**（= 168,260 + 33,314） |
| 去重 UID 分中心 | zhujiang 86,203 / shengyi 82,056 / xinqiao 33,314 |
| 孤儿 series（FK 不满足） | **0** |
| 视图 `total_bytes` | zhujiang **19 TB**（此前 0）/ shengyi 15 TB / xinqiao 4,059 GB |
| 零文件 study 子集 | 415 A / 274 B（回到 issue-8 的原始待处理状态） |

---

## 7. 什么本可以防止它（Phase 6 的 handoff）

按「**先隔离，再断言，最后才 lint**」的优先级排列。

### 7.1 首选：给测试一个真正属于自己的数据库（结构性修复）

**这是唯一能同时消灭这一类 bug 的修复。** 只要测试写的是它自己的库/ schema，
`DELETE ... WHERE center_code = 'zhujiang'` 就只是一条删掉测试数据的语句。

两个关键论据：

- **清理式隔离在失败时必然泄漏。** 本仓已有**两例**实证：
  1. 同文件里**写法正确**的 `TestSourceKindParam`（用 `f"src_kind_{uuid4().hex[:8]}"`）也泄漏了 ——
     `ingest_batch` 里至今躺着 `src_kind_48a6cfd6`（`status='running'`，00:20 创建）。
     原因是用例在 `finally` 清理之前就失败/中断了。
  2. `test_shengyi_placeholder_backfill.py` 的合成中心 `ph_bak_*` 也泄漏了 ——
     `lnrs_anon_patient` 里至今有 `center_code='ph_bak_358c2985'` 的 **5 行**。
  **基于 cleanup 的隔离总是泄漏；基于 rollback 的隔离不会。**
  这两例都是"泄漏"（残留脏数据，尚可容忍）；本次是"泄漏的反面"——
  清理**执行了**但作用域写错，直接删了真数据。
- **"测试必须用合成中心" 是一条纪律，不是一道机制。** 本次违反纪律的正是**新写的**测试文件 ——
  而 `_pg_available()` 的逐文件复制说明这条纪律本来就没有单一落点。
  纪律能约束"记得用合成名"，但约束不了"清理的作用域" —— 本次的合成名纪律**并没有被违反**，
  被违反的是"只删自己创建的东西"。

落地形状：`tests/conftest.py` 提供 `db_url` fixture，指向可丢弃的库/ schema；
`async_db_session()` 的引擎由 fixture 注入；测试结束整库回滚或 drop。
这是**架构改动**，不是测试改动 → **交接 `/improve-codebase-architecture`**。

### 7.2 次选：把行为守卫跑起来（已有，缺 CI）

§5 的守卫已经能抓住这一类（不依赖语法），但**它只在有人本机跑测试时才执行**。
需要给 CI 加 test stage，并用 7.1 的一次性库跑 DB 测试。
**注意顺序**：先有 7.1 再开 CI 跑 DB 测试，否则等于把「删真库」自动化。

### 7.3 兜底：静态门禁（只作纵深防御，不作主防线）

「测试里禁止按业务键删除」做成 AST/lint 规则是**可以加，但不能依赖**：

- 它挡不住同类变体：`UPDATE`、`WHERE patient_id IN (...)`、fixture 里的裸 SQL、
  别名/`text()` 拼接/f-string 拼出的语句
- 它产生的是「规则通过」的错觉 —— 而本次真正失效的是**隔离缺失**，不是某个字符串
- 在没有 test stage 的 CI 里加 lint，等于给一个不运行的测试套件加断言

若要做，规则应是**行为式**而非文本式：任何测试对 `lnrs.*` 的写操作，
其 `WHERE` 必须引用「本用例创建/捕获的 id」。但这本质上是 7.1 的弱化版。

### 7.4 与架构无关、但值得单独做的两件事

- **`@skipif(not PG_READY)` 改名/改语义**：它现在是「PG 在就写真库」。
  应改为显式声明「本测试需要可丢弃的 DB」，缺则 skip；并把 skip reason 从
  「环境依赖」改成「需要 disposable DB，当前环境不提供 → 跳过以免写真库」。
- **级联影响要有文档**：`ingest_batch` 是 4+ 张表的 CASCADE 父表。
  删它 64 行 = 删 168,260 行子数据。这类「元数据表其实是级联根」的关系应在
  `docs/etl2/README.md` 或 DDL 注释里显式写出（部分已有，但不完整）。

---

## 8. Phase 6 检查清单

- [x] **原始复现不再复现** —— 重跑 `pytest tests/anon_etl/test_etl2_cli_defect_fixes.py`，7 passed，四表计数零差异
- [x] **回归测试通过** —— 行为守卫（前后 batch 行数断言）已随 `3d62256f` 提交
- [x] **无 `[DEBUG-...]` 残留** —— `grep -rn '\[DEBUG-' backend/ --include='*.py'` 无命中
- [x] **临时原型已删** —— `/tmp` 下的探查脚本已清理；`lnrs._restore_*` staging 表已 drop
- [x] **正确假设已写入提交信息** —— `3d62256f` 记录了「按 center_code 删 + fake_create_batch 不写库 → 删的全是真实行」及完整级联链
- [x] **数据已恢复** —— `dicom_series` 201,574，孤儿 FK 0，视图 zhujiang 19 TB
- [x] **潜在 bug 顺带修复** —— `series_id` 序列落后于表 max

**遗留（不在本次范围）**：
- **DDL 文件与 live schema 已分叉**（§3.1）——`0006` 声明的 `ingest_batch` FK 在 live 库只剩
  `dicom_series` 一条。按 DDL 建的新环境上，同一个测试会删掉 patient/exam/report_text。
  **建议单独核对一次 live schema 与 DDL 的全量差异**（本复盘只查了指向 `ingest_batch` 的 FK）。
- 测试脏数据泄漏两例：`ingest_batch` 的 `src_kind_48a6cfd6`（`status='running'`）、
  `lnrs_anon_patient` 的 `ph_bak_358c2985`（5 行）—— 可随手清，但根因见 §7.1
- zhujiang 的 `dicom_series.series_count` 仍全 NULL（issue-7 未完成的 16h 回填）
- zhujiang 的 `dicom_series.anon_exam_id` 随备份回到 NULL（事故前亦为 NULL，非回归）；
  可从 `imaging_study.anon_exam_id` 同步 **85,483** 行（计划里的 R13 步骤）
- zhujiang 两个 `csv_report` batch 停在 `running`（issue-6 遗留，`_close_batch` 未调用）

---

## 9. 参考

- 修复提交：`3d62256f`
- 引入缺陷的提交：`296eb602`（issue-7）
- 恢复源备份：`/tmp/lnrs_backup/20260920_xinqiao_pre/`
- 恢复前安全备份：`/tmp/lnrs_backup/20260920_restore_safety_113330/`
- 相关技能：`diagnosing-bugs`（本复盘的 Phase 6）、`improve-codebase-architecture`（§7.1 的交接对象）
