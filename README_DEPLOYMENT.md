# 部署说明

## 1 Docker Compose 部署

建议使用 Windows 11 + WSL2/Docker Desktop，或 Linux + Docker Engine，均需 Compose v2。建议至少 4 核 CPU、16 GB 内存及 20 GB 可用空间。Qwen 由百炼推理，本地 GPU 非必需。首次构建需要下载镜像和依赖；代码压缩包不是离线镜像包。

在解压后的项目根目录执行：

```bash
python tools/init_env.py
docker compose config --quiet
docker compose up --build -d
docker compose ps
```

`init_env.py` 自动生成本机使用的四项随机服务凭证，并创建 `.env`；已有配置不会被覆盖。请先启动 Docker 引擎。只有交互演示时可不填百炼密钥；如需在线 Qwen，在 `.env` 中填写：

```dotenv
DASHSCOPE_API_KEY=填写自己的百炼密钥
QWEN_MODEL=填写本次任务需要的模型标识
QWEN_BASE_URL=填写该密钥在百炼控制台对应的兼容接口地址
```

不要将密钥上传网盘或填写到浏览器前端代码。配置后的令牌位于本机 `.env`，如工作台要求 API Token，使用 `HYPOWEAVER_API_TOKEN`。

启动后访问：

- 工作台：http://127.0.0.1:8000
- 工作流健康检查：http://127.0.0.1:8000/api/v1/health
- 知识服务状态：http://127.0.0.1:8000/api/v1/knowledge/health
- 接口文档：http://127.0.0.1:8000/docs

三服务为 `workflow`、`research-engine` 和 `knowledge`。默认仅将工作流 8000 端口绑定本机；另外两个服务通过内部网络和独立令牌通信。前端在镜像构建时生成并由工作流服务提供，无需另外部署前端。

查看运行日志或停止服务：

```bash
docker compose logs --tail=100 workflow
docker compose logs --tail=100 knowledge
docker compose down
```

不要执行 `docker compose down -v`，除非确认可以删除所有本机研究数据。更新前备份完整 `hypoweaver-data` 卷和本机封存密钥。当前为单实例 SQLite 持久化方案，不应同时启动多个工作流副本共享同一数据库。

## 2 知识库

默认 `knowledge-data/` 仅含项目自编的数据与方法说明，使用 hashing 检索，无需下载 BGE 模型。样例均标记为非全文证据；发现流程可能正确停在证据不足状态。它用于检验服务连通与边界，不能冒充完整实验语料。

如已获准使用完整知识库，将资产置于独立目录，并在 `.env` 中把 `HYPOWEAVER_KNOWLEDGE_DATA_DIR` 改为该目录，`HYPOWEAVER_KNOWLEDGE_EMBEDDING_BACKEND` 改为 `auto`。目录需包含 `all_store.h5`、`cleaned/`、`cleaned_meta/`、`kg/`、`manifest.json` 和 `manifests/doc_registry.csv`。BGE 版本应与建库版本一致，历史版本为 `BAAI/bge-small-zh-v1.5`、revision `7999e1d3359715c523056ef9478215996d62a620`。

知识库以只读方式挂载。知识状态中的 `degraded` 和具体警告必须检查；不应把“HTTP 可访问”当作全文库完整性通过。旧快照的历史边界与字段说明见 `docs/reference/KNOWLEDGE_DISCOVERY_INTEGRATION.md`。

## 3 不使用 Docker 的本地开发

使用 Python 3.11 或 3.12 和 Node.js 22。安装：

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install -r backend/requirements-knowledge.txt
npm --prefix frontend ci
```

按 `.env` 字段在各进程环境中配置同一组服务令牌。`.env` 是 Compose 的配置文件，直接运行 Uvicorn 不会自动加载它。将两个内部服务 URL 改为 `http://127.0.0.1:8001`、`http://127.0.0.1:8002`，知识和运行数据路径改为本机路径，然后分别在四个终端启动：

```bash
python -m uvicorn hypoweaver.knowledge_api:app --app-dir backend/src --host 127.0.0.1 --port 8002
python -m uvicorn hypoweaver.research_api:app --app-dir backend/src --host 127.0.0.1 --port 8001
python -m uvicorn hypoweaver.api:app --app-dir backend/src --host 127.0.0.1 --port 8000
npm --prefix frontend run dev
```

开发前端访问终端显示的 Vite 地址，`/api` 默认代理到本机 8000。机构服务器部署优先使用 Compose；对外访问时再配置域名、HTTPS 反向代理和访问控制。

## 4 常见问题

- Docker 报 `dockerDesktopLinuxEngine` 不存在：启动 Docker Desktop 的 Linux 容器引擎后重试。
- 模型返回未授权：核对密钥所属地域、工作空间、API Host 与模型权限。
- 只有演示，没有真实回归：检查当前模式、数据注册、变量绑定和人工审核状态。Fixture 不代表科学执行。
- 无法加载 BGE：默认公开样例不需要 BGE；完整 HDF5 语料需同版本模型文件或首次下载网络。
- 跨机器找不到数据：运行数据目录必须供工作流和执行服务共同访问；历史证据中的开发机路径仅为记录，不是当前部署路径。
