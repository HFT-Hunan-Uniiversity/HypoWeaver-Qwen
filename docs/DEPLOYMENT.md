# HypoWeaver-Qwen 部署指南

## 1. 部署形态

仓库提供两种部署形态，它们的能力边界不同。

| 形态 | 用途 | 持久化 | 真实执行 |
| --- | --- | --- | --- |
| Vercel 前端演示 | 产品预览、界面评审 | 无 | 不启用 |
| Docker Compose | 本地、单机服务器、带持久卷的容器平台 | SQLite + 私有卷 | 支持 |

Vercel 配置故意构建 `VITE_PUBLIC_DEMO=true` 的静态前端。它不会上传 Group1 数据、API key 或本地回执，也不应被描述成论文生产环境。

## 2. Docker Compose 完整部署

### 2.1 准备配置

```bash
cp .env.example .env
```

至少替换：

```text
HYPOWEAVER_API_TOKEN
RESEARCH_ENGINE_TOKEN
HYPOWEAVER_SEAL_SECRET
```

如需 Qwen，再填写 `DASHSCOPE_API_KEY`。`HYPOWEAVER_SEAL_SECRET` 至少 32 字节，且必须随备份一起安全保存。

### 2.2 启动

```bash
docker compose up --build -d
docker compose ps
docker compose logs --tail=100 workflow
```

验证：

```bash
curl http://127.0.0.1:8000/api/v1/health
curl http://127.0.0.1:8000/openapi.json
python examples/python_client.py \
  --base-url http://127.0.0.1:8000 \
  --token "$HYPOWEAVER_API_TOKEN"
```

### 2.3 数据卷

Compose 使用 `hypoweaver-data` 命名卷，同时挂载到两个容器的 `/app/backend/var`。它保存：

- `hypoweaver.db`；
- 数据集 registry 与上传文件；
- runtime config；
- seal key（未显式设置 `HYPOWEAVER_SEAL_SECRET` 时）；
- 图表和运行产物。

不要只备份 SQLite 文件而遗漏上传数据、registry 和 seal key。建议对整个卷做一致性备份，并在恢复后执行健康检查和一个 Fixture run。

### 2.4 更新

```bash
git pull --ff-only
docker compose build --pull
docker compose up -d
```

更新前备份数据卷。不要在同一个 SQLite 卷上同时运行多个 workflow 副本。

## 3. 部署到通用容器平台

Render、Railway、Fly.io、Cloud Run 或自有服务器均可使用仓库根目录的 `Dockerfile`。完整研究执行需要两个进程：

工作流：

```text
python -m uvicorn hypoweaver.api:app --host 0.0.0.0 --port 8000
```

Research Engine：

```text
python -m uvicorn hypoweaver.research_api:app --host 0.0.0.0 --port 8001
```

两个服务必须能访问同一份私有数据卷，且数据卷在两边挂载为相同路径，否则 Dataset Registry 中的不可变本地路径无法解析。只公开 workflow；Research Engine 放在私有网络，并配置 `RESEARCH_ENGINE_TOKEN`。

生产环境变量：

| 变量 | 必需 | 说明 |
| --- | --- | --- |
| `HYPOWEAVER_API_TOKEN` | 是 | 对外写接口 token |
| `HYPOWEAVER_SEAL_SECRET` | 是 | H4 HMAC 密钥，至少 32 字节 |
| `HYPOWEAVER_DB_PATH` | 是 | 持久卷内 SQLite 路径 |
| `HYPOWEAVER_DATASET_REGISTRY_PATH` | 是 | 两服务共享的 registry 路径 |
| `HYPOWEAVER_UPLOAD_ROOT` | 是 | 持久卷内上传目录 |
| `HYPOWEAVER_RUNTIME_CONFIG_PATH` | 推荐 | 持久卷内运行时配置 |
| `RESEARCH_ENGINE_URL` | 是 | 私网 Research Engine URL |
| `RESEARCH_ENGINE_TOKEN` | 是 | 两服务间 token |
| `DASHSCOPE_API_KEY` | 按需 | Qwen 模型调用 |
| `QWEN_MODEL` | 按需 | 默认 `qwen-plus` |
| `QWEN_BASE_URL` | 按需 | DashScope OpenAI-compatible endpoint |

## 4. Vercel 前端演示

`vercel.json` 会：

- 在 `frontend/` 安装依赖；
- 运行 Vite 生产构建；
- 设置 `VITE_PUBLIC_DEMO=true`；
- 配置 SPA fallback。

CLI：

```bash
npx vercel
npx vercel --prod
```

或在 Vercel 控制台导入 GitHub 仓库，根目录保持仓库根目录。无需填写任何研究数据或 API key。

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

- Python 3.12 后端完整回归；
- Node.js 22 前端 61 项测试；
- TypeScript 和 Vite 生产构建。

工作流不读取真实团队凭据。`backend/run_tests.py` 会主动移除 Qwen、Research Engine 和 HypoWeaver token 环境变量，避免测试误调用外部服务。

## 7. 上线验收清单

- [ ] `.env` 未进入 Git；
- [ ] 三个 token/secret 已替换且不复用；
- [ ] 仅 workflow 对公网开放；
- [ ] `/api/v1/health` 返回 200；
- [ ] `/openapi.json` 可读取；
- [ ] 未带 token 的远程 POST 返回 401；
- [ ] Fixture 示例完成 H1–H4；
- [ ] 数据卷备份和恢复已演练；
- [ ] 工程状态与科学状态在 UI 和 API 中分开显示；
- [ ] Group1 私有数据和验收回执没有进入镜像或公开仓库。
