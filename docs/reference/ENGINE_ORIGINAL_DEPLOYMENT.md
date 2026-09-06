# HypoWeaver-Qwen 部署指南

## 1. 部署形态

仓库提供两种部署形态，它们的能力边界不同。

| 形态 | 用途 | 持久化 | 真实执行 |
| --- | --- | --- | --- |
| Vercel 前端演示 | 产品预览、界面评审 | 无 | 不启用 |
| Docker Compose | 本地、单机服务器、带持久卷的容器平台 | SQLite + 私有卷 | 支持 |

Vercel 配置故意构建 `VITE_PUBLIC_DEMO=true` 的静态前端。它不会上传 Group1 数据、API key 或本地回执，也不应被描述成论文生产环境。

### 1.1 硬件与网络基线

完整研究执行采用“百炼 Qwen 云端推理 + 本地确定性执行”。因此本地 GPU 不是最低要求；CPU、内存、持久存储和稳定的 HTTPS 出站网络比本地大模型显存更关键。

| 资源 | 最低演示与小规模复现 | 推荐完整复现 | 说明 |
| --- | --- | --- | --- |
| CPU | x86-64 4 核 | 8 核及以上 | Research Engine 的统计估计、复算和多服务并行主要使用 CPU |
| 内存 | 16 GB | 32 GB | 16 GB 环境应避免同时运行多组批量任务和无关大型软件 |
| GPU | 不要求 | NVIDIA 8 GB 显存及以上，可选 | 仅用于本地 OCR、向量重建或离线加速；Qwen 推理由百炼完成 |
| 存储 | 20 GB 可用 SSD | 100 GB 以上 NVMe SSD | 需同时保留 Docker 镜像、依赖、上传数据、状态库、图表和多轮不可变快照 |
| 网络 | 稳定 HTTPS 出站连接 | 有线网络并准备热点备份 | 在线 Qwen 节点需要访问 DashScope；8001 和 8002 不应暴露公网 |
| 显示 | 1920×1080 | 1920×1080 或更高 | 便于同时核验工作流、结果和人工门禁 |

扩展到大批量 PDF 解析、本地视觉/OCR模型或多用户环境时，建议使用 16 核以上 CPU、64 GB 内存、200 GB 以上 NVMe SSD 和 16–24 GB 显存 GPU。该配置不是当前在线百炼路线的必要条件。

比赛或现场演示应预置冻结数据、知识资产和依赖镜像，并准备已封存真实调用回放与 Fixture 离线模式。回放和 Fixture 必须明确标注，不能冒充现场新产生的模型结果。

## 2. Docker Compose 完整部署

### 2.1 准备配置

```bash
cp .env.example .env
```

至少替换：

```text
HYPOWEAVER_API_TOKEN
RESEARCH_ENGINE_TOKEN
KNOWLEDGE_SERVICE_TOKEN
HYPOWEAVER_SEAL_SECRET
```

如需真实在线发现或 Qwen 研究节点，再填写 `DASHSCOPE_API_KEY`。`HYPOWEAVER_SEAL_SECRET` 至少 32 字节，且必须随备份一起安全保存。8.23 知识资产按只读目录准备，详见[知识发现整合指南](KNOWLEDGE_DISCOVERY_INTEGRATION.md)。

### 2.2 启动

```bash
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 workflow
docker compose logs --tail=100 knowledge
```

验证：

```bash
curl http://127.0.0.1:8000/api/v1/health
curl http://127.0.0.1:8000/api/v1/knowledge/health
curl http://127.0.0.1:8000/openapi.json
python examples/python_client.py \
  --base-url http://127.0.0.1:8000 \
  --token "$HYPOWEAVER_API_TOKEN"
```

### 2.3 数据卷

Compose 使用 `hypoweaver-data` 命名卷，同时挂载到 workflow 与 research-engine 的 `/app/backend/var`。它保存：

- `hypoweaver.db`；
- 数据集 registry 与上传文件；
- runtime config；
- seal key（未显式设置 `HYPOWEAVER_SEAL_SECRET` 时）；
- 图表和运行产物。

不要只备份 SQLite 文件而遗漏上传数据、registry 和 seal key。建议对整个卷做一致性备份，并在恢复后执行健康检查和一个 Fixture run。

Knowledge Service 不使用这个可写卷。宿主机的 `HYPOWEAVER_KNOWLEDGE_DATA_DIR` 以只读方式挂载到 `/app/knowledge`；知识资产应独立备份、哈希清单化，不能混入运行状态卷。

### 2.4 更新

```bash
git pull --ff-only
docker compose build --pull
docker compose up -d
```

更新前备份数据卷。不要在同一个 SQLite 卷上同时运行多个 workflow 副本。

## 3. 部署到通用容器平台

Render、Railway、Fly.io、Cloud Run 或自有服务器均可使用仓库镜像。完整在线发现与研究执行需要三个进程：

工作流：

```text
python -m uvicorn hypoweaver.api:app --host 0.0.0.0 --port 8000
```

Research Engine：

```text
python -m uvicorn hypoweaver.research_api:app --host 0.0.0.0 --port 8001
```

Knowledge Service（使用 `Dockerfile.knowledge`）：

```text
python -m uvicorn hypoweaver.knowledge_api:app --host 0.0.0.0 --port 8002
```

workflow 与 Research Engine 必须能访问同一份私有运行数据卷，且路径一致，否则 Dataset Registry 中的不可变本地路径无法解析。Knowledge Service 只访问单独的只读知识资产。只公开 workflow；另外两个服务放在私有网络，并分别配置 service token。

生产环境变量：

| 变量 | 必需 | 说明 |
| --- | --- | --- |
| `HYPOWEAVER_API_TOKEN` | 是 | 对外写接口 token |
| `HYPOWEAVER_SEAL_SECRET` | 是 | H4 HMAC 密钥，至少 32 字节 |
| `HYPOWEAVER_DB_PATH` | 是 | 持久卷内 SQLite 路径 |
| `HYPOWEAVER_DATASET_REGISTRY_PATH` | 是 | 两服务共享的 registry 路径 |
| `HYPOWEAVER_UPLOAD_ROOT` | 是 | 持久卷内上传目录 |
| `HYPOWEAVER_LITERATURE_ROOT` | 推荐 | 原始 PDF、逐页文本层和哈希清单的持久卷目录 |
| `HYPOWEAVER_RUNTIME_CONFIG_PATH` | 推荐 | 持久卷内运行时配置 |
| `RESEARCH_ENGINE_URL` | 是 | 私网 Research Engine URL |
| `RESEARCH_ENGINE_TOKEN` | 是 | 两服务间 token |
| `KNOWLEDGE_SERVICE_URL` | 在线发现必需 | 私网 Knowledge Service URL |
| `KNOWLEDGE_SERVICE_TOKEN` | 在线发现必需 | workflow → knowledge Bearer token |
| `HYPOWEAVER_KNOWLEDGE_DATA_DIR` | 在线发现必需 | 宿主机只读知识资产目录 |
| `HYPOWEAVER_KNOWLEDGE_VECTOR_PATH` | 8.23 HDF5 必需 | 容器内 HDF5 路径 |
| `HYPOWEAVER_KNOWLEDGE_CLEANED_DIR` | 无 chunks.jsonl 时必需 | 容器内原文 Markdown 目录 |
| `HYPOWEAVER_KNOWLEDGE_METADATA_DIR` | 推荐 | 容器内 cleaned metadata 目录 |
| `HYPOWEAVER_KNOWLEDGE_GRAPH_DIR` | 图谱检索按需 | 容器内 `*.kg.json` 目录 |
| `HYPOWEAVER_KNOWLEDGE_EMBEDDING_BACKEND` | 推荐 | 8.23 HDF5 默认 `auto`；降级库用 `legacy_rule` |
| `DASHSCOPE_API_KEY` | 按需 | Qwen 模型调用 |
| `QWEN_MODEL` | 按需 | 默认 `qwen-plus` |
| `QWEN_BASE_URL` | 按需 | DashScope OpenAI-compatible endpoint |

## 4. Vercel 前端演示

当前 Production：<https://hypoweaver-qwen.vercel.app>

`frontend/vercel.json` 会：

- 只把 `frontend/` 作为 Vercel 项目根目录；
- 运行 Vite 生产构建；
- 让 `/api/*` 明确返回 404；
- 配置 SPA fallback。

CLI：

```bash
cd frontend
npx vercel link
npx vercel env add VITE_PUBLIC_DEMO production,preview --value true --yes --no-sensitive
npx vercel --prod
```

或在 Vercel 控制台导入 GitHub 仓库，并把 Root Directory 设置为 `frontend`。无需填写任何研究数据或 API key。

限制：

- 该部署只用于前端交互和产品评审；
- 真实创建 run、上传数据、Group1 接入和模型执行均不开放；
- 不把浏览器 mock 结果当作实证结果。

如果以后需要在 Vercel 上运行 API，应先把 SQLite、上传文件、图表与密钥迁移到外部持久数据库/对象存储。Vercel Functions 可运行 FastAPI，但函数实例会按流量创建和回收；当前本地文件型状态模型不适合作为其生产持久层。

## 5. 反向代理与 TLS

单机部署可在 workflow 前放置 Nginx、Caddy 或云负载均衡器：

- 强制 HTTPS；
- 限制最大上传体积；
- 为 `/api/v1/runs/*/gates/*` 等写接口设置审计日志；
- 不对公网暴露 Research Engine 端口；
- 不在代理日志中记录 token header 或请求正文中的密钥。

当前前端与 API 同源，不需要额外 CORS。若拆分域名，应在后端实现并审核明确的 origin allowlist，不能使用 `*` 配合凭据。

## 6. CI/CD

`.github/workflows/ci.yml` 在 push 到 `main` 和 pull request 时运行：

- Python 3.12 工作流后端完整回归；
- Node.js 22 前端 61 项测试；
- TypeScript 和 Vite 生产构建。

工作流不读取真实团队凭据。`backend/run_tests.py` 会主动移除 Qwen、Research Engine 和 HypoWeaver token 环境变量，避免测试误调用外部服务。

CI 的轻量工作流环境不安装 BGE 模型或 `h5py`，因此 HDF5 实读测试会明确跳过；在 Knowledge Service 镜像或任何已安装 `requirements-knowledge.txt` 的环境中，该测试会执行。发布环境仍需用真实 8.23 资产完成一次 chunk 原文与向量命中的抽样核验。

## 7. 上线验收清单

- [ ] `.env` 未进入 Git；
- [ ] 四个 token/secret 已替换且不复用；
- [ ] 仅 workflow 对公网开放；
- [ ] `/api/v1/health` 返回 200；
- [ ] `/api/v1/knowledge/health` 返回 `ok`，或所有 `degraded` warning 已解释并接受；
- [ ] `/openapi.json` 可读取；
- [ ] 未带 token 的远程 POST 返回 401；
- [ ] Fixture 示例完成 H1–H4；
- [ ] 数据卷备份和恢复已演练；
- [ ] 工程状态与科学状态在 UI 和 API 中分开显示；
- [ ] Group1 私有数据和验收回执没有进入镜像或公开仓库；
- [ ] 知识资产只读挂载，BGE/legacy_rule 与建库空间一致；
- [ ] 随机抽样的 EvidenceHit 原文、chunk ID、section 与源 Markdown 一致。
