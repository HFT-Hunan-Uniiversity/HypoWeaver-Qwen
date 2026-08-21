"""
Chunk Schema — 切片数据结构定义

chunk 是检索的最小单元。一篇论文被切成 N 个 chunk，
每个 chunk 可以独立被检索、分类、抽取。

三层切片策略：
  1. 语义层：按段落/小节自然边界切（最大 1024 tokens）
  2. 滑动窗口层：重叠 128 tokens，防止边界信息丢失
  3. 元数据层：不切，整篇论文的元数据独立存一份
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class ChunkLevel(str, Enum):
    """切片层级"""
    SEMANTIC = "semantic"      # 语义层（按段落/小节）
    SLIDING  = "sliding"       # 滑动窗口（重叠 128 tokens）


class ChunkSourceType(str, Enum):
    """来源类型"""
    PAPER      = "paper"
    POLICY     = "policy"
    ESG_REPORT = "esg_report"
    NEWS       = "news"


@dataclass
class ChunkPayload:
    """
    单个 chunk 的数据结构

    字段说明（按重要性排序）：

    chunk_id:         唯一标识，格式 "{doc_id}_{level}_{seq}"
    doc_id:           来源文档 ID（与 ParsedDoc IR 的 doc_id 对齐）
    source_type:      来源类型（论文/政策/ESG 报告等）
    chunk_level:      属于哪一层级（语义层/滑动窗口层）
    chunk_seq:        在该层级下的序号（从 0 开始）

    chunk_text:       切片文本内容（核心字段，检索/抽取都基于它）
    token_count:      token 数（用于控制长度和后续抽取预算）

    metadata:         来源文档的元数据快照（标题、作者、年份等，不每份都重复）
    section_title:    该 chunk 所属小节标题（如 "3.2 数据来源"）
    section_level:    小节层级（h1/h2/h3/...）

    page_range:       该 chunk 覆盖的页码范围（行号也可，用于溯源引用）

    embedding:        向量嵌入（可选，存向量数据库时用）
    topics:           多维分类标签（由后续分类器填充，初始为空 []）
    """
    # ---- 标识 ----
    chunk_id: str                    # 如 "paper_0001_semantic_0"
    doc_id: str                      # 关联 ParsedDoc IR 的 doc_id
    source_type: ChunkSourceType     # 来源类型
    chunk_level: ChunkLevel          # 语义层 / 滑动窗口层
    chunk_seq: int                   # 序号

    # ---- 内容 ----
    chunk_text: str                  # 切片文本
    token_count: int                 # token 数
    language: str = "zh"             # 语言（zh/en）

    # ---- 元数据（快照，非全文重复） ----
    metadata: dict = field(default_factory=dict)

    # ---- 结构信息 ----
    section_title: Optional[str] = None    # 小节标题
    section_level: Optional[int] = None    # 小节层级（1/2/3/...）

    # ---- 溯源 ----
    page_range: Optional[List[int]] = None  # 页码范围 [start, end]

    # ---- 后续填充 ----
    embedding: Optional[List[float]] = None  # 向量嵌入（索引时填充）
    topics: List[str] = field(default_factory=list)  # 多维分类标签（分类器填充）

    def __post_init__(self):
        """创建后自动校验"""
        assert self.chunk_id, "chunk_id 不能为空"
        assert self.doc_id, "doc_id 不能为空"
        assert self.chunk_text, "chunk_text 不能为空"
        assert self.token_count > 0, "token_count 必须 > 0"


@dataclass
class ChunkingConfig:
    """
    切片配置

    语义层和小节层共用一套参数，滑动窗口层用另一套。
    """
    # ---- 语义层配置 ----
    semantic_max_tokens: int = 1024      # 最大 token 数
    semantic_split_marks: List[str] = field(
        default_factory=lambda: ["\n## ", "\n### ", "\n\n", "\n"]
    )  # 分割优先级：标题 > 段落 > 行

    # ---- 滑动窗口层配置 ----
    sliding_window_size: int = 512       # 窗口大小
    sliding_overlap: int = 128           # 重叠 token 数

    # ---- 通用 ----
    min_chunk_tokens: int = 50           # 最小 token 数（低于此丢弃）
    max_chunk_tokens: int = 2048         # 绝对上限