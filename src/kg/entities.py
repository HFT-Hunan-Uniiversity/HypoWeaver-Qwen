# ============================================================================
# KG 实体 Schema — src/kg/entities.py
# ============================================================================
# 定义知识图谱的 5 类实体与关系枚举。
#
# 5 类节点：Paper / Author / Concept / Method / Dataset
# 5 种固定关系 + 概念关联关系（概念间 = 因果关系 | 共现关系）。
#
# 设计要点：
#   - 关系类型用**短英文枚举**存入 Neo4j（规避中文标签兼容问题），
#     中文仅作注释。例如 PROMOTE(线性促进)。
#   - 概念间因果关系的值域被**硬约束在 RELATION_ENUM**，LLM 只能从
#     枚举里选，拒绝自由文本 → 极低脏数据。
#   - 概念共现关系单独打 CO_OCCUR 标签，与因果边严格区分。
#   - 边属性统一挂载 Evidence 证据（原文片段+source_doc+snippet+页码），
#     不把关系做成独立节点（本阶段小样本，普通 REL->NODE 结构即可）。
# ============================================================================

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# ----------------------------------------------------------------------------
# 概念间因果关系的值域（Neo4j 存储英文枚举）
# ----------------------------------------------------------------------------
class RelationKind(str, Enum):
    PROMOTE = "PROMOTE"                    # 线性促进（正向显著）
    INHIBIT = "INHIBIT"                    # 线性抑制（负向显著）
    U_SHAPE = "U_SHAPE"                    # U 型 / U 形曲线关系
    MEDIATION_PART = "MEDIATION_PART"      # 部分中介
    MEDIATION_FULL = "MEDIATION_FULL"      # 完全中介
    MODERATION = "MODERATION"              # 调节效应
    POLICY_EFFECT = "POLICY_EFFECT"        # 政策效应（DID 等准自然实验）
    DIFFERENCE = "DIFFERENCE"              # 存在差异（分组/样本差异）
    HETEROGENEITY = "HETEROGENEITY"        # 异质性
    ROBUST = "ROBUST"                      # 稳健性（验证关系稳定）
    NOT_SIGNIFICANT = "NOT_SIGNIFICANT"    # 未发现显著关系
    CO_OCCUR = "CO_OCCUR"                  # 概念共现（代码自动生成，非 LLM 枚举值）

    @classmethod
    def values(cls) -> List[str]:
        return [e.value for e in cls]

    @classmethod
    def has(cls, value: str) -> bool:
        try:
            cls(value)
            return True
        except ValueError:
            return False


# 概念间关系的中文注释（仅展示用）
RELATION_CN = {
    RelationKind.PROMOTE: "线性促进",
    RelationKind.INHIBIT: "线性抑制",
    RelationKind.U_SHAPE: "U 型曲线",
    RelationKind.MEDIATION_PART: "部分中介",
    RelationKind.MEDIATION_FULL: "完全中介",
    RelationKind.MODERATION: "调节效应",
    RelationKind.POLICY_EFFECT: "政策效应",
    RelationKind.DIFFERENCE: "存在差异",
    RelationKind.HETEROGENEITY: "异质性",
    RelationKind.ROBUST: "稳健性",
    RelationKind.NOT_SIGNIFICANT: "未发现显著关系",
    RelationKind.CO_OCCUR: "概念共现",
}


# ----------------------------------------------------------------------------
# 节点 Schema（metadata 为任意扩展字段）
# ----------------------------------------------------------------------------
class PaperNode(BaseModel):
    """论文节点。唯一键 = doc_id（用于切片与向量检索对齐）。"""
    doc_id: str = Field(description="文档唯一 ID（= cleaned md 的文件名 stem）")
    title: str = ""
    authors: List[str] = Field(default_factory=list)
    abstract: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    journal: Optional[str] = None
    year: Optional[str] = None
    doi: Optional[str] = None
    source_type: str = "paper"          # ALL 流程走 paper；保留泛化余地
    metadata: dict = Field(default_factory=dict)


class AuthorNode(BaseModel):
    """作者节点。唯一键 = name（跨论文归一）。"""
    name: str


class ConceptNode(BaseModel):
    """概念节点（跨论文归一）。唯一键 = name（已归一化后的规范名）。"""
    name: str
    alias_of: Optional[str] = None      # 若本名是某别名 → 指向规范名
    metadata: dict = Field(default_factory=dict)


class MethodNode(BaseModel):
    """方法节点（跨论文归一）。唯一键 = name。"""
    name: str
    category: Optional[str] = None      # 如 "计量模型" / "识别策略" / "指标测算"
    alias_of: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class DatasetNode(BaseModel):
    """数据集节点（跨论文归一）。唯一键 = name。"""
    name: str
    alias_of: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


# ----------------------------------------------------------------------------
# 关系 Schema
# ----------------------------------------------------------------------------
class Evidence(BaseModel):
    """关系边上的证据挂载（本阶段普通属性，不建独立节点）。"""
    evidence: str = ""                  # LLM 抽取的原文摘录
    source_doc: str = ""                # 来源论文 doc_id
    snippet: str = ""                   # 原文片段（可留空）
    page: Optional[int] = None          # 页码（可留空）


class ConceptRelation(BaseModel):
    """概念间关系（因果 或 共现），统一结构。"""
    source: str                         # 源概念规范名
    target: str                         # 目标概念规范名
    relation: RelationKind = RelationKind.CO_OCCUR  # 默认共现
    confidence: float = 1.0
    evidence: Evidence = Field(default_factory=Evidence)

    # 是否属于代码自动生成的共现边
    @property
    def is_co_occur(self) -> bool:
        return self.relation == RelationKind.CO_OCCUR


class KnowledgeGraph(BaseModel):
    """单篇论文抽取出的完整图谱单元，作为写入 batch 的载体。"""
    paper: PaperNode
    authors: List[AuthorNode] = Field(default_factory=list)
    concepts: List[ConceptNode] = Field(default_factory=list)
    methods: List[MethodNode] = Field(default_factory=list)
    datasets: List[DatasetNode] = Field(default_factory=list)
    relations: List[ConceptRelation] = Field(default_factory=list)

    @property
    def doc_id(self) -> str:
        return self.paper.doc_id
