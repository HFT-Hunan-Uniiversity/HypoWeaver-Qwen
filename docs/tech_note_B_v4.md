# B 部分技术笔记 v4(技术栈重构·LlamaIndex 版)

> ⚠️ 本文档描述的是早期未采用的方案（LlamaIndex + Neo4j + PG + GROBID），**非当前项目实际架构**。
> 实际采用的技术栈见 `docs/TECHNICAL_ARCHITECTURE.md`：纯 Python + hdf5 + networkx + qwen-max，无容器依赖。
> 保留此文档仅作为设计历史参考。

> 作者:B(组总负责 + Tech Lead)
> 对应分工:步骤 2(解析清洗)→ 3(切片索引)→ 4(检索图谱)
> 状态:技术栈重构 · **v4.1(吸收 4 项必留修订)**
> 文档版本演变:v1 dataclass IR → v2 Pydantic+SQLite → v3 加固运维 → v4 弃自研 LlamaIndex → **v4.1 恢复 GROBID 轻量 + 章节标记 + KG 白名单 + PG 断点**
> 技术栈:MinerU(正文)+ GROBID 轻量(论文元数据/引用)+ LlamaIndex + PG/Neo4j

---

## 0. v4.1 修订记录(对 v4.0 的 4 项必留校正)

| # | v4.0 原决策 | v4.1 修订 | 理由 |
|---|---|---|---|
| 1 | GROBID 适配器全弃 | **论文 PDF 叠加 GROBID 轻量**,只取标题/作者/DOI/年份/参考文献,不做 TEI 正文解析 | 论文 KG 的引用关系是核心产出,LLM 抽引用误差大,小样本人工核对爆炸 |
| 2 | 清洗只做排版/数值 | 清洗**注入章节语义标记** `#【摘要】` 等,绑定 ParsedDoc | 裸 md 每次检索都要 LLM 分段烧 token;标记一次永久复用 |
| 3 | KG 抽取仅"建议"白名单 | **强制白名单**(prompt + 后置过滤器双保险) | 小样本脏三元组清理成本高,白名单让图谱天然干净 |
| 4 | PG 只存元数据 | PG 加 `file_md5` + `process_stage` 字段,断点续跑+去重 | 调试反复重跑,无哈希重复解析烧 token,无断点报错从头跑 |

---

## 1. 范围:这次重构动什么、砍什么

### 1.1 新技术栈全貌

```
[PDF / 网页文档]
    │
    ├── 电子版论文 ──→ [GROBID 轻量] ──┐
    │   (扫描件跳过)     只取 teiHeader + listBibl        │
    │                    (标题/作者/DOI/年份/参考文献)    │
    ▼                                                    │
[MinerU] ──→ markdown(正文+表格+图片)                    │
   统一 PDF→文本,取代 Docling/PaddleOCR                  │
   (正文独占,不碰引用)                                  │
    │ ◄──────────────────────────────────────────────────┘
    ▼
[清洗规则](B 保留领域逻辑)
    · 去页眉 / 合并段落 / 数值归一 / 异常标记
    · 注入章节语义标记 #【摘要】#【理论假设】#【实证】#【结论】(v4.1)
    ▼
[ParsedDoc IR → markdown 文件(带 #【】 章节标记)]
    │
    ├──────────────┬───────────────────┐
    ▼              ▼                   ▼
[LlamaIndex]   [PostgreSQL+pgvector]  [Neo4j]
 MarkdownNodeParser  元数据+文本向量        知识图谱
  按 #【】自动切片   file_md5/process_stage  白名单强制
 向量+图谱混合检索   断点续跑+去重(v4.1)    实体5类/关系5类
    │
    ▼
[E 假设生成](业务核心,B 不写,继续由 E 负责)
```

### 1.2 砍掉的旧自研代码

| 旧代码 | 状态 | 原因 |
|---|---|---|
| GROBID 全量 TEI 正文解析 | 弃 | 正文归 MinerU;GROBID 只保留轻量 header+引用(见 §1.3 / §5.6) |
| Docling 适配器 | 弃 | MinerU 统一当 PDF→文本 |
| PaddleOCR 适配器 + 形近字纠错库 | 弃 | MinerU 内置 OCR,无需独立纠错库 |
| ChromaDB + BM25 双路索引 | 弃 | LlamaIndex 混合检索替代 |
| 三层切片(语义/滑动窗口) | 弃 | LlamaIndex MarkdownNodeParser 按 `#【】` 标记切 + SentenceSplitter |
| 双队列调度(GROBID HTTP + Docling 本地) | 弃 | GROBID 退化为无状态 HTTP enrich(仅论文),不恢复双队列 |
| 快照软链 + 灰度发布 | 弃 | PG 事务自带版本,不需要快照目录 |
| IR 兼容层(legacy_loader) | 弃 | schema 重做后无需旧版兼容 |
| 引用核验器 | 弃 | v4.1 用 GROBID 轻量直接抽引用,不做二次核验 |

### 1.3 保留的 B 资产

| 保留项 | 为什么留 |
|---|---|
| **ParsedDoc IR 概念**(meta/blocks/tables) | 仍是跨层"普通话",MinerU 输出转 Markdown 后规范进 IR(字段精简) |
| **清洗规则**(页眉页脚/段落合并/特殊字符/数值标准化/标记清理) | 领域知识,引擎无关。MinerU 输出后仍需清洗 |
| **章节语义标记注入**(v4.1 新增) | 清洗时给 markdown 加 `#【摘要】#【理论假设】#【实证】` 等,LlamaIndex MarkdownNodeParser 按标记自动切,一次标注永久复用,省检索期 LLM 分段 token |
| **异常处理**(global_review_flag + 四类异常) | 质量控制必须 |
| **跨页表格合并**(转 LlamaIndex 表格处理前的合并逻辑) | ESG 长表需合并 |
| **Pydantic 数值校验器** | 拦截脏数据,与存储无关 |
| **GROBID 轻量**(论文元数据/引用抽取,v4.1 恢复) | 论文 KG 引用关系核心产出,LLM 抽引用误差大;只取 teiHeader+listBibl,不做 TEI 正文解析 |
| **PG 断点续跑 + 哈希去重**(v4.1 落到表字段) | `documents.file_md5` 去重 + `process_stage` 续跑(unparsed/cleaned/vector_indexed/graph_indexed),30 行实现,调试期防重复解析烧 token |
| **原子写入 / 全局超时熔断 / 文件句柄分批** | 工程底座,适配 MinerU 单引擎(GROBID 是无状态 HTTP,不恢复双队列) |
| **标准化测试样本集** | 5 类各 5-10 份,CI 校验,永不过时 |

---

## 2. 接口契约

### 2.1 输入

| 来源 | 路径 | 形态 | 用途 |
|---|---|---|---|
| A | `<shared>/raw/<source_type>/` | PDF / docx | 待解析文件本体 |
| A | `config/data_source_registry.json` | JSON | 元数据 + `engine_recommend = mineru` |
| 共享 | `config/paths.yaml` | YAML | 所有路径从配置读 |

### 2.2 输出

| 路径 | 形态 | 说明 |
|---|---|---|
| `<shared>/cleaned/<doc_id>.md` | Markdown | MinerU 输出 + 清洗 + 章节标记后的文本,LlamaIndex 直接读 |
| `<shared>/cleaned_meta/<doc_id>.json` | ParsedDoc IR(精简) | 元数据、异常标记、GROBID 论文 meta,供下游查询 doc 级信息 |
| `PostgreSQL(documents 表)` | 元数据 | A 写入 file_md5;B 写入 process_stage / cleaned_path / 论文 meta(见 §5.7 schema) |
| `Neo4j` | 知识图谱 | LLM 抽实体关系(白名单强制 5 实体 / 5 关系),见 §5.5 |

### 2.3 下游接口(在 LlamaIndex 之上)

| 角色 | 通过 LlamaIndex 拿什么 | 时机 |
|---|---|---|
| E | **检索接口**:`query_engine.query("...")`(向量 + 图谱融合) | 阶段 2 末 |
| E | **KG 图谱**:Neo4j 可查 `related papers/concepts` | 阶段 2 末 |
| 全部 | PostgreSQL 查元数据 / pgvector 相似检索 | 阶段 2 末 |

---

## 3. 技术栈与选型

| 用途 | 选择 | 备选 | 理由 |
|---|---|---|---|
| PDF→正文文本 | **MinerU (magic-pdf)** | Docling / PaddleOCR | 一款统一处理所有 PDF,内置版面分析+OCR;正文独占 |
| 论文元数据+引用 | **GROBID 轻量**(v4.1 恢复) | OpenAlex / LLM 抽 | TEI 引用抽取最强;只取 teiHeader+listBibl,不做正文解析;仅电子论文 |
| 存储(元数据+向量) | **PostgreSQL + pgvector** | ChromaDB / 单 JSON | 一个库搞定元数据+向量+断点(file_md5/process_stage),支持事务 |
| 图谱存储 | **Neo4j** | PG+Apache AGE | LlamaIndex 原生支持 Neo4jGraphStore,开箱即用,查询强 |
| LLM 框架 | **LlamaIndex** | LangChain / 自研 | 现成切片/索引/KG 抽取/混合检索,省 60-70% 开发 |
| 嵌入模型 | **DashScopeEmbedding (text-embedding-v3)** | OpenAI | 中文效果好,Qwen 生态匹配 |
| LLM 实体抽取 | **DashScope (qwen-max)** | Qwen2.5-72B | **只对关键块抽 + 白名单约束**,控成本 |
| 调度 | MinerU 单引擎顺序 + PG 断点续跑 | — | GROBID 是无状态 HTTP enrich,不恢复双队列 |
| 容器化 | **docker-compose**(mineru+grobid+pg+neo4j) | 手动部署 | 一键拉起 |

---

## 4. 环境依赖

```bash
# 4.1 Python (3.11)
pip install magic-pdf llama-index-core \
  llama-index-vector-stores-postgres \
  llama-index-graph-stores-neo4j \
  llama-index-embeddings-dashscope \
  llama-index-llms-dashscope \
  grobid-client-python       # GROBID 轻量调用(v4.1)
pip install pydantic psycopg2-binary neo4j lxml

# 4.2 PostgreSQL + pgvector (Docker)
docker run -d --name pg-greenfin \
  -e POSTGRES_PASSWORD=password -p 5432:5432 \
  -v $PWD/data-pg:/var/lib/postgresql/data \
  pgvector/pgvector:0.7.0

# 4.3 Neo4j (Docker)
docker run -d --name neo4j-greenfin \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  -v $PWD/data-neo4j:/data \
  neo4j:5-community

# 4.4 GROBID (Docker,v4.1 论文元数据/引用用)
docker run -d --name grobid-greenfin \
  -p 8070:8070 --shm-size 1g \
  lfoppiani/grobid:0.8.1

# 4.5 MinerU 模型首次下载
python -m magic_pdf install
```

---

## 5. 核心实现(分段)

### 5.1 MinerU 适配器(PDF → Markdown)

```python
# src/parse/adapters/mineru_adapter.py
def pdf_to_markdown(pdf_path: str, out_dir: str) -> str:
    """MinerU 解析 PDF → 输出 Markdown 文件,返回其路径。
    只管正文+表格+图片,不碰引用(引用归 GROBID)。"""
    # 调 magic-pdf 命令行或 SDK,产出 md
    # 输出: <out_dir>/<doc_id>.md
    ...
```

### 5.2 清洗规则(保留,引擎无关)+ 章节语义标记注入(v4.1)

MinerU 输出的 Markdown 仍需清洗,复用原 parsed_doc 清洗逻辑,**新增章节语义标记注入**:

```python
# src/parse/clean/cleaning.py
import re

def clean_mineru_markdown(md_text: str) -> str:
    """对 MinerU 输出的 markdown 做清洗 + 注入章节标记"""
    md = remove_header_footer(md_text)     # 页眉页脚
    md = merge_paragraphs(md)               # 段落合并
    md = normalize_special_chars(md)        # 特殊字符
    md = normalize_values(md)               # 数值标准化 → 记录 normalized_values
    md = cleanup_markers(md)                # 冗余标记
    md = inject_section_markers(md)         # v4.1: 章节语义标记
    return md

# 6 个语义块:把原始标题归类后写成 H1 形式 #【语义名】
SECTION_MAP = {
    "摘要":   ["摘要", "abstract"],
    "综述":   ["引言", "文献综述", "introduction", "literature review", "研究背景"],
    "理论假设": ["理论", "机制", "假设", "hypothesis", "theoretical"],
    "实证":   ["实证", "方法", "数据", "结果", "实证分析", "methodology", "empirical"],
    "异质性": ["异质性", "稳健性", "robustness", "heterogeneity"],
    "结论":   ["结论", "conclusion", "启示"],
}

def inject_section_markers(md: str) -> str:
    """规则匹配标题行,前插 #【语义名】;匹配不到保留原标题(LlamaIndex 仍按原 H 切)"""
    for sem, keys in SECTION_MAP.items():
        md = re.sub(
            r'(?m)^(\s*#{1,4}\s*(' + '|'.join(keys) + r')[^\n]*)$',
            r'#【%s】\n\1' % sem, md, flags=re.IGNORECASE)
    return md
```

> **为什么这一步关键**:LlamaIndex `MarkdownNodeParser` 自动按 `#` 标题切片。注入 `#【摘要】` 后,检索召回直接是"摘要块/实证块",**一次标注永久复用**,检索/问答期不再调 LLM 做章节识别,省 token + 提速。匹配不到的小节保留原标题,LlamaIndex 仍能切,只是没语义标签。

### 5.3 ParsedDoc IR(精简版,适配 LlamaIndex)

MinerU 输出为 Markdown,不必再强塞进复杂多字段 IR。简化:

```python
# src/parse/ir/parsed_doc.py (Pydantic V2)
from pydantic import BaseModel, field_validator
from typing import List, Optional

class ParsedDoc(BaseModel):
    doc_id: str
    doc_type: str            # paper / policy / esg_report / ...
    doc_type_cn: str
    title: str
    source_loc: str
    global_review_flag: str  # ok / needs_human_review
    clean_log: List[dict] = []
    extra_info: dict = {}    # 论文:GROBID 产出的 doi/authors/year/references(§5.6)
                             # 政策:policy_no/issuer/effective_date;ESG:company/report_year
    markdown_path: str       # cleaned/<doc_id>.md(主体,供 LlamaIndex 读)
    normalized_values: List[dict] = []   # 数值标准化结果,供 E 用

    @field_validator('global_review_flag')
    @classmethod
    def check_flag(cls, v):
        assert v in ('ok', 'needs_human_review'), f"非法 flag: {v}"
        return v
```

> **说明**:主体是 Markdown 文件(LlamaIndex 消费),ParsedDoc JSON 只做**元数据容器**(标题/类型/异常标记/归一化数值/GROBID 论文 meta)。

### 5.4 LlamaIndex 索引与检索(核心,替代 C/D 大部分自研)

```python
# src/ingest/index_pipeline.py
from llama_index.core import (SimpleDirectoryReader, VectorStoreIndex,
                              KnowledgeGraphIndex, Settings)
from llama_index.core.node_parser import MarkdownNodeParser   # v4.1: 按 #【】 切
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.graph_stores.neo4j import Neo4jGraphStore
from llama_index.embeddings.dashscope import DashScopeEmbedding
from llama_index.llms.dashscope import DashScope
# KG_WHITELIST_PROMPT 见 §5.5

Settings.embed_model = DashScopeEmbedding(model="text-embedding-v3")
Settings.llm = DashScope(model="qwen-max")

def build_pipelines(cleaned_dir: str):
    # 1) 向量索引 → PG pgvector;按清洗期注入的 #【摘要】 章节标记切,不调 LLM 分段
    documents = SimpleDirectoryReader(cleaned_dir).load_data()
    vec_store = PGVectorStore.from_params(
        host="localhost", port=5432, database="postgres",
        user="postgres", password="password", table_name="esg_docs")
    vector_index = VectorStoreIndex.from_documents(
        documents,
        transformations=[MarkdownNodeParser()],   # v4.1: 按章节标记切
        vector_store=vec_store)

    # 2) 知识图谱(KG) → Neo4j;只抽关键块 + 白名单 prompt(见 §5.5)
    graph_store = Neo4jGraphStore(
        url="bolt://localhost:7687", user="neo4j", password="password")
    kg_index = KnowledgeGraphIndex.from_documents(
        key_docs,                       # 关键块:摘要/方法/结论
        graph_store=graph_store,
        max_triplets_per_chunk=5,       # 每段最多 5 三元组,控成本
        kg_extractor_prompt=KG_WHITELIST_PROMPT,  # v4.1: 白名单
    )
    return vector_index, kg_index

def build_query_engine(vector_index, kg_index):
    """混合查询:向量语义 + 图谱关系"""
    from llama_index.core.retrievers import VectorIndexRetriever
    from llama_index.core.query_engine import RetrieverQueryEngine
    vs_retriever = VectorIndexRetriever(index=vector_index, similarity_top_k=10)
    # KG retrieve:LLM 抽 query 实体 → 图遍历 → 并回向量结果
    query_engine = kg_index.as_query_engine(
        similarity_top_k=10, graph_traversal_depth=2)
    return query_engine

# 对外检索接口(供 E)
def search(query: str, top_k: int = 10):
    qe = build_query_engine(...)
    return qe.query(query)
```

### 5.5 图谱节点/关系(Neo4j,白名单强制 v4.1)

LlamaIndex 默认会乱抽地名/公式/无关短句,小样本也要大量人工清理。v4.1 **双保险**:

**保险一:抽取 prompt 固化白名单**

| 实体(节点) | 关系(边) | 说明 |
|---|---|---|
| 论文 | 引用 cites | 论文间(GROBID 引用 + 正文文本) |
| 作者 | 撰写 authored | 从 GROBID teiHeader / 元数据抽 |
| 绿色金融概念 | 研究 studies | 绿色信贷、融资约束、漂绿等 |
| 计量方法 | 采用方法 uses_method | 双重差分、PSM 等 |
| 数据集 | 采用数据集 uses_dataset | CSMAR / Wind / 企业年报 |

> 你原列 4 关系里"数据集"实体没有关系挂接(orphan),会变孤点。补 `uses_dataset` 做第 5 关系,让数据集能挂到论文上 —— 这是白名单里唯一比你的建议多的一条,其余严格按你的 5 实体 / 4 关系收口。

```python
KG_WHITELIST_PROMPT = """
从给定文本抽取三元组 (subject, relation, object)。严格约束:
- subject/object 的实体类型必须是:论文 / 作者 / 绿色金融概念 / 计量方法 / 数据集
- relation 必须是:cites / authored / studies / uses_method / uses_dataset
- 禁止生成上述白名单之外的实体类型或关系。
- 无法归入白名单的内容,直接丢弃,不要勉强抽。
输出 JSON 数组:[{"subject":"...","relation":"...","object":"...","s_type":"论文","o_type":"作者"}]
"""

kg_index = KnowledgeGraphIndex.from_documents(
    key_docs, graph_store=graph_store,
    max_triplets_per_chunk=5,
    kg_extractor_prompt=KG_WHITELIST_PROMPT,   # 保险一
)
```

**保险二:后置过滤器兜底**(LLM 偶尔不听话)

```python
ALLOWED = {("论文","cites"), ("作者","authored"), ("绿色金融概念","studies"),
           ("计量方法","uses_method"), ("数据集","uses_dataset")}

def clean_graph(graph_store):
    """写入后扫一遍 Neo4j,删掉非白名单的节点/关系"""
    # 遍历 node labels / rel types,不在白名单的 DROP
    # (具体 Cypher 依 Neo4j schema 写,版本无关)
    ...
```

两道关卡后,小样本图谱天然干净,人工清理量接近 0。

### 5.6 GROBID 轻量适配器(论文元数据/引用,v4.1)

只对**电子版论文**跑(扫描件跳过,引用精度 MVP 接受降级)。调一个 endpoint,消费 TEI 的 2 个子树,丢弃 `<body>`:

```python
# src/parse/adapters/grobid_light.py
import requests, lxml.etree as ET

GROBID = "http://localhost:8070/api/processFulltextDocument"
ns = {"tei": "http://www.tei-c.org/ns/1.0"}

def extract_paper_meta(pdf_path: str) -> dict:
    """电子版论文 → 标题/作者/DOI/年份 + 参考文献列表。不解析正文。"""
    with open(pdf_path, "rb") as f:
        r = requests.post(GROBID, files={"input": f}, timeout=120)
    if r.status_code != 200:
        return {"grobid_status": "failed"}

    root = ET.fromstring(r.text.encode())  # TEI XML

    # 1) teiHeader:标题/作者/DOI/年份
    title_el = root.find(".//tei:titleStmt/tei:title", ns)
    authors = [a.text for a in root.findall(".//tei:author/tei:persName", ns)]
    doi_el = root.find(".//tei:idno[@type='DOI']", ns)
    year_el = root.find(".//tei:publicationStmt/tei:date", ns)

    # 2) listBibl:参考文献(只取 raw 文本,parsed 字段按需补)
    refs = []
    for b in root.findall(".//tei:listBibl/tei:biblStruct", ns):
        raw = " ".join(b.itertext()).strip()
        refs.append({"raw": raw})

    return {
        "title": title_el.text if title_el is not None else None,
        "authors": authors,
        "doi": doi_el.text if doi_el is not None else None,
        "year": year_el.get("when") if year_el is not None else None,
        "references": refs,
        "grobid_status": "ok",
    }
```

> **为什么用 `processFulltextDocument`**:GROBID 没有"只给 header+引用"的轻 endpoint(`processHeaderDocument` 拿不到参考文献)。所以调全量 endpoint,但**只消费 `<teiHeader>` + `<listBibl>`**,丢弃 `<body>`(正文归 MinerU)。一次 HTTP 调用拿全论文元数据+引用,十几行合并进 ParsedDoc.extra_info。GROBID 慢的话,退路:`processHeaderDocument` + MinerU md 里抽引用串再逐条 `processCitation`。
>
> 合并进 `ParsedDoc.extra_info`:{doi, authors, year, references[]},blocks 不渲染参考文献(keep:false)。

### 5.7 PG documents 表(元数据 + 断点续跑 + 哈希去重,v4.1)

```sql
CREATE TABLE documents (
    doc_id        TEXT PRIMARY KEY,
    file_md5      TEXT UNIQUE,          -- v4.1 哈希去重:A 落盘后写入
    doc_type      TEXT,                 -- paper / policy / esg_report / ...
    doc_type_cn   TEXT,
    title         TEXT,
    raw_path      TEXT,
    cleaned_path  TEXT,                 -- cleaned/<doc_id>.md
    process_stage TEXT,                 -- v4.1 断点:unparsed / cleaned / vector_indexed / graph_indexed
    global_review_flag TEXT,            -- ok / needs_human_review
    error_type    TEXT,
    -- 论文专属(GROBID 轻量产出)
    doi           TEXT,
    authors       TEXT,                 -- JSON array
    pub_year      INT,
    created_at    TIMESTAMP DEFAULT now(),
    updated_at    TIMESTAMP DEFAULT now()
);
CREATE INDEX idx_md5   ON documents(file_md5);
CREATE INDEX idx_stage ON documents(process_stage);
CREATE INDEX idx_type  ON documents(doc_type);
```

**续跑 + 去重 30 行**:

```python
import hashlib, psycopg2

STAGE_RANK = {"unparsed": 0, "cleaned": 1, "vector_indexed": 2, "graph_indexed": 3}

def should_skip(conn, pdf_path, target_stage):
    """返回 (md5, skip)。已达到 target_stage 则跳过(去重)。"""
    md5 = hashlib.md5(open(pdf_path, "rb").read()).hexdigest()
    with conn.cursor() as cur:
        cur.execute("SELECT process_stage FROM documents WHERE file_md5=%s", (md5,))
        row = cur.fetchone()
    if not row:                       # 没记录 → 新文件
        return md5, False
    if STAGE_RANK.get(row[0], 0) >= STAGE_RANK[target_stage]:  # 已达目标 → 跳过
        return md5, True
    return md5, False                 # 有记录没跑完 → 续跑
```

> 调试期反复重跑脚本:跑前查 `file_md5`,已 `cleaned` 就不重跑 MinerU+GROBID,已 `vector_indexed` 就不重灌向量 —— 直接省 LLM/OCR 重复开销。中途报错,重启只跑 `process_stage < target` 的行,不从头来。

---

## 6. 边界(哪些恢复给 C/D,哪些由 LlamaIndex 承担)

| 原职责 | 现在谁做 |
|---|---|
| **B(解析清洗)** | MinerU 出正文 + GROBID 轻量出论文元数据/引用;清洗注入 `#【】` 章节标记;输出 md + ParsedDoc JSON |
| **C(切片索引)** | **LlamaIndex** `MarkdownNodeParser` 按 `#【】` 自动切(不调 LLM 分段)+ `VectorStoreIndex` |
| **C(多维分类)** | 简化/暂缓——LlamaIndex 靠语义检索,分类标签可作为 pgvector metadata 过滤,**非必须** |
| **D(检索)** | **LlamaIndex** 混合检索:向量 + KG 图遍历 |
| **D(知识图谱)** | **LlamaIndex** `KnowledgeGraphIndex` 抽三元组写入 Neo4j(白名单强制) |
| **E(假设生成)** | 仍由 E 负责,但通过 LlamaIndex `query_engine` 取检索结果 |

> **v4.1 关键**:原先 D 手握的"知识图谱 schema + 检索",现在由 LlamaIndex 承担大部分。D 若要保留价值,应 focus 在 **5.5 的图谱节点/关系定制 + 白名单后置过滤 + 检索后处理**,而不是从头实现。

---

## 7. 阶段交付清单

| 阶段 | 交付物 | 验收 |
|---|---|---|
| **0 环境** | `docker-compose.yml`(mineru+grobid+pg+neo4j)、`pip` 依赖清单 | 四服务能起;MinerU 跑通 1 份 PDF,GROBID 跑通 1 份电子论文 |
| **1 测试集** | `samples/test_set/`(10 论文 + 5 政策 + 5 ESG) | 手动下载的 PDF 可正常解析 |
| **2 单链路** | 1 篇论文:PDF→MinerU→GROBID 轻量(元数据/引用)→清洗(章节标记)→LlamaIndex 向量索引→检索 | 检索"绿色信贷"能召回相关段落;Neo4j 有引用边 |
| **3 KG 抽取** | `KnowledgeGraphIndex` 抽实体/关系 → Neo4j(白名单);检索融合图遍历 | 查"张三(2023)用了什么方法"能答 |
| **4 E 接入** | LlamaIndex → E 假设生成 | 端到端:输入问题→检索→图谱→假设 |

---

## 8. 风险与回退

| 风险 | 触发 | 缓解 |
|---|---|---|
| MinerU 资源重 | 一次加载 GB 级模型,批量慢 | 分批处理;只用 GPU 机器;小数据 CPU 兜底 |
| MinerU 安装坑多 | 依赖冲突 | 用官方 Docker 镜像 magic-pdf-container;pip 装失败换镜像 |
| LlamaIndex 版本迭代快 | API 变动 | 锁定版本;查官方文档适配 |
| KG 抽取成本高 | 全量抽每个 chunk | `max_triplets_per_chunk=5` + **只抽关键块** + 白名单后置过滤 |
| 引用抽取弱 | 电子论文已用 GROBID;扫描件引用降级 | 电子论文 GROBID 精确抽;扫描件 MVP 接受"半精确",要精确再 OCR 后补 GROBID |
| 图谱过度膨胀 | LLM 乱抽无关三元组 | 白名单 prompt + 后置过滤器双保险(§5.5),小样本天然干净 |
| GROBID 额外服务 | 多一个 Docker 容器 | 只对电子论文跑;扫描件跳过;无状态 HTTP 不恢复双队列 |
| Neo4j 额外服务 | 部署复杂度 | 若嫌重退回 PG+AGE;但 LlamaIndex 对 Neo4j 支持更成熟 |

---

## 9. 结论

**v4.1 核心理念**:B 保留"解析清洗 + 领域规则 + 质量控制 + 工程底座",切片/索引/检索/KG 抽取交给 LlamaIndex;论文元数据/引用交给 GROBID 轻量(正文仍 MinerU);存储 PG+pgvector+Neo4j,PG 兼断点去重。

**B 现在要写的代码**(总量仍小,v4.1 +2 项):
1. MinerU 适配器(薄封装)
2. 清洗规则 + **章节标记注入**(§5.2,v4.1 新增)
3. ParsedDoc 精简 Pydantic 模型
4. GROBID 轻量适配器(§5.6,v4.1 恢复,十几行)
5. LlamaIndex 索引/检索编排(§5.4,约 100 行,MarkdownNodeParser + 白名单 prompt)
6. PG documents 表 + 续跑去重(§5.7,v4.1,30 行)
7. docker-compose(mineru + grobid + pg + neo4j)

**其余**(切片参数、混合检索细节、KG 后置过滤细节)由 LlamaIndex 配置项 + Neo4j 查询搞定,不需要从零写。
