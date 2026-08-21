# ============================================================================
# Chunk Schema — C 角色切片引擎的输入输出数据结构
# ============================================================================
# 切片引擎把一篇清洗后的文档 (cleaned/*.md) 切成语义层 + 滑动窗口层两个粒度。
# 每个 chunk 携带来源定位(section/chunk_id)与分类标签，供下游检索与抽取使用。
# ============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ChunkSourceType(str, Enum):
    """chunk 来源的文档类型（与 B 阶段的 doc_type 对齐）"""
    PAPER = "paper"
    POLICY = "policy"
    ESG_REPORT = "esg_report"
    NEWS = "news"


class ChunkLevel(str, Enum):
    """切片层级"""
    SEMANTIC = "semantic"      # 语义层：按段落/小节
    SLIDING = "sliding"        # 滑动窗口层：重叠窗口
    METADATA = "metadata"      # 元数据层：标题/作者/摘要/关键词（不切）


@dataclass
class ChunkPayload:
    """单个 chunk 的完整数据结构"""
    chunk_id: str               # 全局唯一: {doc_id}__c{seq}
    doc_id: str                 # 来源文档 ID（B 阶段 ParsedDoc.doc_id）
    source_type: str            # 文档类型（paper/policy/esg_report/news）
    chunk_level: str            # semantic / sliding / metadata
    chunk_seq: int              # 在文档内的序号
    chunk_text: str             # chunk 文本
    token_count: int            # 大致 token 数
    metadata: Dict[str, Any] = field(default_factory=dict)
    section_title: Optional[str] = None   # 所属章节标题
    section_level: Optional[int] = None   # 章节标题层级(1-4)
    page_range: Optional[List[int]] = None  # 页码范围
    topics: List[str] = field(default_factory=list)       # 主题分类标签
    structures: List[str] = field(default_factory=list)   # 结构分类标签
    embedding: Optional[List[float]] = None  # 向量（可选，延迟计算）
    is_selected: bool = False   # 是否被 ProfileExtractor 选中作为候选 chunk


@dataclass
class ChunkingConfig:
    """切片引擎配置参数（C 角色技术规划 §3.3）"""
    semantic_max_tokens: int = 1024      # 语义层最大 token 数
    sliding_window_size: int = 512       # 滑动窗口大小
    sliding_overlap: int = 128           # 滑动窗口重叠 token 数
    min_chunk_tokens: int = 50           # 小于此丢弃
    max_chunk_tokens: int = 2048         # 绝对上限


def build_chunk_id(doc_id: str, seq: int, level: str = "semantic") -> str:
    """按约定拼接全局唯一 chunk_id"""
    return f"{doc_id}__{level}_{seq:04d}"
