# ============================================================================
# Classification Schema — 多维分类器（C 角色 §4）
# ============================================================================
# 每个 chunk 打两套标签：
#   主题维度(topics) — 在研究内容图谱中的定位
#   结构维度(structures) — 在论文结构中的角色
# 规则层命中的用规则标签；规则未命中或置信度低 → LLM 兜底分类。
# ============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Set


class TopicDimension(str, Enum):
    """主题维度标签（chunk 在研究内容上的定位）"""
    BACKGROUND = "BACKGROUND"     # 背景/文献综述
    METHODOLOGY = "METHODOLOGY"   # 方法论述
    DATA = "DATA"                 # 数据描述
    HYPOTHESIS = "HYPOTHESIS"     # 理论假设
    POLICY = "POLICY"             # 政策/制度背景
    FINDING = "FINDING"           # 实证发现
    CONCLUSION = "CONCLUSION"     # 结论与启示
    LIMITATION = "LIMITATION"     # 研究局限


class StructureDimension(str, Enum):
    """结构维度标签（chunk 在论文结构中的角色）"""
    LITERATURE_REVIEW = "LITERATURE_REVIEW"  # 综述/文献回顾
    THEORETICAL_FRAME = "THEORETICAL_FRAME"  # 理论框架
    EMPIRICAL_DESIGN = "EMPIRICAL_DESIGN"    # 实证设计
    CASE_ANALYSIS = "CASE_ANALYSIS"          # 案例分析
    TOOL_METHOD = "TOOL_METHOD"              # 工具方法
    RESULT_REPORT = "RESULT_REPORT"          # 结果报告
    ROBUSTNESS = "ROBUSTNESS"                # 稳健性检验
    MECHANISM = "MECHANISM"                  # 机制分析
    HETEROGENEITY = "HETEROGENEITY"          # 异质性分析
    DISCUSSION = "DISCUSSION"                # 讨论与解释


@dataclass
class ChunkClassification:
    """一个 chunk 的分类结果"""
    chunk_id: str
    topics: Set[str] = field(default_factory=set)          # 主题标签集合
    structures: Set[str] = field(default_factory=set)      # 结构标签集合
    method: str = "rule"    # rule / llm
    confidence: float = 0.0  # 0~1


# ===== 规则层关键词表（C 角色技术规划 §4.3 初版） =====

SECTION_KEYWORD_RULES = {
    TopicDimension.HYPOTHESIS:  ["假设", "hypothesis", "研究假说", "理论推导", "机制分析"],
    TopicDimension.DATA:        ["数据", "data", "样本", "sample", "描述统计", "数据来源"],
    TopicDimension.METHODOLOGY: ["模型", "model", "方法", "method", "估计", "回归", "设计", "变量定义"],
    TopicDimension.FINDING:     ["结果", "result", "发现", "find", "系数", "显著"],
    TopicDimension.CONCLUSION:  ["结论", "conclusion", "启示", "建议"],
    TopicDimension.LIMITATION:  ["局限", "limitation", "不足", "future", "展望"],
    TopicDimension.POLICY:      ["政策", "policy", "监管", "regulation", "指引", "纲要"],
    TopicDimension.BACKGROUND:  ["引言", "introduction", "综述", "review", "背景"],

    StructureDimension.LITERATURE_REVIEW: ["文献回顾", "文献综述", "已有研究", "prior", "相关文献"],
    StructureDimension.EMPIRICAL_DESIGN:  ["实证设计", "研究设计", "识别策略", "模型构建"],
    StructureDimension.ROBUSTNESS:        ["稳健性", "robustness", "敏感性", "安慰剂"],
    StructureDimension.MECHANISM:         ["机制", "mechanism", "中介", "mediation", "传导"],
    StructureDimension.HETEROGENEITY:     ["异质性", "heterogeneity", "分组", "调节效应"],
    StructureDimension.RESULT_REPORT:     ["回归结果", "基准回归", "表", "图", "结果分析"],
    StructureDimension.THEORETICAL_FRAME: ["理论分析", "理论框架", "理论", "资源配置", "波特假说", "信号传递"],
    StructureDimension.TOOL_METHOD:       ["方法", "method", "测算", "指标", "模型"],
}


def classify_by_section_title(title: Optional[str]) -> ChunkClassification:
    """规则层：仅凭章节标题关键词分类，返回可能的标签集合"""
    cls = ChunkClassification(chunk_id="", confidence=0.0)
    if not title:
        return cls

    lowered = title.lower()
    for label, kws in SECTION_KEYWORD_RULES.items():
        for kw in kws:
            if kw in lowered:
                if isinstance(label, TopicDimension):
                    cls.topics.add(label.value)
                else:
                    cls.structures.add(label.value)
                break

    if cls.topics or cls.structures:
        cls.method = "rule"
        cls.confidence = 0.9
    return cls


# ===== 分类 → query 映射（C 角色技术规划 §8.1）=====

CLASSIFICATION_TO_QUERY_MAP = {
    "method":    {"topic": {TopicDimension.METHODOLOGY.value}, "struct": {
        StructureDimension.EMPIRICAL_DESIGN.value, StructureDimension.TOOL_METHOD.value}},
    "data":      {"topic": {TopicDimension.DATA.value}, "struct": set()},
    "variable":  {"topic": {TopicDimension.DATA.value, TopicDimension.FINDING.value},
                  "struct": {StructureDimension.RESULT_REPORT.value}},
    "gap":       {"topic": {TopicDimension.LIMITATION.value, TopicDimension.BACKGROUND.value},
                  "struct": {StructureDimension.LITERATURE_REVIEW.value}},
    "causality": {"topic": {TopicDimension.METHODOLOGY.value, TopicDimension.FINDING.value},
                  "struct": {StructureDimension.MECHANISM.value, StructureDimension.HETEROGENEITY.value}},
    "policy":    {"topic": {TopicDimension.POLICY.value}, "struct": set()},
}
