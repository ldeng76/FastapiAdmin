# anon 链路联调骨架（HTTP e2e）

本目录下的 `anon_e2e_smoke.py` 是 **anon ETL 链路**的端到端联调骨架脚本，通过纯 HTTP（不依赖 backend Python 模块导入）打通：

```
登录 → 触发 anon 导入 → 轮询 Redis 状态 → 查 anon 数据摘要 → 患者 API 探针
```

## 适用背景

| 背景 | 说明 |
|------|------|
| **链路** | anon ETL（parquet → lnrs_anon_*） |
| **取代对象** | 旧 ETL-1（Excel → med_* 中间层）+ 旧 ETL-2（med_* → lnrs_anon_*） |
| **批次 5 后状态** | `module_medical/controller.py` 已删，前端 `patient.ts` 调用的 3 个路由（`/medical/centers`、`/medical/patients`、`/medical/patients/{id}`）会 404，脚本会**探测并报告**这一现状 |
| **当前活跃路由** | 医院管理 10 条：`/medical/hospital/*` + `/import/anon`、`/import/anon/status`、`/anon-data-summary`、`/online`、`/offline` + 统计路由 |

## 前置条件

- 已执行 alembic upgrade head（dev 库）
- 已执行 `initialize.py`（dev 库种子 admin/123456 存在）
- 后端可访问：`http://127.0.0.1:8610`（或自定义）
- 样例 parquet 存在：`docs/demodata/0723_珠江sample_pq/`（含 6 张：patient.pq / nodule_imaging.pq / pathology_specimen.pq / ihc_result.pq / genetic_test.pq / surgery_record.pq）
- Redis 可访问（后端 `REDIS_HOST=localhost` + `REDIS_PORT=6379`）
- 依赖：`requests`（已预装，`requests==2.34.2`）

## 使用

```bash
# 1) 启动后端（dev 库，新窗口）
cd backend
uv run python main.py run --env=dev
# 或用 dev.ps1 start

# 2) 跑联调骨架（默认参数）
cd backend
uv run python scripts/anon_e2e_smoke.py

# 自定义参数
uv run python scripts/anon_e2e_smoke.py \
    --base-url http://127.0.0.1:8610 \
    --username admin --password 123456 \
    --hospital-id 1 \
    --data-dir ../docs/demodata/0723_珠江sample_pq \
    --centers zhujiang \
    --timeout 120

# 跳过步骤 5 的患者 API 探针
uv run python scripts/anon_e2e_smoke.py --skip-probe
```

## 步骤说明

| 步骤 | 内容 | 期望 |
|------|------|------|
| **0** | 前置检查：data_dir 存在、health 端点 | data_dir 必须存在；health 可 503 |
| **1** | OAuth2 登录 `/system/auth/login` | 200 + access_token |
| **2** | 触发 `/medical/hospital/{id}/import/anon` | 200 + `{job_id, status: pending}` |
| **3** | 轮询 `/medical/hospital/{id}/import/anon/status` | `status=completed` 且 `processed>0` |
| **4** | 查 `/medical/hospital/{id}/anon-data-summary` | `total_rows > 0`，7 张表都有数据 |
| **5** | 探针 `/medical/centers` `/medical/patients` `/medical/patients/{id}` | **批次 5 后预期 404**，提示需补 PatientService 路由 |

退出码：
- `0` = 步骤 1-4 全部通过
- `1` = 任一步骤失败（CI 友好）

## 与前后端的关系

```
frontend/web/src/api/module_medical/patient.ts     → /medical/centers, /medical/patients  ← 步骤 5 探针（404）
frontend/web/src/api/module_medical/hospital.ts    → /medical/hospital/*              ← 已对接 anon
backend/app/plugin/module_medical/hospital/         → anon_query.py / anon_etl_* / anon_medical_query
backend/app/plugin/module_medical/                 → module_medical/{controller,service,schema}.py 已删
```

后续 TODO：
1. **补 PatientService 路由**（最简方案：3 条路由直接挂在 `hospital/controller.py` 上，调用 `anon_medical_query.py` 的 3 个函数即可）
2. 抽取 `useDict` composable 替换前端硬编码翻译函数
3. 把 `patient.ts` 的 `gender` / `source_center` 历史命名清理（已改 anon 字段名）