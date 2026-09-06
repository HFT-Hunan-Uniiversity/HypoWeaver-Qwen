# 基础向量检索契约

`src/retrieve` 是与知识图谱解耦的检索层：它读取 `chunks.jsonl`，不读取或修改
`research_graph.json`。

默认的 `HashingEmbeddingBackend` 是无外部依赖、确定性的词法 hashing 基线，
只用于 CI、接口联调和离线回归；它不是生产语义检索方案。生产环境应接入实现相同
`EmbeddingBackend` 协议的 Qwen embedding 后端，并在 manifest 中固定模型 ID、版本、
维度与算法标识。索引格式、过滤器和返回契约不依赖具体 embedding 后端。

## 输入与哈希

每行至少包含：

```json
{"document_id":"doc:1","text":"chunk text"}
```

支持并原样贯通以下字段：

- 标识与版本：`chunk_id`、`evidence_id`、`release_id`、`asset_id`、
  `document_version`；
- 来源与权限：`access_level`、`license`、`source_type`；
- 定位：`locator`，以及兼容字段 `source_locator`、`section`、`page`、
  `start_char` / `block_char_start`、`end_char` / `block_char_end`、
  `source_block_ids`；
- 哈希：`content_hash`、`text_sha256`、`content_sha256`。

哈希语义：

- `text_sha256` 是 UTF-8 切片正文的 SHA-256；读取时必须重算并校验。
- `content_hash` 是历史兼容字段，等同 `text_sha256`；两者同时存在时必须相同。
- `content_sha256` 是上游原始资产或文档字节的 SHA-256。本层没有原资产字节，
  因而只校验 64 位十六进制格式并保留；实际内容一致性由资产摄取阶段验证。

输入没有 `chunk_id` 时，系统用
`document_id + document_version + text_sha256 + locator` 生成稳定 ID；没有
`evidence_id` 时从稳定 `chunk_id` 派生。

## CLI

构建完全离线的接口基线：

```powershell
python -m src.retrieve build `
  --chunks output/mini_loop/2026-07-22_green_finance_env_outcomes/C_index/chunks.jsonl `
  --index vector-index.json `
  --dimensions 384
```

搜索并组合精确匹配过滤器；每个过滤参数均可重复：

```powershell
python -m src.retrieve search `
  --index vector-index.json `
  --query "green finance renewable energy" `
  --top-k 5 `
  --document-id "doc:1" `
  --source-type "paper_fulltext" `
  --access-level "open" `
  --include-text
```

Python API 接受相同的三个过滤字段，值可以是字符串或字符串序列：

```python
response = index.search(
    "green transition risk",
    top_k=10,
    filters={
        "document_id": ["doc:1", "doc:2"],
        "source_type": "paper_fulltext",
        "access_level": "open",
    },
)
```

缺失的 `source_type` 或 `access_level` 在过滤时按 `unknown` 处理。过滤是严格字符串
匹配；传入不支持的字段会直接报错。

## 索引与返回契约

索引 manifest 记录输入文件 SHA-256、chunk 数、稳定 ID 策略、embedding 后端、模型
ID、算法、维度、cosine 相似度、权限级别计数和正文持久化策略。`snapshot_id` 由输入
hash 与模型/算法配置共同决定，同一输入和配置可以稳定复现。

搜索返回结果信封，而不是裸数组：

- `schema_version`；
- `index_snapshot_id`；
- 规范化查询的 `query_hash`，不回显原始查询；
- 规范化后的 `filter`；
- `results`：每项至少包含 `chunk_id`、`document_id`、`evidence_id`、`score`、
  `rank` 与 `locator`，并贯通可用的版本、哈希、权限、许可和来源元数据。

机器契约见 `schemas/retrieval_result.schema.json`，样例见
`samples/retrieval_result.seed.json`。图谱会把这里的 `evidence_id` 保存为
`research_graph.evidence[].upstream_evidence_id`，图内 `evidence.id` 仍保持全局唯一。

## 权限与正文安全

`access_level` 过滤器只缩小候选集合，**不是授权系统**。调用方仍须在检索前完成
身份鉴别与资源级授权。

本基线采用保守持久化策略：只有明确标为 `access_level="open"` 的 chunk 正文才写入
可携带索引文件。`restricted`、其他值或缺失权限的正文均不写入索引；CLI 即使指定
`--include-text`，也只返回 open 正文，其余结果仅给出 `text_redacted=true`。

这不表示含受限来源向量的索引可以公开。embedding、locator、哈希与元数据仍可能
泄露敏感信息，索引文件必须继承源资产的访问控制、许可与保留期限。任何对外发布的
索引都必须只从明确允许再分发的公开切片重新构建。

## 接入 Qwen embedding

适配器只需实现四项元数据与两个方法：

```python
class QwenEmbeddingBackend:
    backend_id = "qwen"
    model_id = "<固定的生产模型与版本>"
    algorithm = "qwen-embedding"
    dimensions = 1024

    def embed_documents(self, texts):
        return qwen_client.embed(texts)

    def embed_query(self, text):
        return qwen_client.embed([text])[0]
```

构建时传给 `build_index(..., backend=qwen_backend)`，加载时传给
`LocalVectorIndex.load(..., backend=qwen_backend)`。凭据、批处理、限流、重试和网络
调用由适配器负责，核心检索层保持无外部依赖。

生产切换后必须用人工标注查询集评估 Recall@k、nDCG@k、权限过滤、延迟和成本；
不得把 hashing 基线的检索质量当作生产验收标准。
