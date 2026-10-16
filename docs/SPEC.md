# HypoWeaver v2 SPEC：碳市场主流程端到端

> 状态：定稿（2026-10-12），可交付 CodeX 执行。

> 本文是 v2 的唯一产品规格。旧 SPEC v0.21 和 impl_v1 中与本文冲突的内容，一律以本文为准。领域背景见 `00_旧项目蒸馏_项目参考.md`。

## 术语表

| 术语 | 含义 |
|---|---|
| 项目（Project） | 一次研究探索的容器。同一时间只推进一个选中的候选 |
| 研究方向（Direction） | 用户输入的方向、问题、约束和领域，是项目的起点 |
| 文献检索（LiteratureSearch） | 一次联合检索（OpenAlex + Crossref + 本地库），由若干查询组成 |
| 证据卡（EvidenceCard） | 一条可引用的文献证据，包括元数据、摘要或正文片段和来源。ID 形如 `ev_xxx` |
| 文献概况（Landscape） | 代码对证据卡做的样本内统计：年度分布、期刊、关键词/方法共现、高引文献 |
| 候选（Candidate） | 由大模型生成的研究选题，包括缺口、假设、机制、所需数据、识别思路、风险和引用的证据卡 |
| 研究方案（StudyPlan） | 选定候选之后的可执行方案：变量角色、方法类别、模型设定、诊断、稳健性和决策规则 |
| 数据资产（Dataset） | 导入的数据文件（.dta/.csv/.xlsx）及其字段档案 |
| 字段档案（FieldProfile） | 每个字段的类型、缺失率、取值范围、唯一值数和标签 |
| 变量绑定（VariableBinding） | 方案中的变量角色到数据字段或派生公式的映射 |
| 检验运行（AnalysisRun） | 一次对确认后方案的执行，包括主模型、事件研究、稳健性、置换检验和独立复算 |
| 结论评估（ClaimAssessment） | 代码根据决策规则和证据给出的每条结论的强度上限与允许措辞 |
| 研究提案（Proposal） | 项目的最终成果，Markdown 格式，可在浏览器打印 |
| 方法类别 | `policy_causal`（政策 DID）、`panel_association`（面板关联）、`mechanism_boundary`（机制/边界） |
| 结论强度 | `insufficient` < `preliminary` < `mixed` < `associational` < `causal_cautious` |

## Problem Statement

做实证研究的人想从一个方向（例如“碳市场与企业绿色创新”）找到真正有增量、又能用现有数据检验的问题。他们面对三个难点：

1. 文献分散，难以快速看清已有研究做到哪一步、缺口在哪里。
2. 通用大模型给出的选题，往往没有证据依据，也不考虑数据是否可得。
3. 即便有了数据，从方案到回归、诊断、稳健性，再到“结论能说到什么程度”，整个过程耗时且容易过度宣称。

旧版系统有大量演示旁路和硬编码结果，主案例不是通过产品流程真实跑出来的。

## Solution

v2 是一个单用户的本地研究工作台。用户在一个项目里按六个阶段推进：

1. 输入研究方向。
2. 系统在线检索 OpenAlex/Crossref，用户也可以上传 PDF，系统形成证据卡和文献概况。
3. Qwen 基于证据卡生成 2–4 个有差异的候选，每个候选都引用证据卡；代码校验引用，模型自审一次。
4. 用户选择候选并可修改；系统起草研究方案，用户审阅并确认。
5. 用户导入数据，系统生成字段档案，把方案变量绑定到字段，然后执行主检验、诊断、稳健性、置换检验和独立复算；代码给出结论强度上限。
6. 系统生成研究提案页，所有数字来自真实结果，可以打印成 PDF。

全部状态持久化在后端 SQLite 中，任何阶段都可以回看。上游修改后，下游标记为“过期”，由用户决定是否重跑。

首个真实案例：Mendeley rrfwny7byp 碳市场企业面板。

## User Stories

### 项目与方向

1. 作为研究者，我希望新建项目并输入研究方向、具体问题（可选）、研究约束和领域，以便系统围绕我的意图工作。
2. 作为研究者，我希望在项目列表看到每个项目的标题、当前阶段和更新时间，以便继续之前的工作。
3. 作为研究者，我希望在一个页面里看到项目的六个阶段及每个阶段的状态（未开始、进行中、已完成、已过期），以便知道下一步做什么。
4. 作为研究者，我希望随时回到已完成的阶段查看内容，以便核对依据。
5. 作为研究者，我希望修改研究方向后，系统提示哪些下游结果会过期，并由我决定是否重新生成，以便旧结果不被悄悄覆盖。
6. 作为研究者，我希望能删除项目，以便清理试验性内容。

### 文献联合调研

7. 作为研究者，我希望系统根据我的方向自动生成 3–6 条中英文检索式，并允许我编辑后再检索，以便控制检索范围。
8. 作为研究者，我希望系统同时检索 OpenAlex 和 Crossref，并合并、去重结果（按 DOI，没有 DOI 的按规范化标题），以便获得较完整的文献集合。
9. 作为研究者，我希望每条文献显示标题、作者、年份、期刊、DOI、被引次数、摘要（有的话）和来源，以便判断相关性。
10. 作为研究者，我希望在检索结果中勾选“纳入”或“排除”文献，以便控制后续候选生成用到的证据。
11. 作为研究者，我希望上传 PDF，系统抽取全文文本和元数据，形成证据卡，以便纳入付费库或者自己读过的文献。
12. 作为研究者，我希望（可选）接入本地私有文献库目录，以便利用已有收藏。
13. 作为研究者，我希望看到文献概况：年度发表数量、主要期刊、高频关键词或概念、关键词共现关系图、方法关键词（DID、事件研究、中介等）的分布，以便了解研究热点和关系。
14. 作为研究者，我希望文献概况明确标注“基于本次检索样本”，以便不把样本分布误读为学科趋势。
15. 作为研究者，我希望某个外部源检索失败时，仍能看到另一个源的结果，并看到失败原因，以便知道覆盖缺口。
16. 作为研究者，我希望看到每次检索的查询、来源、命中数和时间，以便复查调研过程。

### 研究缺口与多候选

17. 作为研究者，我希望系统基于已纳入的证据卡生成 2–4 个候选选题，以便比较不同方向。
18. 作为研究者，我希望每个候选都包含研究缺口、核心假设、机制链条、所需变量和数据、可行的识别思路、主要风险，以及“增量大但缺数据”或“数据可行但增量有限”这类定位标签，以便权衡。
19. 作为研究者，我希望候选中的每个论断都标注所引用的证据卡，并且点击就能看到原文摘要，以便核查依据。
20. 作为研究者，我希望系统丢弃或修复引用了不存在证据的内容，以便没有编造的引用。
21. 作为研究者，我希望系统对候选做一次自审（有无实质差异、证据是否支撑、能否检验），必要时定向修订一次，以便提高质量。
22. 作为研究者，我希望候选之间有实质差异，而不是同一假设换个说法，以便选择真的有意义。
23. 作为研究者，我希望系统给出有条件的优先建议（例如“如果你有某类数据，优先候选 B”），但不替我做决定，也不给出综合总分，以便保持判断权。
24. 作为研究者，我希望看到哪些证据卡被候选引用、哪些没有被引用，以便发现遗漏。
25. 作为研究者，我希望在当前证据基础上重新生成候选，并保留之前的版本，以便对比。

### 选择、修改与研究方案

26. 作为研究者，我希望选择一个候选作为当前选题，其他候选保留、可以切换，以便专注推进一个方向。
27. 作为研究者，我希望编辑所选候选的问题、假设和变量描述，以便贴合我的想法。
28. 作为研究者，我希望系统根据所选候选起草研究方案，内容包括：方法类别、结果变量、核心解释变量或处理变量、控制变量、固定效应、聚类、事件研究设定、稳健性清单、置换检验次数、决策规则和结论边界说明，以便得到可执行的计划。
29. 作为研究者，我希望方案页先给概览，再列出需要重点审阅的项（例如识别假设、变量含义不确定之处），最后给完整详情，以便高效审阅。
30. 作为研究者，我希望变量含义不确定时，方案将其标记为“待确认”，而不是编造，以便不被误导。
31. 作为研究者，我希望编辑方案的任意字段，以便修正设定。
32. 作为研究者，我希望确认方案之后，决策规则被锁定；执行后如果要改，只能新建方案版本，以便避免结果出来后再调整阈值。
33. 作为研究者，我希望系统检查方案的方法类别是否在支持范围内（policy_causal、panel_association、mechanism_boundary），并在不支持时明确告知，以便不跑出无意义的结果。

### 数据导入与字段档案

34. 作为研究者，我希望上传 .csv、.xlsx（选择工作表）或 .dta 文件作为数据资产，以便使用常见格式。
35. 作为研究者，我希望在导入大型 .dta 时，先看到列清单（带 Stata 变量标签）并只选择需要的列，以便控制体积。
36. 作为研究者，我希望系统为每个字段生成档案（类型、缺失率、最小值、最大值、均值、唯一值数、标签），以便了解数据。
37. 作为研究者，我希望系统识别面板结构（个体字段、时间字段、个体数、期数、是否平衡、重复的个体—时间组合），以便确认数据适合面板方法。
38. 作为研究者，我希望把方案中的每个变量角色绑定到字段，或定义派生变量（例如 `log1p(a+b)`、`log(x)`），系统先给出建议、由我确认，以便完成变量对接。
39. 作为研究者，我希望绑定后看到“就绪检查”结果：哪些变量已绑定、哪些缺失、样本量有多少、处理组和对照组各有多少，以便知道能不能执行。
40. 作为研究者，我希望未就绪时得到“待补数据计划”，并且方案仍然保留，以便后续补数据。
41. 作为研究者，我希望用一个命令下载碳市场主案例数据，并按文档导入，以便复现主案例。
42. 作为研究者，我希望数据资产记录来源、许可、文件大小和导入时间，以便注明出处。

### 探索性检验与独立复算

43. 作为研究者，我希望在就绪后启动检验运行，任务在后台执行，离开页面也不中断，以便处理较长的计算。
44. 作为研究者，我希望看到运行进度和每一步的状态（主模型、事件研究、稳健性、置换检验、复算、结论评估），以便了解进展。
45. 作为研究者，我希望看到主模型结果表（系数、标准误、t 值、p 值、置信区间、样本量、个体数、固定效应、聚类方式），以便解读。
46. 作为研究者，我希望看到事件研究系数图和前趋势联合检验结果，以便判断平行趋势。
47. 作为研究者，我希望看到稳健性结果汇总表（每项设定的系数和显著性），以便判断稳健性。
48. 作为研究者，我希望看到置换检验的分布图和置换 p 值，以便判断结果是否偶然。
49. 作为研究者，我希望系统用独立实现复算主模型和稳健性模型，并显示差异，以便确认结果不是实现错误。
50. 作为研究者，我希望系统按锁定的决策规则判定“支持、混合、不支持”，并给出每条结论的强度上限和允许措辞，以便不过度宣称。
51. 作为研究者，我希望在结果不支持预期时也得到完整结果和解读，以便如实了解。
52. 作为研究者，我希望运行失败时看到明确的失败原因（例如共线性、样本为空、字段缺失），以便修正。
53. 作为研究者，我希望大模型基于结果写一段解读，其中所有数字由系统注入，且通过措辞检查，以便叙述可信。
54. 作为研究者，我希望对每条结论选择“接受、降级、暂缓、拒绝”，但不能升级到超过系统上限，以便保留最终判断权。

### 研究提案与成果

55. 作为研究者，我希望系统按赛题《科学假设与研究计划》十项生成研究提案页，顺序固定：待研究问题（含研究缺口与假设 H1…）；解决思路；必要的技术手段；数据集（分 Source 历史数据与 Target 拟采集验证数据特征）；标题（中英）；摘要（背景、方法、预期/主结果）；方法论（实施步骤与模型公式）；实验设计（表格，含 Baselines 与 Metrics）；实验结果（系统注入真实数字，含结论强度与边界、局限）；参考论文（仅已纳入证据卡的真实文献，并列数据来源），以便得到可交付的成果。
56. 作为研究者，我希望提案中每个数字和每条结论都能追溯到具体的运行结果或证据卡，以便核查。
57. 作为研究者，我希望在没有数据或没有运行结果时，也能生成“计划型提案”（不含实证结果，附待补数据计划），以便在条件不足时有所交付。
58. 作为研究者，我希望下载 Markdown，并用浏览器打印成 PDF（有专门的打印样式），以便分享。
59. 作为研究者，我希望编辑提案中的叙述段落，但不能编辑系统注入的数字，以便保持数字真实。
60. 作为研究者，我希望在上游变更之后看到提案被标记为过期，以便及时更新。

### 系统与配置

61. 作为部署者，我希望通过环境变量配置 DashScope API Key、Base URL 和模型名，以便切换模型。
62. 作为研究者，我希望在设置页看到模型是否可用（连接测试）、外部检索是否可用，以及大模型调用的 token 用量统计，以便了解系统状态和开销。
63. 作为研究者，我希望模型调用失败时看到原因，并能重试该步骤，以便不丢失进度。
64. 作为开发者，我希望每次大模型调用都记录提示名称、模型、token、耗时和状态，以便排查问题。

## Implementation Decisions

### 架构

- 单仓库，包含两部分：`backend`（FastAPI 单服务 + SQLite）和 `frontend`（React + TS + Vite）。开发时 Vite 把 `/api` 代理到后端；生产时由后端托管前端构建产物。
- Python 3.12，依赖用 `uv` 或 pip 加 `requirements.txt` 锁定主要版本。
- 不设多服务、消息队列、登录或多用户。

### 后端模块（深模块、接口少）

| 模块 | 职责 | 对外接口要点 |
|---|---|---|
| `projects` | 项目 CRUD、阶段状态推导、下游过期标记 | `create/get/list/delete/update_direction`；`stage_status(project)` |
| `literature` | OpenAlex/Crossref 客户端、本地库、PDF 解析、去重合并、证据卡 | `run_search(project, queries) -> LiteratureSearch`；`add_pdf(project, file) -> EvidenceCard`；`set_included(card_id, bool)` |
| `landscape` | 基于证据卡的纯代码统计 | `build_landscape(cards) -> Landscape` |
| `llm` | Qwen 客户端、提示模板、结构化输出、修复 1 次、调用日志 | `generate(prompt_name, payload, OutputModel) -> OutputModel` |
| `candidates` | 生成、引用校验、自审、修订 | `generate_candidates(project) -> CandidateSet`；`select(candidate_id)`；`edit(candidate_id, patch)` |
| `plans` | 起草方案、校验、确认锁定 | `draft_plan(project) -> StudyPlan`；`update`；`confirm` |
| `datasets` | 导入 csv/xlsx/dta、列选择、字段档案、面板识别、派生变量 | `inspect(file) -> ColumnList`；`import_(file, columns, sheet) -> Dataset`；`profile(dataset)` |
| `binding` | 变量绑定建议与就绪检查 | `suggest(plan, dataset)`；`readiness(plan, dataset, bindings) -> Readiness` |
| `stats` | 统计引擎：主执行与独立复算两套实现 | `run_analysis(spec: AnalysisSpec, frame) -> AnalysisResult`；`reproduce(spec, frame) -> ReproductionResult` |
| `claims` | 决策规则判定、强度上限、措辞检查 | `assess(plan, result, reproduction) -> list[ClaimAssessment]`；`check_wording(text, max_strength)` |
| `jobs` | 后台任务（asyncio + jobs 表），记录进度与失败 | `submit(kind, project_id, fn)`；`get(job_id)` |
| `proposal` | 汇总产物、注入数字、调用 LLM 写叙述、Markdown 渲染 | `build_proposal(project) -> Proposal`；`render_markdown(proposal)` |

### 领域模型与状态（实体级别）

- **Project**：id、title、direction{text, question?, constraints[], domain}、selected_candidate_id?、created_at、updated_at。六个阶段的状态由各实体推导，不单独存储。
- **LiteratureSearch**：id、project_id、queries[]、per_source_status{openalex: ok/failed+reason, crossref…}、hit_count、created_at。
- **EvidenceCard**：id(`ev_`)、project_id、source(`openalex|crossref|pdf|local`)、doi?、title、authors[]、year、venue、cited_by?、abstract?、fulltext_excerpt?、concepts[]、included(bool)、search_id?。
- **Landscape**：project_id、computed_at、payload（年度计数、期刊 Top N、关键词频次、共现边、方法关键词计数），由代码随时重新计算。
- **CandidateSet**：id、project_id、version、status(`generating|ready|failed`)、review{decision, notes}、recommendation_text、stale(bool)。
- **Candidate**：id、set_id、title、gap、hypothesis、mechanism[]、required_data[]、identification、risks[]、positioning(`high_increment_data_gap|feasible_limited_increment|balanced`)、evidence_ids[]、user_edited(bool)。
- **StudyPlan**：id、project_id、candidate_id、version、status(`draft|confirmed|superseded`)、method_family、variables[{role: outcome|treatment|control|mechanism|moderator|unit|time, name, definition, uncertain(bool)}]、model{fixed_effects[], cluster, event_window, bins}、robustness[{id, change}]、permutation{n, seed}、decision_rules{...}、claims_planned[{id, text, type}]、boundary_notes、stale。
- **Dataset**：id、project_id?（数据资产全局共享，项目引用）、name、source{url, doi, license}、format、sheet?、selected_columns[]、file_path、size_bytes、sha256（仅作元数据）、n_rows、n_cols、panel{unit, time, n_units, n_periods, balanced, duplicates}、profile[FieldProfile]。
- **VariableBinding**：plan_id、dataset_id、role_name → {field | formula}、confirmed(bool)。
- **AnalysisRun**：id、plan_id、dataset_id、status(`queued|running|succeeded|failed`)、steps{main, event_study, robustness, permutation, reproduction, assessment: status+error}、result JSON（AnalysisResult）、reproduction JSON、created_at、finished_at。
- **ClaimAssessment**：run_id、claim_id、verdict(`supportive|mixed|not_supportive|insufficient`)、max_strength、allowed_wording、blockers[]、user_decision(`accepted|downgraded|deferred|rejected|pending`)、final_text。
- **Proposal**：id、project_id、version、sections[{key, markdown, injected_numbers_ref}]、kind(`empirical|plan_only`)、stale。
- **LLMCall**：id、project_id?、prompt_name、prompt_version、model、input_tokens、output_tokens、latency_ms、status、error?、created_at。
- **Job**：id、project_id、kind、status、progress_text、error?、timestamps。

**过期规则**：方向变更时，候选、方案和提案过期；纳入证据变更时，候选过期；候选或方案变更时，运行和提案过期；数据或绑定变更时，运行和提案过期。过期只是加标记，不删除任何数据。

### 存储

SQLite 单文件，用 SQLAlchemy 2.0（或 sqlmodel）定义表，复杂结构存 JSON 列。启动时 `create_all`，**不做迁移框架**。上传的文件和数据放在 `DATA_DIR`（默认 `./var`，已加入 gitignore）。

### API 契约（前缀 `/api`，JSON；长任务返回 `job_id`）

| 方法与路径 | 说明 |
|---|---|
| `GET/POST /projects`，`GET/PATCH/DELETE /projects/{id}` | 项目；PATCH 用于改方向，返回受影响的下游 |
| `GET /projects/{id}/overview` | 各阶段状态和摘要 |
| `POST /projects/{id}/queries:suggest` | LLM 生成检索式（同步） |
| `POST /projects/{id}/searches` | 提交检索 → job |
| `GET /projects/{id}/searches` | 检索记录 |
| `GET /projects/{id}/evidence`，`PATCH /evidence/{card_id}` | 证据卡列表与纳入/排除 |
| `POST /projects/{id}/evidence/pdf` | 上传 PDF（multipart） |
| `GET /projects/{id}/landscape` | 文献概况 |
| `POST /projects/{id}/candidate-sets` | 生成候选 → job |
| `GET /projects/{id}/candidate-sets` | 候选集和候选 |
| `PATCH /candidates/{id}`，`POST /candidates/{id}:select` | 编辑与选择 |
| `POST /projects/{id}/plans` | 起草方案 → job |
| `GET /plans/{id}`，`PATCH /plans/{id}`，`POST /plans/{id}:confirm` | 方案 |
| `POST /datasets:inspect` | 上传后返回列清单和标签（暂存文件） |
| `POST /datasets` | 带列选择和工作表正式导入 → job |
| `GET /datasets`，`GET /datasets/{id}` | 数据资产及字段档案 |
| `POST /plans/{id}/bindings:suggest`，`PUT /plans/{id}/bindings`，`GET /plans/{id}/readiness` | 绑定与就绪 |
| `POST /plans/{id}/runs` | 启动检验 → job |
| `GET /runs/{id}` | 运行结果和步骤状态 |
| `GET /runs/{id}/figures/{name}.png` | 图（matplotlib 生成，或前端用数据画图） |
| `GET /runs/{id}/claims`，`PATCH /claims/{run_id}/{claim_id}` | 结论评估与用户决定 |
| `POST /projects/{id}/proposals` | 生成提案 → job |
| `GET /proposals/{id}`，`PATCH /proposals/{id}/sections/{key}`，`GET /proposals/{id}.md` | 提案 |
| `GET /jobs/{id}` | 任务状态 |
| `GET /settings/status`，`POST /settings/llm:test` | 模型、外部检索可用性，token 统计 |

错误统一返回 `{error: {code, message}}`。

### LLM 交互设计

- **客户端**：OpenAI SDK 指向 `QWEN_BASE_URL`（默认 `https://dashscope.aliyuncs.com/compatible-mode/v1`），模型取 `QWEN_MODEL`（默认 `qwen-plus`）。所有调用使用同一个模型配置，**不在代码里写死模型名**。参数：`response_format=json_object`，temperature 0.2。
- **提示模板**：Python 模块里的命名模板，每个带 `name` 和 `version`。system 提示包括角色、规则（只能引用给定的证据 ID、不得编造数字、不确定时标记 uncertain）和输出 JSON Schema（由 Pydantic 模型生成）。
- **流程**：调用后用 Pydantic 校验；失败时把校验错误摘要附在提示中重试 1 次；再失败则该步骤失败，并显示原因。
- **提示清单**（每个都有对应的 Pydantic 输出模型）：
  1. `suggest_queries`：方向 → `{queries:[{text, lang, rationale}]}`（3–6 条）
  2. `generate_candidates`：方向 + 已纳入证据卡（ID、标题、年份、摘要，截断到 token 上限）+ 文献概况摘要 → `{candidates:[...2–4...], recommendation_text}`
  3. `review_candidates`：候选 + 证据 → `{decision: pass|revise, issues:[{candidate_id, problem, suggestion}]}`；若为 revise，带上 issues 再调一次 `generate_candidates`
  4. `draft_plan`：候选 + 支持的方法类别说明 +（可选）数据字段档案 → StudyPlan 的草案字段
  5. `suggest_bindings`：方案变量 + 字段档案（名称、标签、类型）→ `{bindings:[{role_name, field|formula, confidence, note}]}`
  6. `interpret_results`：结果摘要（由代码生成的数字表）+ 结论上限 → `{paragraphs:[{claim_id, text}]}`。文本中的数字用占位符 `{{num:key}}` 表示，由代码替换；输出先过措辞检查，违规时要求重写 1 次，仍违规则使用代码生成的模板句
  7. `write_proposal_sections`：各节素材 → `{sections:[{key, markdown}]}`，同样使用数字占位符
- **证据引用校验**：候选和提案中的 `evidence_ids` 必须属于本项目已纳入的证据卡；不属于的 ID 会被移除，并在界面上显示“已移除无效引用 N 处”。
- **日志**：每次调用写一条 LLMCall 记录，包含 token（取 API 返回的 usage）。**不设预算门**。

### 文献检索

- **OpenAlex**：`/works?search=…&filter=from_publication_date:…&per_page=25`，取 title、authorships、publication_year、primary_location.source、doi、cited_by_count、abstract_inverted_index（还原为摘要）、concepts/topics。请求中带上 `mailto`（由配置 `CONTACT_EMAIL` 提供）。
- **Crossref**：`/works?query.bibliographic=…&rows=25`，取 DOI、title、author、issued、container-title、is-referenced-by-count、abstract（如果有，去掉 JATS 标签）。
- **合并规则**：按 DOI（转小写）去重，没有 DOI 时用规范化标题加年份；同一文献合并来源标记。单个源失败时只记录状态，不影响其他源。超时 20 秒，最多重试 1 次。
- **PDF**：用 pymupdf 抽取文本，从首页文本或 DOI 正则提取元数据；如果找到 DOI，再查 Crossref 补齐元数据。正文截取前 N 字作为 `fulltext_excerpt`。
- **本地私有库（可选）**：配置 `LOCAL_LIBRARY_DIR` 后，扫描其中的 PDF，或读取 `library.jsonl`（字段与证据卡一致），作为第三个检索源，用简单的关键词匹配。

### 统计引擎接口

- **AnalysisSpec**（由 StudyPlan 加绑定编译而来）：method_family、unit、time、outcome（字段或公式）、treatment、controls[]、fe[`unit`,`time`]、cluster、event{bins, reference=-1, monotone_only=true}、robustness[{id, kind: drop_controls|exclude_years|monotone_only|alt_outcome|add_controls, args}]、permutation{n, seed}、sample_filters。
- **主执行**用 linearmodels `PanelOLS`（entity_effects + time_effects，`cov_type=clustered`）。事件研究在同一框架下加入相对时间虚拟变量，前趋势用联合 Wald 检验。mechanism_boundary 使用交互项或把机制变量作为结果变量。
- **独立复算**：主模型和稳健性模型用 statsmodels OLS 配合个体与时间虚拟变量（或手写双向去均值），聚类协方差由 statsmodels 计算。相对差小于 1e-6 视为一致，结果中记录最大差异。
- **置换检验**：在个体之间随机置换整条处理轨迹，重复 n 次（默认 499）。为了速度，用去均值后的无控制变量 OLS 计算。
- **AnalysisResult**：
  - `main{coef, se, t, p, ci, n_obs, n_units, r2_within}`；
  - `event{terms:[{k, coef, se, p}], pretrend_wald{stat, p}}`；
  - `robustness[{id, coef, se, p, n_obs}]`；
  - `permutation{p, n, observed, distribution_summary}`；
  - `sample_report{dropped_by_reason}`；
  - `warnings[]`。
- 计算在 job 中执行（必要时放进线程池）。失败时给出可读原因（缺失字段、共线、空样本）。

### 结论评估（claims）

- **输入**：方案中的决策规则、AnalysisResult 和复算结果。
- **默认规则**（可在方案中编辑，确认后锁定）：
  - 方向支持：主系数符号符合预期，且 p < 0.05；
  - 前趋势通过：处理前各期联合检验 p ≥ 0.10；
  - 稳健性支持：指定稳健性中至少 3/4 同向；
  - 置换 p < 0.05；
  - 复算一致。
- **判定**：
  - 全部满足 → `supportive`；
  - 部分满足 → `mixed`；
  - 方向不成立 → `not_supportive`；
  - 运行失败或复算不一致 → `insufficient`。
- **强度上限**：
  - panel_association 和 mechanism_boundary 最高为 `associational`。
  - policy_causal 默认最高为 `associational`。只有当方案中“处理变量为真实处理分配”被用户确认，并且判定为 supportive 时，才允许 `causal_cautious`。
  - `mixed` 降到 `preliminary`；`not_supportive` 和 `insufficient` 分别如实表述。
- **措辞检查**：一个中文和英文因果动词词表，加上免责短语白名单（参见 00 文档 3.2）。上限低于 causal 时，检测到因果动词即视为违规。
- **用户决定**：只能等于或低于系统上限。

### 前端页面与路由

使用 React Router，后端数据用 TanStack Query 获取。没有任何本地 mock 或 fixture 数据源。

| 路由 | 页面与主要组件 |
|---|---|
| `/` | 项目列表 + 新建项目对话框 |
| `/p/:id` | 项目总览：六阶段步骤条（状态与过期标记）、各阶段摘要卡 |
| `/p/:id/direction` | 方向表单；修改时弹出影响提示 |
| `/p/:id/literature` | 检索式编辑器、检索记录、证据卡表格（纳入/排除、来源标签）、PDF 上传、文献概况（年度柱图、期刊榜、关键词共现图） |
| `/p/:id/candidates` | 候选卡片对比视图（缺口、假设、机制、数据、风险、定位标签、证据引用 chip）、自审结果、推荐说明、选择或编辑、版本切换 |
| `/p/:id/plan` | 方案页：概览、重点审阅项、完整详情（可编辑）、确认按钮 |
| `/p/:id/data` | 数据资产选择或导入（列选择、工作表）、字段档案表、面板信息、变量绑定表、就绪检查 |
| `/p/:id/analysis` | 运行按钮与步骤进度、主结果表、事件研究图、稳健性表、置换分布、复算对照、结论评估与用户决定 |
| `/p/:id/proposal` | 提案阅读视图（可编辑叙述段落、数字只读高亮）、下载 Markdown、打印（`@media print` 样式） |
| `/settings` | 模型与检索状态、连接测试、token 用量 |

- **共享组件**：StageStepper、EvidenceChip（悬停显示摘要）、JobProgress、StaleBanner、ResultTable、Chart（建议 Recharts 或 ECharts）。
- **视觉**：简洁的学术风格，中文界面。

### 碳市场主案例的设定（基于已核实的数据含义）

- **数据含义**：`carbon_post` 在“行业代码 × 年份”内恒定，是**行业层面的同群暴露**（该行业出现控排企业之后取 1），不表示企业本身被纳入碳交易。数据中**没有**企业层面的控排标识，因此无法区分控排企业和同群企业。
- **v2 中本案例应采用的表述**：
  - 研究问题可以写成：“同行业出现碳交易控排企业后，行业内上市公司的绿色（发明）专利申请是否发生变化？”这是行业同群暴露与企业绿色创新的条件关联。
  - 处理变量绑定 `carbon_post`，定义写明“行业层面同群暴露（数据发布者编码，行业×年份恒定）”，并标记 `uncertain=false`；“是否为真实处理分配”标记为**否**。
  - 方法：policy_causal 框架（企业和年份双向固定效应，企业聚类），附事件研究、稳健性和置换检验。由于暴露在行业层面，**建议把聚类放到行业层面，或者同时报告企业聚类和行业聚类**；这一项在方案中作为可选稳健性。
  - **结论上限为 `associational`**，不允许出现“碳市场促进/导致企业绿色创新”这类表述。机制（融资约束指数）只能称为“机制线索”。
  - 已知事实：样本止于 2021 年，无法覆盖全国碳市场；暴露路径有 76 次 1→0 回退，推断与行业代码变更有关，事件研究只用单调路径。
- **数据获取**：v2 提供命令 `python -m hypoweaver.cases.carbon fetch`，从 Mendeley 公开地址下载 `data.dta` 到 `DATA_DIR/raw/`，并校验文件大小。然后可以选择以下任一方式：
  - 在界面上导入 .dta 并选择列；
  - 运行 `… carbon prepare`，按准备配方生成分析 CSV 并自动登记为数据资产。
- **准备配方**：
  - 保留的列：`Symbol→firm_id`、`year`、`IndustryCode→industry_code`、`PROVINCECODE→province_code`、`CITYCODE→city_code`、`carbon_post→industry_peer_exposure`、`green_patent1–6`（重命名为 independent/joint × all/invention/utility）、`Size`、`Lev`、`ROA`、`SOE`、`HHI_A`、`FC/KZ/SA/WW_index`；
  - 不做行筛选；
  - 派生变量在绑定阶段用公式定义，例如 `log1p(green_invention_independent + green_invention_joint)`、`log(total_assets)`。

## Testing Decisions

- 只在高层接缝测试外部行为，不测私有函数排列。共设三个接缝：
  1. **统计引擎**（`run_analysis` / `reproduce`）：用合成面板（已知真值，含错位处理和前趋势）验证主系数接近真值、主执行与复算一致、置换 p 在合理范围、事件研究基期正确。另加一个碳市场小样本冒烟测试（数据存在时才运行，否则跳过）。
  2. **结论评估**（`assess` / `check_wording`）：表驱动测试，覆盖各类判定组合、强度上限，以及因果动词和免责短语的正例与反例。
  3. **API 主流程**：用 FastAPI TestClient 加一个假 LLM（通过依赖注入替换 `llm.generate`，返回固定的结构化对象）和假文献源（替换 HTTP 客户端），从建项目一直走到生成提案。
- 另外针对 `datasets` 的导入（csv/xlsx/dta 各一个小样本文件）写测试。
- 前端：只做类型检查和构建；可选 1 个 Playwright 主流程冒烟测试。
- **不做**：覆盖率指标、快照测试、对 LLM 输出内容的断言。

## Out of Scope

- Word/docx 导出、论文初稿、复杂期刊排版
- 部署包、Docker、公网部署、多用户、登录
- A/B 对照实验、多模型比较、历史回放、演示模式
- 其他研究方向的专门适配（通用流程可以用于其他方向，但不做专门优化）
- 付费数据库自动登录、全文自动下载（只用元数据和摘要，全文靠用户上传 PDF）
- 预算门、费用控制（只记录 token）
- 哈希清单、冻结门、封存签名
- spatial、IV、RDD 等其他统计方法；向量检索和知识图谱服务

## Further Notes

- 首个真实数据集是 Mendeley `doi:10.17632/rrfwny7byp.1`（CC BY 4.0，作者 Daihui Wei）。成果中必须注明引用。原始 .dta（333 MB）不进入仓库。
- 数据集描述对应的期刊论文目前没有找到（OpenAlex、Crossref、网络检索都无结果）。所以候选和提案中不能把它当作“已发表的结论”引用，只能作为数据来源。
- 外部 API 是否可用，取决于网络。OpenAlex 和 Crossref 已在 2026-10-11 无凭据各成功查询一次（见 check.md）。
