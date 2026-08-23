#!/bin/bash
# ============================================================================
# 云上一键跑批 — run_pipeline.sh
# ============================================================================
# 用法:
#   bash run_pipeline.sh                  # 增量模式（默认）
#   bash run_pipeline.sh --retry-failed   # 只重跑失败文档
#
# 架构: 纯 Python + hdf5 + networkx（无容器依赖）
# 流程: KG 抽取 → 向量化 → 状态报告
# ============================================================================

set -e
cd "$(dirname "$0")"

# 加载环境变量
[ -f .env ] && set -a && . ./.env && set +a

MODE=${1:---incremental}
LOG_DIR="logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/$(date +%Y%m%d_%H%M%S).log"

echo "🚀 开始跑批: $MODE" | tee -a "$LOG_FILE"
echo "时间: $(date)" | tee -a "$LOG_FILE"

# 步骤 1: KG 抽取（LLM 三元组抽取 + 共现补边 + 本地 JSON 存储）
echo "🧠 KG 抽取中..." | tee -a "$LOG_FILE"
python src/kg/pipeline.py --mode "$MODE" 2>&1 | tee -a "$LOG_FILE"

# 步骤 2: 向量化（BGE embedding → hdf5 存储）
echo "🔢 向量化中..." | tee -a "$LOG_FILE"
python scripts/vectorize_all.py --mode "$MODE" 2>&1 | tee -a "$LOG_FILE"

# 步骤 3: 状态报告
echo "📊 状态报告" | tee -a "$LOG_FILE"
python scripts/report_status.py 2>&1 | tee -a "$LOG_FILE"

echo "✅ 完成: $(date)" | tee -a "$LOG_FILE"