# RAG-Graph 技术架构（2026-08-21）

> 本文档反映当前项目的真实技术栈，已移除 GROBID、Neo4j、LlamaIndex、PostgreSQL
> 等旧规划中但实际未使用的组件。覆盖从 PDF 解析 → 清洗 → 切片 → 向量化 → KG 抽取
> → 混合检索 → HTTP API 服务全链路。

---

## 1. 架构总览

```
PDF
  │
  ▼
[MinerU 云端 API] ──── 每日 2000 页免费额度
  │
  ▼
[清洗 + 章节标记注入] ── #【摘要】#【理论假设】#【实证】#【结论】
  │
  ▼
cleaned/*.md + cleaned_meta/*.json
  │
  ├──────────────────────────────────┬──────────────────────┐
  ▼                                  ▼                      ▼
[切片引擎 chunker]           [KG 抽取 qwen-max]        [MinerU 元数据]
  │                                │
  ▼                                ▼
[BGE 嵌入]                   artifacts/kg/*.kg.json
  │                                │
  ▼                                ▼
[向量存储]                    [networkx 内存图]
 hdf5（本地+云上统一）          GraphRetriever（单例）
  │                                │
  └──────────────┬─────────────────┘
                 ▼
         [混合检索 HybridRetriever]
          向量语义 + 图谱因果路径
                 │
                 ▼
         [回答生成 AnswerEngine]
          qwen-max 结构化输出
                 │
                 ├──→ qa_runner.py（CLI）
                 │
                 └──→ src/api/server.py（FastAPI HTTP API）
```

---

## 2. 数据来源与获取

| 来源 | 方式 | 说明 |
|---|---|---|
| 论文元数据 | 服务器本地 Feed API | `http://127.0.0.1:4173/api/feed/articles?scope=green&limit=500`，无需 COS 凭据 |
| 全文 PDF | COS 下载工具 | 需要 `green-finance-reader` COS 凭据 + npm `handoff:download` 工具 |
| 下载脚本 | `scripts/download_papers.py` | 输出到 `input/` 目录，支持增量/全量两种模式 |
| 批量解析 | `scripts/parse_all.py` | 遍历 `input/*.pdf`，调用 MinerU API，输出到 `cleaned/` 和 `cleaned_meta/` |

> **跑批时间估算：** 500 篇 × 平均 20 页 = 10000 页，受每日 2000 页免费额度限制约需 5 天。`run_pipeline.sh` 支持断点续跑，每日额度用完后自动暂停，次日继续。

---

## 3. 核心组件

### 3.1 文档解析 — MinerU

| 项 | 说明 |
|---|---|
| 服务 | `src/parse/adapters/mineru_api.py` |
| 方式 | 云端 API（签名上传 → 轮询 → 下载 zip） |
| 额度 | 每日 2000 页免费，`pipeline` 模型 |
| 产出 | `full.md`（正文 Markdown）+ `content_list.json`（结构化数据） |
| 配额 | 本地 `mineru_quota.json` 跟踪，每日自动重置 |
| 替代 | 无本地解析，不依赖 GROBID / Docling / PaddleOCR |

### 3.2 清洗与章节标记

| 项 | 说明 |
|---|---|
| 服务 | `src/parse/clean/cleaning.py` |
| 处理 | 去页眉页脚 → 段落合并 → 特殊字符归一 → 数值标准化 → 注入章节标记 |
| 章节标记 | `#【摘要】` `#【理论假设】` `#【实证】` `#【异质性】` `#【结论】` 等 |
| 输出 | `cleaned/{doc_id}.md`（带章节标记的 Markdown） |
| 元数据 | `cleaned_meta/{doc_id}.json`（ParsedDoc 格式） |

### 3.3 切片引擎

| 项 | 说明 |
|---|---|
| 服务 | `src/retrieve/chunker.py`（自研，非 LlamaIndex） |
| 分层 | Layer 0：元数据（标题/摘要/关键词，整块不切） |
| | Layer 1：语义层（按 `#【】` → `##` 标题 → 段落，最长 512 token） |
| | Layer 2：滑动窗口层（256 token 窗口，64 token 重叠） |
| 输出 | `ChunkPayload` 列表（含 chunk_id/chunk_level/section_title 等） |
| chunk_id 格式 | `{doc_id}__{level}_{seq:04d}` |

### 3.4 嵌入模型

| 项 | 说明 |
|---|---|
| 服务 | `src/embedding.py` |
| 模型 | `BAAI/bge-small-zh-v1.5`（512 维，CPU 可跑） |
| 加载 | 首次调用时懒加载（SentenceTransformers） |
| 缓存 | 优先加载 `models_cache/models/BAAI--bge-small-zh-v1.5/` 本地权重 |
| 降级（已实现） | 模型不可用时，降级为字符 n-gram 哈希特征向量（零依赖兜底），用于流程调试不中断 |
| 大小 | 权重约 184 MB，不进 Git |

### 3.5 向量存储

#### 当前选择：hdf5（本地 + 云上统一）

| 项 | 说明 |
|---|---|
| 后端 | `VectorStoreH5`（`src/vector/store.py`） |
| 文件 | `artifacts/vector/all_store.h5` |
| 维度 | 512，余弦相似度 |
| 接口 | `open() / add() / search() / count() / close() / all_metas() / get_meta()` |

#### 为什么现阶段选 hdf5 而不是 Qdrant

| 对比项 | hdf5 | Qdrant |
|---|---|---|
| 额外服务 | 无，纯文件读写 | 需运行容器，占用 ~1.5 GB 内存 |
| 500 篇存储 | ~75 MB（500 篇 × 75 chunks × 512 dims × 4 bytes） | 独立存储 |
| 检索速度 | 全量暴力扫描，numpy 矩阵运算 < 10 ms | 索引检索，更快 |
| 部署复杂度 | 零，pip install h5py 即可 | 需 Podman 容器 + 配置 api_key |
| 过滤能力 | 需自行实现（Python 侧过滤） | 内置 payload 过滤 |
| 迁移成本 | 文件拷贝即可 | 需导出/导入 |

**结论：现阶段 hdf5 更合适。** 云服务器内存上限 3.5 GB，省掉 Qdrant 容器的 1.5 GB 意味着 Python + BGE 有更充裕的运行空间。500 篇论文的向量总量约 75 MB，hdf5 暴力扫描性能完全够用。未来如果数据量超过 2000 篇或需要生产级高并发，再迁移到 Qdrant。

#### 架构预留

工厂函数 `get_store()` 支持按环境变量 `VECTOR_BACKEND` 切换后端，迁移到 Qdrant 时无需改动上层代码：

```python
store = get_store()                    # 默认 hdf5（当前）
store = get_store(backend="qdrant")    # 未来切换 Qdrant
```

#### 并发安全说明

h5py 文件对象**非线程安全**。多请求并发读取同一个 h5py File 可能导致数据错乱或崩溃。解决方案：

- `server.py` 启动时创建 `threading.Lock`，每次 `/search` 请求加锁后读取 hdf5
- 或每个请求单独打开 hdf5 文件（开销可接受，约 1-2 ms）

### 3.6 知识图谱

#### 三元组抽取

| 项 | 说明 |
|---|---|
| 服务 | `src/kg/extractor.py` + `src/kg/entities.py` |
| LLM | `qwen-max`（DashScope API），temperature=0.1 |
| 实体类型 | 论文（Paper）、作者（Author）、绿色金融概念（Concept）、计量方法（Method）、数据集（Dataset） |
| 关系类型 | 11 种因果关系：`PROMOTE` / `INHIBIT` / `CAUSE` / `CORRELATE` / `MODERATE` / `MEDIATE` / `LEAD_TO` / `CONTRIBUTE_TO` / `REDUCE` / `ENHANCE` / `WEAKEN` + `CO_OCCUR`（共现） |
| 共现补边 | 同句共现（`CO_OCCUR`），零 token 成本 |

#### 存储与检索

| 项 | 说明 |
|---|---|
| 持久化 | `artifacts/kg/{doc_id}.kg.json`（每篇一个 JSON 文件） |
| 运行时 | `GraphRetriever`（`src/retrieve/graph_retriever.py`） |
| 数据结构 | networkx `DiGraph`，全部 `*.kg.json` 合并加载到内存 |
| 节点前缀 | `paper:` / `author:` / `concept:` / `method:` / `dataset:` |
| 检索接口 | `get_concept_relations(name)` → 因果/共现边列表 |
| | `search_entity(query)` → 模糊实体搜索 |
| | `get_neighborhood(node_id, depth)` → 邻域子图 |
| 不依赖 | **无 Neo4j**，全内存图，启动时加载 |

### 3.7 ChunkCache（文本片段缓存）

检索命中 `chunk_id` 后，需要从 `cleaned/{doc_id}.md` 读取原文片段填充到检索结果中。ChunkCache 负责这个过程：

| 项 | 说明 |
|---|---|
| 服务 | `src/retrieve/hybrid.py` 中的 `ChunkCache` 类 |
| 策略 | 惰性加载 + 按 doc_id 缓存：首次命中某篇论文时，读取其 `cleaned/*.md`，按 `chunk_id` 定位原文 |
| 缓存 | 内存字典 `{chunk_id: text}`，按需加载不预加载 |
| 生命周期 | 每次 `/search` 请求复用，随进程存在 |

### 3.8 混合检索

| 项 | 说明 |
|---|---|
| 服务 | `src/retrieve/hybrid.py` |
| 向量路 | 语义 Top-K 命中原文 chunk（文证） |
| 图谱路 | 问题实体链接 → 概念关系/方法关联（理证） |
| 融合 | 分别去重打 tag，拼成结构化上下文 |
| 输出 | `{question, entities, vector_hits, graph_hits, context}` |

### 3.9 回答生成

| 项 | 说明 |
|---|---|
| 服务 | `src/reason/answer_engine.py` |
| LLM | `qwen-max`（DashScope API） |
| 输入 | 混合检索的结构化上下文（文证 + 理证） |
| 输出 | `{answer, conclusion, confidence, evidence, graph_paths, source_papers}` |
| 约束 | 答案必须基于检索证据，不能编造；证据不足时如实说明 |

### 3.10 HTTP API 服务

| 项 | 说明 |
|---|---|
| 服务 | `src/api/server.py`（FastAPI，待创建） |
| 启动 | 应用启动时加载 GraphRetriever + VectorStore（单例，全局复用） |
| 端口 | 8002 |

#### `POST /search` 接口设计

```
请求:
{
  "question": "绿色金融政策如何影响企业技术创新",
  "top_k": 8,
  "max_graph_edges": 10
}

响应:
{
  "question": "绿色金融政策如何影响企业技术创新",
  "answer": "综合回答（300-500字）...",
  "conclusion": "一句话核心结论",
  "confidence": "high",
  "evidence": [
    {"source_doc": "doc_001", "section": "实证", "snippet": "...", "score": 0.92}
  ],
  "graph_paths": [
    {"source": "绿色金融政策", "relation": "PROMOTE", "target": "绿色技术创新", "confidence": 0.85}
  ],
  "source_papers": ["论文1", "论文2"],
  "elapsed_s": 3.2
}
```

#### `GET /health` 接口

```
响应:
{
  "status": "ok",
  "graph_nodes": 1234,
  "graph_edges": 890,
  "vector_count": 37500,
  "embedder_ready": true
}
```

#### 启动方式

```bash
# 本地开发
uvicorn src.api.server:app --reload --port 8002

# 云上部署
uvicorn src.api.server:app --host 0.0.0.0 --port 8002
```

> 注意：本项目不使用 Qdrant 和 Neo4j，`/search` 直接使用本地 hdf5 + networkx 内存图，无需任何外部容器依赖。

### 3.11 CLI 入口

| 项 | 说明 |
|---|---|
| 服务 | `src/qa_runner.py` |
| 用法 | `python src/qa_runner.py "问题"` 或交互模式 |
| 输出 | 回答 + 结论 + 置信度 + 图谱路径 + 原文证据 + 涉及论文 |

---

## 4. 批处理脚本

| 脚本 | 作用 | 调用方式 |
|---|---|---|
| `run_pipeline.sh` | 云上一键跑批，串联以下所有步骤 | `bash run_pipeline.sh --incremental` |
| `scripts/download_papers.py` | 从 Feed API + COS 获取论文 PDF | `python scripts/download_papers.py --output-dir ./input` |
| `scripts/parse_all.py` | MinerU 批量解析 PDF → Markdown | `python scripts/parse_all.py` |
| `scripts/report_status.py` | 动态扫描，输出系统状态报告 | `python scripts/report_status.py` |
| `scripts/rebuild_status.py` | 从已有产出重建 `processed_docs.json` | `python scripts/rebuild_status.py` |
| `scripts/sample_check.py` | 抽样质检（随机抽取 N 篇检查 KG + 向量） | `python scripts/sample_check.py 10` |
| `scripts/vectorize_all.py` | 切片 → BGE 嵌入 → 写入向量存储 | `python scripts/vectorize_all.py` |

---

## 5. 数据流

```
PDF  →  MinerU  →  清洗+章节标记  →  cleaned/*.md
                                        │
                          ┌─────────────┴─────────────┐
                          ▼                           ▼
                    chunker 切片                  KG 抽取(qwen-max)
                          │                           │
                          ▼                           ▼
                    BGE 嵌入                  artifacts/kg/*.kg.json
                          │                           │
                          ▼                           ▼
                    VectorStore(H5)             GraphRetriever
                    artifacts/vector/           (networkx 内存图)
                    all_store.h5                     │
                          │                           │
                          └────────┬──────────────────┘
                                   ▼
                          HybridRetriever.search()
                                   │
                                   ▼
                          AnswerEngine.answer()
                                   │
                          ┌────────┴────────┐
                          ▼                  ▼
                  qa_runner.py        src/api/server.py
                  (CLI 输出)          (HTTP JSON 响应)
```

---

## 6. 已明确不使用的组件

| 组件 | 说明 | 原因 |
|---|---|---|
| GROBID | 论文元数据/引用抽取 | MinerU 已覆盖正文解析，引用关系暂非核心需求 |
| Neo4j | 图数据库 | 500 篇 KG 约 10-20k 边，networkx 内存图足够，省一个容器 |
| Qdrant（当前阶段） | 向量数据库 | hdf5 足够承载 500 篇 ~75 MB 向量，省 1.5 GB 容器内存 |
| LlamaIndex | 检索框架 | 自研 chunker/retriever/answer_engine 更灵活，无框架锁定风险 |
| PostgreSQL / pgvector | 向量数据库 | 本地 hdf5，不引入数据库依赖 |
| Docling | PDF 解析 | MinerU 统一处理 |
| PaddleOCR | OCR | MinerU 内置 OCR |
| ChromaDB / BM25 | 双路索引 | 自研混合检索替代 |

---

## 7. 依赖清单

```text
# 核心
numpy>=2.0
requests>=2.32
sentence-transformers>=3.0
torch>=2.0
h5py>=3.10
networkx>=3.0
pydantic>=2.0

# HTTP API 服务
fastapi>=0.115
uvicorn[standard]>=0.34

# PDF 解析
PyMuPDF>=1.23          # 读页数，不花 API 额度
# MinerU 是云端 API，只需 requests

# 模型权重（~184MB，不进 Git）
# BAAI/bge-small-zh-v1.5 → models_cache/
```

---

## 8. 目录结构

```
Project正式/
├── src/
│   ├── embedding.py              # BGE 嵌入（懒加载 + 规则兜底）
│   ├── qa_runner.py              # CLI 问答入口
│   ├── api/
│   │   └── server.py             # FastAPI HTTP API（待创建）
│   ├── vector/
│   │   └── store.py              # VectorStoreH5 + get_store() 工厂
│   ├── retrieve/
│   │   ├── chunker.py            # 自研切片引擎
│   │   ├── graph_retriever.py    # networkx 内存图遍历器
│   │   ├── hybrid.py             # 混合检索 + ChunkCache
│   │   └── classifier.py         # 论文分类器（PDF 类型推断：论文/政策/ESG 报告）
│   ├── kg/
│   │   ├── pipeline.py           # KG 批量流水线
│   │   ├── extractor.py          # qwen-max 三元组抽取
│   │   ├── entities.py           # 实体/关系 Pydantic 模型
│   │   ├── config.py             # 路径 + LLM 配置
│   │   ├── aliases.py            # 概念别名归一
│   │   ├── concept_edges.py      # 共现边生成
│   │   ├── neo4j_client.py       # Neo4j 写入层（规划时创建，未实际使用，待清理）
│   │   └── llm_extract_client.py # qwen-max API 调用封装
│   ├── reason/
│   │   └── answer_engine.py      # 回答生成引擎
│   └── parse/
│       ├── pipeline.py           # PDF→清洗→元数据 流水线
│       ├── adapters/
│       │   ├── mineru_api.py     # MinerU 云端 API 封装
│       │   └── ...
│       ├── clean/
│       │   └── cleaning.py       # 清洗 + 章节标记注入
│       └── ir/
│           └── parsed_doc.py     # ParsedDoc 元数据模型
├── scripts/
│   ├── run_pipeline.sh           # 云上一键跑批（增量/全量/重跑失败）
│   ├── download_papers.py        # 从 Feed API + COS 获取论文
│   ├── parse_all.py              # MinerU 批量解析
│   ├── report_status.py          # 系统状态报告
│   ├── rebuild_status.py         # 状态文件重建
│   ├── sample_check.py           # 抽样质检
│   └── vectorize_all.py          # 批量向量化
├── cleaned/                      # 清洗后 Markdown（不进 Git）
├── cleaned_meta/                 # 元数据 JSON（不进 Git）
├── input/                        # 下载的 PDF（不进 Git）
├── artifacts/
│   ├── kg/                       # *.kg.json 三元组文件（不进 Git）
│   └── vector/                   # all_store.h5 向量存储（不进 Git）
├── models_cache/                 # BGE 模型权重（不进 Git）
├── docs/
│   └── TECHNICAL_ARCHITECTURE.md # 本文件
├── .gitignore
├── requirements.txt
└── INSTALL.md
```

---

## 9. 关键设计决策

### 9.1 为什么不用 Neo4j

- 500 篇论文的 KG 约有 10,000-20,000 条边，networkx 内存图 < 300 MB
- 检索模式是 `get_concept_relations()` / `search_entity()` / `in_edges()`，全部是内存图 O(1) 操作
- 去掉 Neo4j 容器省下 2 GB 内存（云服务器 3.5 GB 硬上限的关键让步）
- 持久化靠 `artifacts/kg/*.kg.json`，重启时全部重载，加载 < 2 秒

### 9.2 为什么现阶段选 hdf5 而不是 Qdrant

- 500 篇论文向量总量约 75 MB，hdf5 暴力扫描 < 10 ms，性能完全够用
- 省掉 Qdrant 容器 1.5 GB 内存，Python + BGE 有更充裕的运行空间
- 零额外服务依赖，部署时只需 `pip install h5py`
- 工厂函数 `get_store()` 已预留切换能力，未来可无缝迁移

### 9.3 为什么不用 LlamaIndex

- 自研方案按 `#【】` 章节标记切片，语义清晰，检索时直接定位到"实证块/结论块"
- 自研混合检索显式区分"文证（向量）"和"理证（图谱）"，回答引擎可分别引用
- 避免框架锁定风险，依赖仅为 `numpy` + `networkx` + `requests`

### 9.4 为什么不用 GROBID

- MinerU 已产出完整的正文 Markdown，论文元数据（标题/作者/摘要）从清洗阶段即可获取
- 引用关系抽取当前非核心需求，未来如需可单独接入

### 9.5 云上内存预算

| 组件 | 内存 |
|---|---|
| Python + BGE 模型（批处理/服务） | ~1.5-2 GB |
| networkx 内存图（500 篇） | < 300 MB |
| hdf5 向量存储 | < 10 MB（按需读取，非全量加载） |
| 操作系统 + 其他 | ~500 MB |
| **合计** | **< 3 GB（安全运行）** |

> 对比旧方案：Qdrant（1.5 GB）+ Neo4j（2 GB）+ Python = 必 OOM。
> 现方案：纯 Python 进程 + hdf5 文件 + networkx 内存图，无外部容器依赖。

---

## 10. 状态文件

```
artifacts/status/processed_docs.json
```

单文件追踪所有 doc_id 的处理状态，运行时产物，不进 Git：

```json
{
  "doc_001": {"kg": "done", "vector": "done", "updated_at": "2026-08-20T10:00:00"},
  "doc_002": {"kg": "failed", "vector": "pending", "error": "timeout", "stage": "llm_extract"}
}
```

重建命令：`python scripts/rebuild_status.py`

---

## 11. 服务启动流程

```
启动 server.py
  │
  ├── 1. 加载 GraphRetriever（读 artifacts/kg/*.kg.json → networkx 内存图）
  │
  ├── 2. 打开 VectorStore（artifacts/vector/all_store.h5，按需读取）
  │      + 创建 threading.Lock 保证并发安全
  │
  ├── 3. 初始化 ChunkCache（惰性，首次命中时加载对应 cleaned md）
  │
  ├── 4. 注册 FastAPI 路由
  │     ├── GET  /health    → 返回各组件状态（图节点数/向量数/模型就绪）
  │     └── POST /search    → 加锁读 hdf5 → 混合检索 → 回答生成
  │
  └── 5. 等待请求（uvicorn 事件循环）
```