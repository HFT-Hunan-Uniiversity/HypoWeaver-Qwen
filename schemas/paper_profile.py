# ============================================================================
# PaperProfile Schema — C 角色 PaperProfile 抽取引擎的数据结构
# ============================================================================
# 一篇论文的结构化档案，四层结构（C 角色技术规划 §6 + docs/paper_profile.py）。
# 每个抽取值带 evidence + chunk_id + confidence，确保可追溯、可校验、防幻觉。
# ============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class EvidencedValue:
    """单个抽取值，绑定原文证据"""
    value: str
    evidence: str          # 原文摘录（必须是某个 chunk_text 的子串）
    chunk_id: str          # 来源 chunk
    confidence: str = "high"  # high / medium / low


@dataclass
class EvidencedList:
    """EvidencedValue 的列表"""
    items: List[EvidencedValue] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.items)


# ----- 各层字段 -----

@dataclass
class PaperLayer1:
    """Layer1 元数据（来自 cleaned_meta 与 PDF 第一页）"""
    doc_id: str
    title: str
    authors: List[str] = field(default_factory=list)
    journal: Optional[str] = None
    year: Optional[str] = None
    doi: Optional[str] = None
    abstract: Optional[str] = None
    keywords: List[str] = field(default_factory=list)


@dataclass
class PaperLayer2:
    """Layer2 论文骨架"""
    research_question: Optional[EvidencedValue] = None
    theoretical_framework: Optional[EvidencedValue] = None
    hypotheses: EvidencedList = field(default_factory=EvidencedList)
    methodology: Optional[EvidencedValue] = None
    data_source: Optional[EvidencedValue] = None
    main_findings: EvidencedList = field(default_factory=EvidencedList)
    conclusion: Optional[EvidencedValue] = None


@dataclass
class PaperLayer3:
    """Layer3 细粒度"""
    key_variables: EvidencedList = field(default_factory=EvidencedList)
    key_statistics: EvidencedList = field(default_factory=EvidencedList)
    mechanisms: EvidencedList = field(default_factory=EvidencedList)
    identification_strategy: Optional[EvidencedValue] = None


@dataclass
class PaperLayer4:
    """Layer4 立场"""
    supported_literature: EvidencedList = field(default_factory=EvidencedList)
    challenged_literature: EvidencedList = field(default_factory=EvidencedList)
    gaps_identified: EvidencedList = field(default_factory=EvidencedList)


@dataclass
class PaperProfile:
    """一篇论文的完整结构化档案"""
    layer1: PaperLayer1
    layer2: PaperLayer2 = field(default_factory=PaperLayer2)
    layer3: PaperLayer3 = field(default_factory=PaperLayer3)
    layer4: PaperLayer4 = field(default_factory=PaperLayer4)
    source_chunks: List[str] = field(default_factory=list)   # 参与抽取的 chunk_id 列表
    extraction_model: Optional[str] = None
    extraction_time: Optional[str] = None

    # ---- 便捷访问 ----
    @property
    def doc_id(self) -> str:
        return self.layer1.doc_id

    @property
    def title(self) -> str:
        return self.layer1.title

    @property
    def hypotheses(self) -> List[EvidencedValue]:
        return self.layer2.hypotheses.items

    @property
    def main_findings(self) -> List[EvidencedValue]:
        return self.layer2.main_findings.items

    @property
    def has_evidence(self) -> bool:
        """是否所有非空值都带 evidence（防幻觉基本检查）"""
        for ev in (self.layer2.research_question, self.layer2.theoretical_framework,
                   self.layer2.methodology, self.layer2.data_source,
                   self.layer2.conclusion, self.layer3.identification_strategy):
            if ev is not None and not ev.evidence.strip():
                return False
        for lst in (self.layer2.hypotheses, self.layer2.main_findings,
                    self.layer3.key_variables, self.layer3.key_statistics,
                    self.layer3.mechanisms, self.layer4.supported_literature,
                    self.layer4.challenged_literature, self.layer4.gaps_identified):
            for item in lst.items:
                if not item.evidence.strip():
                    return False
        return True
