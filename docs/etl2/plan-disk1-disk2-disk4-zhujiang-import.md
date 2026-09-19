# 珠江 CT 影像三盘（disk1 + disk2 + disk4 result）→ h196_3 PG 导入计划

## 0. 结论先行

- **目标库**：`h196_3`（10.12.196.3:5432/postgres，schema=lnrs，env=`.env.h196_3`，LNRS_ANON_SECRET 与 dev 同密钥）。
- **数据范围**：把三个目录里的珠江医院 CT DICOM 目录一次性灌进 PG 的三层脱敏表：
  - `lnrs_anon_imaging_study`（patient ↔ StudyInstanceUID ↔ 磁盘 image_path 的桥）
  - `lnrs_anon_dicom_series`（study 级 byte_size / file_count / series_count）
  - 联动表 `lnrs_anon_patient`（新增占位 + 真实档案回填）、`lnrs_anon_exam`（不直接新增，imaging_study 回填 anon_exam_id 复用现有 zhujiang CT exam）、`lnrs_anon_ingest_batch`（每个中心 1 个 batch）、`lnrs_anon_phi_audit`（patient_id HMAC 审计）
- **磁盘三处与规模（h196_3 实测 2026-09-19，按 `<PID>_<StudyUID>` 目录名递归匹配）**：

  | 源目录 | study 目录 | 去重 StudyUID | 去重 PID |
  |---|---:|---:|---:|
  | `01_disk/zhujiang_dicom/`（盘 1） | 27,131 | 26,810 | 23,469 |
  | `02_disk_sorted/staging/`（盘 2 补充） | 19,710 | 19,369 | 17,832 |
  | `04_disk/result/`（盘 4 result） | 40,416 | 40,412 | 32,420 |
  | **合计** | **87,257** | **85,869**（跨盘去重） | **60,217**（跨盘去重） |
  | 另有：UID 非 `1.2.` 开头的 study（见 §1.5.2） | +337 | — | — |
  | **真实总数** | **87,594** | — | — |

  > ⚠️ 早期草稿里的 68,944 / 36,698 / ~52,000 是用 `find -mindepth N -maxdepth N` 固定深度估的，
  > **低估**了（三个盘都存在深度不一的结构）。上表为递归匹配的实测值，以本表为准。
  > 旧 CSV（`ct_image_patient_map.csv`，36,698 行）覆盖面明显小于磁盘实际 —— 它的扫描器只认
  > `<root>/<YYYYMMDD>/<study>` 且要求 UID 以 `1.2.` 开头，两处都会漏（见 §1.5.2）。

- **核心架构**：复用既有资产，不新造轮子：
  - Step 2/3（CSV 重建 + imaging_study 灌库）→ 新建离线脚本（仿 `scripts/build_shengyi_imaging_study_index.py`）；
    **扫描不沿用 `build_image_patient_map.py` 的固定深度口径**（会漏 4,363 个 study，见 §1.5.2/R17）
  - Step 5（dicom_series 落库）→ **复用已验证的 `backend/etl2/backfill_dicom_series_count.py --apply --bypass-exam-fk`**（shengyi 实证 82,057 行 / 16.2 TB）
- **关键决策**（用户已确认）：
  - 包含盘 4 result（新增 `disk4_zhujiang` source）
  - 三层全部走（imaging_study + dicom_series + patient + ingest_batch + phi_audit）
  - **Step 5 走 bypass 回填脚本**（P0-2 决策）：`_import_dicom_series_for_center`（ETL2 CLI 路径）在库内**从未产出过任何一行**（shengyi R1–R15 跑过但 100% skip），且被 `data_root` 守卫拦死；改用已实证的 bypass 脚本，零引擎风险。
  - **B 方案**处理 backfill 缺口：本次不做 exam 回填（h196_3 zhujiang exam 表 0 行，无法做关联）；后续单独批次灌 zhujiang exam 后再 backfill。
  - **patient 发号用 `nextval`**（P0-3 决策）：`pg_advisory_xact_lock(hashtext('zhujiang_patient_seq'))` + `'PT_' || LPAD(nextval('lnrs.lnrs_anon_patient_seq')::text, 8, '0')`。**不用 `MAX(patient_id)+1`**（不推进序列 → 后续 ETL2 引擎发号会 PK 冲突）。与 shengyi 模板、ETL2 引擎口径一致。
  - **占位患者显式写 `is_placeholder = TRUE`**：该列 `DEFAULT FALSE`（0018）；shengyi 离线脚本漏写导致 82,683 个占位患者未标记（R16），本次避免重犯。
  - **脚本产物不入库**（PHI 方案 2）：CSV / patient_added 列表含明文 PHI 与院内 PID，整体加入 `.gitignore`；
    旧 `ct_image_patient_map.csv` 已 `git rm --cached`（磁盘保留）。历史提交中的 PHI 清除另案（§7-7）。
  - 路径与本机一致：`/data/wlx/DATABASE/...`；**`h196_3` 是本机环境名，不是远程主机**（详见 §R12）。
- **预计总耗时**：CSV 重建 ~5 min、imaging_study 灌库 ~30 min、dicom_series ~30 min，合计约 1.5 小时。
- **代码改动**（2026-09-19；均为 issue-2 使能修复，本批不依赖）：
  - `backend/app/plugin/module_medical/hospital/anon_etl_engine.py`：`_import_dicom_series_for_center` 加 `allow_null_exam` 读取（spec 字段 > `LNRS_DICOM_ALLOW_NULL_EXAM` 环境变量 > 默认 False，**默认关闭 → 既有行为零变化**）；`_upsert_dicom_byte_size_for_study` 签名 `anon_exam_id: str | None` + `ON CONFLICT DO UPDATE` 的 anon_exam_id 用 `COALESCE(excluded, existing)`。
  - `backend/etl2/run_dicom_series_etl.sh`：新增 `--allow-null-exam` CLI 参数（自动 export 环境变量）。
  - 不改：既有 shengyi 等中心调用方式；`backfill_imaging_study_exam_id.py`；`backfill_dicom_series_count.py`；所有 DDL。

---

## 1. 背景与现有状态

### 1.1 现有数据基础

- **h196_3 PG 现状（2026-09-19 实测）**：
  - `lnrs_anon_patient (zhujiang)` = 0 行
  - `lnrs_anon_exam (zhujiang CT)` = 0 行
  - `lnrs_anon_imaging_study (zhujiang)` = 0 行
  - `lnrs_anon_imaging_study (shengyi)` = 82,994 行（已含），shengyi dicom_series 82,057 行已落
  - 也就是说 h196_3 上**没有任何 zhujiang 影像数据**
- **PG 密钥**：`LNRS_ANON_SECRET = "change-me-in-production-please"` 在 dev / h196_3 完全一致 → dev 灌的 anon_id 在 h196_3 上等价
- **磁盘路径**：`/data/wlx/DATABASE/01_disk/zhujiang_dicom`、`/data/wlx/DATABASE/02_disk/1第一数据盘/珠江补充ct/`（解包后实质就是 `02_disk_sorted/staging/`）、`/data/wlx/DATABASE/04_disk/result/`，在 h196_3 上挂载一致

### 1.2 既有离线条目 + ETL2 扫盘机制

- `scripts/build_image_patient_map.py`：扫描盘 1 + 盘 2 staging 目录生成 `docs/sour/ct_image_patient_map.csv`（**不含盘 4**）
- `scripts/build_imaging_study_index.py`：读 CSV → 离线 INSERT `lnrs_anon_imaging_study`（含 patient FK 反查、HMAC、ON CONFLICT DO NOTHING 幂等）—— 当前 zhujiang 中心 0 行
- `scripts/build_shengyi_imaging_study_index.py`：shengyi 版同款；**它显式写入 `source_kind='dicom_dir'` 的 ingest_batch**（第 161 行），是本次 Step 3 的直接模板
- `backend/etl2/backfill_imaging_study_exam_id.py`：按 `(patient_id, exam_date ±7d)` 反查 exam 表，UPDATE `lnrs_anon_imaging_study.anon_exam_id`。zhujiang exam 表为 0 行 → 本批必然 0 覆盖（见 Step 4）
- `backend/etl2/backfill_dicom_series_count.py`：**本次 Step 5 的主角**。`--apply --bypass-exam-fk` 扫描 `imaging_study.image_path`，
  实测 `series_count` / `file_count` / `byte_size`，raw SQL upsert（`anon_exam_id=NULL`，复用中心最新 batch UUID）
- `backend/etl2/run_dicom_series_etl.sh`：ETL2 CLI 包装脚本（走 `_import_dicom_series_for_center`）。**本批不用**，原因见 §1.3

### 1.3 ETL2 CLI 的 dicom_series 路径：从未产出过数据（2026-09-19 实测）

- `_import_dicom_series_for_center`（`anon_etl_engine.py:2980`）：
  - 拉 `(study_key, dicom_study_uid, image_path, anon_exam_id, existing_series_count)`，按 `dicom_study_uid` 排序
  - `scope='all'` 默认全量；`scope='unexamined'` 可增量
  - **`imaging_study.anon_exam_id` 为 NULL 时 `continue`**（不写 dicom_series 行）
  - 每 500 study 一次 `db.commit()`，失败 study 不阻断
- **库内证据**：`lnrs_anon_dicom_series` 全部 82,057 行的 `created_batch_id` 都指向同一个
  `source_kind='dicom_dir'` 的 batch（由 `build_shengyi_imaging_study_index.py` 创建）；
  该表数据由 `backfill_dicom_series_count.py --bypass-exam-fk` 写入。**无一行来自 CLI 路径**。
  CLI 路径在 shengyi R1–R15 中执行过，但当时 `anon_exam_id` 100% NULL → 100% skip。
- **`data_root` 守卫**：`ENVIRONMENT=h196_3` 的 `LNRS_DATA_ROOT=/home/dzy/wk/lnrs_dats` 不存在，
  `run_center` 在 `data_dir.exists()` 为假时直接 `return failed`，`import_center` 从不被调用；
  dry-run 只打印 `exists=False` 不报错 → **掩盖问题**（见 §R14）
- **`_create_batch` 硬编码** `source_kind="csv_report"`（`anon_etl_service.py:63`）→ CLI 跑出来的 batch 标签会错
- **`backfill_dicom_series_count.py:218`** 的 `anon_exam_id=row.anon_exam_id or ""`：NULL 时传空串 →
  FK 违反（这正是 `--bypass-exam-fk` 存在的理由）
- **结论**：本批 Step 5 走 bypass 脚本（已验证），CLI 路径的修复列入 §7-1 工单

### 1.4 现有 CSV 数据（`docs/sour/ct_image_patient_map.csv`）

- 36,699 行（1 header + 36,698 data）
- source 分布：`disk1_zhujiang` 19,004 + `disk2_zhujiang_supplement` 17,694
- 列：`source,exam_date,exam_year_month,patient_id,study_instance_uid,sop_instance_count,image_path,exam_no,pat_local_id,sick_id,patient_name,patient_sex,patient_age,exam_class,admission_count`
- **不入库到 PG**（仅作 CSV 桥）；CSV 的字段决定 imaging_study 表的入参

### 1.5 扫描口径实测（M5；2026-09-19）

对三个盘做了一次 `<PID>_<StudyUID>` 目录名的**递归匹配**（命中 study 即剪枝，不下钻 series/文件），
结果用于校验 Step 2 的扫描逻辑与 M5 风险。

#### 1.5.1 跨盘 PID 重叠：**风险不成立**

| 交集 | 数量 |
|---|---:|
| disk1 ∩ disk2 | 3,458 |
| disk1 ∩ disk4 | 6,564 |
| disk2 ∩ disk4 | 5,140 |
| 三盘交集 | 1,658 |
| **并集（将发号的 patient 数）** | **60,217** |

- **身份校验**：CSV 中 2,706 个同时出现在 disk1 与 disk2 的 PID，**姓名 100% 一致（0 冲突）**，
  且无「单盘内同 PID 多姓名」噪声 → **PID 命名空间跨盘一致**。
- **UID → PID 严格 1:1**：0 个 StudyUID 被挂到多个 PID 下 → 不存在「同一检查两个号」。
- 盘内重复 UID（disk1 321 / disk2 341 / disk4 4）**全部是同一 PID 的打包重复**（同一 study 出现在
  两个 zip 批次或 `new-yd20230708_0`/`_3` 两个目录），由
  `ON CONFLICT (patient_id, dicom_study_uid, source) DO NOTHING` 合并 ✅
- 异常 PID 共 6 个 study：`5`（disk2+disk4 各 1，会合并为一个 patient）、`LW`、`16776677`、
  `200903060006` / `200903060003` / `200904060005`（12 位，形似日期）。已抽验均为**真实 CT 目录**，
  量级可忽略。注意 `LW` 不含数字，会被 `<PID>_<UID>` 正则跳过（1 个 study）。

> **结论：M5（同一人不同 PID → 分裂成两个 patient_id）不会发生。** 同一人在各盘使用同一 PID，
> 会正确合并为单一 `anon_id` / `patient_id`。

#### 1.5.2 扫描逻辑的两个漏扫点（**必须修**，否则静默丢数据）

现有 `scripts/build_image_patient_map.py::_iter_dicom_studies` 的扫描口径有两处过滤：

**(a) 只认 `<root>/<YYYYMMDD>/<study>`** → 漏掉 study 直接挂在非日期目录下的情况：

| 盘 | 父目录 = 日期 | 父目录 ≠ 日期（会被漏） |
|---|---:|---:|
| disk1 | 23,106 | **4,025**（`yd20230825` / `new-yd20230708_0` / `new_20250902` …） |
| disk2 | 19,710 | 0 |
| disk4 | 40,415 | 1（`2018-1`） |

**(b) 要求 StudyInstanceUID 以 `1.2.` 开头** → 漏掉另一厂商 OID 根的 study：

| 盘 | 非 `1.2.` 的 study |
|---|---:|
| disk1 | 131 |
| disk2 | 46 |
| disk4 | 160 |
| **合计** | **337** |

已抽验三个样本（`348154_1.3.46.670589.61.128.0.20200928093017741` 512 文件、
`3415142_1.3.46.670589.33.1…` 1372 文件、`5_1.2.276.0.7230010…` 59 文件），
全部为 **DICOM、`Modality=CT`**，确系真实检查数据。

> 合计漏扫 **4,363 个 study（约 5.0%）**。Step 2 必须改成**递归匹配 `<PID>_<UID>` 目录名**，
> 并**去掉 `1.2.` 前缀限制**（`lnrs_anon_imaging_study.dicom_study_uid` 是 `VARCHAR(64)`，
> `1.3.46.670589.61.128.0.20200928093017741` 仅 41 字符，容量充足）。

---

## 2. 目标落地表与字段映射

### 2.1 `lnrs_anon_imaging_study`（DDL 见 0012-imaging-study-bridge.sql）

| 列 | 来源 | 派生规则 |
|---|---|---|
| `study_key` | DB 自增 | `BIGSERIAL` |
| `patient_id` | FK `lnrs_anon_patient` | `SELECT patient_id FROM lnrs_anon_patient WHERE center_code='zhujiang' AND anon_id=$HMAC` |
| `center_code` | 常量 | `'zhujiang'` |
| `dicom_study_uid` | CSV 第 5 列 | 原值（`1.2.*` 开头的 OID） |
| `modality` | CSV / 默认 | `'CT'`（本次全 CT） |
| `image_path` | CSV 第 7 列 | 磁盘 Study 根目录绝对路径 |
| `sop_count` | CSV 第 6 列 | 磁盘目录下文件数（CSV 离线已统计） |
| `source` | 字符串值约定（DDL 是 `VARCHAR(64)`，非 PG ENUM） | `disk1_zhujiang` / `disk2_zhujiang_supplement` / `disk4_zhujiang` |
| `anon_exam_id` | 本批不写入（保持 NULL） | B 方案：exam 表 0 行，无法关联；Step 5 的 bypass 脚本不读该列（见 Step 4） |
| `created_batch_id` | Step 3 脚本生成 UUID | 整批同一 UUID，记录到 `lnrs_anon_ingest_batch`（Step 5 的 dicom_series 行复用同一 UUID） |
| `created_at` / `updated_at` | DB DEFAULT | `CURRENT_TIMESTAMP` + 触发器 |

### 2.2 `lnrs_anon_dicom_series`（DDL 见 0006 §7 + 0023 + 0024）

| 列 | 来源 | 派生规则 |
|---|---|---|
| `series_id` | DB 自增 | `BIGSERIAL` PK |
| `anon_exam_id` | 不写入（保持 NULL） | B 方案：`backfill_dicom_series_count.py --bypass-exam-fk` 的 raw SQL 写 `NULL`；0024 已允许 FK NULL |
| `dicom_study_uid` | 从 imaging_study 取 | UNIQUE 约束（幂等键） |
| `file_count` | 脚本实测 | study 目录 `iterdir` 文件总数 |
| `byte_size` | 脚本实测 | 累加目录下**所有文件**的 `st.st_size`（不限于 `.dcm`，与 `register_folder` 口径一致） |
| `series_count` | 脚本实测 | `DicomIndexer.register_folder` 按 SeriesInstanceUID 去重计数（跳过非图像模态/无 UID） |
| `created_batch_id` | 复用中心最新 batch UUID | = Step 3 离线灌库创建的 `dicom_dir` batch（脚本按 `center_code` 取 `started_at DESC LIMIT 1`） |

### 2.3 `lnrs_anon_patient`（DDL 见 0006 §1）

| 列 | 来源 | 派生规则 |
|---|---|---|
| `patient_id` | DB 发号 | `nextval('lnrs.lnrs_anon_patient_seq')` → `PT_NNNNNNNN` |
| `anon_id` | 离线条目 | `HMAC-SHA256(LNRS_ANON_SECRET, "zhujiang:" + pat_local_id)[:12]` → `ANON_<12hex>` |
| `center_code` | 常量 | `'zhujiang'` |
| `source_system` | 离线条目 | `'disk_image_index'` |
| `source_patient_id` | 离线条目 | 原始院内 PID（如 `270561`） |
| `created_batch_id` / `last_seen_batch_id` | 灌库阶段 | 同一 UUID |
| `sex` / `birth_date` / `ethnicity` / `blood_type` / `native_place` / `bmi` | 不在本次范围 | 全部 NULL |
| `is_placeholder` | 常量 | **必须显式写 `TRUE`**——列 `DEFAULT FALSE`（0018），省略会得到未标记占位行（shengyi 漏了 82,683 行，已实测）。V1 用 `COUNT(*) FILTER (WHERE is_placeholder)` 核对 |

### 2.4 `lnrs_anon_ingest_batch`（DDL 见 0006 §4）

| 列 | 来源 | 备注 |
|---|---|---|
| `batch_id` | Step 3 离线灌库脚本生成 UUID | 整批共用；Step 5 的 dicom_series 行复用同一 UUID（脚本按 center 取最新 batch） |
| `center_code` | `'zhujiang'` | |
| `source_kind` | `'dicom_dir'` | enum 见 0006 §1（已有：`'csv_report'`/`'dicom_dir'`/`'dicom_zip'`）。由 Step 3 离线脚本显式写入（仿 `build_shengyi_imaging_study_index.py:161`）；**ETL2 CLI 的 `_create_batch` 会硬编码 `csv_report`，故本批不走 CLI** |
| `source_locator` | 三个磁盘根目录 | `'/data/wlx/DATABASE/01_disk/zhujiang_dicom,/data/wlx/DATABASE/02_disk_sorted/staging,/data/wlx/DATABASE/04_disk/result'` |
| `source_sha256` | 三个 CSV 拼接的 SHA256 | 校验三盘扫描结果的可重现性 |
| `secret_version` / `key_fingerprint` / `schema_hash` | ETL2 工具函数 | 与 patient/exam 导入一致 |
| `row_counts` | Step 3 灌库完成时写 | `{patient_added, patient_reused, imaging_study_inserted, imaging_skipped_no_patient}`。**注意**：Step 5 的 bypass 脚本不更新 `row_counts`（它只写 dicom_series 行），故 dicom_series 行数需用 V3 单独核对 |
| `status` | `'success'` / `'partial'` / `'failed'` | |

### 2.5 `lnrs_anon_phi_audit`（DDL 见 0006 §10）

本次只写 1 类审计（patient_id HMAC）：

| `source_table` | `source_field` | `source_hash` | `strategy` | 触发阶段 |
|---|---|---|---|---|
| `lnrs_anon_imaging_study` | `patient_id` | `sha256(anon_id_hex)` | `hmac`（0006 §1 enum） | imaging_study 离线条目落库 |

每个 `imaging_study` 行 1 条审计；87,594 行 → 87,594 条 phi_audit。

`dicom_series` 阶段**不写** phi_audit（无 PHI 字段，合规 OK）。

---

## 3. 实施步骤（精确到命令）

### Step 0：环境检查

```bash
# 0.0 确认执行位置：h196_3 就是本机（10.12.196.3），全部命令本机直接跑，不要 ssh
hostname -I | grep -q '10.12.196.3' && echo "本机 = h196_3 ✓"

# 0.1 磁盘可见（三个源目录）
ls /data/wlx/DATABASE/01_disk/zhujiang_dicom | wc -l          # 期望 444
ls /data/wlx/DATABASE/02_disk_sorted/staging | wc -l          # 期望 86
ls /data/wlx/DATABASE/04_disk/result | wc -l                  # 期望 232

# 0.2 dev / h196_3 密钥一致（决定 HMAC 结果是否等价）
diff <(grep LNRS_ANON_SECRET backend/env/.env.dev) \
     <(grep LNRS_ANON_SECRET backend/env/.env.h196_3)
# 期望：无输出（相同）

# 0.3 PG 连通 + ENVIRONMENT 生效
PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres -tAc "SELECT current_database();"
cd /home/dzy/wk/lnrs/backend && ENVIRONMENT=h196_3 uv run python -c \
  "from app.config.setting import settings; print(settings.DATABASE_HOST, settings.DATABASE_NAME, settings.LNRS_DATA_ROOT)"
# 期望：127.0.0.1 postgres /home/dzy/wk/lnrs_dats

# 0.4 zhujiang 中心已注册
PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres -tAc \
  "SELECT id, code FROM lnrs.med_hospital WHERE code='zhujiang'"
# 期望：1 | zhujiang

# 0.5 schema 前置（P1-2；2026-09-19 已实测全部 OK，重跑前可复验）
PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres -tAc "
WITH chk(kind,name,ok) AS (
  SELECT 'table','lnrs_anon_imaging_study',      count(*) FROM information_schema.tables WHERE table_schema='lnrs' AND table_name='lnrs_anon_imaging_study'
  UNION ALL SELECT 'table','lnrs_anon_dicom_series',    count(*) FROM information_schema.tables WHERE table_schema='lnrs' AND table_name='lnrs_anon_dicom_series'
  UNION ALL SELECT 'table','lnrs_anon_patient',         count(*) FROM information_schema.tables WHERE table_schema='lnrs' AND table_name='lnrs_anon_patient'
  UNION ALL SELECT 'table','lnrs_anon_phi_audit',       count(*) FROM information_schema.tables WHERE table_schema='lnrs' AND table_name='lnrs_anon_phi_audit'
  UNION ALL SELECT 'table','lnrs_anon_ingest_batch',    count(*) FROM information_schema.tables WHERE table_schema='lnrs' AND table_name='lnrs_anon_ingest_batch'
  UNION ALL SELECT 'table','lnrs_anon_imaging_orphan',  count(*) FROM information_schema.tables WHERE table_schema='lnrs' AND table_name='lnrs_anon_imaging_orphan'   -- 0016
  UNION ALL SELECT 'view','lnrs_anon_v_imaging_study_counts', count(*) FROM information_schema.views WHERE table_schema='lnrs' AND table_name='lnrs_anon_v_imaging_study_counts'
  UNION ALL SELECT 'col','patient.is_placeholder',      count(*) FROM information_schema.columns WHERE table_schema='lnrs' AND table_name='lnrs_anon_patient' AND column_name='is_placeholder'   -- 0018
  UNION ALL SELECT 'col','patient.deleted_at',          count(*) FROM information_schema.columns WHERE table_schema='lnrs' AND table_name='lnrs_anon_patient' AND column_name='deleted_at'
  UNION ALL SELECT 'col','dicom_series.series_count',   count(*) FROM information_schema.columns WHERE table_schema='lnrs' AND table_name='lnrs_anon_dicom_series' AND column_name='series_count'  -- 0023
  UNION ALL SELECT 'col','dicom_series.byte_size',      count(*) FROM information_schema.columns WHERE table_schema='lnrs' AND table_name='lnrs_anon_dicom_series' AND column_name='byte_size'
  UNION ALL SELECT 'seq','lnrs_anon_patient_seq',       count(*) FROM information_schema.sequences WHERE sequence_schema='lnrs' AND sequence_name='lnrs_anon_patient_seq'
  UNION ALL SELECT 'enumval','phi_strategy.hmac',       count(*) FROM pg_enum WHERE enumtypid='lnrs.lnrs_anon_phi_strategy_enum'::regtype AND enumlabel='hmac'
  UNION ALL SELECT 'enumval','source_kind.dicom_dir',   count(*) FROM pg_enum WHERE enumtypid='lnrs.lnrs_anon_source_kind_enum'::regtype AND enumlabel='dicom_dir'
)
SELECT kind||' '||name||' → '||CASE WHEN ok>0 THEN 'OK' ELSE '*** MISSING ***' END FROM chk ORDER BY ok, kind, name;"
# 期望：15 行全 OK。任何 MISSING → 先补跑对应迁移（0016 / 0018 / 0023 / 0024）

# 0.5b ON CONFLICT 目标约束（灌库幂等的前提；2026-09-19 已实测）
PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres -tAc "
SELECT c.relname||' | '||con.conname||' | '||pg_get_constraintdef(con.oid)
FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='lnrs' AND con.contype IN ('u','p')
  AND c.relname IN ('lnrs_anon_imaging_study','lnrs_anon_dicom_series','lnrs_anon_patient','lnrs_anon_phi_audit')
ORDER BY 1;"
# 必须存在：
#   lnrs_anon_imaging_study  UNIQUE (patient_id, dicom_study_uid, source)  ← Step 3 的 ON CONFLICT 目标
#   lnrs_anon_dicom_series   UNIQUE (dicom_study_uid)                      ← Step 5 的 ON CONFLICT 目标
#   lnrs_anon_patient        UNIQUE (anon_id) + UNIQUE (center_code, anon_id) ← 发号的 ON CONFLICT 目标
# 预期缺失（R11 已确认）：lnrs_anon_phi_audit 只有 PK(audit_id)，**无 UNIQUE** → 重跑必重复，必须靠应用层去重

# 0.6 PG 磁盘余量（R7：/var/lib/postgresql/18/main 曾 99% 满）
df -h /var/lib/postgresql/18/main 2>/dev/null || df -h /var/lib/postgresql
```

### Step 1：备份（必做）

```bash
mkdir -p /home/dzy/wk/lnrs/backend/.backup
TS=$(date +%Y%m%d_%H%M%S)
BK=/home/dzy/wk/lnrs/backend/.backup/pre_disk1_disk2_disk4_imaging_${TS}.sql

PGPASSWORD=lnrs_pwd pg_dump -h 127.0.0.1 -U lnrs -d postgres \
  -t lnrs.lnrs_anon_patient -t lnrs.lnrs_anon_imaging_study \
  -t lnrs.lnrs_anon_dicom_series -t lnrs.lnrs_anon_phi_audit \
  -t lnrs.lnrs_anon_ingest_batch \
  --data-only --rows-per-insert=1000 > "$BK"

# 校验：文件非空 + 含既有 shengyi 数据
ls -la "$BK"
grep -c 'COPY lnrs.lnrs_anon_imaging_study' "$BK"   # 期望 1
```

**回滚命令**（备份时生成，不在本阶段执行）：

```bash
PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres -v ON_ERROR_STOP=1 -f "$BK"
```

> 注：`pg_dump --data-only` 不含表结构；若需连结构一起恢复，改用 `-Fc` 或另备 `--schema-only`。
> 备份仅作本次回滚手段，不替代生产备份流程。


### Step 2：重建 CSV（三盘统一扫描）

#### 2.1 统一扫描函数（替换 `_iter_dicom_studies` 的固定深度口径）

**新文件**：`scripts/build_disk1_disk2_disk4_imaging_study_index.py`（约 300 行）

**为什么不复用 `scripts/build_image_patient_map.py` 的扫描**：它的口径有两处漏扫（§1.5.2 实测）：
① 只认 `<root>/<YYYYMMDD>/<study>`；② 要求 UID 以 `1.2.` 开头。合计漏 4,363 个 study（5.0%）。

**核心实现**：**单一递归匹配器**，三个盘共用（盘 4 的 zip_folder 命名差异不再需要逐个特判）：

```python
STUDY_RE = re.compile(r'^([A-Za-z0-9]+)_([0-9][0-9.]*)$')   # <PID>_<UID>，UID 数字点号

def iter_studies(root: Path, max_depth: int = 6):
    """递归找 <PID>_<StudyUID> 目录；命中即剪枝（不下钻 series/文件）。
    不限制顶层目录名（YYYYMMDD / yd* / pn* / new_* / 20251103_1 / 补充31_zip 一律接受）；
    不限制 UID 前缀（1.2. / 1.3.46.670589... 都收）。"""
    stack = [(root, 0)]
    while stack:
        d, depth = stack.pop()
        try:
            with os.scandir(d) as it:
                entries = list(it)
        except OSError as e:
            log.warning(f'扫描失败 {d}: {e}'); continue
        for e in entries:
            if not e.is_dir(follow_symlinks=False):
                continue
            m = STUDY_RE.match(e.name)
            if m:
                yield m.group(1), m.group(2), e.path
                continue                    # 命中 study → 剪枝
            if depth < max_depth:
                stack.append((e.path, depth + 1))
```

**关键差异（相对旧口径）**：

| 维度 | 旧口径 | 新口径 |
|---|---|---|
| 顶层目录名 | 只认 `^\d{8}$` | **不限**（`yd*` / `pn*` / `new_*` / `20251103_1` / `补充31_zip` 全收） |
| UID 前缀 | 必须 `1.2.` | **不限**（`1.3.46.670589.*` 等也收；列宽 `VARCHAR(64)` 足够） |
| 盘 4 命名 | 需按 5 类命名特判 | 统一递归，无需特判 |
| 深度 | 固定（盘1=2 层，盘4=3 层） | 递归到 6 层（study 命中即剪枝） |

**series/文件不会被误当 study**：series 目录名形如 `0001_000001_1.2.156...`（含**两个**下划线），
不匹配 `^([A-Za-z0-9]+)_([0-9][0-9.]*)$`；且命中 study 后即剪枝，不下钻。

**`exam_date` 的取法**（旧口径用顶层日期目录名）：改为**沿路径向上找最近的 `YYYYMMDD` 目录名**；
找不到则用该 study 目录的 `st_mtime` 的日期，并在 CSV 的 `exam_date_source` 列标记
`path_date` / `mtime`，便于事后核对（盘 4 的 `2014/` 这类年份目录下若无日期层，会走 `mtime`）。

**`source` 列取值**（沿用既有约定，按盘）：
`disk1_zhujiang` / `disk2_zhujiang_supplement` / `disk4_zhujiang`。

**`sop_count`**：study 目录下 `is_file()` 计数（与旧口径一致）。

**dry-run 自检**：脚本必须打印「递归命中数」并与本次实测基线比对，任一盘偏差 >1% 即报错退出
（基线：disk1 27,131 / disk2 19,710 / disk4 40,416，另加非 `1.2.` 的 337）。

#### 2.2 dry-run

```bash
cd /home/dzy/wk/lnrs
ENVIRONMENT=dev backend/.venv/bin/python scripts/build_disk1_disk2_disk4_imaging_study_index.py --dry-run
```

**期望输出**（与 §1.5 实测基线比对，偏差 >1% 即报错）：
```
disk1 study: 27,131   (UID 非 1.2. 的另有 131)
disk2 study: 19,710   (另有 46)
disk4 study: 40,416   (另有 160)
total study dirs            : 87,594
distinct StudyUID           : 85,869
distinct PID                : 60,217
within-disk dup UID         : 666  (同 PID 打包重复，落库时 ON CONFLICT 合并)
cross-disk dup UID          : 722  (不同 source → 保留两行，image_path 各异)
csv_rows                    : 87,594
```

#### 2.3 CSV 重生成（输出到 `docs/sour/ct_image_patient_map_v2.csv`，不入库）

```bash
cd /home/dzy/wk/lnrs
backend/.venv/bin/python scripts/build_disk1_disk2_disk4_imaging_study_index.py \
  --out /home/dzy/wk/lnrs/docs/sour/ct_image_patient_map_v2.csv

# 校验行数 + source 分布
wc -l docs/sour/ct_image_patient_map_v2.csv          # 期望 87,595（含 header）
awk -F, 'NR>1 {print $1}' docs/sour/ct_image_patient_map_v2.csv | sort | uniq -c
# 期望：disk1_zhujiang 27,262 / disk2_zhujiang_supplement 19,756 / disk4_zhujiang 40,576
```

> 该脚本只**输出** CSV（不读 CSV），故只有 `--out`；`--dry-run` 只打印统计不落盘。

**Git 管理（方案 2：不入库）**：CSV 含明文 PHI（`patient_name`/`patient_sex`/`patient_age`/`sick_id`），
整体加入 `.gitignore`，只落本机磁盘、不提交。旧版 `ct_image_patient_map.csv` 同样处理——保留磁盘文件
（供对照），但已 `git rm --cached` 停止跟踪。`.gitignore` 已加规则：
`docs/sour/ct_image_patient_map*.csv` / `docs/sour/*_imaging_study_patient_added.txt` / `docs/sour/scan_skipped_dirs.txt`
（`git check-ignore` 已验证 5 个目标路径全部 IGNORED）。
> ⚠️ 旧 CSV 的 PHI 仍在 git 历史提交中；彻底清除需 `git filter-repo`/BFG 重写历史（破坏性，需单独决策）。

### Step 3：imaging_study 灌库（含 patient 增量 + phi_audit）

#### 3.1 新建灌库脚本

**新文件**：`scripts/build_zhujiang_imaging_study_index_v2.py`（约 400 行）

**复用**：`scripts/build_imaging_study_index.py` 的 90% 代码骨架（patient 反查、advisory_xact_lock 发号、ON CONFLICT DO NOTHING 幂等）。

**核心改造点**：

1. **patient 增量**：CSV 中所有 `pat_local_id` 走 `compute_anon_id('zhujiang', pid)`，反查 PG；未命中则发号 + INSERT 占位行。**照抄 `scripts/build_shengyi_imaging_study_index.py:198-221`**，但**补上 `is_placeholder`**：
   ```sql
   SELECT pg_advisory_xact_lock(hashtext('zhujiang_patient_seq'));   -- 事务级，串行化发号

   INSERT INTO lnrs.lnrs_anon_patient
       (patient_id, anon_id, center_code, sex, is_placeholder,
        created_batch_id, last_seen_batch_id)
   VALUES (
       'PT_' || LPAD(nextval('lnrs.lnrs_anon_patient_seq')::text, 8, '0'),
       %s, 'zhujiang', '0', TRUE, %s, %s
   )
   ON CONFLICT (anon_id) DO NOTHING
   RETURNING patient_id, anon_id;
   ```
   - **必须用 `nextval`，不能用 `MAX(patient_id)+1`**：后者不推进 `lnrs_anon_patient_seq`，后续 ETL2 引擎（`_batch_upsert_patients:449` 用 `nextval`）会发出已占用的号 → PK 冲突。shengyi 模板与引擎口径一致，都是 `nextval`。
   - **必须显式写 `is_placeholder = TRUE`**：该列 `DEFAULT FALSE`（0018），省略会得到未标记的占位行 —— shengyi 就是这么漏的（82,683 个 `sex='0'` 患者全部 `is_placeholder = FALSE`，已实测）。
   - 引擎侧同款（`anon_etl_engine.py:480` 显式设 `is_placeholder`）。
2. **imaging_study 灌库**：`INSERT ... ON CONFLICT (patient_id, dicom_study_uid, source) DO NOTHING`，批大小 2000。
3. **ingest_batch**：脚本内直接 INSERT（**照抄 `scripts/build_shengyi_imaging_study_index.py:156-174`**：`source_kind='dicom_dir'`、`status='success'`、`batch_id=uuid.uuid4()`、`source_locator`= 三个磁盘根目录 join、`key_fingerprint`/`schema_hash` 同款算法）。**不要复用 `anon_etl_service._create_batch`**——它硬编码 `source_kind="csv_report"`。
4. **phi_audit**：每个 imaging_study 行 INSERT 一条 `lnrs_anon_phi_audit`，`source_table='lnrs_anon_imaging_study'`、`source_field='patient_id'`、`source_hash=sha256(anon_id_bytes.hex())`、`strategy='hmac'`（enum 值 `'hmac'` 已存在，见 0006 §1）；批大小 5000。**重跑去重**：phi_audit 表没有 UNIQUE 约束，应用层在脚本里用 set 缓存 (batch_id, source_table, source_field, source_hash) 四元组去重后再批量 INSERT。
5. **新占位 patient 列表输出**：`docs/sour/zhujiang_imaging_study_patient_added.txt`（与 shengyi 同款）。
6. **跳过规则**：
   - PID 不在 PID_STUDY_RE（如目录名无下划线） → WARNING + skip
   - StudyUID 不以 `1.2.` 开头 → WARNING + skip
   - patient_id 在 PG 反查失败 → 进 Step 3.1 占位发号；如占位发号也失败 → ERROR（事务回滚到 checkpoint）
   - image_path 在磁盘上不存在 → WARNING（仍 INSERT，由 lnrs_anon_imaging_orphan 后续审计）
7. **重跑 / 中断恢复**（实测约束已确认，见 §4.2）：
   - `imaging_study` 走 `ON CONFLICT (patient_id, dicom_study_uid, source) DO NOTHING` → 重跑 no-op ✅
   - `patient` 走 `ON CONFLICT (anon_id) DO NOTHING` → 重跑不重发号 ✅
   - **`phi_audit` 无 UNIQUE，重跑会重复**：脚本必须（a）用 set 去重；（b）**重跑前先删本批审计**：
     `DELETE FROM lnrs.lnrs_anon_phi_audit WHERE batch_id = '<本次 batch_id>';`（batch_id 每次新生成，
     所以更简单的做法是**中断后重跑时换新 batch_id**，旧批次的审计行单独清理）
   - ⚠️ **顺序依赖**：patient 反查必须在发号 INSERT **之前**完成（照抄模板的 Step 4b → Step 5 顺序）。
     若先 INSERT 再反查，重跑时 `ON CONFLICT DO NOTHING` 不返回行 → 该 patient 的 study 会被误判为
     `missing_pid` 而跳过。

#### 3.2 dry-run
```bash
cd /home/dzy/wk/lnrs/backend
ENVIRONMENT=h196_3 uv run python ../scripts/build_zhujiang_imaging_study_index_v2.py \
  --csv /home/dzy/wk/lnrs/docs/sour/ct_image_patient_map_v2.csv --dry-run
```

**期望输出**：
```
csv rows: 87,594
distinct patient_id: ~60,217
distinct dicom_study_uid: ~85,869
reused_patients (anon_id hit): 0 （h196_3 zhujiang patient = 0）
patient_to_add: ~60,217
imaging_rows_after_dedup: ~87,594   (含跨 source 的 722 条重复 UID，各占一行)
phi_audit_planned: ~87,594
预估耗时: ~5 min
```

#### 3.3 正式灌库

```bash
cd /home/dzy/wk/lnrs/backend
ENVIRONMENT=h196_3 uv run python ../scripts/build_zhujiang_imaging_study_index_v2.py \
  --csv /home/dzy/wk/lnrs/docs/sour/ct_image_patient_map_v2.csv
```

**期望输出**（预计 35 min）：
```
patient_inserted: ~60,217
imaging_inserted: ~87,594
imaging_skipped_no_patient: 0
phi_audit_inserted: ~87,594
ingest_batch_id: <uuid>      ← 记下这个 UUID，Step 5 会复用它
row_counts: {...}
status: success
耗时: ~35 min
```

### Step 4：exam 回填 —— 本批跳过（B 方案）

**前置事实**：h196_3 上 `lnrs_anon_exam (zhujiang, CT)` = **0 行**（§1.1 实测）。
`backfill_imaging_study_exam_id.py` 的关联口径是 `(patient_id, exam_date ±7d)` 反查 exam 表，
exam 表为空 → 覆盖率必然 0%，回填是 no-op。

**决策：本批不做 exam 回填。**

- `imaging_study.anon_exam_id` 保持 NULL
- `dicom_series.anon_exam_id` 保持 NULL（Step 5 的 bypass 脚本本就写 NULL；0024 已允许 FK NULL）
- 视图 `lnrs_anon_v_imaging_study_counts` 的 `total_bytes` / `series_count` / `instance_count` **正常**；
  仅 `anon_exam_id` 为 NULL

**后续路径**（§7 工单）：先单独批次灌 zhujiang exam（走 ETL2 `nodule_imaging` spec，需先备好
`<data_root>/zhujiang/nodule_imaging.parquet`），再：

```bash
# ① 回填 imaging_study → exam
cd /home/dzy/wk/lnrs/backend
ENVIRONMENT=h196_3 uv run python etl2/backfill_imaging_study_exam_id.py --apply --center zhujiang

# ② 把关联同步到 dicom_series（现有脚本不含此步，需另写；见 §7-2）
# UPDATE lnrs.lnrs_anon_dicom_series d
#    SET anon_exam_id = s.anon_exam_id
#   FROM lnrs.lnrs_anon_imaging_study s
#  WHERE s.dicom_study_uid = d.dicom_study_uid
#    AND s.center_code='zhujiang' AND s.anon_exam_id IS NOT NULL
#    AND d.anon_exam_id IS NULL;
```

### Step 5：跑 dicom_series 落库（复用已验证的 bypass 脚本）

**为什么不用 ETL2 CLI**（`run_dicom_series_etl.sh` / `_import_dicom_series_for_center`）：

1. **该写路径在库内从未产出过任何一行**——shengyi R1–R15 中它确实执行过（shengyi spec 含 dicom_series），
   但当时 `imaging_study.anon_exam_id` 100% NULL → 100% skip。库里 82,057 行 dicom_series 全部来自
   离线脚本 + `backfill_dicom_series_count.py`，无一行来自 CLI。
2. **被 `data_root` 守卫拦死**：`ENVIRONMENT=h196_3` 的 `LNRS_DATA_ROOT=/home/dzy/wk/lnrs_dats` 不存在，
   `run_center` 在 `data_dir.exists()` 为假时直接 `return failed`，`import_center` 根本不被调用；
   而 dry-run 只打印 `exists=False` 不报错，会掩盖问题（已实测复现，见 §R14）。
3. **batch 标签会错**：`_create_batch` 硬编码 `source_kind="csv_report"`（`anon_etl_service.py:63`），
   而本批语义是 `dicom_dir`。

改用 `backend/etl2/backfill_dicom_series_count.py --apply --bypass-exam-fk`：它扫描
`lnrs_anon_imaging_study.image_path`，用 `DicomIndexer.register_folder` 实测 series_count、
`iterdir + stat` 累加 file_count/byte_size，raw SQL upsert（`anon_exam_id=NULL`，复用中心最新 batch UUID）。
**shengyi 实证**：82,057 行 / 16.2 TB / series_count 全实测。

#### 5.1 dry-run（只读）

```bash
cd /home/dzy/wk/lnrs/backend
ENVIRONMENT=h196_3 uv run python etl2/backfill_dicom_series_count.py --dry-run --center zhujiang
```

**期望**：Step 3 完成后输出 `待回填 study` 数 ≈ 68,500（Step 3 之前为 0，属正常）。

#### 5.2 canary（先跑 200 条验证）

```bash
cd /home/dzy/wk/lnrs/backend
ENVIRONMENT=h196_3 uv run python etl2/backfill_dicom_series_count.py \
  --apply --bypass-exam-fk --center zhujiang --limit 200
```

**期望**：`scanned=200 updated≈200 skipped_offline≈0 failed=0`。核对 200 行的 byte_size > 0、series_count 非 NULL。

#### 5.3 正式跑

```bash
cd /home/dzy/wk/lnrs/backend
ENVIRONMENT=h196_3 uv run python etl2/backfill_dicom_series_count.py \
  --apply --bypass-exam-fk --center zhujiang
```

**期望输出**（预计 30 min）：
```
[APPLY-BYPASS] 使用 batch_id=<Step 3 的 dicom_dir batch>
[APPLY-BYPASS] 候选 study 行 68,500 条
[APPLY-BYPASS] 进度 500/68500 updated=… offline=… failed=… elapsed=…
...
[APPLY-BYPASS] 完成：scanned=68,500 updated=68,500 skipped_offline=~50 failed=0 center=zhujiang
```

> 幂等：`ON CONFLICT (dicom_study_uid) DO UPDATE … WHERE dicom_series.series_count IS NULL`
> —— 已实测行不会被复位，重跑为 no-op（天然断点续扫）。离线目录（移动盘出库）计入 `skipped_offline`，
> 其 `series_count` 保持 NULL。
> `anon_exam_id` 为 NULL（B 方案预期，0024 已允许）；`file_count` / `byte_size` / `series_count` 正常落库。

### Step 6：验证 SQL（V1-V10）

**新建**：`docs/etl2/verify_disk1_disk2_disk4_zhujiang_imaging.sql`

```sql
\echo '--- 三盘 zhujiang 影像 灌库核验 ---'

\echo ''
\echo 'V1. patient 总数（zhujiang）'
SELECT COUNT(*) AS zhujiang_patients, COUNT(*) FILTER (WHERE is_placeholder) AS placeholders
FROM lnrs.lnrs_anon_patient WHERE center_code='zhujiang' AND deleted_at IS NULL;

\echo ''
\echo 'V2. imaging_study 总数（zhujiang）+ 按 source 拆分'
SELECT source, COUNT(*) AS rows, COUNT(DISTINCT dicom_study_uid) AS unique_studies
FROM lnrs.lnrs_anon_imaging_study WHERE center_code='zhujiang'
GROUP BY source ORDER BY source;

\echo ''
\echo 'V3. dicom_series 总数（zhujiang，dicom_study_uid 维度）'
SELECT COUNT(*) AS dicom_series_rows,
       SUM(byte_size) AS total_bytes,
       SUM(file_count) AS total_files,
       COUNT(*) FILTER (WHERE series_count IS NOT NULL AND series_count > 0) AS nonzero_series
FROM lnrs.lnrs_anon_dicom_series ds
JOIN lnrs.lnrs_anon_imaging_study s USING(dicom_study_uid)
WHERE s.center_code='zhujiang';

\echo ''
\echo 'V4. anon_exam_id 覆盖率（B 方案：应为 0）'
SELECT COUNT(*) FILTER (WHERE anon_exam_id IS NOT NULL) AS with_exam,
       COUNT(*) FILTER (WHERE anon_exam_id IS NULL) AS without_exam
FROM lnrs.lnrs_anon_imaging_study WHERE center_code='zhujiang';

\echo ''
\echo 'V5. phi_audit 本次 batch 行数（≈ imaging_study 行数）'
SELECT COUNT(*) AS audit_rows
FROM lnrs.lnrs_anon_phi_audit
WHERE batch_id = (SELECT batch_id FROM lnrs.lnrs_anon_ingest_batch
                   WHERE center_code='zhujiang' AND source_kind='dicom_dir'
                   ORDER BY started_at DESC LIMIT 1);

\echo ''
\echo 'V6. ingest_batch 状态（本批）+ dicom_series 归属核对'
SELECT batch_id, status, row_counts::text, source_locator, started_at
FROM lnrs.lnrs_anon_ingest_batch
WHERE center_code='zhujiang' AND source_kind='dicom_dir'
ORDER BY started_at DESC LIMIT 1;

SELECT ds.created_batch_id, COUNT(*) AS series_rows
FROM lnrs.lnrs_anon_dicom_series ds
JOIN lnrs.lnrs_anon_imaging_study s USING(dicom_study_uid)
WHERE s.center_code='zhujiang'
GROUP BY 1;   -- 期望：单行，且 = 上面查到的 batch_id（R15）

\echo ''
\echo 'V7. 视图 v_imaging_study_counts（zhujiang 部分）'
SELECT COUNT(*) AS study_total,
       COUNT(*) FILTER (WHERE total_bytes > 0) AS nonzero_total_bytes,
       SUM(total_bytes) AS sum_bytes
FROM lnrs.lnrs_anon_v_imaging_study_counts WHERE center_code='zhujiang';

\echo ''
\echo 'V8. FK 孤儿检查（dicom_series 引用不存在的 study 应为 0）'
SELECT 'orphan_ds', count(*) FROM lnrs.lnrs_anon_dicom_series ds
  LEFT JOIN lnrs.lnrs_anon_imaging_study s USING(dicom_study_uid)
  WHERE s.dicom_study_uid IS NULL;

\echo ''
\echo 'V9. imaging_study.anon_exam_id 守卫（0024 允许 NULL，但与 exam FK 应一致）'
SELECT 'orphan_to_exam', count(*) FROM lnrs.lnrs_anon_imaging_study s
  LEFT JOIN lnrs.lnrs_anon_exam e ON e.anon_exam_id = s.anon_exam_id
  WHERE s.anon_exam_id IS NOT NULL AND e.anon_exam_id IS NULL;

\echo ''
\echo 'V10. source 列值域（必须 3 个固定字符串）'
SELECT source, COUNT(*) FROM lnrs.lnrs_anon_imaging_study
WHERE center_code='zhujiang' GROUP BY 1;
```

**期望值（B 方案）**：

| V# | 指标 | 期望 |
|---|---|---|
| V1 | zhujiang_patients | ~60,217 |
| V1 | placeholders | ~60,217（全占位，无真实人口学） |
| V2 | disk1_zhujiang rows | ~27,262 |
| V2 | disk2_zhujiang_supplement rows | ~19,756 |
| V2 | disk4_zhujiang rows | ~40,576 |
| V2 | 合计 | ~87,594（= study 目录数） |
| V3 | dicom_series_rows | ~85,869（**= 去重 StudyUID 数**，不是 study 目录数——见下方说明） |
| V3 | nonzero_series | ~80,000+（部分目录可能空） |
| V4 | with_exam | 0（B 方案） |
| V4 | without_exam | ~87,594 |
| V5 | audit_rows | ~87,594（= imaging_study 行数） |
| V6 | status | success |
| V7 | nonzero_total_bytes | ~85,000 |
| V7 | sum_bytes | 数十 TB |
| V8 | orphan_ds | 0 |
| V9 | orphan_to_exam | 0 |
| V10 | source 唯一 | 3 个值 |

> **V3 的口径说明**：`lnrs_anon_dicom_series` 的 UNIQUE 键是 **`dicom_study_uid` 单列**
> （实测约束名 `lnrs_anon_dicom_series_dicom_study_uid_key`，**不含 center/source**），
> 所以跨盘重复的 722 个 UID 在 dicom_series 里**只留一行** —— 该行的 byte/file/series_count
> 反映**最后被扫的那个盘的副本**（另一个盘的副本不体现）。这是既有表结构决定的，本批不改。
> 因此 V3 期望 ≈ 去重 UID 数（85,869），而 V2（imaging_study，UNIQUE 含 source）≈ 87,594。

### Step 7：commit + push

提交清单：

| 文件 | 改动 | 提交 |
|---|---|---|
| `scripts/build_disk1_disk2_disk4_imaging_study_index.py` | 新建（三盘统一递归扫描 + CSV 重建） | ✅ |
| `scripts/build_zhujiang_imaging_study_index_v2.py` | 新建（imaging_study 灌库 + patient 增量 + phi_audit + ingest_batch） | ✅ |
| `docs/etl2/verify_disk1_disk2_disk4_zhujiang_imaging.sql` | 新建（V1-V10 验证 SQL） | ✅ |
| `docs/etl2/plan-disk1-disk2-disk4-zhujiang-import.md` | 本文档 | ✅ |
| `backend/app/plugin/module_medical/hospital/anon_etl_engine.py` | `allow_null_exam` + `COALESCE`（issue-2 使能，已改） | ✅ |
| `backend/etl2/run_dicom_series_etl.sh` | `--allow-null-exam`（同上，已改） | ✅ |
| `docs/sour/ct_image_patient_map.csv` | **从 git 移除跟踪**（`git rm --cached`，磁盘文件保留）——含明文 PHI | ✅ |
| `.gitignore` | 新增 PHI 产物忽略规则（已改） | ✅ |

**不提交（方案 2：`.gitignore` 忽略）**——均可由脚本重新生成，且含 PHI：

| 文件 | 内容 | 状态 |
|---|---|---|
| `docs/sour/ct_image_patient_map.csv` | 10.4 MB；`patient_name`（明文姓名）/`patient_sex`/`patient_age`/`sick_id`/院内 PID | **已 `git rm --cached`**，磁盘保留 |
| `docs/sour/shengyi_imaging_study_patient_added.txt` | 3.2 MB；`source_patient_local_id`（院内 PID，如 `01010_P980295`） | **已 `git rm --cached`**，磁盘保留 |
| `docs/sour/ct_image_patient_map_v2.csv` | 本批产物；同 PHI 列 | 待生成，已被忽略 |
| `docs/sour/zhujiang_imaging_study_patient_added.txt` | 本批产物；院内 PID | 待生成，已被忽略 |
| `docs/sour/scan_skipped_dirs.txt` | 本批产物；目录名 | 待生成，已被忽略 |

`.gitignore` 新增规则（已生效，`git check-ignore` 验证 5 个路径全部 IGNORED）：
```
docs/sour/ct_image_patient_map*.csv
docs/sour/*_imaging_study_patient_added.txt
docs/sour/scan_skipped_dirs.txt
```

> ⚠️ **历史残留**：这两个文件的 PHI 仍在 git 历史提交里。`git rm --cached` 只停止后续跟踪，
> **不会**从历史中删除。彻底清除需 `git filter-repo` / BFG 重写历史 + 强制推送（破坏性，
> 影响所有协作者与 CI，需单独决策——已列入 §7-7）。

**不改动**：
- `backend/etl2/backfill_dicom_series_count.py`（Step 5 直接复用其 `--bypass-exam-fk`）
- `backend/etl2/backfill_imaging_study_exam_id.py`
- `backend/sql/postgres/*`（已有 0024 允许 anon_exam_id NULL）

---

## 4. 风险与缓解

| # | 风险 | 缓解 |
|---|---|---|
| R1 | ~~盘 4 zip_folder 命名不规范~~ → **已消解** | 新扫描口径（Step 2.1）用**统一递归匹配 `<PID>_<UID>` 目录名**，不再依赖 zip_folder 命名分类，盘 4 的 5 类命名差异无需特判。原「命名识别失败 → skip」逻辑随之删除 |
| R2 | 跨盘 / 盘内同一 StudyInstanceUID 重复 | 实测（§1.5.1）：盘内重复 UID disk1 321 / disk2 341 / disk4 4，**全部同 PID 打包重复** → `ON CONFLICT (patient_id, dicom_study_uid, source) DO NOTHING` 合并为 1 行（先到者胜，另一物理副本被忽略——若其中一个副本在离线盘上，存活行的 `image_path` 可能指向已下线的副本，属可接受）。跨盘重复 UID 722（d1∩d2 165 / d1∩d4 242 / d2∩d4 315），`source` 不同 → **保留两行**，各自 image_path 正确 |
| R3 | patient 发号：序列不推进 → 后续 PK 冲突 | ① 用 `nextval('lnrs.lnrs_anon_patient_seq')`（**不用 `MAX(patient_id)+1`**）；② `pg_advisory_xact_lock(hashtext('zhujiang_patient_seq'))` 事务级串行化；③ INSERT `ON CONFLICT (anon_id) DO NOTHING` 双保险。与 shengyi 模板、ETL2 引擎口径一致。<br>**量化（2026-09-19 实测）**：序列 `last_value=434,997`，`MAX(patient_id)=PT_00434929`（=434,929）——序列领先 68，说明当前无冲突。若改用 `MAX+1` 发 52,000 个号（PT_00434930…PT_00486929），序列仍停在 434,997，引擎下一次 `nextval` 返回 434,998 → 撞上已存在的 `PT_00434998` |
| R4 | image_path 不存在磁盘但仍 INSERT | 接受；由 `lnrs_anon_imaging_orphan` 审计链路捕获（0016 迁移已就绪） |
| R5 | CSV 中 pat_local_id 解析失败 | WARNING + skip；写入 `ct_image_patient_map_skipped.csv` |
| R6 | dicom_series 落库时单 study 失败 / 目录离线 | bypass 脚本单 study 容错（`failed` / `skipped_offline` 计数），不阻断；跑完看末尾汇总，`failed` >5% 则排查后重跑（幂等：`WHERE series_count IS NULL` 只补未实测行） |
| R7 | disk 满（h196_3 /var/lib/postgresql/18/main 99%） | skill 已记录 98G 卷 99% 满；建议先迁到 /data 或扩 vda3；本次需用户在跑前确认磁盘状态 |
| R8 | phi_audit strategy enum 范围与 `hmac` 值确认 | 见 §4.1 验证；`'hmac'` 已在 0006 §1 enum 中，不需要 ALTER TYPE |
| R9 | B 方案：dicom_series 与 exam 表无 FK 关联（业务查询受限） | 0024 已允许 NULL；视图正常；后续单独批次灌 zhujiang exam 后再 backfill |
| R10 | 占位 patient 与未来真实档案的「重复 PID 但 anon_id 不同」 | PID 都是数字（PAT_LOCAL_ID），院内同中心不冲突；如果发生冲突（极小概率），则 ETL2 patient kind 阶段会以 anon_id 命中复用 → 不重复发号 |
| R11 | 重跑导致 audit 重复 / ingest_batch 重复 | **已实测确认（2026-09-19）**：`lnrs_anon_phi_audit` 只有 `PRIMARY KEY (audit_id)`，**无任何 UNIQUE 约束** → `ON CONFLICT` 不可用，重跑必产生重复审计行。缓解：**Step 3 脚本在应用层用 set 缓存 `(batch_id, source_table, source_field, source_hash)` 四元组去重后再批量 INSERT**（这是唯一手段，不能依赖 DB 约束）。`ingest_batch` 每次新 UUID，天然可区分 |
| R12 | ETL2 CLI 必须设 `ENVIRONMENT=h196_3`（否则加载不到对应 env 文件） | **本机直接运行即可，不要加 ssh 前缀**：`h196_3` 不是远程主机，而是这台机器的环境名（10.12.196.3 = 本机 `ens3`；`deploy-h196_3.sh` 自称「本机部署脚本」；`run-h196_3.sh` 用 `REPO_ROOT=/home/dzy/wk/lnrs`）。ENVIRONMENT 只决定加载哪个 env 文件。ssh 的两个副作用：① 无 `-t` 时 `read -rp` 的提示不显示；② 非 tty 上下文（CI/脚本/自动化）下 `read` 返回 1，`set -e` 直接终止脚本（已实测 exit=1） |
| R13 | B 方案下 dicom_series.anon_exam_id 全 NULL；未来 zhujiang exam 灌库 + backfill 后需要把关联补上 | ① 本批 bypass 脚本的 `ON CONFLICT … WHERE series_count IS NULL` **不改 `anon_exam_id`**，故已写入的 NULL 不会被覆盖；② 后续用 `backfill_imaging_study_exam_id.py` 回填 imaging_study 后，需**另写 UPDATE 把 dicom_series.anon_exam_id 从 imaging_study 同步过来**（现有脚本不含此步）——已列入 §7 工单 |
| R14 | **`LNRS_DATA_ROOT` 守卫拦死 ETL2 CLI 的 dicom_series 路径**：`.env.h196_3` 的 `LNRS_DATA_ROOT=/home/dzy/wk/lnrs_dats` 不存在（2026-07-22 commit `a2a7c093` 起即为死路径），`run_center` 在 `data_dir.exists()` 为假时直接 `return failed`，`import_center` 从不被调用；**dry-run 只打印 `exists=False` 不报错，掩盖问题**（已实测复现） | **本批不受影响**（Step 5 走 bypass 脚本，不经过 `run_center`）。修复列入 §7 工单（issue-2 后续） |
| R15 | bypass 脚本复用「中心最新 batch UUID」作为 `created_batch_id`；若 Step 3 未先跑（无 zhujiang batch），脚本会 fallback 到**任意**中心的 batch，造成归属错误 | 执行顺序强制：Step 3 必须先于 Step 5；脚本日志首行打印 `使用 batch_id=…`，核对它等于 Step 3 输出的 batch UUID |
| R16 | **占位患者漏标 `is_placeholder`**：该列 `DEFAULT FALSE`（0018），INSERT 若省略则占位行被当成真实患者（shengyi 已踩：82,683 个 `sex='0'` 患者全部 `is_placeholder=FALSE`，2026-09-19 实测） | Step 3 的 INSERT **显式写 `is_placeholder=TRUE`**；V1 核对 `COUNT(*) FILTER (WHERE is_placeholder)` ≈ 本次新增数；shengyi 的历史漏标列入 §7 工单 |
| R17 | **沿用旧扫描口径会静默漏扫 4,363 个 study（5.0%）**：① 只认 `<YYYYMMDD>` 顶层目录 → 漏 4,026（disk1 的 `yd*`/`new*` 下 study 直挂）；② 要求 UID 以 `1.2.` 开头 → 漏 337（`1.3.46.670589.*` 厂商 OID 根）。已抽验三样本均为真实 CT（§1.5.2） | Step 2.1 改为**统一递归匹配**：不限顶层目录名、不限 UID 前缀；dry-run 与实测基线（27,131/19,710/40,416 + 337）比对，偏差 >1% 即报错退出 |
| R18 | 跨盘重复 UID 在 `dicom_series` 里只剩一行（UNIQUE 键是 `dicom_study_uid` 单列，不含 source）→ 该行只反映最后被扫的盘的副本 | 既有表结构决定，本批不改。V3 期望按去重 UID 数（85,869）而非 study 目录数（87,594）核对；imaging_study 侧不受影响（UNIQUE 含 source，两行都留） |

### 4.1 R8 验证（2026-09-19 已实测通过）

```bash
PGCLIENTENCODING='SQL_ASCII' PGPASSWORD='lnrs_pwd' psql -h 127.0.0.1 -U lnrs -d postgres -tAc "
SELECT enumlabel FROM pg_enum
WHERE enumtypid = 'lnrs.lnrs_anon_phi_strategy_enum'::regtype
ORDER BY enumsortorder;"
```

实测结果：`hmac` / `clear` / `partial_keep` / `llm_replace` / `manual_review` —— **`hmac` 存在，无需 ALTER TYPE**。
（同批实测 `lnrs_anon_source_kind_enum` 含 `dicom_dir`，Step 3 的 batch 写入可用。）

### 4.2 R11 验证（2026-09-19 已实测确认）

```bash
PGCLIENTENCODING='SQL_ASCII' PGPASSWORD='lnrs_pwd' psql -h 127.0.0.1 -U lnrs -d postgres -tAc "
SELECT c.relname||' | '||con.conname||' | '||pg_get_constraintdef(con.oid)
FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid
JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='lnrs' AND con.contype IN ('u','p')
  AND c.relname IN ('lnrs_anon_imaging_study','lnrs_anon_dicom_series','lnrs_anon_patient','lnrs_anon_phi_audit')
ORDER BY 1;"
```

实测结果：

| 表 | 约束 | 对计划的含义 |
|---|---|---|
| `lnrs_anon_imaging_study` | `lnrs_anon_uq_imaging_study` UNIQUE (patient_id, dicom_study_uid, source) | Step 3 的 `ON CONFLICT (patient_id, dicom_study_uid, source) DO NOTHING` ✅ 可用 |
| `lnrs_anon_dicom_series` | `lnrs_anon_dicom_series_dicom_study_uid_key` UNIQUE (dicom_study_uid) | Step 5 的 `ON CONFLICT (dicom_study_uid)` ✅ 可用 |
| `lnrs_anon_patient` | `lnrs_anon_patient_anon_id_key` UNIQUE (anon_id)；`lnrs_anon_uq_patient_center` UNIQUE (center_code, anon_id) | 发号的 `ON CONFLICT (anon_id) DO NOTHING` ✅ 可用 |
| `lnrs_anon_phi_audit` | **仅 `PRIMARY KEY (audit_id)`，无 UNIQUE** | ❌ `ON CONFLICT` 不可用 → 重跑必重复；**只能靠应用层 set 去重**（R11） |

另实测可空性（0024 生效）：`dicom_series.anon_exam_id` = YES、`imaging_study.anon_exam_id` = YES、
`imaging_study.created_batch_id` = YES —— B 方案与 C 方案的 NULL 语义均合法。

---

## 5. 数字预期对照表

### 5.1 行数预期

| 表 | 导入前 | 导入后 |
|---|---:|---:|
| `lnrs_anon_patient (zhujiang)` | 0 | ~60,217 |
| `lnrs_anon_imaging_study (zhujiang)` | 0 | ~87,594 |
| `lnrs_anon_imaging_study (shengyi)` | 82,994 | 82,994（不变） |
| `lnrs_anon_imaging_study (总计)` | 82,994 | ~170,600 |
| `lnrs_anon_dicom_series (zhujiang)` | 0 | ~85,869（= 去重 UID；扣除 `skipped_offline`） |
| `lnrs_anon_dicom_series (总计)` | 82,057 | ~167,900 |
| `lnrs_anon_phi_audit (本次 batch)` | - | ~87,594 |
| `lnrs_anon_ingest_batch (zhujiang, dicom_dir)` | 0 | 1 |

### 5.2 时间预期

> 规模比早期草稿大 27%（87,594 vs 68,944 study），Step 3/5 耗时按比例上调。

| 阶段 | 预计耗时 |
|---|---|
| Step 0 环境检查 | 1 min |
| Step 1 备份 | 2 min |
| Step 2 CSV 重建 dry-run | 30 s |
| Step 2 CSV 重建 apply | 5 min |
| Step 3 imaging_study dry-run | 1 min |
| Step 3 imaging_study apply | ~35 min |
| Step 4 backfill（B 方案跳过） | 0 min |
| Step 5.1 dicom_series dry-run | 30 s |
| Step 5.2 canary（200 条） | ~10 s |
| Step 5.3 dicom_series 正式跑 | ~40 min |
| Step 6 验证 SQL | 2 min |
| **合计** | **~2 小时** |

### 5.3 磁盘空间预期

- `ct_image_patient_map_v2.csv` ≈ 25 MB
- `lnrs_anon_patient (zhujiang)` 增量 ≈ 10 MB
- `lnrs_anon_imaging_study (zhujiang)` 增量 ≈ 25 MB
- `lnrs_anon_dicom_series (zhujiang)` 增量 ≈ 50 MB（不存像素，只存元数据 + byte_size 数字）
- `lnrs_anon_phi_audit (本次 batch)` 增量 ≈ 10 MB
- `lnrs_anon_ingest_batch` 增量 ≈ 4 KB
- **PG 侧总增量**：~120 MB
- **磁盘侧**：不复制 DICOM 文件，只读

---

## 6. 回退方案

| 阶段 | 回退命令 |
|---|---|
| Step 3 imaging_study 灌库失败 | `psql -f /tmp/pre_disk1_disk2_disk4_imaging_${TS}.sql`（恢复 patient + imaging_study + phi_audit + ingest_batch） |
| Step 5 dicom_series 失败/需要重来 | `DELETE FROM lnrs.lnrs_anon_dicom_series WHERE created_batch_id='<本次 batch_id>';`（本批 dicom_series 行与 imaging_study 行共用同一 batch UUID） |
| 全部回退 | 见下方脚本（按 batch_id 逐表删除，顺序：审计 → series → study → 孤立 patient → batch） |

回退脚本草稿（**本机执行，不要 ssh**；`PGPASSWORD` 走 `lnrs_pwd`）：

```bash
BATCH_ID=$(PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres -tAc \
  "SELECT batch_id FROM lnrs.lnrs_anon_ingest_batch
    WHERE center_code='zhujiang' AND source_kind='dicom_dir'
    ORDER BY started_at DESC LIMIT 1")
echo "回退 batch_id: $BATCH_ID"

PGPASSWORD=lnrs_pwd psql -h 127.0.0.1 -U lnrs -d postgres -v ON_ERROR_STOP=1 <<EOF
DELETE FROM lnrs.lnrs_anon_phi_audit      WHERE batch_id        = '$BATCH_ID';
DELETE FROM lnrs.lnrs_anon_dicom_series   WHERE created_batch_id = '$BATCH_ID';
DELETE FROM lnrs.lnrs_anon_imaging_study  WHERE created_batch_id = '$BATCH_ID';
DELETE FROM lnrs.lnrs_anon_patient
 WHERE created_batch_id = '$BATCH_ID'
   AND NOT EXISTS (SELECT 1 FROM lnrs.lnrs_anon_imaging_study s
                    WHERE s.patient_id = lnrs.lnrs_anon_patient.patient_id);
DELETE FROM lnrs.lnrs_anon_ingest_batch   WHERE batch_id        = '$BATCH_ID';
EOF
```

---

## 7. 后续工单（不在本批次）

1. **ETL2 CLI 的 dicom_series 路径修复**（issue-2 核心）——本批绕开了它，但它仍是设计路径：
   - 修 `data_root` 守卫：`.env.h196_3` 的 `LNRS_DATA_ROOT=/home/dzy/wk/lnrs_dats` 不存在，导致 `run_center` 直接 failed（R14）。要么创建该目录、要么给 `run_dicom_series_etl.sh` 加 `--data-root` 透传、要么放宽守卫
   - 修 `_create_batch` 硬编码 `source_kind="csv_report"`（`anon_etl_service.py:63`）→ 应按调用方传参
   - 修 `backfill_dicom_series_count.py:218` 的 `anon_exam_id=row.anon_exam_id or ""`（NULL 传空串 → FK 违反）
   - 然后用 `--allow-null-exam`（已就绪）跑一次，与 bypass 脚本结果交叉校验
2. **zhujiang exam 灌库 + backfill**：把 `nodule_imaging.parquet`（如果有 2025-09 重抽版）灌库后，用 `backfill_imaging_study_exam_id.py` 回填 imaging_study.anon_exam_id；**再另写 UPDATE 把 `dicom_series.anon_exam_id` 从 imaging_study 同步过来**（现有脚本不含此步，见 R13）
3. **patient 占位 → 真实档案**：ETL2 patient kind 后续批次如有真实人口学，upsert 会替换 sex='0' 占位（引擎侧 `is_placeholder` 会随记录类型翻回 False）
4. **shengyi 占位漏标修复**（R16 的存量）：`lnrs_anon_patient` 中 shengyi 有 **82,683 个 `sex='0'` 患者 `is_placeholder=FALSE`**（离线脚本漏写该列）。修复：
   ```sql
   UPDATE lnrs.lnrs_anon_patient SET is_placeholder = TRUE
    WHERE center_code='shengyi' AND sex='0' AND NOT is_placeholder
      AND birth_date IS NULL AND ethnicity IS NULL AND smoking_status IS NULL
      AND abo_blood_type IS NULL AND rh_blood_type IS NULL
      AND native_place IS NULL AND first_nodule_date IS NULL AND bmi IS NULL;
   ```
   （与 0018 的回填规则同口径；`build_shengyi_imaging_study_index.py` 也应补上该列，避免重跑再漏）
5. **扫描跳过清单 review**：`docs/sour/scan_skipped_dirs.txt`（深度超限 / 目录名不匹配）人工核对
6. **h196_3 → 1.59（h42）同步**：本次 zhujiang 影像数据落地后，按 `scripts/migrate_dev_to_h59_zhujiang0814.sh` 模式扩展，搬运 `lnrs_anon_imaging_study / lnrs_anon_dicom_series / lnrs_anon_phi_audit` 三张表到 192.168.1.59（可选）
7. **git 历史中的 PHI 清除**（方案 2 的遗留）：`docs/sour/ct_image_patient_map.csv`（明文姓名）与
   `docs/sour/shengyi_imaging_study_patient_added.txt`（院内 PID）虽已 `git rm --cached`，
   但其内容仍存在于历史提交中。彻底清除需 `git filter-repo --path <file> --invert-paths`
   或 BFG + 强制推送（**破坏性**：改写所有 commit hash，影响协作者、CI、已克隆的工作区）。
   需单独决策，不在本批范围。

---

## 8. 变更文件清单

| 文件 | 改动 |
|---|---|
| `scripts/build_disk1_disk2_disk4_imaging_study_index.py` | 新建（~300 行；三盘统一递归扫描 + CSV 输出） |
| `scripts/build_zhujiang_imaging_study_index_v2.py` | 新建（~400 行；imaging_study + patient + phi_audit + ingest_batch 灌库） |
| `docs/etl2/verify_disk1_disk2_disk4_zhujiang_imaging.sql` | 新建（~80 行；V1-V10 验证 SQL） |
| `docs/etl2/plan-disk1-disk2-disk4-zhujiang-import.md` | 新建（本文档） |
| `docs/sour/ct_image_patient_map.csv` | **`git rm --cached`**（含明文 PHI；磁盘文件保留供对照） |
| `.gitignore` | 新增 PHI 产物忽略规则 |
| `docs/sour/ct_image_patient_map_v2.csv` | 生成但不提交（被忽略；含明文 PHI） |
| `docs/sour/zhujiang_imaging_study_patient_added.txt` | 生成但不提交（被忽略；含院内 PID） |
| `docs/sour/scan_skipped_dirs.txt` | 生成但不提交（被忽略；含目录名） |

**已改动**（2026-09-19；issue-2 使能修复，本批不依赖）：
- `backend/app/plugin/module_medical/hospital/anon_etl_engine.py` — `_import_dicom_series_for_center` 加 `allow_null_exam`；`_upsert_dicom_byte_size_for_study` 的 `anon_exam_id: str | None` + `COALESCE` 保护
- `backend/etl2/run_dicom_series_etl.sh` — 新增 `--allow-null-exam`（自动 export `LNRS_DICOM_ALLOW_NULL_EXAM`）

**不改动**：
- `backend/etl2/backfill_dicom_series_count.py`（Step 5 直接复用其 `--apply --bypass-exam-fk`；其已知缺陷见 §7-1）
- `backend/etl2/backfill_imaging_study_exam_id.py`
- `backend/sql/postgres/*`（已有 0024 允许 anon_exam_id NULL）
- `scripts/build_image_patient_map.py` / `scripts/build_imaging_study_index.py`（保留兼容；新功能由 v2 脚本承担）

---

## 9. 与既有文档的关系

- **复用**：
  - `scripts/build_shengyi_imaging_study_index.py` 的灌库模式（patient FK 反查 → advisory_xact_lock 发号 → patient_added 列表 → `source_kind='dicom_dir'` batch 写法）
  - `scripts/build_image_patient_map.py` 的 **CSV 字段定义**与路径常量（**但不复用其扫描口径**——固定深度 + `YYYYMMDD`-only + `1.2.` 前缀，会漏 4,363 个 study，见 §1.5.2）
  - **`backend/etl2/backfill_dicom_series_count.py --apply --bypass-exam-fk`（Step 5 直接用；shengyi 已实证 82,057 行 / 16.2 TB）**
  - `docs/etl2/plan-shengyi-CT-image-import.md` 的方案结构（数据现状 → 字段映射 → 步骤 → 风险 → 回退）
  - `docs/etl2/verify_shengyi_imaging_study.sql` 的验证 SQL 模板
- **差异**：
  - 范围更广（盘 1+2+4 vs shengyi 仅 06+07 disk parquet），规模 87,594 study vs shengyi 82,153
  - 含 `phi_audit` 与 `ingest_batch` 一致化（shengyi plan 未涉及）
  - **扫描口径重写**（统一递归匹配，不限顶层目录名与 UID 前缀；盘 4 的命名差异不再需要特判）
  - Step 5 走 bypass 脚本而非 ETL2 CLI（P0-2 决策，见 §0）
  - B 方案：backfill 推迟到 zhujiang exam 灌库之后
- **对既有脚本的反哺**（§7 工单）：
  - `scripts/build_image_patient_map.py` / `build_imaging_study_index.py` 的扫描口径有漏扫（R17），
    若要重跑旧路径需同步修；
  - `scripts/build_shengyi_imaging_study_index.py` 缺 `is_placeholder`（R16）。
- **与 PRD/Issue 关联**：
  - 推进 `docs/etl2/prd/PRD.md`「medicalFiles 页面显示真实文件总大小」（Step 5 落 byte_size 后视图 total_bytes 非零）
  - `docs/etl2/prd/issue-2-run-dicom-series-etl.md`：**本批不等同于 issue-2 的验收**——issue-2 要求走 `run_dicom_series_etl.sh --apply`，本批绕开它（见 §7-1 后续工单）
  - `docs/etl2/prd/issue-4-investigate-shengyi-exam-gap.md`：zhujiang 方向的同类问题（exam 表空缺）
