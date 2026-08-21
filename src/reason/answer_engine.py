# ============================================================================
# 回答生成引擎 — src/reason/answer_engine.py
# ============================================================================
# 接收混合检索的结构化上下文（向量文证 + 图谱理证），
# 拼 prompt → 调 qwen-max 生成结构化回答。
#
# 输出格式：
#   {
#     "question": "原始问题",
#     "answer": "综合结论（300-500字）",
#     "evidence": [{"source_doc", "原文片段", "置信度"}, ...],
#     "graph_paths": [{"source", "relation", "target", "来源论文"}, ...],
#     "source_papers": ["论文1", "论文2", ...],
#   }
# ============================================================================

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from src.embedding import get_embedder
from src.kg.llm_extract_client import chat_json
from src.retrieve.hybrid import ChunkCache, HybridRetriever

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class AnswerEngine:
    """混合检索 + qwen-max 生成回答。"""

    def __init__(self):
        self.retriever = HybridRetriever().load()
        self.chunk_cache = ChunkCache()

    def answer(self, question: str, top_k: int = 8,
               max_graph_edges: int = 10) -> dict:
        """主入口：检索 → 生成 → 返回结构化回答。"""
        # 1. 混合检索
        result = self.retriever.search(question, top_k=top_k,
                                       max_graph_edges=max_graph_edges)

        # 2. 填充原文（向量命中的 chunk）
        vector_hits = self.chunk_cache.hydrate(result["vector_hits"])

        # 3. 组装 prompt
        prompt = self._build_prompt(question, result["entities"],
                                    vector_hits, result["graph_hits"])

        # 4. 调 qwen-max 生成回答
        answer_data = self._generate(prompt)

        # 5. 提取证据源
        evidence = self._extract_evidence(answer_data, vector_hits)
        graph_paths = self._extract_graph_paths(result["graph_hits"])
        source_papers = self._extract_source_papers(vector_hits, result["graph_hits"])

        return {
            "question": question,
            "answer": answer_data.get("answer", ""),
            "evidence": evidence[:5],
            "graph_paths": graph_paths[:5],
            "source_papers": source_papers[:10],
            "raw_context": result["context"],
        }

    def _build_prompt(self, question: str, entities: dict,
                      vector_hits: List[dict],
                      graph_hits: List[dict]) -> str:
        """构建回答生成 prompt。"""
        parts = [
            "你是一名绿色金融论文研究助手。请基于以下检索到的论文证据，回答用户问题。",
            "",
            f"用户问题：{question}",
            "",
        ]

        # 识别实体
        if any(entities.values()):
            parts.append("识别到的研究实体：")
            for et, names in entities.items():
                if names:
                    parts.append(f"  - {et}：{'、'.join(names)}")
            parts.append("")

        # 向量原文证据
        if vector_hits:
            parts.append("相关原文片段（按语义相似度降序）：")
            for i, v in enumerate(vector_hits, 1):
                text = v.get("text", "")[:200]
                if not text:
                    continue
                parts.append(
                    f"  [{i}] 来源：{v['doc_id'][:30]} | "
                    f"章节：{v['section_title'] or '无'}\n"
                    f"      {text}"
                )
            parts.append("")

        # 图谱因果证据
        causal = [h for h in graph_hits if h.get("type") == "concept_relation"]
        if causal:
            parts.append("知识图谱因果关系（跨论文关联）：")
            for i, h in enumerate(causal, 1):
                parts.append(
                    f"  [{i}] {h['source']} --{h['relation']}--> {h['target']}\n"
                    f"      （证据：{h['evidence'][:100] or '无'}，"
                    f"来源：{h['source_doc'][:20]}）"
                )
            parts.append("")

        # 输出要求
        parts.append("""请根据以上检索到的证据，输出严格 JSON（不要多余文字）：
{
  "answer": "综合回答（300-500字，引用原文证据，指出因果关系路径）",
  "conclusion": "一句话核心结论",
  "confidence": "high/medium/low"
}

要求：
1. 答案必须基于检索到的证据，不要编造
2. 明确指出因果关系路径（如：绿色金融政策→促进→绿色技术创新）
3. 如果证据不足，请如实说明
4. 区分已确认的因果方向和仅发现的关联关系""")

        return "\n".join(parts)

    def _generate(self, prompt: str) -> dict:
        """调 qwen-max 生成回答。"""
        try:
            content = chat_json(
                [{"role": "user", "content": prompt}],
                max_tokens=2048,
            )
            if not content:
                return {"answer": "LLM 返回为空，请稍后重试。", "conclusion": "", "confidence": "low"}
            # 提取 JSON
            s = content.strip()
            m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", s, re.DOTALL)
            if m:
                s = m.group(1)
            parsed = json.loads(s)
            return parsed
        except Exception as e:
            return {
                "answer": f"回答生成异常: {e}",
                "conclusion": "",
                "confidence": "low",
            }

    @staticmethod
    def _extract_evidence(answer_data: dict,
                          vector_hits: List[dict]) -> List[dict]:
        """提取证据源。"""
        evidence = []
        seen = set()
        for v in vector_hits:
            text = v.get("text", "")[:150]
            if not text or text in seen:
                continue
            seen.add(text)
            evidence.append({
                "source_doc": v.get("doc_id", ""),
                "section": v.get("section_title", ""),
                "snippet": text,
                "score": v.get("score", 0),
            })
        return evidence

    @staticmethod
    def _extract_graph_paths(graph_hits: List[dict]) -> List[dict]:
        """提取图谱路径。"""
        paths = []
        for h in graph_hits:
            if h.get("type") == "concept_relation":
                paths.append({
                    "source": h["source"],
                    "relation": h["relation"],
                    "target": h["target"],
                    "confidence": h["confidence"],
                    "source_doc": h.get("source_doc", ""),
                })
        return paths

    @staticmethod
    def _extract_source_papers(vector_hits: List[dict],
                               graph_hits: List[dict]) -> List[str]:
        """提取涉及的论文列表。"""
        papers = set()
        for v in vector_hits:
            did = v.get("doc_id", "")
            if did:
                papers.add(did)
        for h in graph_hits:
            sd = h.get("source_doc", "")
            if sd:
                papers.add(sd)
        return sorted(papers)[:10]


if __name__ == "__main__":
    # 命令行测试
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else \
        "绿色金融政策如何影响高耗能企业的绿色技术创新"
    eng = AnswerEngine()
    result = eng.answer(q)
    print(f"\n{'='*60}")
    print(f"Q: {result['question']}")
    print(f"\nA: {result['answer']}")
    print(f"\n📎 证据源 ({len(result['evidence'])} 条):")
    for e in result['evidence'][:3]:
        print(f"  [{e['source_doc'][:25]}] {e['snippet'][:60]}...")
    print(f"\n🔗 图谱路径 ({len(result['graph_paths'])} 条):")
    for p in result['graph_paths'][:3]:
        print(f"  {p['source']} -{p['relation']}-> {p['target']}")
    print(f"\n📚 涉及论文 ({len(result['source_papers'])} 篇):")
    for p in result['source_papers'][:5]:
        print(f"  - {p[:40]}")