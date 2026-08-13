# HypoWeaver-Qwen

HypoWeaver-Qwen 是一个面向实证研究的代码原生工作流系统。它把案例接入、研究设计、统计执行、独立复现、主张审查和 H1–H4 人工闸门放在同一条可审计链路中，并明确区分“工程执行成功”和“科学结论获支持”。

> 当前公开部署：[hypoweaver-qwen.vercel.app](https://hypoweaver-qwen.vercel.app)。公开站点是无真实数据、无外部模型调用的交互演示；完整研究执行请使用本地或 Docker 部署。

## 当前能力

- React + Vite 研究工作台；
- FastAPI 工作流 API 与自动 OpenAPI 文档；
- H1 研究边界、H2 设计冻结、H3 逐条主张授权、H4 封存；
- Fixture、Qwen 和 `code_owned` 三种模型路由；
- 独立 Research Engine，支持真实面板、政策因果、空间模型与独立复现；
- SQLite 状态仓库、不可变数据引用、哈希绑定和 HMAC-SHA256 封存；
- Group1 → Group2 冻结交接包接入；
- Docker Compose 双服务部署和 GitHub Actions 回归。

2026-08-13 的 Group1 → Group2 真实验收已经完成：工程执行 `succeeded`、估计器级复现 `matched`、科学状态 `limited`、5 条候选主张全部拒绝。详见[产品验收记录](docs/group1-group2-product-acceptance-2026-08-13.md)。

## 重要边界

公开仓库不包含：

- Group1 私有交接目录与原始研究数据；
- `backend/var/` 下的数据库、上传文件、验收回执和图表；
- Qwen/DashScope API key、工作流 token、Research Engine token 或封存密钥。

因此，克隆仓库后默认可以运行 Fixture 全流程；真实研究运行需要用户自行登记数据并配置执行器。前端显示“工程通过”不等于论文级因果结论获准。

## 1 分钟启动：Docker Compose

要求：Docker Desktop 或 Docker Engine + Compose v2。

```bash
git clone https://github.com/HFT-Hunan-Uniiversity/HypoWeaver-Qwen.git
cd HypoWeaver-Qwen
cp .env.example .env
```

修改 `.env` 中的三个占位秘密：

- `HYPOWEAVER_API_TOKEN`
- `RESEARCH_ENGINE_TOKEN`
- `HYPOWEAVER_SEAL_SECRET`（至少 32 字节）

然后启动：

```bash
docker compose up --build
```

可用入口：

- 工作台：<http://127.0.0.1:8000>
- 健康检查：<http://127.0.0.1:8000/api/v1/health>
- Swagger UI：<http://127.0.0.1:8000/docs>
- OpenAPI：<http://127.0.0.1:8000/openapi.json>

容器把工作流和 Research Engine 作为两个隔离服务运行，并共享同一个私有数据卷。只有工作流端口 `8000` 对宿主机开放。

## 本地开发

要求：Python 3.11 或 3.12、Node.js 22+。

### 安装

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r backend/requirements-lock.txt
npm --prefix frontend ci
```

### 启动三个进程

终端 1：Research Engine。

```bash
python -m uvicorn hypoweaver.research_api:app --app-dir backend/src --host 127.0.0.1 --port 8001
```

终端 2：工作流 API。

```bash
# Windows PowerShell
$env:RESEARCH_ENGINE_URL='http://127.0.0.1:8001'
python -m uvicorn hypoweaver.api:app --app-dir backend/src --host 127.0.0.1 --port 8000
```

```bash
# macOS/Linux
RESEARCH_ENGINE_URL=http://127.0.0.1:8001 \
python -m uvicorn hypoweaver.api:app --app-dir backend/src --host 127.0.0.1 --port 8000
```

终端 3：前端。

```bash
npm --prefix frontend run dev
```

打开 <http://127.0.0.1:5173>。

## 最短 API 调用

健康检查：

```bash
curl http://127.0.0.1:8000/api/v1/health
```

创建一个 Fixture run：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/runs \
  -H "Content-Type: application/json" \
  -H "X-Hypoweaver-Token: $HYPOWEAVER_API_TOKEN" \
  -d '{
    "preset_case_id": "green-finance-did",
    "mode": "fixture",
    "model_provider": "fixture",
    "execution_mode": "fixture"
  }'
```

运行仓库自带的完整 H1–H4 示例客户端：

```bash
python examples/python_client.py \
  --base-url http://127.0.0.1:8000 \
  --token "$HYPOWEAVER_API_TOKEN"
```

完整的请求结构、上传数据、H1–H4 决策、Python/JavaScript 示例和错误码见 [API 调用指南](docs/API.md)。

## 文档

- [API 调用指南](docs/API.md)
- [部署指南](docs/DEPLOYMENT.md)
- [Group1 → Group2 后端验收](docs/group1-group2-backend-acceptance-2026-08-12.md)
- [Group1 → Group2 前端真实链路验收](docs/group1-group2-product-acceptance-2026-08-13.md)

## 项目结构

```text
backend/
  src/hypoweaver/       工作流、统计执行、复现、图表与 API
  tests/                 后端回归套件
  scripts/               数据面板构建与 Group1→Group2 验收脚本
frontend/
  src/                   React 工作台
  tests/                 Vitest 回归
  vercel.json            无真实数据的公开前端演示部署
docs/                    调用、部署与验收文档
examples/                可直接运行的 API 客户端
Dockerfile               工作流与 Research Engine 的共同镜像
docker-compose.yml       双服务与持久卷编排
```

## 验证

```bash
python backend/run_tests.py
npm --prefix frontend test
npm --prefix frontend run build
```

当前基线：后端 572 项测试、前端 61 项测试通过。GitHub Actions 会在每次 push 和 pull request 上重复执行这些检查。

公开 CI 不包含私有企业面板数据；对应的 29,919 行真实回归锚点会明确标记为 `skipped`。在受控环境登记该数据后，同一测试会自动执行完整估计与复现校验。

## 安全提示

- 对外部署必须设置 `HYPOWEAVER_API_TOKEN`；所有写接口使用 `X-Hypoweaver-Token`。
- `RESEARCH_ENGINE_TOKEN` 只用于工作流服务到 Research Engine 的内部调用。
- `HYPOWEAVER_SEAL_SECRET` 必须稳定保存；更换后旧封存无法用新密钥复核。
- 不要把 `.env`、数据集、`backend/var` 或运行回执提交到 Git。
- SQLite 方案适合单实例或共享持久卷；多实例生产环境应先迁移到外部事务数据库和对象存储。

## 许可证

当前仓库尚未声明开源许可证。公开可见不等于自动授予复制、修改或再分发权；项目方确定许可证后应补充 `LICENSE`。
