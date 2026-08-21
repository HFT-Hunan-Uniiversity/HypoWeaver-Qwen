# 当前进度与后续执行计划

> 更新时间：2026-08-21。本文件是给用户审阅的**执行进度快照 + 后续计划**。
> 完整的技术决策记录在 `docs/TECHNICAL_ARCHITECTURE.md`。

---

## 一、已完成 ✅

### 阶段 1：Git 基础（仓库 A）

| 文件 | 说明 |
|---|---|
| `.gitignore` | 排除 `models_cache/ .venv/ PDFs/ cleaned/ cleaned_meta/ artifacts/ input/ logs/ .env` |
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
| `scripts/download_papers.py` | 数据中心论文下载：路径 A 公开 Feed API（元数据）+ 路径 B npm 全文工具（需 token）；分页 + dataset_version 一致性检查 |
| `scripts/parse_all.py` | 批量文档解析：**自动检测 PDF/TXT/XML**；PDF 走 MinerU，TXT/XML 直接读取；断点续跑 |
| `scripts/report_status.py` | 动态状态报告：不写死 37，动态扫描 cleaned/ |
| `scripts/rebuild_status.py` | 状态文件重建：从 cleaned/ + kg/ + hdf5 产出重建 `processed_docs.json` |
| `scripts/sample_check.py` | 抽样质检：随机抽 N 篇，输出 KG 实体/关系/向量 chunks 统计表 |
| `run_pipeline.sh` | **云上一键跑批**：环境检查 → 下载 → 解析 → KG → 向量化 → 状态报告，全流程 tee 日志 |
| `src/api/server.py` | **FastAPI HTTP 服务**：`/health` `/status` `/query` `/search/vector` `/search/graph`，端口 8002 |

### 已验证
- 全部 13 个 Python 文件 **AST 语法检查通过** ✅
- `src/status.py` 模块导入冒烟测试通过 ✅

---

## 二、待办（按优先级）

### P0 — 本地回归（现在可做，不影响云端）⏳

| # | 任务 | 说明 |
|---|---|---|
| 1 | 本地回归测试 | 验证改造后本地 37 篇不回归：`python src/qa_runner.py "绿色金融政策如何影响企业技术创新"` |
| 2 | 状态文件冒烟 | `python scripts/rebuild_status.py` 重建本地状态 → `python scripts/report_status.py` 看动态数字 |
| 3 | FastAPI 冒烟 | `uvicorn src.api.server:app --port 8002` 起服务，curl `/health` `/status` `/query` |

### P0 — Git 提交 + 云部署准备 🚀

| # | 任务 | 说明 |
|---|---|---|
| 4 | `git init` + 首次 commit | 纳入 `.gitignore requirements.txt INSTALL.md src/ scripts/ run_pipeline.sh docs/` 两个 md 交接文档 |
| 5 | 生成 SSH 公钥 | 发给交接人，等 `ACCESS_READY`（交接文档已确认账号开通） |

### P1 — 云上执行（等收到 ACCESS_READY 后）

| # | 步骤 | 命令概览 |
|---|---|---|
| 6 | 首次登录确认 | `ssh greenfinance-vector@106.53.153.215` + 校验主机指纹 |
| 7 | 确认数据下载工具 | 服务器上 clone/定位 `green-finance-data-center`，确认 token 获取方式 |
| 8 | git clone 仓库 A | 拉到 `/srv/green-finance-vector/` |
| 9 | 建 venv + 装依赖 | `pip install -r requirements.txt` + modelscope 下载 BGE |
| 10 | 配置 `.env` | `DASHSCOPE_API_KEY` 等（0600） |
| 11 | 下载全文 | `npm run fulltext:download` → `input/`（564 份资产，SHA-256 校验） |
| 12 | 一键跑批 | `bash run_pipeline.sh --incremental`（MinerU 2000 页/天限制，按天分批） |
| 13 | 验证 | `python scripts/report_status.py` + `sample_check.py 10` + `qa_runner.py` 问答 |

### P2 — 监控增强 / 交付收尾

| # | 任务 | 说明 |
|---|---|---|
| 14 | 更新 `docs/TECHNICAL_ARCHITECTURE.md` | 把最终运行时架构（纯 Python + hdf5 + networkx，无 Neo4j/Qdrant）固化进文档 |
| 15 | 更新交接文档 | 云上跑批记录、失败清单、如何增量重跑 |

---

## 三、风险点与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| **MinerU 2000 页/天限制** | 551 篇 PDF 约数万页，需要多天 | 断点续跑已内置（cleaned_meta 存在即跳过）；`--mode incremental` 按天重跑 |
| **服务器 3.5GB 内存硬上限** | torch + hdf5 + networkx 同时驻留可能紧张 | 一次只跑一个阶段；向量化 batch_size=32；KG 与向量化分开执行 |
| **全文下载 token 缺失** | 无法下载全文 | 先用 37 篇本地回归；token 由交接人私下提供，不入 Git |
| **LLM 抽取失败** | 单篇 KG 抽取 API 超时/限额 | 失败记录到 `processed_docs.json`，`--mode retry_failed` 重试；jsonl 日志定位 |
| **状态文件损坏** | 断点续跑失效 | `rebuild_status.py` 从产出重建 |
| **文件名冲突/清洗不一致** | doc_id 不唯一 | `article_id` 作为主键；`parse_all.py` 用 safe_filename 规范化 |

---

## 四、架构最终形态（无 Neo4j、无 Qdrant）

```
input/ (PDF/TXT/XML)
  │  download_papers.py (Feed API + npm 工具)
  ▼
parse_all.py (MinerU 云 API)
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

**完成上述 P0 后即可 git push 上云。计划文档以本文件为准。**

---

## 五、我需要你确认的事

1. ✅ **本地回归**：现在跑本地 37 篇回归 + FastAPI 冒烟吗？（P0 项 1-3）
2. ⏳ **Git 提交**：确认 `.gitignore` 规则后 `git init + commit`（P0 项 4）——需要你提供想推送的远程仓库地址（或先本地 commit）
3. ⏳ **SSH 公钥**：需要生成 `id_ed25519` 公钥发给交接人（P0 项 5）——需要你告知是否有现成公钥

其余云上步骤等收到 `ACCESS_READY` 后执行。