# RAG-Graph 服务器部署与运维指南

> 更新时间：2026-08-21
> 描述当前实际架构：纯 Python + hdf5 + networkx，无容器依赖。

---

## 0. 服务器信息

```text
HOST=106.53.153.215
USER=greenfinance-vector
LOGIN=ssh greenfinance-vector@106.53.153.215
WORKDIR=/srv/green-finance-vector
```

- 系统：Ubuntu Server 24.04 LTS，2 核、8 GB 内存、120 GB 系统盘
- Python：3.12.3
- 云防火墙已开放 SSH 22；**不得开放其他端口**

---

## 1. 首次登录与环境确认

```bash
ssh greenfinance-vector@106.53.153.215
id
python3 --version
git --version
```

首次连接会显示服务器 Ed25519 主机指纹。指纹不一致时立即停止并联系管理员。

---

## 2. 部署步骤

### 2.1 克隆仓库

```bash
cd /srv/green-finance-vector
git clone -b feature/rag-graph <仓库地址> .
# 或已克隆时拉取最新：
git fetch origin && git checkout feature/rag-graph && git pull
```

### 2.2 创建虚拟环境 + 安装依赖

```bash
cd /srv/green-finance-vector
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

### 2.3 配置环境变量

```bash
cd /srv/green-finance-vector
umask 077
nano .env
chmod 600 .env
```

`.env` 最小内容：

```bash
DASHSCOPE_API_KEY=你的DashScope_API_Key
```

> ⚠️ 密钥禁止提交 Git、禁止粘贴到聊天/日志中。

### 2.4 下载 BGE 模型权重

```bash
source .venv/bin/activate
pip install modelscope
python -c "from modelscope import snapshot_download; snapshot_download('BAAI/bge-small-zh-v1.5', cache_dir='./models_cache')"
```

权重约 184 MB，不进 Git。

### 2.5 准备全文数据

全文数据通过 Windows 下载器获取后传输到服务器：

```bash
# 从本地传输（Windows 终端）
scp -r input/fulltexts/ greenfinance-vector@106.53.153.215:/srv/green-finance-vector/input/
```

或使用服务器本机 Feed API：

```bash
python scripts/download_feed_metadata.py
```

---

## 3. 一键跑批

```bash
cd /srv/green-finance-vector
source .venv/bin/activate

# 增量跑批（推荐）
bash run_pipeline.sh --incremental

# 重试失败的文档
bash run_pipeline.sh --retry-failed
```

`run_pipeline.sh` 内部执行三步：

| 步骤 | 脚本 | 说明 |
|---|---|---|
| 1 | `python src/kg/pipeline.py` | KG 抽取（qwen-max LLM + 共现补边） |
| 2 | `python scripts/vectorize_all.py` | 切片 → BGE 嵌入 → hdf5 向量存储 |
| 3 | `python scripts/report_status.py` | 输出系统状态报告 |

---

## 4. 系统状态查看

```bash
# 实时状态报告
python scripts/report_status.py

# 抽样质检（随机抽 10 篇检查 KG + 向量）
python scripts/sample_check.py 10

# 重建状态文件（状态文件损坏时）
python scripts/rebuild_status.py
```

### /health 接口（FastAPI 服务运行时）

```bash
curl -s http://127.0.0.1:8002/health
```

预期响应：

```json
{
  "status": "ok",
  "graph_nodes": 10138,
  "graph_edges": 13366,
  "vector_count": 19567,
  "embedder_ready": true
}
```

---

## 5. 启动 HTTP API 服务

```bash
cd /srv/green-finance-vector
source .venv/bin/activate
uvicorn src.api.server:app --host 0.0.0.0 --port 8002
```

> 注意：h5py 非线程安全，多请求并发需加锁。`server.py` 已内置 `threading.Lock`。

---

## 6. 云上数据规模（实测）

| 指标 | 数值 |
|---|---|
| 论文/文档 | 1169 篇（455 份全文 + 714 篇仅元数据） |
| 全文正文 | 84 TXT + 371 XML，零 MinerU 成本 |
| 向量 | 19567 条（BGE-small-zh，512 维，hdf5 45.9 MB） |
| 知识图谱 | 10138 节点 / 13366 边（networkx 内存图） |
| 内存占用 | < 3 GB（8 GB 实例上安全运行） |

---

## 7. 内存预算

| 组件 | 内存 |
|---|---|
| Python + BGE 模型 | ~1.5-2 GB |
| networkx 内存图 | < 300 MB |
| hdf5 向量存储 | < 10 MB（按需读取） |
| 操作系统 + 其他 | ~500 MB |
| **合计** | **< 3 GB** |

---

## 8. 常见问题

### Q: `ImportError: No module named 'src'`

确保在项目根目录运行，且 `PYTHONPATH` 包含当前目录：

```bash
export PYTHONPATH=/srv/green-finance-vector:$PYTHONPATH
```

### Q: BGE 模型加载失败

确认 `models_cache/models/BAAI--bge-small-zh-v1.5/` 目录存在且有权读取。嵌入模块在模型不可用时会降级为字符 n-gram 哈希向量（零依赖兜底）。

### Q: KG 抽取超时

`qwen-max` API 调用超时默认 60 秒。网络不稳定时可在 `.env` 中增加超时：

```bash
LLM_TIMEOUT=120
```

### Q: hdf5 文件损坏

删除 `artifacts/vector/all_store.h5`，重新运行 `bash run_pipeline.sh --incremental` 重建向量存储。

### Q: 状态文件与实际产出不一致

```bash
python scripts/rebuild_status.py
```

从 `cleaned/`、`artifacts/kg/`、`artifacts/vector/` 实际产出重建 `processed_docs.json`。

---

## 9. 目录结构

```text
/srv/green-finance-vector/
├── src/                    # 核心代码
├── scripts/                # 批处理脚本
├── schemas/                # 数据模型
├── docs/                   # 技术文档
├── input/                  # 下载的全文（不进 Git）
├── cleaned/                # 清洗后 Markdown（不进 Git）
├── cleaned_meta/           # 元数据 JSON（不进 Git）
├── artifacts/
│   ├── kg/                 # *.kg.json 三元组文件
│   └── vector/             # all_store.h5 向量存储
├── models_cache/           # BGE 模型权重
├── logs/                   # 跑批日志
├── .venv/                  # Python 虚拟环境
├── .env                    # 环境变量（0600 权限）
├── .gitignore
├── requirements.txt
└── run_pipeline.sh         # 一键跑批
```

---

## 10. 需要管理员处理的事项

1. 首次开通或轮换 SSH 公钥
2. 调整 CPU、内存、磁盘上限
3. 修改云防火墙、Nginx、systemd 或宿主机目录权限
4. 需要公网服务、域名、TLS 或新的腾讯云资源

申请时给出用途、准确端口/目录、预计峰值 CPU/内存/磁盘、回滚方法和所需时限。

---

## 参考

- `docs/TECHNICAL_ARCHITECTURE.md` — 完整技术架构
- `docs/EXECUTION_PLAN_STATUS.md` — 执行进度与交付状态
- `README.md` — 项目概览与快速开始
- `INSTALL.md` — 本地安装指南
