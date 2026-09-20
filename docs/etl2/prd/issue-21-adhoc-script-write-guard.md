# Issue 21: ad-hoc 执行脚本的安全闸 —— 写生产表必须显式确认

## Parent

[事故复盘：测试清理按 center_code 级联删除 168,260 行 dicom_series](../findings/incident-20260920-test-cascade-delete.md)（§7.4 / §10）

## What to build

**用比「独立 stage 数据库」低一个量级的成本，拿到「脚本不能悄悄写生产」这个能力。**

事故复盘给出的结论是「隔离要么靠机制、要么靠纪律」，而纪律会失效
（本仓已有两例清理泄漏实证）。已落地的**测试沙箱**（`lnrs_dev` + `_db_guard`）解决的是
「测试」这一类；本 issue 解决**另一类**：`backend/etl2/` 下的**一次性/执行型脚本**。

现状：`backfill_dicom_series_count.py`、`_issue13_ingest_xinqiao_ct_exam.py`、
`_issue6_ingest_zhujiang_ct_exam.py` 等脚本带着 `--apply` 就能直接改生产库
（`lnrs.lnrs_anon_patient` / `_exam` / `_imaging_study` / `_dicom_series`），
**没有任何「你确定要写生产吗」的闸**，也没有把目标库名打出来。

**端到端行为**：写生产表的执行型脚本在被调用时必须**显式声明目标**（例如
`--target production` 或确认目标库名），否则**拒绝执行并退出非 0**；
脚本启动时**打印目标库 / 目标表 / 预计影响行数**。

## Acceptance criteria

- [ ] 存在一个可复用的闸（函数或装饰器），供 `backend/etl2/` 下的执行型脚本调用
- [ ] 未显式声明目标时，脚本**拒绝执行**、退出码非 0、错误信息说明如何显式声明
- [ ] 脚本启动时打印：**目标库名 + 目标 schema + 将写入的表 + 预计影响行数**
      （预计行数尽量来自各自的 `--dry-run`，做不到则打印「未知」而不是假装知道）
- [ ] **至少** `backfill_dicom_series_count.py`、`_issue13_ingest_xinqiao_ct_exam.py`、
      `_issue6_ingest_zhujiang_ct_exam.py` 三个脚本接入
- [ ] 明确**豁免面**：ETL 主路径（`anon_etl_engine` / `anon_etl_service` 被 API 调用）
      不受本闸影响 —— 否则会打断线上流程。豁免理由写进代码注释
- [ ] 沙箱环境（`DATABASE_NAME='lnrs_dev'`）下不要求显式声明（沙箱本身就是安全的），
      但**仍打印目标库名**
- [ ] 有测试覆盖「未声明 → 拒绝」「已声明 → 放行」两条路径
- [ ] 不动 `tests/anon_etl/_db_guard.py` 的既有语义（那个面向 pytest，本 issue 面向脚本）

## Blocked by

None - can start immediately.

## Notes for implementer

- **别做成一个「正则检查 SQL 里有没有 DELETE」的静态门** —— 复盘 §7.3 已论证那类门
  挡不住同类变体（`UPDATE` / `WHERE patient_id IN (...)` / f-string 拼语句），
  且产生「规则通过」的错觉。要的是**行为式**：目标库名 + 显式确认。
- 与既有约束的对齐：`backend/etl2/run_dicom_series_etl.sh` 已有 `--allow-null-exam`
  之类的前置开关习惯，本闸可以沿用同一种「不给 flag 就不动」的形状。
- 本 issue 与 Issue 20/22/23 正交：那几片是「把写入搬到 stage」，本片是「给仍在直写的路径加闸」。
  两者都做才算「脚本不能再悄悄写生产」。