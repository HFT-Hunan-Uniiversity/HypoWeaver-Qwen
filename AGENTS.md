# AGENTS.md（HypoWeaver v2）

- 产品规格见 `docs/SPEC.md`，任务清单见 `docs/PLAN.md`。冲突时以 SPEC 为准；不确定的地方在 PR 描述里提问，不要自行扩大范围。
- 早期在分支 `v2` 上开发；当前演示版本在分支 `ui-merged`（不要覆盖用户的前端改动）。每个任务一个或多个小提交，提交信息格式为 `T<编号>: <动词开头的说明>`。不要强推，也不要改写已推送的历史。
- 运行方式：
  - 后端：`cd backend && uv sync && uv run uvicorn hypoweaver.app:app --reload`
  - 前端：`cd frontend && npm i && npm run dev`
  - 测试：`cd backend && uv run pytest`；`cd frontend && npm run build`
- 密钥只放在环境变量或本地 `.env` 中（已 gitignore）：`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`、`CONTACT_EMAIL`（大模型为 DashScope Qwen 的 OpenAI 兼容接口）。不要提交数据文件、`var/` 或 `.env`。
- 禁止：
  - 演示旁路、硬编码结果、前端 mock 数据源；
  - 写死模型名；
  - 哈希清单、冻结门、预算门；
  - 为假想故障堆叠回退逻辑（失败就显示清楚的错误）。
- 数字只由代码产生。大模型输出必须经过 Pydantic 校验，引用的证据 ID 必须校验存在。
- 测试只测高层接缝：统计引擎、结论评估、API 主流程（假 LLM）、数据导入。不追求覆盖率。
- 保持模块接口小、实现深。单个文件超过约 600 行时考虑拆分。
