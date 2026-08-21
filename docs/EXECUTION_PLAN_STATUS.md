# 当前进度与后续执行计划

> 更新时间：2026-08-21。本文件是给用户审阅的**执行进度快照 + 后续计划**。
> 完整的技术决策记录在 `docs/TECHNICAL_ARCHITECTURE.md`。

---

## 一、已完成 ✅

### 阶段 1：Git 基础（仓库 A）

| 文件 | 说明 |
|---|---|
| `.gitignore` | 排除 `models_cache/ .venv/ PDFs/ cleaned/ cleaned_meta/ artifacts/ input/ logs/ .env config/` |
| `requirements.txt` | numpy / requests / sentence-transformers / torch / h5py / networkx / pydantic / fastapi / uvicorn / PyMuPDF / tqdm |
| `INSTALL.md` | 环境要求、pip install、BGE 模型下载、环境变量配置、验证命令 |

### 阶段 2：核心代码改造（仓库 A）

| 文件 | 改动 |
|---|---|
| `src/vector/store.py` | **新增 `get_store()` 工厂**（环境变量 `VECTOR_BACKEND` 切换后端，当前 hdf5，qdrant 预留）；新增 `get_vec()` / `get_batch()` 供迁移 |
| `src/retrieve/hybrid.py` | `HybridRetriever` 改用 `get_store()` 工厂，不锁定 `VectorStoreH5` |
| `src/kg/pipeline.py` | KG 成功/失败同时写入统一状态文件 `processed_docs.json`；新增 jsonl 结构化日志；CLI 新增 `--mode`（incremental/full/retry_failed） |
| `scripts/vectorize_all.py` | **全文重写**：断点续跑改用 `processed_docs.json`；用 `get_store()` 工厂；jsonl 日志；每 50 篇写分批中间报告；支持 `--mode` |

### 阶段 3：新增脚本与模块（仓库 A）

| 文件 | 说明 |
|---|---|
| `src/status.py` | **统一状态管理模块**：`processed_docs.json` 读-改-写、`mark_kg_done/failed`、`mark_vector_done/failed`、`rebuild_from_artifacts()` |
| `scripts/download_papers.py` | 数据中心论文下载：路径 A 公开 Feed API（元数据，Scopus 版）+ 路径 B 全文（Windows 下载器 + SSH 隧道）；分页 + dataset_version 一致性检查 |
| `scripts/parse_all.py` | 批量文档解析：**自动检测 PDF/TXT/XML**；PDF 走 MinerU，TXT/XML 直接读取（不花 MinerU 额度）；断点续跑 |
| `scripts/report_status.py` | 动态状态报告：不写死 37，动态扫描 cleaned/ |
| `scripts/rebuild_status.py` | 状态文件重建：从 cleaned/ + kg/ + hdf5 产出重建 `processed_docs.json` |
| `scripts/sample_check.py` | 抽样质检：随机抽 N 篇，输出 KG 实体/关系/向量 chunks 统计表 |
| `run_pipeline.sh` | **云上一键跑批**：环境检查 → 下载 → 解析 → KG → 向量化 → 状态报告，全流程 tee 日志 |
| `src/api/server.py` | **FastAPI HTTP 服务**：`/health` `/status` `/query` `/search/vector` `/search/graph`，端口 8002 |

### 已验证
- 全部 13 个 Python 文件 **AST 语法检查通过** ✅
- `src/status.py` 模块导入冒烟测试通过 ✅

### P0 — 本地回归（已完成 ✅）

| # | 任务 | 状态 |
|---|---|---|
| 1 | 本地回归测试 | ✅ 37 篇全部完成，KG 完成/向量化完成/状态文件一致 |
| 2 | 状态文件冒烟 | ✅ `report_status.py` 动态输出 37 篇，v5863 条向量 |
| 3 | FastAPI 冒烟 | ✅ `/health` `/status` 返回正常，`/query` 首调超时（模型加载期） |

### P0 — Git 提交与推送（已完成 ✅）

| # | 任务 | 状态 |
|---|---|---|
| 4 | `git init` + 2 次 commit | ✅ 66 文件入库，14171 行代码 |
| 5 | 密钥清理 | ✅ 3 个文件硬编码密钥已改为环境变量读取（`DASHSCOPE_API_KEY` / `MINERU_API_KEY`） |
| 6 | 推送到远程仓库 | ✅ `feature/rag-graph` 分支已推送 `github.com/HFT-Hunan-Uniiversity/HypoWeaver-Qwen` |

### P1 — 云上准备（进行中 🔄）

| # | 任务 | 状态 | 说明 |
|---|---|---|---|
| 1 | 登录服务器 + 指纹校验 | ✅ | ED25519 指纹 `SHA256:yA0y7TrY627Xav6sh0wYM+zoOOsulj7UdahAcsvtYdM` 匹配 |
| 2 | 确认环境 | ✅ | Python 3.12.3 / git 2.43 / Podman 4.9.3 / Node v20.20.0 |
| 3 | 确认 Feed API | ✅ | `matching_total: 1084`（Scopus 版元数据，免凭据） |
| 4 | 获取全文 Token + 下载 | ✅ | Windows 下载器 1.0.0（SSH 隧道 + Node v24），**455 份正文 = 84 TXT + 371 XML，598 MB** |
| 5 | 全文传输到服务器 | ✅ | `/srv/green-finance-vector/input/`（manifest.json + articles.ndjson + fulltexts/） |
| 6 | 克隆仓库到服务器 | ✅ | 工作目录 `/srv/green-finance-vector/`，`feature/rag-graph` 分支 |
| 7 | 建 venv + 装依赖 | 🔄 | 系统无 `python3-venv`/ensurepip，改用 `virtualenv` 创建成功；pip 安装中（阿里云镜像） |
| 8 | **云上前置冒烟** | ⏳ | 模块导入 + rebuild_status + report_status；报错即停 |
| 9 | 配置 `.env` | ⏳ | `umask 077` + `chmod 600`，密钥不入 Git/聊天 |
| 10 | 一键增量跑批 | ⏳ | `bash run_pipeline.sh --incremental` |
| 11 | 云上结果验收 | ⏳ | report_status → sample_check 10 → qa_runner |

### P2 — 监控增强 / 交付收尾（待办）

| # | 任务 | 说明 |
|---|---|---|
| 12 | 更新 `docs/TECHNICAL_ARCHITECTURE.md` | 把最终运行时架构（纯 Python + hdf5 + networkx，无 Neo4j/Qdrant；TXT/XML 直读，MinerU 仅作 PDF 兜底）固化进文档 |
| 13 | 更新交接文档 | 云上跑批记录、失败清单、如何增量重跑 |

---

## 二、数据处理架构（重要：本次会议确认）

> **两类数据不是分开的两批，而是全集与子集的关系。**

### 数据关系

```
Feed API 元数据（1084 条，Scopus 版）   ← 论文注册中心（article registry）
    │
    ├── 有全文正文（455 份资产 / 443 篇文章）→ 全流程：解析 → KG → 向量化（多 chunk）
    │
    └── 无全文正文（约 640 篇）→ 轻量处理：摘要向量化（1 chunk/篇，无 KG）
```

- **全文正文（455 份 = 84 TXT + 371 XML）**：KG 抽取与向量化的主原料，走完整流程
- **元数据（1084 条）**：统一注册，无全文的用摘要做向量化入库（`has_fulltext=false`），可检索但无深度问答

### 全文格式与 MinerU 的关系

| 格式 | 数量 | 解析方式 | 花费 MinerU 额度 |
|---|---|---|---|
| TXT | 84 | `parse_all.py` 直接读取 | ❌ 不花 |
| XML | 371 | `parse_all.py` 直接读取 | ❌ 不花 |
| PDF | 0（如后续补充） | MinerU 云 API | ✅ 2000 页/天 |

> **结论：当前 455 份全文全部零 MinerU 成本。** MinerU 降级为"仅 PDF 兜底"，不再是主路径。

### 目标向量库形态（同一库，分层）

```
向量库（all_store.h5）
├── 443 篇全文 → 每篇 N 条向量（全文分块） has_fulltext=true   可 KG / 深度问答
└── ~640 篇摘要 → 每篇 1 条向量（摘要嵌入） has_fulltext=false  仅摘要级检索
```

---

## 三、风险点与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| **MinerU 2000 页/天限制** | 仅影响后续补充的 PDF；当前 455 份全文为 TXT/XML，**不耗额度** | 断点续跑内置；PDF 按天分批 |
| **服务器 3.5GB 内存硬上限** | torch + hdf5 + networkx 同时驻留可能紧张（实际内存充足，见技术文档第 9.5 节） | 一次只跑一个阶段；向量化 batch_size=32；KG 与向量化分开执行 |
| **全文下载 token 缺失** | 无法下载全文 | 已解决；token 由交接人私下提供，不入 Git、不进聊天 |
| **LLM 抽取失败** | 单篇 KG 抽取 API 超时/限额 | 失败记录到 `processed_docs.json`，`--mode retry_failed` 重试；jsonl 日志定位 |
| **状态文件损坏** | 断点续跑失效 | `rebuild_status.py` 从产出重建 |
| **文件名冲突/清洗不一致** | doc_id 不唯一 | `article_id` 作为主键；`parse_all.py` 用 safe_filename 规范化 |
| **无全文的论文检索质量低** | 摘要级检索不如全文 | 向量库分两层标记 `has_fulltext`；问答时优先全文文证 |

---

## 四、架构最终形态（纯 Python，无 Neo4j、无 Qdrant）

```
input/fulltexts/（84 TXT + 371 XML）   ← Windows 下载器 + SSH 隧道
    │
    ▼
parse_all.py（TXT/XML 直接读取；PDF 走 MinerU 兜底）
    ▼
cleaned/*.md + cleaned_meta/*.json
    ├─► src/kg/pipeline.py (qwen-max 三元组)
    │        ▼
    │    artifacts/kg/*.kg.json  ──► graph_retriever (networkx 内存图)
    │
    └─► scripts/vectorize_all.py (BGE 嵌入)
           ▼
       artifacts/vector/all_store.h5  ──► get_store() 工厂 ──► HybridRetriever
                                            │
                                            └──(未来) qdrant 后端
                        AnswerEngine (qwen-max 回答生成)
                            │
                            ▼
                    src/api/server.py (:8002) ← HTTP
                    python src/qa_runner.py    ← CLI
```

---

## 五、P1 云上执行流程（当前进度快照）

```
┌──────┬────────────────────┬───────────────────────────────────────────────────────────────┐
│  #   │       步骤         │                    状态 / 说明                                 │
├──────┼────────────────────┼───────────────────────────────────────────────────────────────┤
│ 1    │ 登录 + 指纹校验     │ ✅ ED25519 指纹匹配                                           │
│ 2    │ 确认环境           │ ✅ Python 3.12 / git 2.43 / Podman 4.9.3                       │
│ 3    │ 确认 Feed API      │ ✅ matching_total: 1084（Scopus 版）                           │
│ 4    │ 获取 Token + 下载  │ ✅ Windows 下载器 1.0.0，455 份正文（84 TXT + 371 XML）        │
│ 5    │ 传输到服务器       │ ✅ /srv/green-finance-vector/input/                            │
│ 6    │ 克隆仓库           │ ✅ feature/rag-graph → .（工作目录已确认）                      │
│ 7    │ venv + 依赖        │ 🔄 virtualenv 创建成功；pip 安装中（阿里云镜像）                 │
│ 8    │ 云上前置冒烟       │ ⏳ import src.status/vector/kg + rebuild + report              │
│ 9    │ 配置 .env          │ ⏳ umask 077; DASHSCOPE_API_KEY; chmod 600                     │
│ 10   │ 一键增量跑批       │ ⏳ bash run_pipeline.sh --incremental                           │
│ 11   │ 云上结果验收       │ ⏳ report_status → sample_check 10 → qa_runner                  │
└──────┴────────────────────┴───────────────────────────────────────────────────────────────┘
```

> 说明：
> - 步骤 8 冒烟在**装完 venv 依赖后、配置 .env 前**执行，报错即停，**不执行 run_pipeline.sh**。
> - 全文下载用交接人提供的 **Windows 下载器 1.0.0**（SSH 隧道 `127.0.0.1:4173` + Token 隐藏输入），产物在本地，需 scp 到服务器，不入 Git。
> - 当前数据全部为 TXT/XML，**MinerU 2000 页/天不构成瓶颈**；重跑同一命令靠 `processed_docs.json` 断点续跑。

---

## 六、下一步动作

1. **等待依赖安装完成**（后台任务）→ 步骤 8 前置冒烟
2. **配置 `.env`**：需要你提供 DashScope API Key 的配置方式（本机已有的 `DASHSCOPE_API_KEY` 在服务器上需重新配置，由你在终端执行，不贴聊天）
3. **一键跑批**：`bash run_pipeline.sh --incremental`（先处理 455 份全文，KG + 向量化）
4. **全量元数据入库**：1084 条 Feed 元数据拉取（Scopus 版），无全文的走摘要向量化
5. **验收**：report_status / sample_check / qa_runner