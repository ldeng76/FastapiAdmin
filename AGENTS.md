<!-- CODEGRAPH_START -->
## CodeGraph

In repositories indexed by CodeGraph (a `.codegraph/` directory exists at the repo root), reach for it BEFORE grep/find or reading files when you need to understand or locate code:

- **MCP tool** (when available): `codegraph_explore` answers most code questions in one call — the relevant symbols' verbatim source plus the call paths between them, including dynamic-dispatch hops grep can't follow. Name a file or symbol in the query to read its current line-numbered source. If it's listed but deferred, load it by name via tool search.
- **Shell** (always works): `codegraph explore "<symbol names or question>"` prints the same output.

If there is no `.codegraph/` directory, skip CodeGraph entirely — indexing is the user's decision.
<!-- CODEGRAPH_END -->

## 语言

本项目一律使用简体中文交流：

- 与用户的所有对话、提问、状态更新、总结、提交信息、错误说明一律用中文。
- 工具调用之间的进度提示也用中文。
- 代码内的标识符、字符串、日志、API 字段名保持英文，不要翻译。
- 注释可使用中文，但若该注释贴近代码语义，优先英文以保持可检索性。

## Python 环境

跑本项目的 Python 代码（含一次性脚本、ad-hoc 命令、xlsx/duckdb/SQLAlchemy/ETL2 等导入）统一使用 `backend/` 下的 uv 虚拟环境：

```bash
cd /home/dzy/wk/lnrs/backend && uv run python ...
```

- **不要**用系统 `/usr/bin/python3`（缺本项目依赖）。
- **不要**用 `pip install` / `uv pip install` 临时装包——`backend/.venv` 已包含 openpyxl 3.1.5、duckdb 1.2.2、SQLAlchemy、asyncpg、FastAPI 等全部本项目依赖。
- **不要**用 `PYTHONPATH=` 注入其他 venv——直接进 backend 目录调 `uv run` 即可。
- 写进 `backend/` 目录的 Python 脚本若需要 ETL2 / SQLAlchemy 导入，shebang 用 `#!/usr/bin/env -S uv run python` 让脚本本身自动用 backend venv。
