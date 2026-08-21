# ============================================================================
# 混合检索融合层 — src/retrieve/hybrid.py
# ============================================================================
# 向量检索（语义 Top-K） + 图谱检索（因果/概念关联）融合。
#
# 设计原则（互补不互覆盖）：
#   - 向量层：召回语义相近的原文 chunk（文证）
#   - 图谱层：召回因果/概念关联路径（理证）
#   - 融合：两个来源分别去重、打 tag，拼成结构化上下文给下游回答引擎
#
# 输出一个结构化 dict：
#   {
#     "question": 原始问题,
#     "entities": {concepts, methods},           # 问题抽出实体
#     "vector_hits": [ {chunk, score, ...} ],    # 语义文证
#     "graph_hits": [ {relation chain, ...} ],   # 图谱理证
#     "context": "拼接后的 prompt 文本"           # 供回答引擎直接使用
#   }
# ============================================================================

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from src.embedding import get_embedder
from src.retrieve.graph_retriever import get_graph_retriever
from src.vector.store import get_store

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_STORE = str(PROJECT_ROOT / "artifacts" / "vector" / "all_store.h5")


class HybridRetriever:
    """向量 + 图谱混合检索。"""

    def __init__(self, store_path: str = DEFAULT_STORE):
        self.store_path = store_path
        self._store = None
        self.vector_hits: List[dict] = []
        self.graph_hits: List[dict] = []

    # ---------------- 初始化 ----------------
    def load(self) -> "HybridRetriever":
        """打开向量存储（通过工厂） + 加载内存图谱。"""
        self._store = get_store(self.store_path).open()
        gr = get_graph_retriever()  # 加载图谱（单例）
        return self

    # ---------------- 向量检索 ----------------
    def vector_search(self, question: str, top_k: int = 8) -> List[dict]:
        """向量语义检索，返回带元数据的 hits。"""
        if self._store is None:
            raise RuntimeError("store 未加载，先调用 .load()")
        embedder = get_embedder()
        qv = embedder.embed(question)
        results = self._store.search(qv, top_k=top_k)
        hits = []
        for score, meta in results:
            hits.append({
                "chunk_id": meta.get("chunk_id", ""),
                "doc_id": meta.get("doc_id", ""),
                "chunk_level": meta.get("chunk_level", ""),
                "section_title": meta.get("section_title", ""),
                "title": meta.get("title", ""),
                "score": score,
                "text": self._get_chunk_text(meta),
            })
        return hits

    def _get_chunk_text(self, meta: dict) -> str:
        """从 chunk_id + doc_id 定位原文（暂时返回占位，实际应由文档切片缓存提供）。"""
        doc_id = meta.get("doc_id", "")
        chunk_id = meta.get("chunk_id", "")
        # 尝试从 chunk 缓存读取（后续接入）
        return f"[{chunk_id}]"

    # ---------------- 图谱检索 ----------------
    def graph_search(self, entities: Dict[str, List[str]], max_edges: int = 10) -> List[dict]:
        """根据问题实体，做图谱检索，返回因果/概念关联。

        参数:
          entities: {"concepts": [...], "methods": [...]}
          max_edges: 单概念最多返回的关系边数
        """
        gr = get_graph_retriever()
        hits: List[dict] = []

        # 概念检索
        concepts = (entities or {}).get("concepts", [])
        for concept in concepts:
            rels = gr.get_concept_relations(concept)[:max_edges]
            for r in rels:
                if r["relation"] == "CO_OCCUR":
                    continue  # 共现关系强度弱，不作为因果证据
                hits.append({
                    "type": "concept_relation",
                    "source": r["source"],
                    "relation": r["relation"],
                    "target": r["target"],
                    "confidence": r["confidence"],
                    "evidence": r["evidence"],
                    "source_doc": r["source_doc"],
                })

        # 方法检索
        methods = (entities or {}).get("methods", [])
        for method in methods:
            # 搜索方法节点，找关联论文
            method_hits = gr.search_entity(method, top_k=5)
            for nid, ntype, label, score in method_hits:
                if ntype != "Method":
                    continue
                # 找用到该方法的论文
                for src, _, attrs in gr.graph.in_edges(nid, data=True):
                    if attrs.get("relation") == "USES_METHOD":
                        hits.append({
                            "type": "method_paper",
                            "method": label,
                            "paper": src.split(":", 1)[-1],
                            "source_doc": attrs.get("source_doc", ""),
                        })

        # 去重（同一条关系只保留一次）
        seen = set()
        dedup = []
        for h in hits:
            if h["type"] == "concept_relation":
                key = (h["source"], h["relation"], h["target"])
            elif h["type"] == "method_paper":
                key = (h["method"], h["paper"])
            else:
                key = tuple(sorted(h.items()))
            if key not in seen:
                seen.add(key)
                dedup.append(h)

        # 按置信度降序
        dedup.sort(key=lambda x: -x.get("confidence", 0))
        return dedup

    # ---------------- 融合 ----------------
    def search(self, question: str, top_k: int = 8,
               max_graph_edges: int = 10) -> Dict[str, object]:
        """混合检索主入口。

        参数:
          question: 问题文本
          top_k: 向量 Top-K
          max_graph_edges: 图谱每个概念最大返回边数

        返回: 结构化结果 dict
        """
        # 1. 实体链接
        entities = get_graph_retriever().extract_entities(question)
        # 实体可能为空（纯语义问题），不影响向量检索

        # 2. 向量检索
        self.vector_hits = self.vector_search(question, top_k)

        # 3. 图谱检索
        self.graph_hits = self.graph_search(entities, max_graph_edges)

        # 4. 组装上下文
        context = self._build_context(question, entities)

        return {
            "question": question,
            "entities": entities,
            "vector_hits": self.vector_hits,
            "graph_hits": self.graph_hits,
            "context": context,
        }

    def _build_context(self, question: str, entities: Dict[str, List[str]]) -> str:
        """把两个来源拼成给 LLM 的上下文。"""
        parts = [f"问题: {question}"]

        # 实体
        if any(entities.values()):
            parts.append("识别实体:")
            for et, names in entities.items():
                if names:
                    parts.append(f"  - {et}: {', '.join(names)}")

        # 图谱理证
        if self.graph_hits:
            parts.append("\n知识图谱证据（因果/概念关联）:")
            for i, h in enumerate(self.graph_hits, 1):
                if h["type"] == "concept_relation":
                    parts.append(
                        f"  [{i}] {h['source']} -{h['relation']}-> {h['target']} "
                        f"(置信度 {h['confidence']}, 来源 {h['source_doc'][:20]}, "
                        f"证据: {h['evidence'][:80] or '无'})"
                    )
                elif h["type"] == "method_paper":
                    parts.append(
                        f"  [{i}] 方法 {h['method']} 被论文 `{h['paper'][:40]}` 使用"
                    )

        # 向量文证（在此合并原文，实际由 answer_engine 展开）
        parts.append("\n相关原文片段（语义命中）：")
        for i, v in enumerate(self.vector_hits, 1):
            parts.append(f"  [{i}] (相似度 {v['score']:.3f}) {v['section_title'] or '无标题'}")

        return "\n".join(parts)


# ============================================================================
# 原文 chunk 缓存（向量检索命中的 chunk 需要真实文本）
# ============================================================================
class ChunkCache:
    """
    从 cleaned md 重新切片得到真实 chunk 文本缓存。
    因为 hdf5 只存了 chunk_id，需要把 37 篇重新切片建映射。
    惰性构建，首次命中时加载对应文档。
    """

    def __init__(self):
        self._cache: Dict[str, str] = {}  # chunk_id -> text
        self._doc_cache: Dict[str, List] = {}  # doc_id -> chunks

    def get(self, doc_id: str, chunk_level: str, chunk_seq: int) -> str:
        """按 doc_id + level + seq 定位原文。"""
        key = f"{doc_id}__{chunk_level}_{chunk_seq:04d}"
        if key in self._cache:
            return self._cache[key]
        # 加载该文档的所有 chunk
        if doc_id not in self._doc_cache:
            from src.retrieve.chunker import chunk_markdown
            md_path = PROJECT_ROOT / "cleaned" / f"{doc_id}.md"
            if not md_path.exists():
                return ""
            from src.kg.pipeline import load_meta
            meta = load_meta(PROJECT_ROOT / "cleaned_meta" / f"{doc_id}.json")
            title = meta.get("title") or doc_id
            chunks = chunk_markdown(doc_id, md_path.read_text(encoding="utf-8"),
                                    {"title": title, "source_type": "paper"})
            self._doc_cache[doc_id] = chunks
        for c in self._doc_cache[doc_id]:
            cid = c.chunk_id
            if not cid in self._cache:
                self._cache[cid] = c.chunk_text
        return self._cache.get(key, "")

    def hydrate(self, vector_hits: List[dict]) -> List[dict]:
        """把向量命中的 chunk_id 填充真实文本。"""
        for v in vector_hits:
            meta = v
            if "text" in v and v["text"] and not v["text"].startswith("["):
                continue
            # 从 chunk_id 解析
            cid = v.get("chunk_id", "")
            # 解析 {doc_id}__{level}_{seq}
            if "__" in cid:
                head, _, tail = cid.partition("__")
                doc_id = head
                # tail: semantic_0004
                parts = tail.split("_")
                level = parts[0]
                seq = int(parts[1])
                v["text"] = self.get(doc_id, level, seq)
        return vector_hits


if __name__ == "__main__":
    # 冒烟测试
    import json
    hr = HybridRetriever().load()
    q = "绿色金融政策如何影响绿色技术创新"
    result = hr.search(q)
    print(json.dumps({k: v for k, v in result.items() if k != "context"},
                     ensure_ascii=False, indent=2)[:1500])