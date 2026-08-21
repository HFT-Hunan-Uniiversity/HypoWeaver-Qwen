# ============================================================================
# KG 模块统一配置 — src/kg/config.py
# ============================================================================
# 集中所有 KG 构建相关的可配置项：
#   - Neo4j 连接
#   - LLM（三元组抽取专用 qwen-max）
#   - 概念共现参数
#   - 文件路径（输入 cleaned_md / cleaned_meta，输出 artifacts/kg）
#   - 行为开关（别名归一、失败是否中止）
#
# 优先级：环境变量 > 默认值。这样不改代码即可切换服务器、账号、密钥。
# API-KEY 统一复用现有 DASHSCOPE_API_KEY，不新增环境变量。
# ============================================================================

from __future__ import annotations

import os
from pathlib import Path

# ----------------------------------------------------------------------------
# 路径（相对项目根）
# ----------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CLEANED_DIR = PROJECT_ROOT / "cleaned"          # cleaned/*.md 输入
CLEANED_META_DIR = PROJECT_ROOT / "cleaned_meta"  # cleaned_meta/*.json 输入
ARTIFACTS_KG_DIR = PROJECT_ROOT / "artifacts" / "kg"

# 失败清单 & 断点续跑记录文件
FAILED_LIST_PATH = ARTIFACTS_KG_DIR / "failed_docs.jsonl"   # 失败文档（可重试）
RECORD_PATH = ARTIFACTS_KG_DIR / "kg_done.json"             # 已成功写入的 doc_id（断点）

# ----------------------------------------------------------------------------
# Neo4j 连接
# ----------------------------------------------------------------------------
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password")
# 每笔写事务的最大语句数（分批，避免单事务过大）
NEO4J_BATCH_SIZE = 200
# 健康检查失败是否直接中止流水线
NEO4J_REQUIRED = True

# ----------------------------------------------------------------------------
# LLM 三元组抽取（qwen-max 正式版）
# ----------------------------------------------------------------------------
LLM_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
LLM_BASE_URL = os.environ.get(
    "LLM_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
)
LLM_MODEL = os.environ.get("KG_LLM_MODEL", "qwen-max")   # 正式版 qwen-max
LLM_TIMEOUT = int(os.environ.get("KG_LLM_TIMEOUT", "120"))  # 秒
LLM_MAX_RETRIES = int(os.environ.get("KG_LLM_MAX_RETRIES", "2"))  # 失败重试次数
LLM_RETRY_BACKOFF = 2.0      # 重试指数退避基数（秒）
LLM_TEMPERATURE = 0.1        # 抽取任务确定性优先

# ----------------------------------------------------------------------------
# 概念共现（代码生成，零 token）
# ----------------------------------------------------------------------------
CO_OCCUR_MIN_COUNT = 2       # 概念在单篇内出现次数≥此值才参与共现
CO_OCCUR_WINDOW_SENT = 1     # 同句共现才算（窗口=相邻句，可按需放宽）

# ----------------------------------------------------------------------------
# 行为开关
# ----------------------------------------------------------------------------
ENABLE_ALIAS = True          # 是否开启静态别名归一
# 达到该置信度阈值的 LLM 关系才写入（保留尾部弱信号但可过滤）
MIN_CONFIDENCE = 0.0


def ensure_dirs() -> None:
    """确保输出目录存在"""
    ARTIFACTS_KG_DIR.mkdir(parents=True, exist_ok=True)


def resolve_input_pairs() -> list:
    """扫描 cleaned/ 与 cleaned_meta/，返回 (doc_id, md_path, meta_path) 对齐列表。

    只返回两边都存在的论文；元数据缺失的不参与 KG 抽取。
    """
    pairs = []
    for md_path in sorted(CLEANED_DIR.glob("*.md")):
        doc_id = md_path.stem
        meta_path = CLEANED_META_DIR / f"{doc_id}.json"
        if meta_path.exists():
            pairs.append((doc_id, md_path, meta_path))
    return pairs
