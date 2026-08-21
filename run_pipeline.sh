#!/bin/bash
# ============================================================================
# 云上一键跑批脚本 — run_pipeline.sh
# ============================================================================
# 用法:
#   bash run_pipeline.sh                  # 增量模式（默认）
#   bash run_pipeline.sh --full           # 全量重新跑（慎用）
#   bash run_pipeline.sh --incremental    # 增量模式
#   bash run_pipeline.sh --retry-failed   # 只重跑失败文档
#
# 设计:
#   - 纯 Python 调用，无外部容器依赖
#   - 每一步独立，可单独重跑
#   - 状态文件 artifacts/status/processed_docs.json 追踪进度
#   - 结构化日志写入 logs/ 目录
# ============================================================================

set -euo pipefail
cd "$(dirname "$0")"

# 加载环境变量
[ -f .env ] && set -a && . ./.env && set +a

MODE="${1:---incremental}"
LOG_DIR="logs"
mkdir -p "$LOG_DIR"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$LOG_DIR/pipeline_${TIMESTAMP}.log"

echo "==============================================" | tee -a "$LOG_FILE"
echo " RAG-Graph 跑批流水线" | tee -a "$LOG_FILE"
echo " 模式: $MODE" | tee -a "$LOG_FILE"
echo " 时间: $(date)" | tee -a "$LOG_FILE"
echo "==============================================" | tee -a "$LOG_FILE"

# ---- 步骤 0: 环境检查 ----
echo "" | tee -a "$LOG_FILE"
echo "📋 步骤 0: 环境检查" | tee -a "$LOG_FILE"
python3 -c "import sys; print(f'Python {sys.version}')" 2>&1 | tee -a "$LOG_FILE"
python3 -c "import numpy; print(f'numpy {numpy.__version__}')" 2>&1 | tee -a "$LOG_FILE"
python3 -c "import h5py; print(f'h5py {h5py.__version__}')" 2>&1 | tee -a "$LOG_FILE"
python3 -c "from sentence_transformers import SentenceTransformer; print('sentence-transformers OK')" 2>&1 | tee -a "$LOG_FILE"
echo "✅ 环境检查完成" | tee -a "$LOG_FILE"

# ---- 步骤 1: 下载论文 ----
if [ "$MODE" = "--full" ] || [ "$MODE" = "--incremental" ]; then
    echo "" | tee -a "$LOG_FILE"
    echo "📥 步骤 1: 同步论文数据" | tee -a "$LOG_FILE"
    python3 scripts/download_papers.py \
        --output-dir ./input \
        --mode "${MODE#--}" 2>&1 | tee -a "$LOG_FILE"
    echo "✅ 下载完成" | tee -a "$LOG_FILE"
fi

# ---- 步骤 2: PDF/TXT/XML 解析（MinerU） ----
echo "" | tee -a "$LOG_FILE"
echo "📄 步骤 2: 文档解析（MinerU）" | tee -a "$LOG_FILE"
python3 scripts/parse_all.py \
    --input ./input \
    --output ./cleaned \
    --meta-output ./cleaned_meta \
    --mode "${MODE#--}" 2>&1 | tee -a "$LOG_FILE"
echo "✅ 解析完成" | tee -a "$LOG_FILE"

# ---- 步骤 3: KG 抽取 ----
echo "" | tee -a "$LOG_FILE"
echo "🧠 步骤 3: 知识图谱抽取" | tee -a "$LOG_FILE"
python3 -m src.kg.pipeline \
    --mode "${MODE#--}" 2>&1 | tee -a "$LOG_FILE"
echo "✅ KG 抽取完成" | tee -a "$LOG_FILE"

# ---- 步骤 4: 向量化 ----
echo "" | tee -a "$LOG_FILE"
echo "🔢 步骤 4: 向量化（BGE 嵌入 → hdf5）" | tee -a "$LOG_FILE"
python3 scripts/vectorize_all.py \
    --mode "${MODE#--}" 2>&1 | tee -a "$LOG_FILE"
echo "✅ 向量化完成" | tee -a "$LOG_FILE"

# ---- 步骤 5: 状态报告 ----
echo "" | tee -a "$LOG_FILE"
echo "📊 步骤 5: 系统状态报告" | tee -a "$LOG_FILE"
python3 scripts/report_status.py 2>&1 | tee -a "$LOG_FILE"
echo "✅ 报告完成" | tee -a "$LOG_FILE"

# ---- 完成 ----
echo "" | tee -a "$LOG_FILE"
echo "==============================================" | tee -a "$LOG_FILE"
echo " ✅ 流水线完成" | tee -a "$LOG_FILE"
echo "    日志: $LOG_FILE" | tee -a "$LOG_FILE"
echo "    时间: $(date)" | tee -a "$LOG_FILE"
echo "==============================================" | tee -a "$LOG_FILE"