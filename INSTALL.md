# RAG-Graph 安装指南

## 环境要求

- Python 3.10+
- 8 GB 内存（推荐）
- 操作系统：Windows / Linux / macOS

## 安装步骤

### 1. 克隆仓库

```bash
git clone <仓库地址>
cd Project正式
```

### 2. 创建虚拟环境

```bash
# Linux/macOS
python3 -m venv .venv
source .venv/bin/activate

# Windows
python -m venv .venv
.venv\Scripts\activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 下载 BGE 模型权重

模型权重约 184 MB，不进 Git，需手动下载：

```bash
# 方式一：通过 modelscope 下载（国内推荐）
pip install modelscope
python -c "from modelscope import snapshot_download; snapshot_download('BAAI/bge-small-zh-v1.5', cache_dir='./models_cache')"

# 方式二：自动下载（首次运行 embedding 时自动从 HuggingFace 拉取）
# 国内用户设置镜像：
export HF_ENDPOINT=https://hf-mirror.com
```

### 5. 配置环境变量

创建 `.env` 文件（不进 Git）：

```bash
# .env — 不进 Git，权限设为 0600

# DashScope API Key（用于 qwen-max LLM 调用）
DASHSCOPE_API_KEY=你的DashScope_API_Key（从 https://dashscope.console.aliyun.com 获取）

# 可选：VECTOR_BACKEND=hdf5（默认，当前仅支持 hdf5）
```

## 验证安装

```bash
# 检查 embedding 模型
python -c "from src.embedding import get_embedder; e = get_embedder(); print('ready:', e.is_ready)"

# 冒烟测试（需要本地有 cleaned/ 产出）
python src/qa_runner.py "绿色金融政策如何影响企业技术创新"
```

## 数据下载

论文元数据从服务器本地 Feed API 获取，无需额外凭据：

```bash
curl -fsS 'http://127.0.0.1:4173/api/feed/articles?scope=green&limit=500'
```

全文 PDF 下载需要 `green-finance-reader` COS 凭据，详见 `INTERNAL_FULLTEXT_API.md`。

## 云上部署

云服务器 Ubuntu 24.04，rootless Podman 模式。详见 `VECTOR_GRAPH_SERVER_HANDOFF.md`。

一键跑批：

```bash
bash run_pipeline.sh --incremental
```