# RAG-Graph 技术架构（2026-08-21）

> 本文档反映当前项目的真实技术栈。覆盖从全文获取 → 解析 → 清洗 → 切片 → 向量化 → KG 抽取
> → 混合检索 → HTTP API 服务全链路。

---

## 1. 架构总览

```
        Windows 下载器（SSH 隧道 + Token）     Feed API（Scopus 版元数据）
            │                                        │
            ▼                                        ▼
     input/fulltexts/（.txt / .xml）          input/metadata/（.json）
      84 TXT + 371 XML = 455 份资产                 1088 条元数据
            │
            ▼
    [parse_all.py]  — TXT/XML 直接读取，PDF 走 MinerU 兜底
            │
            ▼
    [清洗 + 章节标记注入]  — #【摘要】#【理论假设】#【实证】#【结论】
            │
            ▼
  cleaned/*.md + cleaned_meta/*.json
            │
      ┌─────┴──────────────────┬──────────────────────┐
      ▼                        ▼                      ▼
  [切片引擎 chunker]    [KG 抽取 qwen-max]     [元数据摘要向量化]
  （全文分块）            （有全文才做）          （无全文的 714 篇）
      │                        │                      │
      ▼                        ▼                      ▼
  [BGE 嵌入]            artifacts/kg/*.kg.json  [BGE 嵌入]
      │                        │                1 条/篇
      ▼                        ▼                      │
  [向量存储 hdf5]       [networkx 内存图]              │
    all_store.h5         GraphRetriever（单例）         │
      │                        │                      │
      └──────────────┬─────────┴──────────────────────┘
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
               └──→ src/api/server.py（FastAPI HTTP API，端口 8002）
```

---

## 2. 数据来源与获取

### 2.1 两类数据的关系

| 数据 | 来源 | 数量 | 凭据 | 用途 |
|---|---|---|---|---|
| 元数据（Scopus 版） | Feed API `http://127.0.0.1:4173/api/feed` | 1088 条 | 无（公开） | 论文注册中心：标题/摘要/作者/关键词/期刊 |
| 全文正文 | Windows 下载器（SSH 隧道 + GREEN_FINANCE_RESEARCH_TOKEN） | 455 份资产，443 篇去重 | Token（私下提供） | KG 抽取 + 全文分块向量化 |

**核心关系：Feed API 作为论文注册中心，全文正文是子集。**

```
Feed API 元数据（1088 条）
    ├── 有全文正文（443 篇）→ 全流程：解析 → KG → 向量化（多 chunk）
    └── 无全文正文（~640 篇）→ 轻量处理：摘要向量化（1 chunk/篇，无 KG）
```

### 2.2 全文正文格式

| 格式 | 数量 | 解析方式 | MinerU 消耗 |
|---|---|---|---|
| TXT | 84 | `parse_all.py` 直接读取纯文本 | ❌ 不花额度 |
| XML | 371 | `parse_all.py` 解析 XML 提取文本 | ❌ 不花额度 |
| PDF | 0（后续补充） | MinerU 云 API 解析 | ✅ 2000 页/天 |

> **当前 455 份全文全部为 TXT/XML，零 MinerU 成本。** MinerU 降级为"仅 PDF 补充时兜底"。

```
Windows 本地：
  PowerShell 1: SSH 隧道（-L 4173:127.0.0.1:4173），保持开启
  PowerShell 2: Node.js 24 下载器，Token 隐藏输入
                → green-finance-research-input/
                  ├── manifest.json
                  ├── articles.ndjson（元数据+资产映射）
                  └── fulltexts/（.txt / .xml）

服务器：
  scp 传输到 /srv/green-finance-vector/input/
```

### 2.4 下载脚本

`scripts/download_papers.py` 支持：
- **路径 A（元数据）**：服务器本地 Feed API，分页拉取 1088 条 Scopus 版元数据
- **路径 B（全文）**：调用外部下载工具（Windows 下载器或 npm 工具），产出入 `input/`

---

## 3. 核心组件

### 3.1 文档解析 — parse_all.py

| 项 | 说明 |
|---|---|
| 服务 | `scripts/parse_all.py` |
| 格式检测 | 自动识别 `.pdf` → MinerU，`.txt` / `.xml` → 直接读取 |
| TXT 处理 | 直接读取纯文本，跳过 MinerU |
| XML 处理 | 解析 XML 提取文本内容，跳过 MinerU |
| PDF 处理 | MinerU 云端 API（签名上传 → 轮询 → 下载 zip），每日 2000 页免费 |
| 断点续跑 | `cleaned_meta/*.json` 存在即跳过，已解析的不重复处理 |
| 输出 | `cleaned/{doc_id}.md`（清洗后 Markdown）+ `cleaned_meta/{doc_id}.json`（ParsedDoc 元数据） |

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

hdf5 纯文件读写，无需额外服务；1169 篇论文的向量总量约 45.9 MB，numpy 暴力扫描 < 10 ms，完全够用。省掉 Qdrant 容器的 1.5 GB 内存意味着 Python + BGE 有更充裕的运行空间。未来如果数据量超过 2000 篇或需要生产级高并发，再迁移到 Qdrant。

#### 架构预留

工厂函数 `get_store()` 支持按环境变量 `VECTOR_BACKEND` 切换后端：

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
| 处理范围 | **仅对有全文的论文执行**；无全文的论文不进入 KG 流程 |

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
| 图谱路 | 问题实体链接 → 概念关系/方法关联（理证）；仅对有全文的论文生效 |
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
| 服务 | `src/api/server.py`（FastAPI，端口 8002） |
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
  "graph_nodes": 10138,
  "graph_edges": 13366,
  "vector_count": 19567,
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
| `scripts/download_papers.py` | 从 Feed API 获取元数据 + 调用外部工具下载全文 | `python scripts/download_papers.py --output-dir ./input` |
| `scripts/download_feed_metadata.py` | 分页拉取 Feed API 元数据（1088 条） | `python scripts/download_feed_metadata.py` |
| `scripts/merge_abstracts.py` | 将 Feed API 摘要合入 cleaned_meta | `python scripts/merge_abstracts.py` |
| `scripts/parse_all.py` | 批量解析 TXT/XML/PDF → 清洗 Markdown | `python scripts/parse_all.py` |
| `scripts/report_status.py` | 动态扫描，输出系统状态报告 | `python scripts/report_status.py` |
| `scripts/rebuild_status.py` | 从已有产出重建 `processed_docs.json` | `python scripts/rebuild_status.py` |
| `scripts/sample_check.py` | 抽样质检（随机抽取 N 篇检查 KG + 向量） | `python scripts/sample_check.py 10` |
| `scripts/vectorize_all.py` | 切片 → BGE 嵌入 → 写入向量存储 | `python scripts/vectorize_all.py` |
| `scripts/vectorize_one.py` | 单文档向量化测试 | `python scripts/vectorize_one.py <doc_id>` |
| `scripts/qa_remote.py` | SSH 远程问答（服务器跑全量，拉回结果） | `python scripts/qa_remote.py "问题"` |

---

## 5. 数据流

```
input/fulltexts/（84 TXT + 371 XML）
    │
    ▼
parse_all.py（TXT/XML 直接读取；PDF 兜底走 MinerU）
    │
    ▼
cleaned/*.md + cleaned_meta/*.json
    │
    ├── chunker 切片 → BGE 嵌入 → VectorStore（hdf5）
    │
    └── KG 抽取（qwen-max）→ artifacts/kg/*.kg.json → GraphRetriever（networkx）
    │
    └──（无全文的论文）摘要向量化 1 条/篇 → same VectorStore（has_fulltext=false）
    │
    └── HybridRetriever.search() → AnswerEngine.answer()
         │
         ├──→ qa_runner.py（CLI 输出）
         │
         └──→ src/api/server.py（HTTP JSON 响应，端口 8002）
```

---

## 6. 已明确不使用的组件

| 组件 | 说明 | 原因 |
|---|---|---|
| GROBID | 论文元数据/引用抽取 | MinerU 已覆盖正文解析，引用关系暂非核心需求 |
| Neo4j | 图数据库 | 1169 篇 KG 约 10-20k 边，networkx 内存图足够，省一个容器 |
| Qdrant | 向量数据库 | hdf5 足够承载 1169 篇 ~45.9 MB 向量，省 1.5 GB 容器内存 |
| LlamaIndex | 检索框架 | 自研 chunker/retriever/answer_engine 更灵活，无框架锁定风险 |
| PostgreSQL / pgvector | 向量数据库 | 本地 hdf5，不引入数据库依赖 |
| Docling | PDF 解析 | MinerU 统一处理（但当前数据为 TXT/XML，直接读取） |
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

# PDF 解析（仅页数检测，不用于正文提取）
PyMuPDF>=1.23

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
│   ├── status.py                 # 状态管理
│   ├── api/
│   │   └── server.py             # FastAPI HTTP API（端口 8002）
│   ├── vector/
│   │   └── store.py              # VectorStoreH5 + get_store() 工厂
│   ├── retrieve/
│   │   ├── chunker.py            # 自研切片引擎
│   │   ├── graph_retriever.py    # networkx 内存图遍历器
│   │   ├── hybrid.py             # 混合检索 + ChunkCache
│   │   └── utils/                # 检索工具
│   ├── kg/
│   │   ├── pipeline.py           # KG 批量流水线
│   │   ├── extractor.py          # qwen-max 三元组抽取
│   │   ├── entities.py           # 实体/关系 Pydantic 模型
│   │   ├── config.py             # 路径 + LLM 配置
│   │   ├── aliases.py            # 概念别名归一
│   │   ├── concept_edges.py      # 共现边生成
│   │   ├── neo4j_client.py       # Neo4j 写入层（预留，未使用）
│   │   └── llm_extract_client.py # qwen-max API 调用封装
│   ├── reason/
│   │   └── answer_engine.py      # 回答生成引擎
│   └── parse/
│       ├── adapters/
│       │   ├── mineru_api.py     # MinerU 云端 API 封装（PDF 兜底）
│       │   ├── metadata_extractor.py  # 元数据抽取
│       │   └── llm_metadata.py   # LLM 元数据增强
│       ├── clean/
│       │   └── cleaning.py       # 清洗 + 章节标记注入
│       ├── config/
│       │   ├── doc_types.py      # 文档类型定义
│       │   └── llm_type_infer.py # LLM 类型推断
│       └── ir/
│           └── parsed_doc.py     # ParsedDoc 元数据模型
├── scripts/
│   ├── run_pipeline.sh           # 云上一键跑批
│   ├── download_papers.py        # 从 Feed API 获取论文
│   ├── download_feed_metadata.py # Feed API 元数据下载
│   ├── merge_abstracts.py        # 摘要合并工具
│   ├── parse_all.py              # 批量解析（TXT/XML/PDF 自动检测）
│   ├── report_status.py          # 系统状态报告
│   ├── rebuild_status.py         # 状态文件重建
│   ├── sample_check.py           # 抽样质检
│   ├── vectorize_all.py          # 批量向量化
│   ├── vectorize_one.py          # 单文档向量化测试
│   └── qa_remote.py              # SSH 远程问答
├── schemas/
│   ├── __init__.py
│   └── chunk_schema.py           # ChunkPayload 数据模型
├── cleaned/                      # 清洗后 Markdown（不进 Git）
├── cleaned_meta/                 # 元数据 JSON（不进 Git）
├── input/                        # 下载的全文（不进 Git）
├── artifacts/
│   ├── kg/                       # *.kg.json 三元组文件（不进 Git）
│   └── vector/                   # all_store.h5 向量存储（不进 Git）
├── models_cache/                 # BGE 模型权重（不进 Git）
├── docs/
│   ├── TECHNICAL_ARCHITECTURE.md # 本文件
│   ├── EXECUTION_PLAN_STATUS.md  # 执行计划状态
│   ├── Graph Schema.md           # 图谱 Schema
│   └── tech_note_B_v4.md         # 早期方案笔记
├── .gitignore
├── requirements.txt
├── INSTALL.md
├── README.md
└── .env.example
```

---

## 9. 关键设计决策

### 9.1 为什么不用 Neo4j

- 1169 篇论文的 KG 约有 13,366 条边（10,138 节点），networkx 内存图 < 300 MB
- 检索模式是 `get_concept_relations()` / `search_entity()` / `in_edges()`，全部是内存图 O(1) 操作
- 去掉 Neo4j 容器省下 2 GB 内存（云服务器 8 GB RAM 的关键让步）
- 持久化靠 `artifacts/kg/*.kg.json`，重启时全部重载，加载 < 2 秒

### 9.2 为什么现阶段选 hdf5 而不是 Qdrant

- 1169 篇论文向量总量约 45.9 MB（19567 条，512 维），hdf5 暴力扫描 < 10 ms，性能完全够用
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
- 当前数据为 TXT/XML，直接读取文本，无需任何 PDF 解析工具

### 9.5 TXT/XML 直接读取策略

- **不花 MinerU 额度**：455 份全文全部为 TXT/XML，直接读取，零配额消耗
- **MinerU 降级为兜底**：未来补充 PDF 论文时才调用 MinerU 云 API
- **断点续跑**：`cleaned_meta/*.json` 存在即跳过，已解析不重复处理
- **格式自动检测**：`parse_all.py` 根据文件后缀自动选择解析方式

### 9.6 双层数据处理策略

| 层级 | 覆盖范围 | 数据来源 | 处理内容 | 是否有 KG | 向量化方式 |
|---|---|---|---|---|---|
| 全文层 | 443 篇 | fulltexts/（TXT/XML） | 全文清洗 → 分块 → 嵌入 | ✅ | 多 chunk/篇 |
| 摘要层 | ~645 篇 | Feed API 元数据 | 摘要直接嵌入 | ❌ | 1 条/篇 |

向量库合并，`has_fulltext` 字段区分。检索时全文层优先。

### 9.7 云上内存预算

| 组件 | 内存 |
|---|---|
| Python + BGE 模型（批处理/服务） | ~1.5-2 GB |
| networkx 内存图（1169 篇） | < 300 MB |
| hdf5 向量存储 | < 10 MB（按需读取，非全量加载） |
| 操作系统 + 其他 | ~500 MB |
| **合计** | **< 3 GB（8 GB 实例上安全运行）** |

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
  "doc_001": {"kg": "done", "vector": "done", "has_fulltext": true, "updated_at": "2026-08-20T10:00:00"},
  "doc_002": {"kg": "failed", "vector": "pending", "has_fulltext": true, "error": "timeout", "stage": "llm_extract"}
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