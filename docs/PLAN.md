# 02 v2 执行计划（给 CodeX）

> 状态：定稿（2026-10-12），可交付 CodeX 执行。

> 先读 `01_HypoWeaver_v2_SPEC.md`（下文简称 SPEC），领域背景见 `00_旧项目蒸馏_项目参考.md`。
> 本计划按“纵向切片”排序：每个任务完成后，应用都能跑起来，并且可以亲眼验证。

## 0. 工作方式

- **仓库与分支**：`HFT-Hunan-Uniiversity/HypoWeaver-Qwen`。从空树创建孤儿分支 `v2`：

  ```bash
  git checkout --orphan v2
  git rm -rf .
  ```

  旧代码只在 `main` 上参考，不要复制大段代码。
- **提交**：信息格式为 `T<编号>: <说明>`；每个任务结束时应用可以运行、测试通过。通过 PR 合入 `v2`，或直接推送到 `v2`，由架构师决定。
- **环境**：Python 3.12（用 uv 管理），Node 22。
- **环境变量**（本地 `.env`，不提交；仓库内提供 `.env.example`）：

  ```
  DASHSCOPE_API_KEY=
  QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
  QWEN_MODEL=qwen-plus
  CONTACT_EMAIL=          # 用于 OpenAlex / Crossref 的 mailto
  DATA_DIR=./var          # SQLite、上传文件、数据
  LOCAL_LIBRARY_DIR=      # 可选
  ```

- **运行命令**：
  - 后端：`cd backend && uv run uvicorn hypoweaver.app:app --reload --port 8000`
  - 前端：`cd frontend && npm run dev`（Vite 把 `/api` 代理到 8000）
  - 测试：`cd backend && uv run pytest -q`；`cd frontend && npm run build`
  - 一键启动（可选）：根目录 `make dev`
- **依赖**：
  - 后端：fastapi、uvicorn、pydantic v2、sqlalchemy 2、httpx、openai、pandas、pyreadstat、openpyxl、pymupdf、numpy、scipy、statsmodels、linearmodels、matplotlib（可选）、pytest；
  - 前端：react、react-router、@tanstack/react-query、recharts（或 echarts）、typescript、vite。
- **密钥**：仓库中不出现任何密钥；测试一律使用假 LLM。

## 1. 仓库骨架

```
/AGENTS.md  /README.md  /.env.example  /.gitignore  /Makefile
/docs/SPEC.md  /docs/PLAN.md  /docs/DATA_carbon_case.md
/backend/pyproject.toml
/backend/hypoweaver/
    app.py            # FastAPI 装配、路由注册、静态托管
    config.py  db.py  jobs.py  errors.py
    projects/  literature/  landscape/  llm/  candidates/  plans/
    datasets/  binding/  stats/  claims/  proposal/  cases/carbon.py
/backend/tests/
/frontend/ (vite + react-ts)
    src/api/  src/pages/  src/components/  src/styles/
```

每个领域包对外只暴露 `service.py`（函数接口）和 `router.py`；`models.py` 放 ORM 和 Pydantic 定义。

## 2. 任务清单（按顺序）

### T01 骨架与项目 CRUD

- **目标**：前后端可以运行；能创建、列出、删除项目，并编辑研究方向。
- **范围**：
  - 后端：`config`、`db`（SQLite + `create_all`）、`errors`（统一错误格式）、`projects`（模型、服务、路由）、`GET /api/health`；
  - 前端：路由框架、`/` 项目列表、新建对话框、`/p/:id` 总览（步骤条上 6 个阶段都显示“未开始”）、`/p/:id/direction`；
  - 文件：README、`.env.example`、AGENTS.md、`docs/SPEC.md`（复制 SPEC）。
- **验收**：
  - `make dev` 启动后，在浏览器中新建项目“碳市场与企业绿色创新”，刷新后仍然存在；删除后消失。
  - `pytest` 有一个 API 测试，覆盖项目 CRUD。

### T02 作业系统与 LLM 客户端

- **目标**：有可复用的后台作业和结构化 LLM 调用能力。
- **范围**：
  - `jobs`：jobs 表，`submit` 用 asyncio 任务执行，记录进度和异常；`GET /api/jobs/{id}`；
  - `llm`：OpenAI SDK 客户端；命名提示模板注册表；`generate(prompt_name, payload, OutputModel)`，内容包括 json_object、Pydantic 校验、修复 1 次、写入 LLMCall 记录（含 usage token）；
  - LLM 必须可以通过依赖注入替换为 FakeLLM；
  - `/settings` 页面和 `GET /api/settings/status`、`POST /api/settings/llm:test`。
- **验收**：
  - 配置真实 Key 后，设置页的“测试连接”成功，并显示模型名和 token 数；不配 Key 时显示明确的未配置提示。
  - 有一个单元测试：FakeLLM 第一次返回非法 JSON、第二次返回合法 JSON 时，修复成功。

### T03 文献联合检索与证据卡

- **目标**：阶段 ② 的检索部分可以真实使用。
- **范围**：
  - `literature`：OpenAlex 和 Crossref 客户端（摘要还原、去 JATS 标签）、合并去重、`LiteratureSearch` 和 `EvidenceCard` 表、单源失败独立记录；
  - `suggest_queries` 提示；
  - API：`queries:suggest`、`searches`（作业）、`evidence` 列表和 PATCH；
  - 前端 `/p/:id/literature`：检索式编辑 → 检索 → 证据卡表格（纳入/排除、来源标签、摘要展开）和检索记录。
- **验收**：
  - 输入方向“碳市场 企业绿色创新”，生成检索式并检索后，出现 ≥30 条去重的证据卡，其中有中英文献，且带 DOI 和年份。
  - 断网或把某个源的 URL 改坏时，另一个源的结果照常显示，并能看到失败原因。
  - 测试：用假 HTTP 响应验证合并去重。

### T04 PDF 上传与可选本地库

- **范围**：pymupdf 抽取文本；用 DOI 正则查 Crossref 补齐元数据；生成 `source=pdf` 的证据卡；如果配置了 `LOCAL_LIBRARY_DIR`，作为第三个检索源。
- **验收**：上传一篇论文 PDF 后出现一张证据卡，标题和年份正确或可编辑，正文摘录可以查看。

### T05 文献概况

- **范围**：
  - `landscape.build_landscape(cards)`：纯代码统计，包括年度计数、期刊 Top 10、概念或关键词频次（OpenAlex concepts，中文用简单分词或从标题提取关键词）、共现边（Top N）、方法关键词计数（DID、事件研究、中介、工具变量、门槛等）；
  - 前端：年度柱图、期刊榜、共现网络（简单力导图）、方法分布图，并标注“基于本次检索样本”。
- **验收**：碳市场项目的概况页显示 4 类图表，数据与证据卡一致（抽查年度计数）。
- **测试**：给定 5 张卡片，统计结果正确。

### T06 多候选生成与自审

- **范围**：
  - `generate_candidates` / `review_candidates` 提示；
  - 证据 ID 校验，移除无效引用并计数；
  - 审阅结果为 revise 时修订 1 次；
  - CandidateSet 版本管理；纳入证据变更后把候选集标记为过期；
  - 前端：候选对比卡片、证据 chip（悬停显示摘要）、推荐说明、未被引用的证据列表、重新生成。
- **验收**：
  - 用真实 Qwen 生成 2–4 个候选，每个都有缺口、假设、机制、数据需求、识别思路、风险、定位标签，并引用 ≥2 张证据卡；点击 chip 能看到对应文献。
  - FakeLLM 测试：返回不存在的证据 ID 时被移除。

### T07 选择、编辑与研究方案

- **范围**：
  - 候选选择和编辑；
  - `draft_plan` 提示与 StudyPlan（变量角色、方法类别、模型、事件窗口、稳健性、置换、决策规则默认值、计划结论、边界说明、uncertain 标记、“处理是否为真实分配”布尔值）；
  - 方法类别白名单校验；
  - 确认后锁定（再编辑会生成新版本）；
  - 过期规则（SPEC 中“过期规则”一段）；
  - 前端 `/p/:id/plan`：概览、重点审阅（uncertain 项和识别假设）、完整可编辑详情、确认。
- **验收**：选中碳市场候选并起草方案后，方案的方法类别为 policy_causal，包含 ≥4 项稳健性，决策规则带默认值；确认后字段变为只读，“新建版本”可用。

### T08 数据资产导入与字段档案

- **范围**：
  - `datasets.inspect`：csv、xlsx（工作表列表）、dta（列名加变量标签，只读元数据）；
  - `import_`：按选择的列读取（dta 用 pyreadstat 的 `usecols`），转成 parquet 或 CSV 存放在 `DATA_DIR/datasets/`；
  - 字段档案和面板识别；
  - 来源、许可等元数据可编辑；
  - `cases/carbon.py`：`fetch` 从 Mendeley 公开地址下载 `data.dta`（校验文件大小为 332,614,843 字节）；`prepare` 按 SPEC 中的准备配方做列选择和重命名，并登记为数据资产（来源：doi:10.17632/rrfwny7byp.1，CC BY 4.0）；
  - `docs/DATA_carbon_case.md`：下载、准备和引用说明；
  - 前端 `/p/:id/data`：导入向导（上传 → 列选择 → 确认）、档案表、面板信息卡。
- **验收**：
  - `uv run python -m hypoweaver.cases.carbon fetch && … prepare` 完成后，界面中出现数据资产：14,208 行，firm_id × year 面板，1,184 个个体，12 期，没有重复。
  - 直接上传 data.dta、只选 10 列时同样可以导入。
  - 测试：csv、xlsx、dta 小样本文件导入和档案正确。

### T09 变量绑定与就绪检查

- **范围**：
  - `suggest_bindings` 提示；
  - 公式派生（白名单函数：log、log1p、加减乘除、字段引用；用安全的表达式解析，不使用 eval）；
  - `readiness`：已绑定/缺失、有效样本量、处理组和对照组数量、首次暴露年份分布、单调路径个体数；
  - 不就绪时生成“待补数据计划”（代码列出缺失项，并可让 LLM 补充获取建议）；
  - 前端绑定表和就绪卡。
- **验收**：碳市场方案绑定 outcome=`log1p(green_invention_independent+green_invention_joint)`、treatment=`industry_peer_exposure`、controls=`log(total_assets)`、`leverage`、`return_on_assets` 后，就绪状态为 ready，并显示处理个体数和首次暴露年份分布（2013 年最多）。

### T10 统计引擎：主执行、事件研究、稳健性、置换

- **范围**：
  - `stats.run_analysis(spec, frame)`：按 SPEC 的“统计引擎接口”实现，覆盖 policy_causal、panel_association、mechanism_boundary；
  - 用 PanelOLS 加聚类；事件研究分箱和前趋势 Wald 检验；稳健性的 5 种 kind；置换检验（向量化）；
  - 可读的失败原因；
  - `POST /plans/{id}/runs` 作业，`GET /runs/{id}`，步骤状态；
  - 前端 `/p/:id/analysis`：步骤进度、主结果表、事件研究图（含置信区间）、稳健性表、置换直方图。
- **验收**：
  - 合成面板测试（已知效应 0.3）：主系数落在 0.3 ± 2 倍标准误之内；置换 p < 0.05；对无效应数据，置换 p 不显著。
  - 在碳市场数据上运行完成，置换 499 次在普通笔记本上 2 分钟内完成，界面显示全部结果。

### T11 独立复算与结论评估

- **范围**：
  - `stats.reproduce`：statsmodels 实现，对主模型和稳健性模型复算，比较差异；
  - `claims.assess` 与 `check_wording`（规则见 SPEC）；
  - 强度上限遵守“处理是否为真实分配”这一项；
  - 用户决定只能等于或低于上限；
  - 前端：复算对照表、每条结论卡（判定、上限、允许措辞、阻断原因、用户决定）。
- **验收**：
  - 碳市场运行的复算最大相对差 < 1e-6，结论上限显示为“关联”，界面不允许选择更高强度。
  - 表驱动测试覆盖 supportive、mixed、not_supportive、insufficient 四种判定，以及措辞的正例和反例（例如“与……存在关联”通过，“促进了”被拦截，“不能解释为因果”通过）。

### T12 结果解读与研究提案

- **范围**：
  - `interpret_results` 和 `write_proposal_sections` 提示（数字占位符注入，措辞检查后重写 1 次，仍违规则回落到模板句）；
  - `proposal.build_proposal`：按 SPEC 的章节结构，参考文献由证据卡生成；无运行结果时生成 plan_only 提案；
  - 叙述可以编辑，数字只读；
  - Markdown 下载；打印样式；
  - 过期标记。
- **验收**：
  - 碳市场项目生成提案，提案中的系数和 p 值与分析页一致；没有“促进/导致”这类因果措辞；参考文献列出被引用的证据卡；浏览器打印预览排版整洁。
  - 另建一个没有数据的项目，同样可以生成计划型提案。

### T13 总览、过期与主流程测试

- **范围**：
  - 项目总览汇总各阶段状态和摘要；
  - StaleBanner 贯通所有页面；
  - 修改方向时弹出影响提示；
  - API 主流程测试（FakeLLM + 假文献源 + 合成数据）：从建项目一路走到提案；
  - README 中写完整的上手步骤（含碳市场案例）。
- **验收**：
  - `pytest` 全部通过，其中包括主流程测试。
  - 修改方向后，候选、方案、提案显示过期，旧内容仍然可以查看。

### T14 界面打磨

- **范围**：统一视觉（中文学术风格、排版、空状态、加载和错误状态）；所有作业显示进度和失败原因；设置页显示 token 统计；文案中不出现内部术语（job、H1 等）。
- **验收**：架构师按下面的“验收清单”逐项走查。

## 3. 验收清单（架构师审查用）

- [ ] 克隆 `v2` 后按 README 操作，10 分钟内可以在本机跑起前后端；仓库中没有密钥、数据文件或 `var/`。
- [ ] 代码中没有 mock 或 fixture 数据源、写死的结果、写死的模型名，也没有演示旁路（全局搜索 `mock`、`showcase`、`qwen3`、`max` 进行确认）。
- [ ] 新建碳市场项目后，检索式生成和联合检索都是真实网络请求；证据卡 ≥30 条，来源标签正确；单源失败可见。
- [ ] 能上传 PDF 并形成证据卡。
- [ ] 文献概况的 4 类图表与证据数据一致，并标注“样本内”。
- [ ] 生成 2–4 个有实质差异的候选，引用都能点开，并显示无效引用的处理计数。
- [ ] 能选择或编辑候选；方案起草、审阅、确认后锁定；修改时生成新版本。
- [ ] 碳市场数据可以通过 fetch/prepare 命令导入，也可以通过 .dta 列选择导入；字段档案和面板信息正确（14,208 行、1,184 家企业、2010–2021 年）。
- [ ] 变量绑定（含派生公式）和就绪检查正确；未就绪时给出待补数据计划。
- [ ] 主模型、事件研究、稳健性、置换检验都有结果；复算一致；结论上限为“关联”，用户不能升级。
- [ ] 解读和提案中的数字与结果一致，没有违规的因果措辞；Markdown 下载可用，打印样式可用；计划型提案可用。
- [ ] 上游修改会引发下游过期标记，旧内容保留。
- [ ] 每次 LLM 调用都有日志（模型、token、耗时）；设置页能看到统计。
- [ ] `pytest` 通过（统计引擎、结论评估、数据导入、API 主流程）；`npm run build` 通过。
- [ ] 代码结构符合骨架，模块接口小，单个文件不超过约 600 行。

## 附：AGENTS.md（定稿，见 AGENTS.md）

见同目录 `03_AGENTS.md`，放在仓库根目录。
