# ============================================================================
# 多维分类器 (Classifier) — C 角色技术规划 §4
# ============================================================================
# 规则 + LLM 级联：
#   第1步 规则层：依据章节标题关键词分类，命中且置信度高 → 直接用
#   第2步 LLM 层：规则未命中 / 语义模糊 → 调 qwen-turbo 兜底
# 输出 ChunkClassification（topics + structures + method + confidence）。
# ============================================================================

from __future__ import annotations

import json
import re
from typing import List, Optional, Set

from schemas.classification import (
    ChunkClassification, SECTION_KEYWORD_RULES, TopicDimension, StructureDimension,
)
from schemas.chunk_schema import ChunkPayload

try:
    from src.parse.adapters.llm_metadata import DASHSCOPE_URL, MODEL, HEADERS
    import requests
except Exception:  # pragma: no cover
    # 纯规则测试时不需要 LLM 依赖
    requests = None
    DASHSCOPE_URL = MODEL = HEADERS = None

# 主题标签的可信命中（用于规则层置信度计算）
_TOPIC_KW: dict = {}
_STRUCT_KW: dict = {}
for _k, _v in SECTION_KEYWORD_RULES.items():
    if isinstance(_k, TopicDimension):
        _TOPIC_KW[_k.value] = _v
    elif isinstance(_k, StructureDimension):
        _STRUCT_KW[_k.value] = _v


def classify_by_rules(chunk: ChunkPayload, threshold: float = 0.9) -> ChunkClassification:
    """
    规则层分类：基于 section_title 关键词匹配。
    只在规则命中时给标签；全部未命中 → 保留空标签，交由 LLM 层。
    """
    cls = ChunkClassification(chunk_id=chunk.chunk_id, confidence=0.0)

    title = (chunk.section_title or "").lower()

    # 主题维度
    for label, kws in _TOPIC_KW.items():
        if any(k.lower() in title for k in kws):
            cls.topics.add(label)

    # 结构维度
    for label, kws in _STRUCT_KW.items():
        if any(k.lower() in title for k in kws):
            cls.structures.add(label)

    # 命中才给高置信度
    if cls.topics or cls.structures:
        cls.method = "rule"
        cls.confidence = threshold
    return cls


def classify_by_llm(chunk: ChunkPayload) -> ChunkClassification:
    """
    LLM 层分类：qwen-turbo 兜底。
    规则未命中或需进一步确认时调用。
    """
    cls = ChunkClassification(chunk_id=chunk.chunk_id, method="llm", confidence=0.5)
    if requests is None or HEADERS is None:
        return cls

    prompt = f"""请判断以下论文段落属于哪个类别。

主题维度（单选或最多2个）：
- BACKGROUND：背景介绍/文献综述
- METHODOLOGY：方法论述（模型/回归/估计）
- DATA：数据描述（样本/数据来源）
- HYPOTHESIS：理论假设
- POLICY：政策/制度背景
- FINDING：实证发现
- CONCLUSION：结论与启示
- LIMITATION：研究局限

结构维度（单选或最多2个）：
- LITERATURE_REVIEW：综述/文献回顾
- THEORETICAL_FRAME：理论框架
- EMPIRICAL_DESIGN：实证设计/识别策略
- CASE_ANALYSIS：案例分析
- TOOL_METHOD：工具方法/指标测算
- RESULT_REPORT：结果报告
- ROBUSTNESS：稳健性检验
- MECHANISM：机制分析/中介
- HETEROGENEITY：异质性分析
- DISCUSSION：讨论与解释

只输出 JSON，不要多余文字：
{{"topics": [...], "structures": [...]}}

段落：
---
{chunk.chunk_text[:1500]}
---"""

    data = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 128,
        "temperature": 0.1,
    }
    try:
        resp = requests.post(DASHSCOPE_URL, headers=HEADERS, json=data, timeout=30)
        if resp.status_code != 200:
            return cls
        content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if m:
            content = m.group(1)
        parsed = json.loads(content)
        vs = set(TopicDimension.__members__)
        for t in parsed.get("topics", []) or []:
            if t in vs:
                cls.topics.add(t)
        for s in parsed.get("structures", []) or []:
            if s in StructureDimension.__members__:
                cls.structures.add(s)
        cls.confidence = 0.85 if (cls.topics or cls.structures) else 0.0
    except Exception:
        pass
    return cls


def classify_chunk(chunk: ChunkPayload, use_llm: bool = True) -> ChunkClassification:
    """
    对外主入口：规则 + LLM 级联分类。
    """
    cls = classify_by_rules(chunk)
    # 规则层未命中任一标签 → LLM 兜底
    if not cls.topics and not cls.structures and use_llm:
        cls = classify_by_llm(chunk)
    return cls


def classify_batch(chunks: List[ChunkPayload], use_llm: bool = True) -> Dict[str, ChunkClassification]:
    """批量分类，返回 {chunk_id: ChunkClassification}"""
    result = {}
    for c in chunks:
        result[c.chunk_id] = classify_chunk(c, use_llm=use_llm)
    return result


# ===== 命令行测试 =====
if __name__ == "__main__":
    import sys
    from pathlib import Path
    from src.retrieve.chunker import chunk_markdown

    md_path = sys.argv[1] if len(sys.argv) > 1 else \
        "cleaned/绿色金融政策如何影响绿色技术创新基于高耗能企业的经验证据_周莹莹.md"
    chunks = chunk_markdown(
        "test_doc", Path(md_path).read_text(encoding="utf-8"),
        {"title": "测试", "source_type": "paper"})

    # 规则层测试（不发 LLM，控制成本）
    print("===== 规则层分类结果（前 12 个语义 chunk）=====")
    sem = [c for c in chunks if c.chunk_level == "semantic"]
    for c in sem[:12]:
        cls = classify_by_rules(c)
        print(f"  [{c.chunk_seq}]({c.section_title})")
        print(f"      topics={sorted(cls.topics)} structures={sorted(cls.structures)}")
