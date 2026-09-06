# `PaperProfile` 到 `ResearchGraph` 的映射

## 映射总览

| Profile 字段 | 图节点 | 图关系 | 备注 |
|---|---|---|---|
| `document` | `paper` | — | DOI 优先；无 DOI 时使用 A/B 共同维护的稳定 `document_id`，最后才回退到题名与年份 |
| `document.authors[]` | `author` | `paper -AUTHORED_BY-> author` | 无外部作者 ID 时按论文隔离并标记待归一，不自动跨论文合并同名作者 |
| `document.journal_or_source` | `venue` | `paper -PUBLISHED_IN-> venue` | 支持期刊/会议维度研究版图 |
| `citations[]` | `paper` stub | `paper -CITES-> paper` | 用于共被引、文献耦合和流派演化；被拒绝引用不得入图 |
| `research_fields[]` | `research_field` | `paper -STUDIES_FIELD-> field` | 稳定的上位领域 taxonomy |
| `topics[]` | `topic` | `paper -STUDIES_TOPIC-> topic` | 中英文同义词归一后跨论文复用 |
| `theories[]` | `theory` | `paper -USES_THEORY-> theory` | 理论与机制分开，避免把理论名当作作用路径 |
| `mechanisms[]` | `mechanism` | `paper -PROPOSES_MECHANISM-> mechanism` | 具体 Finding 若引用该机制，再建 `HAS_MECHANISM` |
| `variables[]` | `variable` | `paper -USES_VARIABLE-> variable` | 角色写入 `context.variable_roles`；定义、操作化和单位写在该论文的边属性上 |
| `measures[]` | `measure` | `paper -USES_MEASURE-> measure` | 变量通过 `MEASURED_BY` 连接测量，测量通过 `DERIVED_FROM` 连接数据集 |
| `methods[]` | `method` | `paper -USES_METHOD-> method` | 如文本分析、案例研究、计量分析 |
| `models[]` | `model` | `paper -USES_MODEL-> model` | 如固定效应模型、中介模型、分类模型 |
| `identification_strategies[]` | `identification_strategy` | `paper -USES_IDENTIFICATION_STRATEGY-> strategy` | 如 DID、IV、RDD、事件研究 |
| `datasets[]` | `dataset` | `paper -USES_DATASET-> dataset` | 后续与 A 的数据源登记实体对齐 |
| `policies[]` | `policy` | `paper -EVALUATES_POLICY-> policy` | 政策正式名称、发文机关、日期用于归一 |
| `findings[]` | `finding` | `paper -REPORTS_FINDING-> finding` | Finding 按论文隔离，不跨论文合并 |
| `finding.predictor_refs` | 已有 `variable` | `finding -HAS_PREDICTOR-> variable` | 效应方向和显著性保留在关系上下文 |
| `finding.outcome_refs` | 已有 `variable` | `finding -HAS_OUTCOME-> variable` | 同上 |
| `finding.mediator_refs` | 已有 `variable` | `finding -HAS_MEDIATOR-> variable` | 不把中介固化为节点类型 |
| `finding.moderator_refs` | 已有 `variable` | `finding -HAS_MODERATOR-> variable` | 不把调节固化为节点类型 |
| `finding.mechanism_refs` | 已有 `mechanism` | `finding -HAS_MECHANISM-> mechanism` | 机制必须有原文证据 |
| `limitations[]` | `limitation` | `paper -REPORTS_LIMITATION-> limitation` | 节点属性保留空白类别 |
| `future_work[]` | 暂存在 `paper.properties` | — | 样本稳定后再决定是否与 limitation 合并或单列节点 |

## 为什么不直接建立 `X -AFFECTS-> Y`

直接把论文结论压成全局因果边，会丢失四类关键信息：是哪篇论文、什么样本、什么方法、结论是否显著。它还会让互相矛盾的论文覆盖彼此。

v0.2 继续采用断言节点：

```text
Paper P -REPORTS_FINDING-> Finding F
Finding F -HAS_PREDICTOR-> Variable X
Finding F -HAS_OUTCOME-> Variable Y
Finding F -HAS_MECHANISM-> Mechanism M
```

`Finding F` 自身记录方向、显著性、子样本、条件和原文证据。跨论文的 `X -> Y` 视图由查询层聚合生成，可同时统计正向、负向、不显著和异质性结果。

## 实体归一边界

- `paper`、`finding`、`limitation` 按论文隔离。
- `topic`、`theory`、`mechanism`、`variable`、`method`、`dataset`、`policy` 可跨论文归一。
- v0.2 只做保守自动归一：Unicode 标准化、大小写和连续空白归一、完全同名合并。
- 缩写、多语言和近义词只在人工词表确认后通过 `aliases` 或 `SAME_AS` 合并。
- 不让大模型直接删除或覆盖实体；低置信度候选先保留为两个节点，等待人工审核。

## 证据传播

- Profile 的局部 `evidence_id` 在入图时转换为全局稳定 ID。
- 节点和边都只保存 `evidence_ids`，完整原文位置统一放在图的 `evidence[]` 中。
- 被标记为 `rejected` 的证据不得被任何节点或边引用。
- 项目设计文档可以支撑 `curated` taxonomy，但 `scientific_evidence=false`，不可用于论证研究发现。
- 新 Profile 应显式填写 `source_type`、`evidence_type` 与 `evidence_level`；旧 Profile 的定位推断只用于兼容迁移，不是正式生产规则。
- Finding、Limitation、Future Work、理论、机制、变量/测量、模型和识别策略必须至少引用一条已定位并核验的正文证据。
- 摘要即使被切成 chunk，仍是 `paper_abstract + metadata`；它不能因存在 `chunk_id` 自动升级成全文证据。
- `paper.properties.research_question_evidence_ids` 和 `future_work_items[].evidence_ids` 保留问题与未来研究建议的逐项证据映射，供 Gap 发现审计。

## 正式构建与兼容模式

不传 `--run-manifest` 只适合旧 Profile 迁移和本地调试；它保留 locator-based 的兼容
推断。正式发布必须传 `schemas/graph_build_manifest.schema.json` 对应的 manifest，此时：

- 每条 Profile evidence 必须显式填写 `source_type/evidence_type/evidence_level`；
- `profile_set_sha256` 必须等于按 `profile_id` 排序后的 Profile 集合 canonical SHA-256；
- `build_timestamp`、`pipeline_run_id`、`as_of` 和输入 manifest hash 被固定；
- 增量运行必须同时固定 `base_snapshot_id` 和 `base_graph_sha256`；
- 节点、边和证据按稳定 ID 规范排序，`snapshot_id` 由最终内容寻址生成；
- 生成结果写盘前再次经过完整 JSON Schema 与语义校验。

可先用以下代码计算 Profile 集合 hash；校验失败也会打印实际 hash：

```python
from src.reason.build_research_graph import profile_set_sha256

profile_hash = profile_set_sha256(profiles)
```

正式命令：

```powershell
python -m src.reason.build_research_graph `
  --input-dir profiles `
  --run-manifest graph-build-manifest.json `
  --output research-graph.json
```
