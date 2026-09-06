# 覆盖证明与研究空白声明门槛

> 合同版本：`coverage_certificate/1.0.0`  
> 机器 Schema：`schemas/coverage_certificate.schema.json`  
> 目的：在趋势、稀疏关系或研究空白被发布前，证明“搜索和抽取覆盖足以支持该类声明”。

## 1. 核心原则

覆盖证书证明的是一个**有边界的语料观察**，不是对全球文献的全知证明。所有缺失或空白声明必须同时绑定：

- `certificate_id`；
- `release_id` 与 `manifest_sha256`；
- 来源、语言、年份、文档类型和截止时间；
- 采集、去重、全文、解析、索引、字段抽取和检索协议版本；
- 与具体 `gap_type` 对应的准入决定。

安全表述示例：

> 在证书 `coverage-...` 定义的来源、语言、2020–2024 年期刊论文及截至时间范围内，未观察到满足条件 X 的研究；该结论不外推至证书范围之外。

禁止表述：

> “没有任何研究”“学界从未研究”“数据库为空所以不存在”。

## 2. 五种观察状态

任何字段或来源状态必须使用以下值，不能把 `null`、空数组或异常统一解释为“不存在”。

| 状态 | 精确定义 | 能否支持空白声明 |
|---|---|---|
| `observed_present` | 输入可用，适用的观察/抽取已执行，并发现至少一个实例 | 支持“存在”及覆盖统计 |
| `observed_absent` | 输入可用，适用的观察/抽取已成功执行，但实例数为零 | 仅在相关门槛通过时支持**语料范围内**的缺失声明 |
| `not_extracted` | 字段适用且输入可能存在，但抽取未运行、失败或质量不足 | 不支持；必须修复或降级声明 |
| `source_missing` | 来源、正文或必需输入不可得 | 不支持；不得改写成 `observed_absent` |
| `not_applicable` | 字段对该文档类型或本次问题不适用 | 从该字段可观测率分母排除，不支持存在或缺失判断 |

字段可观测率按以下公式计算：

```text
applicable = target - not_applicable
observable = observed_present + observed_absent
observability_rate = observable / applicable
presence_rate = observed_present / observable
```

当 `applicable=0` 时，两个 rate 必须为 `null`。`source_missing` 和 `not_extracted` 保留在适用分母中，防止用缩小分母美化覆盖。

## 3. 必须证明的九个覆盖维度

1. **来源**：预先登记 required/optional；required 来源缺失不能事后降为 optional。
2. **语言**：声明范围内每种语言的已知数量和未知语言数量。
3. **年份**：目标窗口逐年数量及未知年份；未知年份不能被静默排除。
4. **全文**：全文可用、仅元数据、权利阻断、来源缺失和不适用数量。
5. **解析**：只对实际取得全文的文档计算成功率；失败必须保留。
6. **索引**：只对解析成功文档计算索引成功率，并固定 `index_snapshot_id`。
7. **字段可观测率**：对方法、机制、样本、数据、模型、政策、结论方向等逐字段证明。
8. **去重**：记录输入记录、规范文档、精确/近似重复和未决候选；空白计数必须基于规范文档。
9. **检索饱和度**：保存查询集哈希、每轮新增唯一文档、停止阈值和连续低增益轮数。

主要比率：

```text
required_source_coverage = covered_required_sources / required_sources
language_coverage = covered_language_documents / target_documents
year_coverage = known_year_documents / target_documents
fulltext_coverage = fulltext_available / (target_documents - fulltext_not_applicable)
parsing_success = parse_success / parse_input
indexing_success = indexed_documents / index_input
dedup_resolution = resolved_candidate_pairs / duplicate_candidate_pairs
round_marginal_gain = new_unique_documents / cumulative_unique_documents_after_round
```

若去重候选对为零，则 `dedup_resolution_rate=1.0`；必须同时保存候选对计数，避免误解。所有算术约束由合同测试补充验证，因为 JSON Schema 本身不能表达跨字段加总。

## 4. 证书状态

| `coverage_status` | 含义 | 声明权限 |
|---|---|---|
| `draft` | 指标尚未全部计算 | 不允许 gap/absence 声明 |
| `coverage_ready` | 所有 blocking gate 通过 | 只允许 `allowed_gap_types` |
| `coverage_conditional` | blocking gate 通过，但部分非关键字段不足 | 允许列表内声明，其余必须显式标为 conditional/blocked |
| `coverage_blocked` | 至少一个关键门槛失败或未评估 | 不允许研究空白声明，只能报告覆盖缺陷 |
| `invalidated` | 算术、版本、证据或审计一致性失败 | 所有派生声明撤回并重算 |

`coverage_ready` 不代表十种 gap 全部可声明。准入以 `claim_gate.gap_type_decisions` 为准；例如全文覆盖合格也不能弥补政策文档完全不在语料范围内。

## 5. Gap 类型准入

合同沿用现有 GapCard 的十类：

`mechanism`、`data`、`population`、`context`、`method`、`model`、`policy`、`controversy`、`temporal`、`cross_stream`。

每类必须且只能有一个决定：

- `allowed`：相关覆盖维度和字段达到预设阈值；可以生成带范围限定的候选 gap。
- `conditional`：可生成“待补证”信号，不能进入已接受的研究空白结论。
- `blocked`：不得生成该类 gap；`blocked_by` 必须指出覆盖或字段原因。

最低逻辑依赖建议：

| Gap 类型 | 至少依赖 |
|---|---|
| `temporal` | 年份、去重、检索饱和度 |
| `method` / `model` | 全文、解析、对应字段可观测率、检索饱和度 |
| `mechanism` | 全文、机制字段、证据定位、检索饱和度 |
| `population` / `context` | 样本或地理字段可观测率 |
| `data` | 数据集/变量字段可观测率及来源覆盖 |
| `controversy` | finding 方向、证据核验、去重 |
| `policy` | 政策来源实际纳入；论文提到政策不能替代政策语料覆盖 |
| `cross_stream` | 研究领域/主题的稳定分配、去重和检索饱和度 |

## 6. 门槛计算与阻断

每个 `gate` 必须记录 observed、threshold、比较符、是否 blocking 及证据引用。状态规则：

- 任一 blocking gate 为 `failed` 或 `not_assessed`：证书必须为 `coverage_blocked`，`allowed_gap_types` 必须为空。
- 所有 blocking gate 通过，但某些非关键 gate 不足：可以是 `coverage_conditional`。
- `coverage_ready`：blocking gate 全部通过且 `blockers=[]`。
- 门槛必须在运行前确定并版本化；不得看到结果后调低阈值。

`blockers` 只记录真正阻止声明的问题；optional 来源失败、但不影响预先声明的 required-source 门槛时，应写入 `warnings`，不能伪造成完全无异常。

## 7. 检索饱和度

检索饱和度不是“检索到很多”，而是继续扩展查询时新增唯一文档已稳定低于阈值。证书必须保存：

- 查询集 SHA-256；
- 检索空间和来源；
- 每轮查询族、候选数、新增唯一文档、累计唯一文档；
- 最少轮次；
- 需要连续满足低增益的轮数；
- 固定停止规则。

若来源不可访问、查询日志丢失、去重未完成或轮数不足，状态必须为 `blocked`/`not_assessed`，不能标为 `saturated`。

## 8. 与现有图谱、GapCard 的衔接

本合同独立存在，不修改现有 `research_graph`、`research_landscape` 或 `gap_card` schema。当前衔接规则为：

1. 图谱/索引快照 ID 写入 `subject`。
2. GapCard 生成时，把 `certificate_id` 放入 `derivation.input_refs` 或同批发布 manifest。
3. GapCard 的 `gap_type` 必须出现在证书 `allowed_gap_types` 中。
4. `conditional` 只能成为待补证候选，不能进入 `accepted`。
5. 证书被 `invalidated` 或由新证书 supersede 后，依赖旧证书的 gap 必须重审。

## 9. 发布检查清单

- JSON Schema 通过；
- 所有计数、分母和 rate 通过算术检查；
- source/language/year/fulltext/parsing/indexing 数量能闭合；
- 每个字段五种状态之和等于目标文档数；
- allowed/conditional/blocked 三个 gap 集合互斥且覆盖十种类型；
- 每个 gap 决定与三份集合一致；
- blocking gate 与 `coverage_status`、`blockers` 一致；
- retrieval rounds 累计数与边际增益一致；
- `release_id`、manifest、图谱和索引快照仍可读取；
- 最终声明包含 `required_scope_qualifier`。

样例 `samples/coverage_certificate.seed.json` 是合成数据，只证明合同和算术自洽，不代表真实生产覆盖。

## 10. 无外部依赖的语义校验 CLI

JSON Schema 负责必填字段、类型、枚举、格式和额外字段；标准库校验器负责 Schema 无法表达的跨字段算术与状态机约束。发布前两者都必须通过，不能用语义校验器替代 Schema 校验。

```powershell
python src/coverage/validate_coverage_certificate.py samples/coverage_certificate.seed.json
python src/coverage/validate_coverage_certificate.py --json samples/coverage_certificate.seed.json
Get-Content -Raw samples/coverage_certificate.seed.json | python src/coverage/validate_coverage_certificate.py -
```

可以一次传入多个证书，或用 `-` 从标准输入读取一个证书。全部通过时退出码为 `0`；任一证书存在 JSON 读取错误、计数不闭合、rate 不一致或门禁冲突时退出码为 `1`；命令参数错误由 `argparse` 返回 `2`。`--json` 输出适合 CI 读取的结果数组，否则输出 `VALID` / `INVALID` 和逐条错误。

校验器 `src/coverage/validator.py` 仅使用 Python 标准库，并复算：

- 来源、语言、年份、全文、解析、索引和去重的计数闭合与 rate；
- 每个字段的五状态总数、适用数、可观测数、observability/presence rate 和关键字段最低可观测率；
- 每轮检索的连续轮号、累计唯一文档数、`marginal_gain`、最终累计数和饱和停止条件；
- 十种 gap 类型在 allowed/conditional/blocked 三集合中的互斥、完备、唯一决定和 `blocked_by`；
- gate 的 observed/threshold/比较结果，以及 blocking gate、`coverage_status`、`blockers`、`claim_gate.status` 和声明上限的一致性。

分母为零时，来源和流水线成功率采用空集合完备值 `1.0`；字段 observability/presence rate 必须为 `null`；尚无累计结果的空检索轮次其边际增益为 `0.0`。关键字段不得以 `not_applicable=target` 绕过可观测率门槛。

测试中的错误变异样例 `tests/contracts/fixtures/coverage_certificate.invalid-field-count.json` 把 seed 的摘要 `observed_absent` 从 10 改为 9，使五状态合计为 99；单元测试要求 CLI 对变异后的完整证书返回退出码 `1`。
