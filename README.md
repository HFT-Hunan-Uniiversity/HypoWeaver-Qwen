# HypoWeaver v2

从研究方向出发，以真实文献、数据和检验结果形成研究提案的单用户本地工作台。产品规格见 [SPEC](docs/SPEC.md)，任务清单见 [PLAN](docs/PLAN.md)，已完成内容与验证记录见 [PROGRESS](PROGRESS.md)。

## 启动

需要 Python 3.12、uv 和 Node 22。在仓库根目录运行：

```sh
cp .env.example .env
make setup
make dev
```

打开 http://localhost:5173。开发服务器把 `/api` 转发到本机 8000 端口；SQLite 默认存放在仓库根目录 `var/`，刷新或重启不会丢失项目。相对 `DATA_DIR` 始终以仓库根目录为基准。

在项目列表新建项目，进入研究方向页填写问题和约束并保存。列表提供删除入口，删除需确认。目前按任务顺序交付，各阶段以 PROGRESS 的实际完成情况为准。

```sh
make test
make build
# 构建后也可只运行后端，由其托管前端
cd backend && uv run uvicorn hypoweaver.app:app --port 8000
```

模型配置只从本地 `.env` 或环境变量读取。`.env.example` 提供配置示例；密钥、数据库、上传文件和碳市场原始数据均不入 Git。真实模型调用需要 DASHSCOPE_API_KEY 和 QWEN_MODEL，测试使用替代客户端。
