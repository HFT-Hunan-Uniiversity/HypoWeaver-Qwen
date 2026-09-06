# Research Graph v0.2 设计说明

## 1. Schema 的职责

`research_graph` 不是单纯知识库，而是 Group1 的共同证据底座。它需要同时支持：

1. 回查论文、政策和数据说明；
2. 识别研究领域、研究流派、热点、常用模型与方法；
3. 聚合支持、反对、不显著和异质性发现；
4. 识别研究空白；
5. 向 E 提供可追溯的检索与图谱证据，支撑空白识别和可证伪假设生成。

JSON Schema：`schemas/research_graph.schema.json`，当前版本 `0.2.0`。

## 2. 顶层对象

|字段|作用|
|---|---|
|`graph_id`|同一逻辑图谱的稳定身份|
|`snapshot_id`|一次不可变图谱快照|
|`as_of`|该图谱包含资料的截止时间|
|`scope`|主题、语言、文档类型和年份范围|
|`build`|代码、配置、输入 schema、run ID、source watermark 和父快照|
|`nodes`|来源、知识、分析和发现节点|
|`edges`|节点间的有向关系|
|`evidence`|统一证据仓，每个节点/边只引用 evidence ID|
|`quality_summary`|事实边回查率、证据核验率和未归一实体数量|
|`statistics`|可重算的数量或统计，不作为原始事实|

## 3. 四个严格分离的图层

### Source：来源层

|节点类型|含义|
|---|---|
|`paper`|论文；未完整入库的引用论文可先作为 stub|
|`policy_document`|一份有版本、状态和发布机构的政策文件|
|`report`|ESG 报告、年报、研报等来源文档|
|`dataset`|论文使用或 A 登记的实际数据来源|
|`author`、`institution`、`venue`|作者、机构和期刊/会议|

来源层保存“材料是谁、何时发布、哪一版、从哪里获取”，不直接表达研究推理。

### Knowledge：可核验知识层

|节点类型|含义|
|---|---|
|`research_field`|稳定上位领域，如绿色信贷、ESG 与资产定价|
|`topic`|更细研究主题|
|`theory`|理论框架|
|`mechanism`|作用机制，如信息不对称、融资约束|
|`variable`|研究构念或变量；角色不固化|
|`measure`|变量的具体测量/构造，如 SA 指数、绿色专利数|
|`method`|研究方法，如文本分析、案例研究|
|`model`|模型或模型设定，如固定效应、中介模型、分类模型|
|`identification_strategy`|因果识别策略，如 DID、IV、RDD、事件研究|
|`policy_instrument`|政策中抽取出的工具或机制|
|`finding`|某篇论文报告的一条研究发现|
|`limitation`|某篇论文明确提出的局限|
|`population`、`context`|研究对象与地区/行业/制度情境|

### Analytics：研究版图层

|节点类型|含义|
|---|---|
|`research_stream`|由引用、文本和研究实体共同聚类形成的研究流派|
|`trend_snapshot`|某流派/领域/模型在给定时间窗的增长与热度|
|`controversy`|由多条方向不一致的 Finding 聚合形成的争议|

Analytics 节点只能是 `computed`、`inferred` 或人工 `curated`，不能标为 `extracted`。每个节点都要保存 derivation。

### Discovery：发现与交接层

|节点类型|含义|
|---|---|
|`research_gap`|通过信号、证据和最新检索确认的候选空白|
|`hypothesis`|围绕 Gap 形成的候选可证伪假设|

Discovery 结果不得反向污染原始事实。完整载荷分别保存为 `GapCard` 和 `HypothesisCard`；E 负责形成卡片，D 负责科学判断与引用核验。

## 4. 核心关系

### 来源结构

```text
Paper -AUTHORED_BY-> Author
Author -AFFILIATED_WITH-> Institution
Paper -PUBLISHED_IN-> Venue
Paper -CITES-> Paper
PolicyDocument -AMENDS/SUPERSEDES-> PolicyDocument
PolicyDocument -CONTAINS_INSTRUMENT-> PolicyInstrument
```

### 单篇研究结构

```text
Paper -STUDIES_FIELD/TOPIC-> Field/Topic
Paper -USES_THEORY-> Theory
Paper -PROPOSES_MECHANISM-> Mechanism
Paper -USES_VARIABLE-> Variable
Paper -USES_MEASURE-> Measure
Paper -USES_METHOD/MODEL/IDENTIFICATION_STRATEGY-> ...
Paper -USES_DATASET-> Dataset
Paper -EVALUATES_POLICY-> PolicyDocument/PolicyInstrument
Paper -REPORTS_FINDING-> Finding
Paper -REPORTS_LIMITATION-> Limitation
```

### 变量、测量与发现

```text
Variable -MEASURED_BY-> Measure
Measure -DERIVED_FROM-> Dataset
Variable -PROXIED_BY-> Variable/Measure/Dataset

Finding -HAS_PREDICTOR-> Variable/Policy
Finding -HAS_OUTCOME-> Variable
Finding -HAS_MEDIATOR/MODERATOR-> Variable
Finding -HAS_MECHANISM-> Mechanism
Finding -SUPPORTS/CONTRADICTS-> Finding
```

Finding 必须保留论文、样本、方向、显著性、方法上下文和证据，不能把“X 影响 Y”直接当作全局真理。

### 研究版图

```text
Paper -ASSIGNED_TO_STREAM-> ResearchStream
ResearchStream -STREAM_IN_FIELD-> ResearchField
ResearchStream -STREAM_FOCUSES_ON-> Topic/Mechanism/Variable
ResearchStream -STREAM_USES_METHOD/MODEL-> Method/Model
ResearchStream -EVOLVES_INTO-> ResearchStream
TrendSnapshot -TREND_OF-> Stream/Field/Topic/Model
Finding -INDICATES_CONTROVERSY-> Controversy
```

### 空白与假设

```text
Finding/Limitation/Trend/Policy -INDICATES_GAP-> ResearchGap
ResearchGap -GAP_CONCERNS-> Topic/Mechanism/Variable/Model/Context
ResearchGap -ENABLED_BY-> Dataset/Measure/Policy

Hypothesis -ADDRESSES_GAP-> ResearchGap
Hypothesis -HAS_PREDICTOR/OUTCOME/MEDIATOR/MODERATOR/MECHANISM-> ...
Hypothesis -SUPPORTED_BY_EVIDENCE/CHALLENGED_BY_EVIDENCE-> Finding/Policy/Trend
Hypothesis -RECOMMENDS_METHOD/MODEL/IDENTIFICATION_STRATEGY/DATASET-> ...
```

## 5. 每个节点和边的公共字段

|字段|规则|
|---|---|
|`id`|稳定、机器可用，不以自然语言名称作为唯一身份|
|`type`、`layer`|类型和四层归属必须一致|
|`origin`|`extracted / curated / computed / inferred` 四选一|
|`review_status`|`unreviewed / auto_validated / human_verified / rejected`|
|`confidence`|0–1；不能代替审核状态|
|`version`|该对象的版本|
|`validity`|发现时间与有效期；政策尤其需要 valid_from/to|
|`source_profile_ids`|产生该对象的 Gold Profile|
|`evidence_ids`|至少一条证据；不得引用 rejected evidence|
|`derivation`|computed/inferred 对象必须提供算法、版本、输入快照、输入节点/边、参数和 prompt hash|
|`properties`|类型特有属性；不能把关键溯源信息只藏在这里|

## 6. Evidence 对象

Evidence 不是只保存一段 quote，还要说明它是什么证据：

|字段|含义|
|---|---|
|`source_type`|论文全文/摘要、政策文本、数据登记、图谱快照等|
|`evidence_type`|直接引文、元数据、表格单元、派生统计、人工标注或设计决策|
|`evidence_level`|`primary_source / metadata / derived / design`|
|`source_document_id + document_version`|对应哪份材料的哪一版|
|`content + content_hash`|证据内容与防篡改 hash|
|`retrieved_at + published_at`|获取时间和发布时间|
|`locator`|页、节、字符区间、表格行列|
|`verification_status`|是否已定位、交叉核验或拒绝|

项目设计文档可以支撑 taxonomy，但其 `evidence_level=design`，不能用于支撑论文结论或研究假设。

## 7. 研究热点为什么不能直接写入 Topic 属性

热点是时间相关的派生判断。正确方式是创建 `TrendSnapshot`：

```text
snapshot_id: landscape@2026-07-15
window: 2024-01-01 ~ 2026-07-15
baseline: 2021-01-01 ~ 2023-12-31
metrics:
  paper_growth_rate
  recent_paper_share
  citation_velocity
  policy_alignment
  method_diversity
  hotness_score
```

这样才能回答“截至何时、相对哪个时期变热”，也能在未来重算并比较趋势。

## 8. Schema 之外的三个正式产物

- `ResearchLandscapeSnapshot`：可复现的研究版图，不是一段 LLM 总结。
- `GapCard`：每个空白的现状、缺口、信号、正反证据、新颖性与数据可行性。
- `HypothesisCard`：E 生成的可证伪假设、机制、变量、证据、数据可行性与阻塞项；通过 D 的科学与引用审核后进入假设清单。

三者都引用 `graph_snapshot_id`，防止最终假设脱离确定的知识截止时间。
