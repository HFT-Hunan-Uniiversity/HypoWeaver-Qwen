# ============================================================================
# PaperProfile 抽取 Prompt 模板 — C 角色技术规划 §6.2
# ============================================================================
# 从已分类的论文 chunk 中抽取结构化档案。
# 关键规则（§6.2 / §6.4）：
#   - 每条值必须带 evidence（原文摘录）
#   - evidence 必须是某个 chunk_text 的精确子串（防幻觉）
#   - 无信息返回 null / 空数组，不编造
#   - confidence: high（原文明确）/ medium（隐含可推断）/ low（推测）
# ============================================================================

from typing import List


def build_profile_prompt(
    title: str,
    abstract: str,
    relevant_chunks: List[dict],
) -> str:
    """
    构建 PaperProfile 抽取 prompt。

    参数:
      title: 论文标题
      abstract: 论文摘要
      relevant_chunks: 参与抽取的已分类 chunk 列表
        每个元素: {"chunk_id": str, "text": str, "topics": [...], "structures": [...]}
    """
    # 分字段组装 chunk 上下文，方便 LLM 对照
    lines = []
    for c in relevant_chunks:
        topics = ",".join(c.get("topics", []) or [])
        structs = ",".join(c.get("structures", []) or [])
        lines.append(
            f"[chunk_id={c['chunk_id']}] (topics:{topics or '-'} | struct:{structs or '-'})\n{c['text']}"
        )
    chunks_text = "\n\n".join(lines)

    return f"""你是一名绿色金融论文的结构化抽取助手。请从以下论文 chunk 中抽取指定信息到 JSON。

论文标题：{title}
论文摘要：{abstract}

相关 chunk（按 chunk_id 标记来源）：
{chunks_text}

请抽取以下字段（每条必须带原文证据 evidence，evidence 必须是某个 chunk_id 内文本的精整子串）：

1. research_question   研究问题（单个）
2. theoretical_framework  理论框架（单个）
3. hypotheses          假设列表（每条为 {{"value","evidence","chunk_id","confidence"}}）
4. methodology         方法概述（单个）
5. data_source         数据来源（单个，如"CNRDS 数据库，2008-2024 年 A 股"）
6. main_findings       主要发现列表
7. key_variables       关键变量列表（自变量/因变量/调节变量/控制变量）
8. key_statistics      关键统计量列表（如系数、显著性、样本量）
9. mechanisms          机制/中介列表
10. identification_strategy  因果识别策略（DID/IV/RDD/中介 等，单个）
11. gaps_identified    作者自认的局限/空白列表

输出格式（严格 JSON，不要多余文字）：
{{
  "research_question": {{"value","evidence","chunk_id","confidence"}} | null,
  "theoretical_framework": ... ,
  "hypotheses": [ ... ],
  "methodology": ...,
  "data_source": ...,
  "main_findings": [ ... ],
  "key_variables": [ ... ],
  "key_statistics": [ ... ],
  "mechanisms": [ ... ],
  "identification_strategy": ...,
  "gaps_identified": [ ... ]
}}

重要规则：
- 每条值必须有 evidence（原文摘录）和 chunk_id（来源）
- evidence 必须是某个 chunk_id 对应文本的精确子串，不得改写
- 如果没有相关信息，返回 null 或空数组 []，不要编造
- confidence 标注：high（原文明确陈述）/ medium（隐含可推断）/ low（推测）"""
