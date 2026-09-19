# Handoff：lnrs_anon_exam 的 Other 模态清零重划 + files 统计口径切换

> 生成：2026-09-19（ZCode 规划会话产出，规划阶段已完成全部侦查与决策确认）。
> 执行位置：**10.12.196.3 服务器本地**（源 parquet 与生产库均在该机；本地 Windows 不再远程驱动）。
> 本文档自包含：执行者无需原会话上下文即可开工。

---

## 0. 一句话目标

把 `lnrs.lnrs_anon_exam` 中 57171 条 `exam_type='Other'` 全部重划到 26 个模态键（`docs/all_modalities.json`），并做「彻底终态」清理（字典/约束/ETL 引擎不再保留 Other），同时把 files 页模态计数统计口径切到 exam 表（分母 = 全部模态数量之和）。

## 1. 背景与根因

- 医疗文件页（前端 `frontend/web/src/views/module_medical/files/index.vue`）左侧「模态类型」筛选项的计数取自 `GET /api/v1/medical/files/statistics` 的 `by_exam_type`，其口径是 `GROUP BY lnrs_anon_imaging_study.modality`（`backend/app/plugin/module_medical/files/service.py:306`）——该影像表当前 100% 是 CT（82994 行），导致 UI 上 CT 显示 82994(100%)、其余模态全 0(0%)。
- 真正的多模态数据在检查主表 `lnrs_anon_exam`（「跨模态桥梁」）。其中 57171 条 `Other` 全部来自省医（shengyi）影像学报告 ETL 批次。
- **根因**：ETL1 适配脚本 `backend/etl1_adapt_shengyi_202609.py`（`SQL_IMAGING`，:200-227）只对源「检查类型名称」列做 ILIKE 关键词分桶（PET→PETCT；MR|磁共振→MR；CT|计算机体层→CT；DR|胸片|照片|X线|放射→Radiology；超声→Ultrasound；ELSE Other），而**核医学块的「检查类型名称」列从不出现 PET 字样**（PET 信息只在「检查项目/检查方法/检查部位」列）→ 约 1.8 万行核医学 + 内镜/普放/造影等 5.7 万行落入 Other。

## 2. 环境与凭据

| 项 | 值 |
|---|---|
| 服务器 | 10.12.196.3（生产，从外部经跳板 10.12.115.3 免密可达；本文档假定你已在服务器本地） |
| 代码仓库 | `/home/dzy/wk/lnrs`（独立 git 副本；完成后需同步回本地 Windows 仓库，见 §7） |
| Python | 一律 `cd /home/dzy/wk/lnrs/backend && uv run python ...`（venv 含 duckdb/pyarrow/SQLAlchemy/asyncpg，勿用系统 python、勿临时装包） |
| 数据库 | 本地 PG `127.0.0.1:5432`，库 `postgres`，schema `lnrs`，用户 `lnrs`；连接参数见 `backend/env/.env.h196_3`。**凭据不得写入任何文件/提交**，命令示例中用 `$PGPASSWORD` 占位 |
| 源 parquet | `/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/非隐私信息.就诊.影像学报告.parquet`（515,585 行，全 VARCHAR） |
| staging parquet | `/home/dzy/wk/lnrs/data_shengyi202609/shengyi/imaging_report.parquet`（198MB，含 ETL1 归一化列 `exam_type`） |
| 后端服务 | systemd `lnrs-backend`（env=h196_3，端口 8610），重启：`sudo systemctl restart lnrs-backend` |

源 parquet 实际列名（带前缀，duckdb 读取时注意引号）：`患者编号`、`当前命中就诊次数/命中就诊总次数`、`非隐私信息.就诊.影像学报告.就诊编号`、`非隐私信息.就诊.影像学报告.报告编号`、`…检查类型代码`、`…检查类型名称`、`…检查部位`、`…检查方法`、`…检查日期`、`…检查项目`、`…检查所见（镜下所见）`、`…印象`。

staging 列：`patient_id / visit_id / report_id / exam_type / exam_body_part / exam_item / exam_date / exam_detail{findings,impression}`（staging **没有**类型代码/类型名称列，需回源文件取）。

## 3. 已查明数据事实

### 3.1 库内现状（2026-09-19 实测）

`lnrs.lnrs_anon_exam` 全表仅 shengyi 一个中心，exam_type 共 8 值，无 NULL：

| exam_type | 行数 | 来源 |
|---|---:|---|
| CT | 226,151 | 影像学报告（关键词命中） |
| pathology_text | 189,966 | 病理报告批次 |
| ultrasound | 181,691 | 超声诊断报告批次（含影像学报告贡献 87 行） |
| radiology | 170,104 | 影像学报告（关键词命中） |
| ECG | 149,072 | 心电批次 |
| MRI | 62,059 | 影像学报告（关键词命中） |
| **Other** | **57,171** | **全部来自影像学报告批次**（verify 文档零差异） |
| gene | 1,309 | 基因批次 |
| 合计 | 1,037,523 | |

### 3.2 Other 57,185 行构成（源文件口径；库内 57,171，差 17 行为 ETL2 去重，量级可忽略）

distinct（检查类型代码, 检查类型名称）= 247 对。大头：

| 类别 | 行数 | 判定依据 | 拟归属 |
|---|---:|---|---|
| 核医学（类型代码/名称双空） | 18,353 | 检查项目=PET/CT-体部显像(FDG) 10443、PET/CT(FDG-全身显像) 1847、全身骨显像 4223；方法=3D 12323、全身平面采集 4546、平面采集 1224、动态采集 112、断层采集 104；部位=会阴－颅底+颅脑 12268、全身骨 4535 | nuclear_medicine |
| 支气管镜 | 6,248 | 名称「支气管镜」（代码 4 / -4 两变体） | bronchoscope |
| 消化内镜 | ≈3,600 | 胃镜 2060+14、肠镜 2086+15、东病区胃镜 724、东病区肠镜 740、十二指肠镜 17、小肠镜 12、ERCP 14 | **待定（决策 1）** |
| 耳鼻喉科 | 1,013 | 名称「耳鼻喉科」（代码 5） | **待定（决策 1）** |
| 胸腔镜 | 29 | 名称「胸腔镜」（代码 16） | **待定（决策 1）** |
| 普放摄影（名称无 DR/照片关键词） | ≈15,000 | 胸部正位 5366、胸部侧位 4125、各椎体/关节正侧位、乳腺 CC/MLO（钼靶）、长骨图像拼接、婴幼儿胸部正位、腹部立/卧位 | radiology |
| 造影类 | ≈1,500 | 食道/食管造影、上消化道造影 GI、下消化道造影 BE、钡灌肠、IVP（3 个代码）、全消化道/口服小肠/下咽造影 | radiology |
| CT 类（名称无 CT 字样） | ≈3,000 | 胸部+上腹增强 3189、胸部+全腹增强/平扫、颈部+胸部+…增强/平扫、主动脉全程平扫+增强、头部血管+颈部血管增强扫描、上腔血管平扫+增强 | CT（该表命名惯例） |
| MR 高级序列（名称无 MR 字样） | ≈1,100 | 特检 DWI 286、DWI 161、SWI 117、PWI 37、束椎体 DTI 14、VBM 12、ASL 8、功能成像-弥散 9 | MRI |
| 会诊读片 | ≈1,090 | 会诊(心胸腹) 905+8+10、会诊(四肢神经) 125、会诊（神经） 43 | **待定（决策 2 兜底）** |
| 代码有值名称空 | ≈1,076 | 代码 5500(1007)/6153(35)/5499(34)，名称空（辅助列大概率可判为核医学，dry-run 验证） | 按辅助列判定 |
| 其他长尾 | ≈300 | 经皮穿刺肺活检术 96、三维重建加收 11、各部位小项目 | 多数可规则化，余量兜底 |

### 3.3 关键技术事实

1. **回填 join 键**：`source_exam_hash = sha256("{center_code}:{exam_no}")`，其中 center_code=`shengyi`、exam_no=源「报告编号」（`backend/app/plugin/module_medical/hospital/anonymize.py:131`）。无密钥、可离线重算；verify 文档已证明 staging hash→PG 命中率 100%（515,585/515,585）。
2. **重跑安全**：exam 表 upsert（`anon_etl_engine.py:553` `_batch_upsert_exams`）`ON CONFLICT (center_code, source_exam_hash) DO UPDATE` 只刷 `last_seen_batch_id` + `exam_date`，**不覆盖 exam_type**——重跑 ETL 不会破坏重划结果，因此存量必须用 SQL/脚本显式 UPDATE。
3. **辅助列信息量**（Other 子集）：检查项目 98.1% 非空、检查部位 75.3% 非空、检查方法 32.1% 非空；`lnrs_anon_report_text.body_clean`（检查所见+印象全文，PK=anon_exam_id 一对一）可作最后兜底推断。
4. **值域约束**：`lnrs_anon_ck_exam_type`（0022 SQL 加，27 值含 Other；表属主为 postgres，ALTER 需 `sudo -u postgres psql`，仿 `backend/sql/postgres/0022-add-exam-type-check-manual.sql` 的幂等+事务内自检写法）。
5. **先例与范式**：存量 exam_type 重划先例=0023 SQL（60.5 万行改名，幂等+守卫）；脚本范式=`backend/etl2/backfill_imaging_study_exam_id.py`（dry-run/apply 双模式、WHERE 守卫、回退 SQL、覆盖率统计）。
6. **既有口径先例**：dashboard「模态检查量」饼图 `query_modality_counts`（`backend/app/plugin/module_medical/hospital/stats_query.py:356`）已是 exam 表口径。
7. **verify 文档**：`docs/etl2/verify_result/shengyi_imaging_report_20260914.md`（§3.1 有 100 行关键词边界分析；§6 建议 ETL1 补 肠镜/胃镜/支气管镜 分桶；记载 1 行脏日期 exam_date=8122-08-03，report_id=669666——本次默认不动）。

## 4. 用户已定决策与待定项

已定（2026-09-19 用户确认）：

1. **内镜/耳鼻喉/胸腔镜归属**：优先按**源 parquet 文件名/路径**判断——若 `/data/wlx/DATABASE/extracted_tables/shengyi/` 下存在独立的内镜/耳鼻喉报告源表，按文件定模态；**无法区分时必须回报用户定夺**，不得自行拍板。
2. **无法可靠判定的行**：先产出**明细清单**（报告编号+类型代码/名称+项目/方法/部位+body 摘要）交用户确认后再定兜底键，不得自行拍板。
3. **终态彻底清理**：med_exam_type 字典删 Other 项 + CHECK 约束收紧到 26 值 + ETL 引擎兜底从写 'Other' 改为 **fail-fast 报错**。
4. **files 统计口径切换一并实施**（见 Step 4）。
5. `med_dict_mapping` 中 hos301（hospital_id=12）指向 Other 的 5 项映射**保留不动**（该中心数据尚未入库；保留 Other 目标，未来 hos301 导入时被 fail-fast/约束拒绝，逼迫人工补映射，符合终态哲学）。

## 5. 执行步骤

### Step 0 源文件侦查（落实决策 1，半小时内可完成）

```bash
ls -la /data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/
ls -la /data/wlx/DATABASE/extracted_tables/shengyi/          # 看有无其他子目录/版本
ls -la /home/dzy/wk/lnrs/data_shengyi202609/shengyi/         # staging 全清单
ls -d /home/dzy/wk/lnrs/data_*                               # 已有批次全貌
```

若文件名含 内镜/胃/肠/支气/耳鼻喉/心电/病理/超声 等的**独立**报告源表存在：用 duckdb 只读看 schema 与行数（注意 `:memory:`、`SET temp_directory=''` 禁落盘）：

```bash
cd /home/dzy/wk/lnrs/backend && uv run python - <<'PY'
import duckdb
con = duckdb.connect(":memory:")
con.execute("SET temp_directory=''")
f = "/data/wlx/DATABASE/extracted_tables/shengyi/原始文本整合版/<某文件>.parquet"
print(con.execute(f"DESCRIBE SELECT * FROM read_parquet('{f}')").fetchall())
print(con.execute(f"SELECT count(*) FROM read_parquet('{f}')").fetchone())
PY
```

判断：影像学报告 parquet 里的胃镜/肠镜/耳鼻喉行，是否另有独立源表（即医院原始库中本就该来自单独文件）。**结论回报用户后**再定消化内镜/耳鼻喉/胸腔镜的目标键；若不存在独立源表，把构成表（§3.2）与选项（bronchoscope 键义扩展为「内镜」并改字典标签 / 归 imaging_report）呈给用户选。

### Step 1 编写回填脚本 `backend/etl2/reclassify_shengyi_other_exam_type.py`

仿 `backfill_imaging_study_exam_id.py` 范式：`--dry-run`（默认）/ `--apply` 双模式、日志输出、回退 SQL 落地。流程：

1. duckdb 只读源 parquet，**逐字复算 ETL1 关键词 CASE**（§1 根因中的 ILIKE 规则，仅对「检查类型名称」列），得 Other 子集（应得 57,185 行；与 staging `exam_type='Other'` 行数对账，2026-09-14 实测逐行吻合）。
2. 规则引擎（优先级从上到下；对 Other 子集重分类；规则表写成脚本内显式常量便于评审调整）：
   - 核医学：项目/方法/部位 任一命中 `PET`|`骨显像`|`平面采集`|`断层采集`|`动态采集`|`会阴－颅底` → `nuclear_medicine`
   - 气管镜：名称/项目含 `支气管镜` → `bronchoscope`
   - （消化内镜/耳鼻喉/胸腔镜规则——Step 0 结论确定后再写）
   - MR 序列：`DWI`|`SWI`|`PWI`|`DTI`|`ASL`|`VBM`|`弥散`|`功能成像` → `MRI`
   - 造影：`造影`|`GI`|`BE`|`钡灌肠`|`IVP` → `radiology`
   - 普放摄影：`正位`|`侧位`|`斜位`|`平片`|`照片`|`拼接`|`立位`|`卧位`|`乳腺CC`|`MLO`（注意先于下一排 CT 规则）→ `radiology`
   - CT：`平扫`|`增强`（且未命中 MR/放射词）→ `CT`
   - 穿刺介入：`穿刺`|`活检` → `radiology`
   - 未命中 → 进入「未分类」清单
3. 计算 `sha256("shengyi:" + 报告编号)` 得 (source_exam_hash → new_exam_type) 映射。
4. **dry-run 输出**：目标值分布表；未分类明细清单（报告编号/类型代码/类型名称/项目/方法/部位，必要时连 `lnrs_anon_report_text.body_clean` 前 80 字符）——此清单交用户（决策 2）。
5. `--apply`：单事务 `UPDATE lnrs.lnrs_anon_exam SET exam_type=%s WHERE center_code='shengyi' AND exam_type='Other' AND source_exam_hash=%s`（逐值批量，5.7 万行一次事务可接受；脚本内打印 rowcount 并与预期对账，不符即 ROLLBACK）。回退方式：apply 前先 `CREATE TABLE lnrs.p_backfill_other_bak_20260919 AS SELECT anon_exam_id, exam_type FROM lnrs.lnrs_anon_exam WHERE center_code='shengyi' AND exam_type='Other';` 回退 = 按备份表回填。

### Step 2 用户确认 → apply → 库内验证

- 把 dry-run 分布 + 未分类明细呈用户；按用户答复补规则/定兜底；重跑 dry-run 直到未分类=0（或有用户明示的去向）。
- `--apply` 后验证：

```bash
psql -h 127.0.0.1 -U lnrs -d postgres <<'SQL'
SELECT exam_type, count(*) FROM lnrs.lnrs_anon_exam GROUP BY 1 ORDER BY 2 DESC;
SELECT count(*) FROM lnrs.lnrs_anon_exam WHERE exam_type='Other';   -- 必须为 0
SQL
```

对账：各模态增量与 dry-run 分布一致；总和仍为 1,037,523；26 键之外无值。

### Step 3 终态联动

1. 新建 `backend/sql/postgres/0024-drop-other-exam-type.sql`（幂等）：
   - `DELETE FROM lnrs.sys_dict_data WHERE dict_type='med_exam_type' AND dict_value='Other';`（同时清理 Redis 字典缓存 `system_dict:1:med_exam_type`，db7，可用后端缓存刷新接口或 redis-cli DEL；`med_modality` 字典本就 26 键无 Other，不动；Lab/Order 两个历史字典项保留不动）
   - 仿 0022：`sudo -u postgres psql` 内 `ALTER TABLE lnrs.lnrs_anon_exam DROP CONSTRAINT IF EXISTS lnrs_anon_ck_exam_type;` + `ADD CONSTRAINT lnrs_anon_ck_exam_type CHECK (exam_type IS NULL OR exam_type IN (26 值))`，事务内自检（试 UPDATE 成 26 值之外应被拒，ROLLBACK）。
2. `backend/app/plugin/module_medical/hospital/anon_etl_engine.py` `_normalize_exam_type`（:1127-1153）：兜底 `return "Other"` 改为 `raise ValueError(f"unmapped exam_type: ...")`（fail-fast；调用方 `_import_exam_text_table` 会中断导入并留日志，人工补 `med_dict_mapping` 后重跑——upsert 幂等，安全）。
3. `backend/etl1_adapt_shengyi_202609.py` `SQL_IMAGING` CASE 同步补全关键词（PET/骨显像/平面采集→PETCT；支气管镜/胃镜/肠镜等按最终定案；正位/侧位/造影/DWI 等按最终定案），防止未来重跑 staging 再产生 Other。
4. hos301 的 5 项 Other 映射**不动**（决策 5）。

### Step 4 files 统计口径切换（已定决策 4）

`backend/app/plugin/module_medical/files/service.py` `statistics` 内 by_exam_type 段（:305-330）改为 exam 表口径：

```python
by_exam_sql = select(e.exam_type, func.count().label("n")).group_by(e.exam_type)
by_exam_sql = cls._apply_exam_conditions(by_exam_sql, exam_type=exam_type, center_type=center_type)
by_exam_sql = await Permission(e, auth).filter_query(by_exam_sql)
```

- `_apply_exam_conditions` 已存在（:73-88，exam_type→exam.exam_type、center_type→exam.center_code）；file_type 参数废弃不传。
- 分母逻辑不动：`exam_total = sum(所有分组行)`，口径切换后即为「全部模态数量之和」。
- 同步更新 :220 的口径注释（写明 2026-09-19 切换原因）。
- label 仍取 `med_exam_type` 字典翻译（前端 `statisticsTypeText` 只按 value 匹配，label 不参与渲染）。
- 前端零改动（选项字典 `med_modality` 26 键、find 不到显示 0(0%) 的逻辑均不变）。

### Step 5 部署与全链路验证

```bash
sudo systemctl restart lnrs-backend   # 等待日志 Application startup complete
curl -s "http://127.0.0.1:8610/api/v1/medical/files/statistics?exam_type=&file_type=&center_type=&order_by=%5B%5D" -H "Authorization: Bearer <token>" | python3 -m json.tool
```

验收标准：

1. 无筛选 `by_exam_type`：返回重划后全部有数据组，全部落在 26 键、percentage 合计 = 100%，总数 1,037,523 不变；预期量级 nuclear_medicine ≈18,353(1.8%)、bronchoscope ≈6,248+内镜定案量、gene 1,309(0.13%)、CT/MRI/radiology 各自增量与 dry-run 一致。
2. 带筛选语义不变：`exam_type=gene` → gene 1,309(100%)；KPI 区「记录」= imaging_study 口径、「总记录」= exam 口径，与现状一致。
3. 前端文件页（强刷/清 localStorage 字典缓存后）：模态类型列表无 Other 项；各模态计数与接口一致。
4. 引擎 fail-fast：`_normalize_exam_type` 单测/手工构造未知值验证抛错；0022 自检同款手法验证新约束拒绝 27 值。

## 6. 回退与风险

| 风险 | 缓解 |
|---|---|
| UPDATE 误伤 | WHERE 三重守卫（center_code + exam_type='Other' + source_exam_hash 精确集合）；apply 前备份表；rowcount 对账不符即 ROLLBACK |
| 规则误分类 | dry-run 明细先交用户（决策 2）；规则表显式常量可评审 |
| 未来导入遇到未知 exam_type | fail-fast 抛错中断（预期行为），人工补 `med_dict_mapping` 后重跑即可（upsert 幂等） |
| 约束收紧后 hos301 映射指向 Other | 保留（决策 5）：导入时被拒 → 人工补映射，符合终态哲学 |
| 字典删 Other 后 Redis 残留 | 0024 中同步 DEL `system_dict:1:med_exam_type`（db7），或在后端字典管理界面刷新 |
| 脏数据 exam_date=8122-08-03（1 行） | 本次不动，仅记录 |

## 7. 改动同步清单（服务器 → 本地 Windows 仓库 `E:\mw3\wspy\2026\lnrs`）

全部完成后，以下文件需同步回本地仓库并提交（服务器侧先行验证）：

1. `backend/etl2/reclassify_shengyi_other_exam_type.py`（新增）
2. `backend/sql/postgres/0024-drop-other-exam-type.sql`（新增）
3. `backend/app/plugin/module_medical/hospital/anon_etl_engine.py`（兜底 fail-fast）
4. `backend/etl1_adapt_shengyi_202609.py`（CASE 补全）
5. `backend/app/plugin/module_medical/files/service.py`（by_exam_type 口径）
6. `docs/etl2/verify_result/` 下补一份重划验证记录（仿 shengyi_imaging_report_20260914.md 格式）

同步方式任选：服务器侧 `git` 分支推送，或把补丁文件经跳板拷回本地（`ssh jump-115-3 "ssh dzy@10.12.196.3 'cat /path/file'"` > 本地文件）。
