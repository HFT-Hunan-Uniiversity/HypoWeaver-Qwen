"""
多维分类法 — 给每个 chunk 打标签

为什么要打标签？
  一篇论文可能有 200 个 chunk，但你的检索问的是 "DID 方法在 ESG 研究中的应用"。
  如果每个 chunk 都标了 "方法 → 实证设计"，你就能只搜有方法标签的 chunk，精度翻倍。

两套维度，正交使用：

  1. 主题维度（研究内容）：背景/方法/数据/假设/政策/发现
  2. 结构维度（文本角色）：理论框架/实证设计/综述/案例/工具方法

一套 chunk 可以同时有 "方法"（主题）+ "实证设计"（结构）两个标签。
"""

from enum import Enum
from typing import List, Set


class TopicDimension(str, Enum):
    """
    主题维度：这个 chunk 在说什么研究内容

    BACKGROUND:     背景介绍 / 文献综述（研究动机、已有成果）
    METHODOLOGY:    方法论述（模型设定、估计方法）
    DATA:           数据描述（数据来源、样本构造、描述统计）
    HYPOTHESIS:     理论假设（研究假设提出、理论推导）
    POLICY:         政策/制度背景（政策条文、监管框架）
    FINDING:        实证发现（回归结果、机制检验、稳健性检验）
    CONCLUSION:     结论与启示
    LIMITATION:     研究局限与未来方向
    """
    BACKGROUND   = "topic_background"
    METHODOLOGY  = "topic_methodology"
    DATA         = "topic_data"
    HYPOTHESIS   = "topic_hypothesis"
    POLICY       = "topic_policy"
    FINDING      = "topic_finding"
    CONCLUSION   = "topic_conclusion"
    LIMITATION   = "topic_limitation"


class StructureDimension(str, Enum):
    """
    结构维度：这个 chunk 在论文里扮演什么角色

    LITERATURE_REVIEW:   综述/文献回顾（引述他人工作）
    THEORETICAL_FRAME:   理论框架（搭建分析框架）
    EMPIRICAL_DESIGN:    实证设计（模型设定 + 识别策略）
    CASE_ANALYSIS:       案例分析（具体企业/事件）
    TOOL_METHOD:         工具方法（公式推导、算法说明）
    RESULT_REPORT:       结果报告（表格、系数、显著性）
    ROBUSTNESS:          稳健性检验
    MECHANISM:           机制分析
    HETEROGENEITY:       异质性分析
    DISCUSSION:          讨论与解释
    """
    LITERATURE_REVIEW = "struct_literature_review"
    THEORETICAL_FRAME = "struct_theoretical_frame"
    EMPIRICAL_DESIGN  = "struct_empirical_design"
    CASE_ANALYSIS     = "struct_case_analysis"
    TOOL_METHOD       = "struct_tool_method"
    RESULT_REPORT     = "struct_result_report"
    ROBUSTNESS        = "struct_robustness"
    MECHANISM         = "struct_mechanism"
    HETEROGENEITY     = "struct_heterogeneity"
    DISCUSSION        = "struct_discussion"


# ============================================================
# 分类结果
# ============================================================

@dataclass
class ChunkClassification:
    """
    一个 chunk 的分类结果

    chunk_id:      被分类的 chunk
    topics:        主题维度标签（至少 1 个，最多 3 个）
    structures:    结构维度标签（至少 1 个，最多 2 个）
    confidence:    分类置信度
    """
    chunk_id: str
    topics: Set[TopicDimension]
    structures: Set[StructureDimension]
    confidence: float = 1.0  # 0.0 ~ 1.0


# ============================================================
# 分类→query 映射（C 给 D 的接口）
# ============================================================

CLASSIFICATION_TO_QUERY_MAP = {
    # 当用户问 DID/PSM/RDD 时 → 搜 METHODOLOGY + EMPIRICAL_DESIGN
    "method": {
        "topics":      {TopicDimension.METHODOLOGY},
        "structures":  {StructureDimension.EMPIRICAL_DESIGN, StructureDimension.TOOL_METHOD},
    },

    # 当用户问数据来源/样本构造 → 搜 DATA
    "data": {
        "topics":      {TopicDimension.DATA},
        "structures":  set(),
    },

    # 当用户问某个变量/指标 → 搜 DATA + FINDING
    "variable": {
        "topics":      {TopicDimension.DATA, TopicDimension.FINDING},
        "structures":  {StructureDimension.RESULT_REPORT},
    },

    # 当用户问研究空白 → 搜 LIMITATION + LITERATURE_REVIEW
    "gap": {
        "topics":      {TopicDimension.LIMITATION, TopicDimension.BACKGROUND},
        "structures":  {StructureDimension.LITERATURE_REVIEW},
    },

    # 当用户问因果关系/机制 → 搜 MECHANISM + HETEROGENEITY
    "causality": {
        "topics":      {TopicDimension.METHODOLOGY, TopicDimension.FINDING},
        "structures":  {StructureDimension.MECHANISM, StructureDimension.HETEROGENEITY},
    },

    # 当用户问政策/监管 → 搜 POLICY
    "policy": {
        "topics":      {TopicDimension.POLICY},
        "structures":  set(),
    },
}