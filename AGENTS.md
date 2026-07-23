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
