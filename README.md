# HypoWeaver v2

从研究方向出发，以真实文献、数据和检验结果形成研究提案的单用户本地工作台。产品规格见 [SPEC](docs/SPEC.md)，任务清单见 [PLAN](docs/PLAN.md)，已完成内容与验证记录见 [PROGRESS](PROGRESS.md)，逐项验收与延期边界见 [ACCEPTANCE](docs/ACCEPTANCE.md)。

## 启动

需要 Python 3.12、uv 和 Node 22。在仓库根目录运行：

```sh
cp .env.example .env
make setup
make dev
```

打开 http://localhost:5173。开发服务器把 `/api` 转发到本机 8000 端口；SQLite 默认存放在仓库根目录 `var/`，刷新或重启不会丢失项目。相对 `DATA_DIR` 始终以仓库根目录为基准。

在项目列表新建项目，进入研究方向页填写问题和约束并保存。列表提供删除入口，删除需确认。六阶段主流程均已接入，验证记录与真实模型接入边界见 PROGRESS。

```sh
make test
make build
# 构建后也可只运行后端，由其托管前端
cd backend && uv run uvicorn hypoweaver.app:app --port 8000
```

模型配置从本地 `.env`、环境变量及设置接口读取；设置接口保存到忽略的 `DATA_DIR/.env.llm`（权限 0600），重启后仍生效，并优先于环境配置。`.env.example` 提供配置示例；密钥、数据库、上传文件和碳市场原始数据均不入 Git。真实模型调用需要 LLM_API_KEY 和 LLM_MODEL，测试使用替代客户端。

文献页支持最多 6 条手动中英文检索式、OpenAlex/Crossref 联合检索和 PDF 上传。可用 `LOCAL_LIBRARY_DIR` 指向一个已有本地目录：优先读取 `library.jsonl`（每行是一张证据卡，至少有字符串 title；可带 year、doi、authors、abstract、concepts），否则读取目录顶层 PDF。索引最多 10 MB/2000 行，PDF 最多 200 个，每个 30 MB；截断或坏行会在来源状态中提示。上传 PDF 提取前 100 页文字，保留前 12000 字摘录；扫描件需先 OCR。

### 导入研究数据

在项目的“数据与检验”页面上传 `.csv`、`.xlsx` 或 `.dta`，查看列名及标签后选择所需列，再确认导入。Excel 可切换工作表；Stata 仅加载选择的列。已上传文件可复用，不需要为了改变列选择重复上传。

公开碳市场案例的下载、准备、字段含义与引用见 [DATA_carbon_case.md](docs/DATA_carbon_case.md)。运行 `cd backend && uv run python -m hypoweaver.cases.carbon fetch`，然后 `uv run python -m hypoweaver.cases.carbon prepare`；刷新数据页即可选择资产。

如果已有该公开来源的原始 `data.dta`，可直接放入 `DATA_DIR/raw/data.dta`（默认是项目 `var/raw/data.dta`），然后在 `backend` 运行 `uv run python -m hypoweaver.cases.carbon prepare`，无需重复 fetch。prepare 会核验文件大小及所需字段，并登记准备后的资产。

真实碳数据测试在 `DATA_DIR/hypoweaver.sqlite` 不存在，或库中没有 DOI 与 prepare 字段集合匹配的登记资产时会 skip；登记文件缺失或路径不一致则测试失败。先准备数据再运行全量测试，才能验证真实数据这一项。

数据读取上限为单文件 500 MB、300 列、200 万行，`DATA_DIR` 下 `staging/`、`datasets/`、`raw/` 的合计文件大小上限为 3 GB。达到上限会停止新导入并显示原因，不会删除历史数据。`staging/` 存上传原件（含失败留下的片段），`datasets/` 存已登记资产引用的 CSV，`raw/` 存案例原件。需要释放空间时先备份并核对用途；不要删除 SQLite 正在引用的分析 CSV。产品暂不提供自动清理或历史资产删除功能。

## 从研究方向到提案

1. 新建项目，在“研究方向”写下具体问题、研究对象和约束；保存后总览显示实际进度。
2. 在“文献调研”生成检索式，或手动输入中英文检索式。开始联合检索，查看每个来源的成功/失败记录。筛选纳入证据，上传可公开使用的 PDF，并核对标题、年份和摘要；概况图只描述本次样本。
3. 生成候选，比较缺口、假设、数据需求和风险，打开引用查看依据；选择并编辑一个候选。重新生成保留旧版本。
4. 起草研究方案，审阅变量定义、识别假设、事件窗口、稳健性和决策规则。模型不能替研究者确认真实处理分配。确认后锁定；编辑已确认方案会产生新的草稿版本，需要重新确认。
5. 导入数据，在数据页选择已确认方案，逐项绑定字段或公式，保存并明确确认绑定。就绪卡列出有效样本、分组、首次暴露和缺失项。点击“统计检验”，执行并查看主模型、事件研究、稳健性、置换、独立复算及结论评估。研究者可接受、降级、暂缓或拒绝结论，不能升级。
6. 生成研究提案。已有合适运行时带探索性结果；缺少数据时生成计划型提案和待补清单。编辑叙述时保留数字占位符，结果与引用只读。下载 Markdown，或通过浏览器打印保存 PDF。

上游修改会标记下游过期，历史方案、运行和提案仍可查看。应按顺序更新过期阶段。方向修改会先显示影响提示；总览和各阶段均提示过期状态。共享数据来源信息修改会使引用它的项目更新运行/提案。

### 碳市场案例的人工核对

准备数据后，结果变量可绑定 `log1p(green_invention_independent + green_invention_joint)`，核心解释变量绑定 `industry_peer_exposure`，个体和时期绑定 `firm_id`、`year`；控制可用 `log(total_assets)`、`leverage`、`return_on_assets`。原始 `Size` 是资产总计，不能再次误当成已取对数。

该数据变量是行业同群暴露，不是企业实际控排身份。保留“真实处理分配”为否，最高只报告条件关联。默认企业聚类；如要核验行业层面的误差关联，可在新方案版本把聚类字段改为 `industry_code` 后单独运行。事件研究仅用单调路径样本，不能把前趋势检验通过直接当成识别假设已成立。数据来源需引用 Daihui Wei 的 Mendeley 数据集，不能当成已找到的期刊论文结论。

### 验证与当前边界

`make test` 运行真实统计计算、数据格式导入、结论规则和从建项目到提案的 API 主流程；模型和文献网络在自动测试中由明确隔离的测试替身提供。产品运行时没有模拟数据入口。`make build` 执行 TypeScript 检查与生产构建。

本轮真实 Qwen 连接和输出质量验收按使用者要求后置。未配置密钥时模型步骤会明确报错；可以先使用真实文献检索、PDF和数据导入。配置后在设置页测试连接，并逐项验收检索式、候选、方案和提案内容。不要把离线测试通过视为真实模型的内容质量已验证。

### 第二轮后端接口约定

- `GET /api/settings/llm` → `{base_url, llm_model, configured}`，不包含密钥，也不会主动调用模型。
- `PUT /api/settings/llm` 接受可选的 `base_url`、`api_key`、`llm_model`；省略密钥保留现值，传空字符串清除。保存后后续请求使用新配置，进行中的任务保持启动时配置。默认地址和模型集中在后端 Settings / `.env.example`，模型名不限制枚举。未知字段（包括旧名 `model`）返回 422 和中文提示，配置不会被部分写入。
- 未配置时，生成查询、候选、方案、绑定建议、提案及连接测试均直接返回 HTTP 409 / `llm_not_configured`，不会创建待执行任务。前端可先 GET 配置，再跳转设置页填写。
- 候选集、方案和提案版本统一用 `llm_model` 记录生成模型；提案的 `interpretation` 保存 `{llm_model, paragraphs, status}`。方案的 `model` 只表示统计模型设定。手工新建版本继承该来源；历史记录未知模型为 null，不补猜测值。
- `PATCH /api/datasets/{id}/fields/{name}` 接受 `semantics`、`level`；方案接口返回 `treatment_semantics`，运行保存当时的语义快照。字段语义变化后，旧运行和提案标为过期。

本轮仅交付后端与接口，前端设置界面由另一项工作接入。真实千问连接与生成验收按用户要求延后；离线接口测试不能替代真实连通性证据。

项目创建和更新接口接受 `case: "carbon" | null`。碳市场稳健性约束仅由该标记或项目实际绑定资产的 DOI `10.17632/rrfwny7byp.1` 触发；仅上传/登记资产、标题或研究方向出现碳相关字样都不会触发。案例标记变更会使下游过期。

### 第五轮后端接口约定

- 候选生成及方案起草按最新方案绑定查找项目数据；未绑定且 `case=carbon` 时使用已登记的“碳市场企业面板 · Mendeley V1”。有数据时传入 `dataset_fields`（name、label、type、semantics、level、missing_rate），否则省略。不可由已有字段和白名单公式构造的概念应写入边界。
- 方案可带 `suggested_binding: {变量名: {field | formula}}`。`GET /api/plans/{id}/bindings` 在尚未保存绑定时返回预填建议及 dataset_id、confirmed=false、note；已有绑定优先。新版本只继承同名变量及数据资产，必须重新确认。预填与建议都不代表已保存或确认。
- `case=carbon` 起草固定为 policy_causal：行业同群暴露、绿色发明对数结果及总资产对数/杠杆率/资产收益率控制，默认四项稳健性由案例模块提供。确认时解析稳健性中的方案变量别名；有可用数据时校验真实字段，无法解析返回中文 422。尚无数据时仅能校验公式语法；完整绑定被确认时再校验实际字段。新增已在基准中的控制变量会被拒绝。
- 复算返回 `main_consistent`；整体 consistent 只覆盖主模型及原先成功的稳健性。原先失败项仍在 rows 中标为 failed、origin=analysis。主结论仅以主模型复算作为复算门槛，其余稳健性、置换、前趋势规则继续独立适用。
- 提案接口返回 `narrative_status: complete | partial | null` 与 `narrative_errors`。旧提案未知状态为 null。失败原因含 section、snippet、rule，结果解读另含 claim_id；两次仍未通过的部分才用默认说明，合格章节/解读保留。年份也使用 `dataset.year_min/year_max` 占位符，企业数使用 `dataset.n_units`。本轮未接入前端状态展示。
- 文献联合检索先去重，按各来源及各查询的相关性名次做倒数名次融合；新卡默认仅纳入排序前 40 条，其他卡仍可手动纳入。重新检索不会覆盖已有卡的手工纳入/排除状态。

### 第六轮后端接口约定

- 数字校验排除常见非数量术语、字段标识、公式和反引号代码；中文数字需带量词/单位才触发。未注入的真实数量仍被拦截，否定因果语境不作为肯定因果表述。
- 提案 `narrative_failures` 为 `[{section, reason}]`，同节多条规则与段落摘要合并。`narrative_errors` 暂保留一版，作为同结构兼容别名；数据库中的原始诊断不改写，旧提案也在读取时转换。
- 继承绑定返回 `inherited_from`（来源方案 ID），未确认时 note 为“继承自 vN，请重新确认”。历史未知来源为 null，不猜测来源；重新确认后 note 显示已确认。
- 方案 PATCH 与确认复用稳健性参数校验，非法编辑返回中文 422，既不保存新版本也不使下游过期。空 args 的 drop_controls 在保存前展开为基准控制变量名列表。
