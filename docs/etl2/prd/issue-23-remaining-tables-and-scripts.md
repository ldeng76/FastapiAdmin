# Issue 23: 其余 3 张表接入 promote + 另两个 ad-hoc 脚本切换

## Parent

[事故复盘：测试清理按 center_code 级联删除 168,260 行 dicom_series](../findings/incident-20260920-test-cascade-delete.md)（§10 → 「先暂存再上」）

## What to build

Issue 20 只打通了 `dicom_series`。本 issue 把**其余 3 张表**接入同一套
「写 stage → 校验 → promote」，并把**剩下两个 ad-hoc 脚本**切过去。
做完这一片，「脚本直写生产」这个风险面才算关掉。

**涉及的 4 张表与 FK 顺序**（实测，来自 `pg_constraint`）：

```
lnrs_anon_patient         ← 无父（但 created_batch_id/last_seen_batch_id 在 live 库无 FK）
  └─ lnrs_anon_exam         (patient_id → patient)
       └─ lnrs_anon_imaging_study  (patient_id → patient)
            └─ lnrs_anon_dicom_series (anon_exam_id → exam, created_batch_id → ingest_batch)
lnrs_anon_ingest_batch    ← 批次锚点（dicom_series.created_batch_id 的 CASCADE 父表）
```

promote 必须按此顺序，否则外键会失败。

**要切换的两个脚本**：

- `backend/etl2/_issue13_ingest_xinqiao_ct_exam.py`（写 `exam` / `dicom_series` / `imaging_study`）
- `backend/etl2/_issue6_ingest_zhujiang_ct_exam.py`（写 `exam` / `imaging_study`）

**端到端行为**：三个 ad-hoc 脚本各自跑一次，**生产库在 promote 之前完全不变**；
promote 之后生产库出现预期行；三个脚本的 promote 顺序满足上面的 FK 依赖。

## Acceptance criteria

- [ ] `lnrs.lnrs_stage_patient` / `lnrs.lnrs_stage_exam` / `lnrs.lnrs_stage_imaging_study`
      三张 stage 表存在，列结构与对应生产表一致
- [ ] `_issue13_ingest_xinqiao_ct_exam.py` 与 `_issue6_ingest_zhujiang_ct_exam.py`
      **不再直写生产表**，改为写 stage
- [ ] **真库不变断言**（三个脚本各一次）：脚本跑完后
      `patient` / `exam` / `imaging_study` / `dicom_series` 四表行数与
      `pg_stat_user_tables` 计数**逐字节相同**
- [ ] **FK 顺序断言**：promote 按 `patient → exam → imaging_study → dicom_series` 执行；
      违反顺序时**报错而不是静默跳过**
- [ ] **完整性断言**：promote 后
      `SELECT COUNT(*) FROM lnrs_anon_imaging_study s WHERE NOT EXISTS (SELECT 1 FROM lnrs_anon_patient p WHERE p.patient_id = s.patient_id)`
      返回 **0**；`dicom_series` 对 `ingest_batch` 的孤儿引用同样返回 **0**
- [ ] **幂等断言**：三个脚本 + promote 全跑完后，再 promote 一次，四表行数不变
- [ ] 复用 Issue 22 的校验闸与审计：每次 promote 都有审计记录
- [ ] 在测试沙箱（`ENVIRONMENT=test`）上跑通；沙箱上既有失败用例数**不增加**
- [ ] 不改变三个脚本各自的业务语义（关联算法 / 计算口径）—— 本 issue 只改**写入目标**

## Blocked by

- [Issue 20](./issue-20-dicom-series-stage-and-promote.md)（同一套 stage+promote 机制）
- [Issue 22](./issue-22-promote-guardrails.md)（表变多 → 失败面变大 → 护栏必须先到位）

## Notes for implementer

- **别一次改四张表**。按 FK 顺序一张一张来，每张跑通「真库不变 → promote → 可见 → 幂等」再下一张。
- `_issue13_ingest_xinqiao_ct_exam.py` 已经有 `[SERIES] dicom_series.anon_exam_id 回填` 这类步骤，
  改写入目标时注意**别把「写 stage」和「读生产」混了** —— 关联算法需要读生产数据，
  但**结果要写 stage**。
- 该脚本目前会建 `lnrs_tmp_issue13_series_before` 之类的中转表（实测库里还留着）。
  迁到 stage 机制时顺手评估这些中转表是否还需要。
- 参考：`backend/etl2/README.md` 的回退一节；复盘 §3.1（**级联范围查 live `pg_constraint`，不读 DDL**）。