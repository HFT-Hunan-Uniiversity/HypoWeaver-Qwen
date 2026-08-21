# ============================================================================
# 概念共现关联 — src/kg/concept_edges.py
# ============================================================================
# 纯代码生成（零 Token 消耗）。
# 对单篇论文下所有已抽取的 Concept 做两两配对，统计在同句同段内是否
# 共同出现；满足门槛的生成 CO_OCCUR 关系边。
#
# 与 LLM 识别的因果边严格区分（边类型 = CO_OCCUR），在 Neo4j 中通过
# relation 标签区别，下游检索可选择是否纳入共现关系。
# ============================================================================

from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, List, Set, Tuple

from src.kg.config import CO_OCCUR_MIN_COUNT, CO_OCCUR_WINDOW_SENT
from src.kg.entities import ConceptRelation, Evidence, RelationKind

# 句子切分（中文句号/感叹/问号/分号，英文句号留空不切以免缩写误杀）
_SENT_SPLIT = re.compile(r"[。！？\n]+")


def extract_co_occur(
    md_text: str,
    concepts: List[str],
    doc_id: str,
    min_count: int = CO_OCCUR_MIN_COUNT,
    window_sent: int = CO_OCCUR_WINDOW_SENT,
) -> List[ConceptRelation]:
    """
    从一篇论文的 md 正文中提取概念共现关系。

    参数:
      md_text:   cleaned/*.md 全文
      concepts:  该论文的 Concept 规范名列表（已归一化）
      doc_id:    来源论文 ID
      min_count: 最低共现次数门槛（低于此不生成边，过滤噪声）
      window_sent: 共现窗口（同句=1，相邻句=2，放宽可调）

    返回 ConceptRelation 列表（relation=CO_OCCUR）。
    """
    if len(concepts) < 2:
        return []

    # 构建概念名索引（非重叠匹配，取最长匹配优先）
    # 按长度降序排列，避免"双重差分模型"被"双重差分"局部吃掉
    sorted_concepts = sorted(concepts, key=len, reverse=True)

    # 句子切分
    sents = [s.strip() for s in _SENT_SPLIT.split(md_text) if s.strip()]

    # 统计共现矩阵
    co_matrix: Dict[Tuple[str, str], int] = defaultdict(int)

    for sent in sents:
        # 当前句子中出现了哪些概念
        present: Set[str] = set()
        for c in sorted_concepts:
            if c in sent:
                present.add(c)
        # 如果句子里有多个概念，两两配对加 1
        if len(present) >= 2:
            for a in present:
                for b in present:
                    if a < b:  # 只计一次 (a,b) 排序对
                        co_matrix[(a, b)] += 1

    # 超过门槛的生成边
    relations: List[ConceptRelation] = []
    for (a, b), cnt in co_matrix.items():
        if cnt >= min_count:
            relations.append(
                ConceptRelation(
                    source=a,
                    target=b,
                    relation=RelationKind.CO_OCCUR,
                    confidence=min(cnt / 10.0, 1.0),  # 频次越高置信度越高，上限 1.0
                    evidence=Evidence(
                        evidence=f"概念共现 {cnt} 次",
                        source_doc=doc_id,
                        snippet=f"同{window_sent}句窗口内共现 {cnt} 次",
                    ),
                )
            )

    return relations