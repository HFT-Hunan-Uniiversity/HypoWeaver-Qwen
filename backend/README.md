# HypoWeaver 后端

FastAPI + SQLite（SQLAlchemy），Python 3.12，依赖用 uv 管理。整体说明见根目录 [README](../README.md)，接口细节见 [docs/API_NOTES.md](../docs/API_NOTES.md)。

## 运行

```sh
uv sync
uv run uvicorn hypoweaver.app:app --reload --port 8000
```

配置从仓库根目录 `.env`、环境变量和 `DATA_DIR/.env.llm`（设置页保存，优先级最高）读取，配置项定义在 `hypoweaver/config.py`：`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`、`CONTACT_EMAIL`、`DATA_DIR`、`LOCAL_LIBRARY_DIR`。健康检查：`GET /api/health`。

## 模块

| 目录 | 作用 |
|---|---|
| `projects/` | 项目增删改查、总览与阶段状态 |
| `jobs.py` `staleness.py` | 后台任务；上游修改后标记下游过期 |
| `llm/` | 大模型配置（`/api/settings/*`）与调用：OpenAI SDK → DashScope 兼容模式，输出经 Pydantic 校验 |
| `literature/` `landscape/` | OpenAlex/Crossref 联合检索、PDF 解析、本地文献库、文献概况 |
| `candidates/` `plans/` | 候选假设、研究方案（方法族：policy_causal / panel_association / mechanism_boundary） |
| `datasets/` `binding/` | 数据导入（csv/xlsx/dta）、字段语义、变量绑定、就绪检查 |
| `stats/` | 主模型、事件研究、稳健性、置换检验（默认 499 次）、独立复算 |
| `claims/` | 结论评估与强度上限、措辞校验 |
| `proposal/` | 十项提案生成、渲染、确认（`POST /api/proposals/{id}/confirm`）与 Markdown 导出 |
| `cases/` | `carbon.py` 碳市场数据 fetch/prepare；`legacy.py` 旧案例（`case` 以 `legacy:` 开头）只读标记 |

## 测试

```sh
uv run pytest -q
```

测试一律使用临时数据目录，不会碰真实 `var/`。依赖真实碳市场数据的 2 项测试在没有登记数据时会自动跳过。
