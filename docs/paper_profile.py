"""
PaperProfile JSON Schema — 论文结构化抽取产物

PaperProfile 是"把一篇论文里所有有价值的信息结构化"的结果。
它不是全文，而是从论文 chunk 中抽取出的关键字段，每条字段带 evidence_span（原文证据）。

关键原则：严禁编造。每一条值必须有原文出处。
"""

from dataclasses import dataclass, field
from typing import List, Optional


# ============================================================
# 辅助类型：带证据的值
# ============================================================

@dataclass
class EvidencedValue:
    """
    带原文证据的值

    value:         抽取出的值
    evidence:      原文摘录（chunk_text 的子串）
    chunk_id:      证据来自哪个 chunk（可溯源）
    confidence:    置信度（high / medium / low）
    """
    value: str
    evidence: str
    chunk_id: str
    confidence: str = "medium"  # high / medium / low


@dataclass
class EvidencedList:
    """
    带证据的列表（每项独立证据）
    """
    items: List[EvidencedValue] = field(default_factory=list)


# ============================================================
# PaperProfile 主体
# ============================================================

@dataclass
class PaperProfile:
    """
    论文结构化档案

    分层结构：
      Layer 1 - 元数据：标题/作者/期刊/年份（来自 ParsedDoc IR，无需 LLM 抽取）
      Layer 2 - 论文骨架：研究问题/理论/假设/方法/数据/发现
      Layer 3 - 细粒度：关键变量/统计量/机制/因果识别策略
      Layer 4 - 立场：对已有文献的支持/反驳/修正

    每层之间独立，下游用 Layer 1 快速过滤，用 Layer 3-4 做图谱入图。
    """
    # ---- Layer 1: 元数据（来自 IR，不需 evidence） ----
    doc_id: str
    title: str
    authors: List[str] = field(default_factory=list)
    journal: str = ""
    year: int = 0
    doi: str = ""
    abstract: str = ""

    # ---- Layer 2: 论文骨架（核心研究内容） ----
    research_question: Optional[EvidencedValue] = None      # 研究问题
    theoretical_framework: Optional[EvidencedValue] = None   # 理论框架
    hypotheses: EvidencedList = field(default_factory=EvidencedList)  # 假设列表
    methodology: Optional[EvidencedValue] = None             # 方法概述
    data_source: Optional[EvidencedValue] = None             # 数据来源
    main_findings: EvidencedList = field(default_factory=EvidencedList)  # 主要发现
    conclusion: Optional[EvidencedValue] = None              # 结论

    # ---- Layer 3: 细粒度（入图用） ----
    key_variables: EvidencedList = field(default_factory=EvidencedList)   # 关键变量
    key_statistics: EvidencedList = field(default_factory=EvidencedList)  # 关键统计量
    mechanisms: EvidencedList = field(default_factory=EvidencedList)      # 机制/中介
    identification_strategy: Optional[EvidencedValue] = None  # 因果识别策略

    # ---- Layer 4: 立场（与已有文献的关系） ----
    supported_literature: EvidencedList = field(default_factory=EvidencedList)  # 支持
    challenged_literature: EvidencedList = field(default_factory=EvidencedList)  # 反驳/修正
    gaps_identified: EvidencedList = field(default_factory=EvidencedList)        # 作者自认的局限/空白

    # ---- 元信息 ----
    source_chunks: List[str] = field(default_factory=list)    # 该论文用了哪些 chunk 生成
    extraction_model: str = ""                                 # 抽取所用的模型
    extraction_time: str = ""                                  # 抽取时间


# ============================================================
# 辅助：空值判断
# ============================================================

def has_content(ev: Optional[EvidencedValue]) -> bool:
    """判断一个 EvidencedValue 是否有内容"""
    return ev is not None and bool(ev.value.strip())

def has_list_content(el: EvidencedList) -> bool:
    """判断一个 EvidencedList 是否有内容"""
    return len(el.items) > 0