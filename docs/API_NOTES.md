# 后端接口约定（按开发轮次）

> 本文件收录原 README 中按轮次记录的后端接口约定，内容原样保留，便于开发者查阅。
> 面向使用者的说明见根目录 [README](../README.md)。

## 后续新增（2026-10，ui-merged 分支）

- `POST /api/proposals/{id}/confirm`：确认提案，写入 `confirmed_at`（重复确认保留首次时间）。提案已过期（`stale`）时返回中文错误，需先重新生成。确认后 `GET /api/projects` 中该项目的 `completed` 为 `true`，总览里“研究提案”阶段显示“已确认”。
- `case` 以 `legacy:` 开头的项目（由 `scripts/import_legacy_cases.py` 导入的旧案例）为只读展示：总览各阶段直接显示已完成，提案各节 `editable=false`，`POST /api/projects/{id}/proposals` 返回 409，不会重新生成。
- 提案固定为十项：problem 待研究问题、rationale 解决思路、techniques 必要的技术手段、datasets 数据集、title 标题、abstract 摘要、methods 方法论、experiments 实验设计、results 实验结果、references 参考论文。其中 results 与 references 由系统根据运行结果和证据卡生成，只读；其余八项由模型撰写并经数字与措辞校验。旧版九节提案（overview、question……）仅用于查看历史版本。

## 第二轮后端接口约定

- `GET /api/settings/llm` → `{base_url, llm_model, configured}`，不包含密钥，也不会主动调用模型。
- `PUT /api/settings/llm` 接受可选的 `base_url`、`api_key`、`llm_model`；省略密钥保留现值，传空字符串清除。保存后后续请求使用新配置，进行中的任务保持启动时配置。默认地址和模型集中在后端 Settings / `.env.example`，模型名不限制枚举。未知字段（包括旧名 `model`）返回 422 和中文提示，配置不会被部分写入。
- 未配置时，生成查询、候选、方案、绑定建议、提案及连接测试均直接返回 HTTP 409 / `llm_not_configured`，不会创建待执行任务。前端可先 GET 配置，再跳转设置页填写。
- 候选集、方案和提案版本统一用 `llm_model` 记录生成模型；提案的 `interpretation` 保存 `{llm_model, paragraphs, status}`。方案的 `model` 只表示统计模型设定。手工新建版本继承该来源；历史记录未知模型为 null，不补猜测值。
- `PATCH /api/datasets/{id}/fields/{name}` 接受 `semantics`、`level`；方案接口返回 `treatment_semantics`，运行保存当时的语义快照。字段语义变化后，旧运行和提案标为过期。

本轮仅交付后端与接口，前端设置界面由另一项工作接入。真实千问连接与生成验收按用户要求延后；离线接口测试不能替代真实连通性证据。

项目创建和更新接口接受 `case: "carbon" | null`。碳市场稳健性约束仅由该标记或项目实际绑定资产的 DOI `10.17632/rrfwny7byp.1` 触发；仅上传/登记资产、标题或研究方向出现碳相关字样都不会触发。案例标记变更会使下游过期。

## 第五轮后端接口约定

- 候选生成及方案起草按最新方案绑定查找项目数据；未绑定且 `case=carbon` 时使用已登记的“碳市场企业面板 · Mendeley V1”。有数据时传入 `dataset_fields`（name、label、type、semantics、level、missing_rate），否则省略。不可由已有字段和白名单公式构造的概念应写入边界。
- 方案可带 `suggested_binding: {变量名: {field | formula}}`。`GET /api/plans/{id}/bindings` 在尚未保存绑定时返回预填建议及 dataset_id、confirmed=false、note；已有绑定优先。新版本只继承同名变量及数据资产，必须重新确认。预填与建议都不代表已保存或确认。
- `case=carbon` 起草固定为 policy_causal：行业同群暴露、绿色发明对数结果及总资产对数/杠杆率/资产收益率控制，默认四项稳健性由案例模块提供。确认时解析稳健性中的方案变量别名；有可用数据时校验真实字段，无法解析返回中文 422。尚无数据时仅能校验公式语法；完整绑定被确认时再校验实际字段。新增已在基准中的控制变量会被拒绝。
- 复算返回 `main_consistent`；整体 consistent 只覆盖主模型及原先成功的稳健性。原先失败项仍在 rows 中标为 failed、origin=analysis。主结论仅以主模型复算作为复算门槛，其余稳健性、置换、前趋势规则继续独立适用。
- 提案接口返回 `narrative_status: complete | partial | null` 与 `narrative_errors`。旧提案未知状态为 null。失败原因含 section、snippet、rule，结果解读另含 claim_id；两次仍未通过的部分才用默认说明，合格章节/解读保留。年份也使用 `dataset.year_min/year_max` 占位符，企业数使用 `dataset.n_units`。本轮未接入前端状态展示。
- 文献联合检索先去重，按各来源及各查询的相关性名次做倒数名次融合；新卡默认仅纳入排序前 40 条，其他卡仍可手动纳入。重新检索不会覆盖已有卡的手工纳入/排除状态。

## 第六轮后端接口约定

- 数字校验排除常见非数量术语、字段标识、公式和反引号代码；中文数字需带量词/单位才触发。未注入的真实数量仍被拦截，否定因果语境不作为肯定因果表述。
- 提案 `narrative_failures` 为 `[{section, reason}]`，同节多条规则与段落摘要合并。`narrative_errors` 暂保留一版，作为同结构兼容别名；数据库中的原始诊断不改写，旧提案也在读取时转换。
- 继承绑定返回 `inherited_from`（来源方案 ID），未确认时 note 为“继承自 vN，请重新确认”。历史未知来源为 null，不猜测来源；重新确认后 note 显示已确认。
- 方案 PATCH 与确认复用稳健性参数校验，非法编辑返回中文 422，既不保存新版本也不使下游过期。空 args 的 drop_controls 在保存前展开为基准控制变量名列表。
