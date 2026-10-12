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

文献页支持最多 6 条手动中英文检索式、OpenAlex/Crossref 联合检索和 PDF 上传。可用 `LOCAL_LIBRARY_DIR` 指向一个已有本地目录：优先读取 `library.jsonl`（每行是一张证据卡，至少有字符串 title；可带 year、doi、authors、abstract、concepts），否则读取目录顶层 PDF。索引最多 10 MB/2000 行，PDF 最多 200 个，每个 30 MB；截断或坏行会在来源状态中提示。上传 PDF 提取前 100 页文字，保留前 12000 字摘录；扫描件需先 OCR。

### 导入研究数据

在项目的“数据与检验”页面上传 `.csv`、`.xlsx` 或 `.dta`，查看列名及标签后选择所需列，再确认导入。Excel 可切换工作表；Stata 仅加载选择的列。已上传文件可复用，不需要为了改变列选择重复上传。

公开碳市场案例的下载、准备、字段含义与引用见 [DATA_carbon_case.md](docs/DATA_carbon_case.md)。运行 `cd backend && uv run python -m hypoweaver.cases.carbon fetch`，然后 `uv run python -m hypoweaver.cases.carbon prepare`；刷新数据页即可选择资产。

数据读取上限为单文件 500 MB、300 列、200 万行，`DATA_DIR` 下 `staging/`、`datasets/`、`raw/` 的合计文件大小上限为 3 GB。达到上限会停止新导入并显示原因，不会删除历史数据。`staging/` 存上传原件（含失败留下的片段），`datasets/` 存已登记资产引用的 CSV，`raw/` 存案例原件。需要释放空间时先备份并核对用途；不要删除 SQLite 正在引用的分析 CSV。产品暂不提供自动清理或历史资产删除功能。
