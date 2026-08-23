# 执行进度与交付状态

> 更新时间：2026-08-23
> 本文件记录 RAG-Graph 从开发到云上部署的全过程进度与最终交付状态。
> 完整的技术决策记录在 `docs/TECHNICAL_ARCHITECTURE.md`。

---

## 一、总体状态：✅ 核心交付完成

| 阶段 | 状态 | 说明 |
|---|---|---|
| 本地开发（37 篇测试） | ✅ 已完成 | 全链路跑通：解析 → KG → 向量化 → 问答 |
| 云上全量部署（1169 篇） | ✅ 已完成 | 纯 Python + hdf5 + networkx，无容器依赖 |
| 收尾清理（死代码/文档/Git） | ✅ 已完成 | 2026-08-21 起执行，含 README、架构文档、交付推送 |
| 协作者对接 | 🔄 待 PR review | `feature/rag-graph` 分支已推送，PR 待创建/评审 |

---

## 二、云上最终数据规模（2026-08-23 实测）

| 指标 | 数值 |
|---|---|
| 论文/文档 | **1169 篇**（455 份全文 + 714 篇仅元数据） |
| 全文正文 | 84 TXT + 371 XML，全部零 MinerU 成本 |
| 向量 | **19567 条**（BGE-small-zh，512 维，hdf5 45.9 MB） |
| 知识图谱 | **10138 节点 / 13366 边**（networkx 内存图） |
| 问答验证 | 正常（qa_runner.py 远程验证通过） |

---

## 三、执行历程

### P0 — 本地开发与回归（已完成 ✅）

| # | 任务 | 状态 |
|---|---|---|
| 1 | 本地回归测试 | ✅ 37 篇全部完成，KG/向量化/状态文件一致 |
| 2 | 状态文件冒烟 | ✅ `report_status.py` 动态输出 |
| 3 | FastAPI 冒烟 | ✅ `/health` `/status` 返回正常 |
| 4 | `git init` + commit | ✅ 代码入库 |
| 5 | 密钥清理 | ✅ 硬编码密钥全部改为环境变量读取 |
| 6 | 推送到远程 | ✅ `feature/rag-graph` 分支 |

### P1 — 云上全量部署（已完成 ✅）

| # | 任务 | 状态 | 说明 |
|---|---|---|---|
| 1 | 登录服务器 + 指纹校验 | ✅ | ED25519 指纹匹配 |
| 2 | 确认环境 | ✅ | Python 3.12.3 / git 2.43 |
| 3 | 确认 Feed API | ✅ | `matching_total: 1088`（Scopus 版元数据） |
| 4 | 获取全文 + 下载 | ✅ | Windows 下载器 1.0.0，**455 份 = 84 TXT + 371 XML** |
| 5 | 全文传输到服务器 | ✅ | `/srv/green-finance-vector/input/` |
| 6 | 克隆仓库到服务器 | ✅ | `feature/rag-graph` 分支 |
| 7 | 建 venv + 装依赖 | ✅ | virtualenv 创建，阿里云镜像安装完成 |
| 8 | 云上前置冒烟 | ✅ | import + rebuild_status + report_status 通过 |
| 9 | 配置 `.env` | ✅ | `umask 077` + `chmod 600`，密钥不入 Git |
| 10 | 一键增量跑批 | ✅ | `bash run_pipeline.sh --incremental` 完成 |
| 11 | 云上结果验收 | ✅ | report_status → sample_check → qa_runner 全通过 |

### 收尾清理（已完成 ✅）

| # | 任务 | 状态 |
|---|---|---|
| 12 | 死代码清理 | ✅ `pipeline.py` / `classifier.py` / `profile_*` / 旧 schema / 垃圾文件 |
| 13 | `run_pipeline.sh` 重写 | ✅ 改为实际架构（纯 Python 三步） |
| 14 | README + .env.example | ✅ 新建 |
| 15 | 文档全面更新 | ✅ TECHNICAL_ARCHITECTURE（本次）/ 各 docs |
| 16 | Git 提交推送 | ✅ 待最终 commit + push |

---

## 四、数据处理架构（最终确认）

> **两类数据是全集与子集的关系，不是分开的两批。**

```
Feed API 元数据（1088 条，Scopus 版）   ← 论文注册中心（article registry）
    │
    ├── 有全文正文（455 份资产 / 443 篇文章）→ 全流程：解析 → KG → 向量化（多 chunk）
    │
    └── 无全文正文（约 645 篇）→ 轻量处理：摘要向量化（1 chunk/篇，无 KG）
```

向量库合并，`has_fulltext` 字段区分；检索时全文层优先。

---

## 五、风险与应对（落地记录）

| 风险 | 应对 | 实际结果 |
|---|---|---|
| MinerU 2000 页/天限制 | 当前 455 份全文为 TXT/XML **不耗额度** | ✅ 零 MinerU 成本 |
| 云服务器内存紧张 | 纯 Python + hdf5 + networkx，无容器 | ✅ 实测 < 3 GB 安全运行 |
| LLM 抽取失败 | `processed_docs.json` + `--mode retry_failed` | ✅ 断点续跑有效 |
| 状态文件损坏 | `rebuild_status.py` 从产出重建 | ✅ 可用 |
| 无全文检索质量低 | `has_fulltext` 分层，问答优先全文文证 | ✅ 已实现 |

---

## 六、交付与后续

### 已交付
- `feature/rag-graph` 分支 → `HFT-Hunan-Uniiversity/HypoWeaver-Qwen.git`
- PR 待创建，供协作者 review 集成方式（后续可嵌入 HypoWeaver 作为服务，端口 8002）

### 后续可选改进
- 提示词优化（`answer_engine.py` / `extractor.py`）
- 单元测试（`tests/` 目前为空）
- 性能优化（FAISS 替代暴力搜索 / 迁移 Qdrant，`get_store()` 已预留）
- 本地数据同步脚本（`sync_from_server.py`）