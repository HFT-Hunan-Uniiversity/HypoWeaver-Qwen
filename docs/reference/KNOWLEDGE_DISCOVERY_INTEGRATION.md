# 8.23 RAG-Graph 与 HypoWeaver 主线整合指南

更新日期：2026-08-31

## 结论

两条线已经按“资产服务化、科学流程主线化”整合，而不是直接执行 Git merge：

- `main`（`fe84404`）继续作为工作流、H1–H4、执行、复现与主张授权的权威主线；
- 8.23 的 `feature/rag-graph`（`d1b9525`）没有与 `main` 共享 merge base，不能安全当作普通功能分支合并；
- 8.23 的向量/HDF5、知识图谱 JSON 和清洗文本目录通过独立的只读 Knowledge Service 接入；
- 旧 Group1 Discovery Engine 的 schema、确定性 builder 与跨产物 validator 已迁入主线；
- Qwen 只生成受 EvidenceBundle 约束的 `DiscoveryPlan` 草案；人工 H0 审阅后，代码才把草案编译成 Group1 `GapCard` / `HypothesisCard`；
- H0 批准只允许候选进入现有 H1。未绑定真实数据时可以审阅研究边界，但不能执行统计分析或生成科学主张。

## 当前架构

```text
8.23 只读资产
  all_store.h5 + cleaned/ + cleaned_meta/ + kg/
                         │
                         ▼
Knowledge Service :8002
  BGE/向量召回 ──► EvidenceHit（清洗片段、位置、内容哈希）
  图谱召回 ──────► GraphEdgeCandidate（非权威提示）
                         │
                         ▼
EvidenceBundle ──► Qwen DiscoveryPlan（仍未获科学批准）
                         │
                    H0 人工审阅
                         │
                         ▼
Group1 deterministic builder + schema/semantic validators
             GapCard + HypothesisCard + ResearchGraph snapshot
                         │
                    H0 明确批准
                         │
                         ▼
HypoWeaver H1 → H2 → 执行/复现 → H3 → H4
```

三类对象不能混淆：

| 对象 | 含义 | 是否可作为科学证据 |
|---|---|---|
| `EvidenceHit` | 带稳定 chunk ID、清洗文本位置和 SHA-256 的检索命中 | 可进入 H0 审阅，但不是原始 PDF 页证据 |
| `GraphEdgeCandidate` | 8.23 LLM 图谱抽取的关系候选 | 否，不能单独支持结论 |
| `DiscoveryPlan` | Qwen 对 EvidenceBundle 的结构化解释草案 | 否，必须经过 H0 |

## 产品中的三类文献资源

资源库明确拆成三类，避免把不同证据等级混在一起：

| 页面 | 实际内容 | 可以做什么 |
|---|---|---|
| 系统论文库 | 8.23 离线语料快照；1,169 条记录，其中 105 条当前可通读，350 条为短索引文本，714 条仅有元数据 | 浏览语料覆盖；执行 BGE 语义召回与图谱扩展；打开单篇可用正文 |
| 我的原始 PDF | 用户上传的、可解析且未加密的论文 PDF | 按原始页阅读；整篇或当前页 AI 问答；引用原始页码；二次确认后删除本机文件 |

系统论文库通过 `GET /api/v1/knowledge/catalog` 返回库存、可读状态和分页目录，通过 `POST /api/v1/knowledge/search` 返回检索片段，通过 `GET /api/v1/knowledge/catalog/{document_id}/text` 分段读取单篇清洗正文。系统库中的清洗 Markdown 不等于上传区里的原始 PDF，两者不会在界面上混称为“原文”。原始 PDF 通过 `DELETE /api/v1/literature/documents/{document_id}` 精确删除单篇原文件及其逐页文本。

## 8.23 资产布局

Docker Compose 默认把宿主机 `knowledge-data/` 只读挂载到 `/app/knowledge`：

```text
knowledge-data/
  all_store.h5             # 8.23 BGE 向量库
  cleaned/                 # 加工后的清洗 Markdown；HDF5 本身不含 chunk 文本
    <doc_id>.md
  cleaned_meta/
    <doc_id>.json
  manifests/
    doc_registry.csv       # 权威全文/元数据边界与逐文档哈希
  kg/
    *.kg.json
  manifest.json            # 推荐：发布时绑定资产哈希/版本
  chunks.jsonl             # 可选；存在时优先用作已物化 chunk 目录
```

`all_store.h5` 只有向量和 metadata，不包含 chunk 文本。Knowledge Service 会按 8.23 分支的切片规则，从只读 `cleaned/` 与 `cleaned_meta/` 惰性重建命中 chunk；它不会修改或复制这些加工文件。

8.23 的 HDF5 metadata 本身没有 `has_fulltext`。必须配置 `HYPOWEAVER_KNOWLEDGE_DOCUMENT_REGISTRY_PATH` 指向交付包的 `manifests/doc_registry.csv`；服务会按注册表阻止 714 篇 metadata-only 文档冒充全文，并核对命中文档及元数据的 SHA-256。

### 2026-08-31 实物交付审计

当前收到的交付包与清单存在两处重要差异：清单声明应有 `input/fulltexts/` 下 455 份 TXT/XML 源文件，但已解压资产中这个目录不存在；注册表标记的 455 条全文记录中，只有 105 个 `cleaned/*.md` 文件包含可通读正文，另 350 个文件小于 500 字节，基本只有标题、期刊或摘要壳。原始 PDF 数量为 0。因此：

- 现有快照足以支持语义检索、图谱扩展和研究空白初筛，并可在线通读其中 105 篇正文；
- 现有快照不能提供原始 PDF 版式、图表、公式和可靠的原始页码阅读；
- 资源库会把 105 篇可通读正文、350 篇短索引文本和 714 篇题录分开显示；
- 这项缺口不会把检索服务健康状态误报为故障，但会作为目录边界警告返回。

论文目录接口支持 `readable_only=true`，资源库默认启用该筛选，只把当前 105 篇可通读正文放入阅读列表；短索引文本和纯元数据记录仍保留在总量与覆盖统计中。

如果需要补齐可持续的系统论文库，应向 8.23 开发者索取：

1. 清单声明的 `input/fulltexts/` 目录及 455 份 TXT/XML 源文件，并提供与 manifest/doc registry 一致的 SHA-256；
2. 实际采集、爬取、去重、清洗、入库和增量更新代码或服务，包括来源清单、配置、调度方式、限速策略、失败恢复和授权/许可说明；
3. 若要在系统库中实现原始页阅读，再提供原始 PDF 或稳定且获许可的下载地址，以及 `doc_id → PDF → 原始页码` 映射。

当前仓库和本次交付中没有发现在线采集器。产品因此把状态写成“离线快照 / 在线采集未接入”，不能对用户宣称系统正在实时爬取论文。

### 嵌入空间必须一致

8.23 README 声明向量由 `BAAI/bge-small-zh-v1.5` 生成。默认 `HYPOWEAVER_KNOWLEDGE_EMBEDDING_BACKEND=auto` 在检测到 HDF5 后会使用：

- 相同 BGE 模型；
- 交付清单声明的模型 revision；
- 相同标点/Markdown 预处理；
- 归一化余弦检索。

模型必须在容器可访问的缓存中，或允许首次启动下载。也可以把本地模型放在只读资产目录并将 `HYPOWEAVER_KNOWLEDGE_EMBEDDING_MODEL` 设置为容器内路径。

8.23 代码在 BGE 加载失败时会静默降级成 MD5 字符 n-gram。若建库日志证明 `all_store.h5` 使用了这个降级空间，必须显式设置：

```dotenv
HYPOWEAVER_KNOWLEDGE_EMBEDDING_BACKEND=legacy_rule
```

不要用 BGE 查询规则向量库，也不要用 hashing 查询 BGE 向量库；维度相同不代表向量空间兼容。

## 启动

1. 将 `.env.example` 复制为 `.env`，替换四个秘密，并配置 `DASHSCOPE_API_KEY`。
2. 把知识资产放入 `HYPOWEAVER_KNOWLEDGE_DATA_DIR` 指向的目录。
3. 启动三服务：

```bash
docker compose up --build
```

4. 检查状态：

```bash
curl http://127.0.0.1:8000/api/v1/health
curl http://127.0.0.1:8000/api/v1/knowledge/health
```

Knowledge Service 的 `status=degraded` 不应被忽略。常见原因包括缺少 manifest、缺少 chunk 清洗文本目录、BGE backend 不匹配或图谱目录不存在。

## 在线发现 API 顺序

前端本地版调用以下受保护接口：

1. `POST /api/v1/discovery/plans/generate`
   - 调用 Knowledge Service 检索；
   - 生成 EvidenceBundle；
   - 调用 Qwen 输出严格 `DiscoveryPlan`；
   - 拒绝任何引用 bundle 外 chunk 的计划。
2. `POST /api/v1/discovery/plans/review`
   - 要求至少 10 个字符的 H0 审阅记录；
   - 把计划编译为 `human_verified` 的 reviewed graph patch；
   - 运行 Group1 JSON Schema 与语义交叉验证；
   - 返回发布预览，不创建研究 run。
3. `POST /api/v1/discovery/plans/launch`
   - 再次确定性重建并校验发布包；
   - 记录 H0 批准理由、发布哈希、图谱 snapshot 和 evidence refs；
   - 创建停在现有 H1 的真实 run。

底层接口 `/api/v1/knowledge/catalog`、`/api/v1/knowledge/search`、`/api/v1/discovery/evidence-preview` 和 `/api/v1/discovery/releases/*` 用于资源库浏览、检索或其他客户端；研究计划产品链路走 `/api/v1/discovery/plans/*` 高层接口。

## 安全与科学边界

- Knowledge Service 不暴露宿主端口，只允许工作流容器访问，并使用 Bearer token；
- 知识目录是只读 bind mount，不进入 Git，不复制到工作流状态卷；
- HDF5 每次检索以只读模式打开，并进行分块扫描，不保留跨请求可写句柄；
- 只有带清洗文本、稳定定位与内容哈希的 chunk 能成为 EvidenceHit；元数据命中不能冒充全文证据，EvidenceHit 也不能冒充原始 PDF 页证据；
- 图谱关系保留为候选，不能自动写成 `REPORTS_FINDING`；
- Qwen 不能引用 bundle 外证据，不能声称语料外的“全球研究空白”；
- 若原文访问级别是 `authenticated_internal_research_only`，在数据所有者明确批准第三方处理、并确认供应商条款前，不得把全文片段发送给 DashScope/Qwen；
- H0、H1、H2、H3、H4 的授权含义保持分离；H0 绝不授权执行或结论；
- 前端只把轻量 Gap/Idea 摘要保存在浏览器项目草稿中，完整 EvidenceBundle 和 DiscoveryPlan 只留在当前会话，批准后的状态由后端持久化。

## 当前仍需由部署者提供的外部资产

代码整合已经完成，但仓库不会包含以下私有或大型内容：

- 8.23 的 1,169 条论文记录、105 篇可通读正文、350 篇短索引文本、19,567 条向量和 10,138 节点图谱；
- BGE 模型缓存；
- DashScope API key；
- 用于真正执行研究的授权数据文件与 Research Engine 配置。

缺少这些资产时，服务会显式返回 `empty/degraded` 或阻断，不会回退成演示证据、伪造原文或继续统计执行。

## 验收命令

```bash
python backend/run_tests.py
npm --prefix frontend test
npm --prefix frontend run build
docker compose config

# 对已解压的 8.23 交付包做只读全量审计
python backend/scripts/audit_legacy_knowledge_delivery.py /path/to/knowledge-data

# 不向第三方发送全文：真实检索 + 本地技术 fixture，停在 H1
python backend/scripts/run_legacy_knowledge_e2e.py \
  --workflow-token "$HYPOWEAVER_API_TOKEN" \
  --output output/legacy-knowledge-e2e-receipt.json

# 仅在数据权利人明确授权后：真实检索 + Qwen 规划，仍停在 H1
python backend/scripts/run_qwen_knowledge_e2e.py \
  --workflow-token "$HYPOWEAVER_API_TOKEN" \
  --full-output output/qwen-generation.json \
  --receipt output/qwen-e2e-receipt.json
```

若 Qwen 生成已成功落盘，但后续确定性编译暴露了兼容性问题，可在修复后复用同一授权结果，不重复调用或计费：

```bash
python backend/scripts/run_qwen_knowledge_e2e.py \
  --workflow-token "$HYPOWEAVER_API_TOKEN" \
  --generation-input output/qwen-generation.json \
  --full-output output/qwen-generation.json \
  --receipt output/qwen-e2e-receipt.json
```

知识服务专用镜像还会安装 `h5py` 与 `sentence-transformers`。审计脚本会核验交付清单中的每个 SHA-256、全部 HDF5 metadata、向量有限性、重复 chunk、注册表覆盖、清洗文本回填和 NetworkX 图统计；两个 E2E 脚本都会再次验证 API 返回的全文标记、内容哈希和重复证据边界。离线脚本只证明本地 EvidenceBundle→H0 编译→H1 停门能够工作；Qwen 脚本还会拒绝包外引用，并把完整生成结果写入 Git 忽略的本地输出。两者都不构成科学批准。
