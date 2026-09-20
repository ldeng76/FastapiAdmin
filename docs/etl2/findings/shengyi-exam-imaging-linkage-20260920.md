# 省医 exam 世界 × 影像世界关联调研 — 报告（219/82,988 脱节根因）

> **Issue**: docs/etl2/prd/issue-29-shengyi-exam-imaging-linkage.md
> **执行日期**: 2026-09-20
> **执行环境**: h196_3 本地 PostgreSQL + 源 parquet（只读，全程 `write=0`）
> **结论一句话**: 219 个交集患者是「DICOM 目录名 == HIS 患者号」的真实同值匹配（非哈希碰撞、非人工映射）；
> 纯影像人群的 DICOM header（PatientID / AccessionNumber）与 HIS ID 空间**正交，无任何可用桥接键** →
> 走 **不可关联分支**：根因文档化 + UI 标注落地（患者列表「影像占位」badge，本 commit 同步交付）。

---

## 1. 219 个交集患者的解剖（AC-1）

### 1.1 两侧灌库来源

| 侧 | batch / source | 灌库时间 | 219 中覆盖 | 说明 |
|---|---|---|---|---|
| exam 侧 | `f83cc91b-0956-43da-b23e-29885e91cff6`（ETL-2 主灌库） | 2026-09-02 | 219/219 | 9 类 exam 行（pathology 755 / radiology 571 / ultrasound 522 / CT 472 / ECG 331 / MRI 127 / imaging_report 12 / nuclear_medicine 11 / bronchoscope 10） |
| imaging 侧 | `disk_06_shengyi`（208 人）+ `disk_07_shengyi`（11 人），batch `913e071d` | 2026-09-14 | 219/219 | `build_shengyi_imaging_study_index.py` 离线目录扫描 |

patient 表属性：219/219 `is_placeholder=f`，且 **0/219** 满足 issue-9 占位判据（sex='0' 且人口学全空）
——他们是有完整 HIS 档案的真实患者，恰好也出现在 DICOM 目录名空间。

### 1.2 匹配机制（关键推理链）

1. 灌库脚本 `scripts/build_shengyi_imaging_study_index.py` 的 raw patient_id **就是 DICOM 目录第一级目录名**
   （如 `03373-3`、`10000404`），不是 header 值——parquet `dir_path` 与 `patient_id` 逐行核对确认。
2. 匿名化是确定性 HMAC-SHA256(secret, "shengyi:pid")[:12]，48-bit 截断。
   83k × 67k 两个 ID 空间随机碰撞期望 ≈ 0.02 个，**219 不可能是哈希巧合**。
   → PG 里的 219 匹配只能来自「两侧 raw ID 字符串相同 + 灌库时密钥一致」。
3. 独立于密钥的 raw 层证据（DuckDB 对源 parquet，issue-4 已测、本次复算一致）：
   DICOM 82,988 raw pid ∩ `imaging_report.parquet` = **205**，∩ `patient.parquet` = **306**，
   ∩ `diagnosis`/`visit_record` = 306 —— 同值 ID 在源数据层面真实两侧存在。
4. **密钥轮换旁证**：用当前 `LNRS_ANON_SECRET`（现为开发占位密钥）重算两侧 raw pid 的 anon_id，
   对 219 的 anon_id 命中 0/219 —— 说明 2026-09 灌库时使用了另一个密钥、之后被轮换。
   这不影响结论 2/3（密钥内部一致性 + raw 层同值证据独立成立）。

**结论**：219 = 「目录名撞上 HIS ID 空间」的真实同值患者。谁灌的：exam 侧 ETL-2 主灌库
（`f83cc91b`，09-02）+ imaging 侧离线目录灌库（`913e071d`，09-14）；匹配键：raw 患者号字符串本身。

## 2. header ID 审计（AC-2，n=150）

抽样方法：`shengyi_06_disk_CT.parquet` 52,991 个 (patient_id, dir_path) 随机洗牌，取前 150 个可读
DICOM 文件，`pydicom` 只读 header；**header 全程仅驻内存，落盘只留统计数与形态**（issue-14 同款 PHI 纪律）。

| 类别 | 计数 |
|---|---:|
| header PatientID == 目录名（灌库键） | **147** |
| header PatientID != 目录名 | **3** |
| header PatientID 空 | **0** |

替代键命中情况：
- header PatientID 落在 HIS ID 空间（patient/imaging_report/lab/visit 四表并集）：**1/150**（即交集型患者本身）。
- **AccessionNumber**：150/150 存在，但对 HIS `imaging_report.parquet` 的
  `patient_id` / `visit_id` / `report_id` 三列命中 **0/150**。

| 匹配 | 不匹配 | header 空 |
|---:|---:|---:|
| 147 | 3 | 0 |

**结论**：设备工作列表/目录名 ID 与 HIS ID 是两套正交编号体系；header 内不存在
住院号/门诊号/AccessionNumber 等可桥接的替代键。issue-14 的"zhujiang 100/100 对账"在省医
没有对应物——省医 RIS 未把 HIS 患者号写入 PACS header。

## 3. 结论分流（AC-4）

按 PRD 三步分流：**不可关联**（header 空间正交、AccessionNumber 0 命中、无外部映射表）。

- 修数据的唯一路径仍是 issue-4 路线 4.1：**依赖上游**（省医信息科提供 dicom_pid → his_pid 映射表）。
  若未来拿到映射，走 issue-20/22/23 stage+promote 体系回填，不直写生产——本次不产出回填 PRD。
- 即刻落地 = issue-4 路线 4.2 的 UI 标注（本 commit 交付）：
  患者列表 `patient_id` 列对 `is_placeholder=TRUE` 行渲染「影像占位」badge，
  tooltip 说明"影像灌库建档、与 HIS 临床/检查数据不可关联、无检查记录属数据源事实"（issue-29）。
  数据列 `is_placeholder` 后端本就下发（`patient_controller.py:200` 出参注释即为此用途），零后端改动。

## 4. write=0 断言（AC-5）

探针复放前后 `pg_stat_user_tables` 全部 `lnrs_anon_*` 表的
`n_tup_ins / n_tup_upd / n_tup_del / n_tup_hot_upd` 逐行 diff = **NONE**（零写入）。
全程仅 SELECT（psql）与只读文件访问；HMAC 重算在进程内存完成。

## 5. 对其他 issue 的影响

- **issue-28**：关联失败的结论固化了 exam 口径人群不会扩大 → medicalFiles 的 KPI 标签措辞
  按 issue-28 既定方案执行即可，无需为"未来回填"预留。
- **issue-9**：82,682 占位翻 TRUE 的语义冲突（复盘 §11.7 问题 2）不在本 issue 范围，但本报告
  确认了"占位 = 无 HIS 档案对应"的语义在省医是**事实正确**的，供语义统一讨论引用。
- **新桥互参**：xinqiao 有 `3_cxf_archives` 外部映射可走 ct_mapped（issue-24）；省医**没有**
  类似映射表，两中心不可套用同一流程。

## 6. 参考

- 前置调研：`docs/etl2/findings/shengyi-exam-gap-20260920.md`（issue-4）
- 复盘 §11.7：`docs/etl2/findings/incident-20260920-test-cascade-delete.md`
- 方法论：`docs/etl2/prd/issue-14-zhujiang-study-uid-audit.md`
- 灌库脚本：`scripts/build_shengyi_imaging_study_index.py`
- UI 标注落点：`frontend/web/src/views/module_medical/patient/index.vue`（patient_id 列槽渲染）
