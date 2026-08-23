# RAG-Graph — 绿色金融论文知识图谱问答系统

基于 **知识图谱 + 向量检索混合增强 (RAG-Graph)** 的绿色金融论文问答系统。从 1169 篇绿色金融论文中抽取实体关系构建知识图谱，结合 BGE 语义向量检索，回答「绿色金融如何影响技术创新」类研究问题。

## 功能特性

- 🧠 **知识图谱检索**：LLM 抽取论文三元组 → networkx 内存图 → 实体/邻域检索
- 🔢 **向量检索**：BGE-small-zh 语义嵌入 → hdf5 存储 → 余弦 Top-K 检索
- 🔀 **混合融合**：图谱路径 + 向量证据 → LLM 综合生成答案（带引用）
- 🚀 **远程问答**：本地零数据，SSH 远程跑全量数据 (`scripts/qa_remote.py`)
- ⚙️ **批量处理**：解析 → KG 抽取 → 向量化 全流程一键跑批，断点续跑

## 当前数据规模

| 指标 | 数值 |
|---|---|
| 论文/文档 | **1169 篇**（含 455 篇全文 + 714 篇元数据） |
| 向量 | **19567 条**（BGE-small-zh, 512 维） |
| 知识图谱 | **10138 节点 / 13366 边** |
| 向量存储 | hdf5 (45.9 MB, `artifacts/vector/all_store.h5`) |
| 图谱存储 | 本地 JSON (`artifacts/kg/*.kg.json`) + networkx 内存图 |

## 技术栈

| 组件 | 选型 |
|---|---|
| 语言 | Python 3.12 |
| 嵌入模型 | `BAAI/bge-small-zh-v1.5`（512 维） |
| 向量存储 | hdf5（`h5py`，按需切换后端） |
| 知识图谱 | `networkx` 内存图（无图数据库） |
| 生成 LLM | `qwen-max`（DashScope API） |
| 文档解析 | MinerU 云 API + 本地清洗 |
| HTTP 服务 | FastAPI（`src/api/server.py`, 端口 8002） |

## 快速开始

### 环境要求

- Python 3.10+
- 云服务器 ≥ 2 核 / 4 GB RAM（本地跑 37 篇测试数据够用）

### 安装

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install modelscope
# 下载 BGE 模型（首次运行需要）
python -c "from modelscope import snapshot_download; snapshot_download('BAAI/bge-small-zh-v1.5', cache_dir='./models_cache')"
```

### 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 DASHSCOPE_API_KEY（必填）
```

### 运行问答

```bash
# 单条问答
python src/qa_runner.py "绿色金融政策如何影响企业技术创新"

# 交互模式
python src/qa_runner.py
```

### 远程问答（推荐，无需本地数据）

```bash
# 前提: 服务器 `/srv/green-finance-vector` 已部署全量数据 + 本机已配置免密 SSH
python scripts/qa_remote.py "碳中和目标下绿色金融有哪些政策工具"
python scripts/qa_remote.py        # 交互模式
```

Windows 终端如遇中文乱码，先执行 `chcp 65001`。

## 架构概览

```
cleaned/*.md (1169 篇)
      │
      ├──→ KG 抽取 (LLM 三元组 + 共现补边) ──→ artifacts/kg/*.kg.json ──→ networkx 内存图
      │
      └──→ 分块 + BGE 嵌入 ──→ artifacts/vector/all_store.h5 (19567 条)
                                            │
用户问题 ──→ 向量检索 Top-K + 图谱路径检索
                                            │
                                 混合上下文组装 ──→ qwen-max 生成 ──→ 带引用答案
```

## 目录结构

```
├── src/                      # 核心源码
│   ├── reason/answer_engine.py   # 问答引擎（检索融合 + LLM 生成）
│   ├── retrieve/                 # 分块 / 混合检索 / 图谱检索
│   ├── kg/                       # 三元组抽取 / 共现补边 / pipeline
│   ├── vector/                   # hdf5 向量存储
│   ├── parse/                    # 文档解析（MinerU）+ 清洗 + 元数据
│   ├── embedding.py              # BGE 嵌入统一适配
│   ├── api/server.py             # FastAPI HTTP 服务
│   └── qa_runner.py              # 问答 CLI
├── scripts/                 # 批量工具
│   ├── qa_remote.py             # SSH 远程问答
│   ├── parse_all.py             # 批量文档解析（断点续跑）
│   ├── vectorize_all.py         # 批量向量化
│   ├── report_status.py         # 系统状态报告
│   ├── sample_check.py          # 抽样质检
│   └── ...
├── schemas/                 # Pydantic 数据模型
├── docs/                    # 技术文档
├── cleaned/                 # 清洗后的论文 markdown（数据，不进 Git）
├── cleaned_meta/            # 论文元数据 JSON（数据，不进 Git）
└── artifacts/               # KG / 向量 / 状态文件（数据，不进 Git）
```

## 批量处理

```bash
# 云上一键跑批（KG 抽取 + 向量化 + 状态报告）
bash run_pipeline.sh --incremental

# 分步执行
python src/kg/pipeline.py --mode incremental     # KG 抽取
python scripts/vectorize_all.py --mode incremental  # 向量化
python scripts/report_status.py                  # 状态报告
```

## 相关文档

| 文档 | 内容 |
|---|---|
| `docs/TECHNICAL_ARCHITECTURE.md` | 技术架构详解 |
| `docs/Graph Schema.md` | 知识图谱 Schema 定义 |
| `VECTOR_GRAPH_SERVER_HANDOFF.md` | 服务器部署与运维指南 |
| `docs/EXECUTION_PLAN_STATUS.md` | 执行进度追踪 |

## 数据来源

- 绿色金融论文全文 / 元数据（数据中心 Feed API + 全文下载工具）
- 报告数据规模：**1169 篇**（455 篇全文 + 714 篇仅元数据）

## 安全说明

- `DASHSCOPE_API_KEY` 等密钥只存在于服务器的 `.env`（`chmod 600`），**不进 Git / 聊天 / 日志**
- 远程问答通过 SSH 在服务器执行，密钥不传回本地

## 许可证

内部研究项目，未公开授权。