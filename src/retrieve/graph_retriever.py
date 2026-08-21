# ============================================================================
# 内存图谱遍历器 — src/retrieve/graph_retriever.py
# ============================================================================
# 基于 artifacts/kg/*.kg.json 构建 networkx 有向图，支持：
#   - 按实体名（概念/方法/论文/数据集）检索邻域
#   - 按实体类型筛选
#   - 实体链接（从用户问题中提取研究实体，轻量级 qwen 调用）
#   - 跨论文概念关联路径检索
#
# 设计：
#   - 节点类型：Paper / Author / Concept / Method / Dataset
#   - 边类型：PROMOTE / INHIBIT / CO_OCCUR / AUTHORED_BY / MENTIONS / USES_METHOD / USES_DATASET
#   - 边属性：evidence / source_doc / confidence
#   - 全部 37 篇 KG JSON 加载到内存，避开 Neo4j 依赖
# ============================================================================

from __future__ import annotations

import glob
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

from src.kg.llm_extract_client import chat_json

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
KG_DIR = PROJECT_ROOT / "artifacts" / "kg"


class GraphRetriever:
    """内存知识图谱（networkx 有向图）。"""

    def __init__(self):
        self._g: nx.DiGraph = nx.DiGraph()
        self._entity_index: Dict[str, List[Tuple[str, str]]] = {}  # 小写名 → [(节点id, 类型)]
        self._loaded = False

    # ---------------- 加载 ----------------
    def load(self, kg_dir: str = None) -> int:
        """加载 artifacts/kg/*.kg.json 构建有向图。

        返回加载的节点数。
        """
        kg_dir = kg_dir or str(KG_DIR)
        files = sorted(glob.glob(os.path.join(kg_dir, "*.kg.json")))
        if not files:
            print(f"⚠️  KG 目录无 .kg.json 文件: {kg_dir}")
            return 0

        for fpath in files:
            try:
                data = json.loads(Path(fpath).read_text(encoding="utf-8"))
                self._add_kg_json(data)
            except Exception as e:
                print(f"  ⚠️  加载 {Path(fpath).name} 失败: {e}")

        self._build_index()
        self._loaded = True
        n = self._g.number_of_nodes()
        print(f"📊 内存图谱: {n} 节点, {self._g.number_of_edges()} 边, {len(files)} 篇论文")
        return n

    def _add_kg_json(self, data: dict) -> None:
        """将单篇 KG JSON 加入图。"""
        paper = data.get("paper", {})
        doc_id = paper.get("doc_id", "")
        if not doc_id:
            return

        # Paper 节点
        paper_id = f"paper:{doc_id}"
        self._g.add_node(paper_id, type="Paper", label=paper.get("title", doc_id),
                         doc_id=doc_id, **{k: v for k, v in paper.items() if k != "doc_id"})

        # Author 节点 + 边
        for a in data.get("authors", []):
            name = a.get("name", "")
            if not name:
                continue
            author_id = f"author:{name}"
            self._g.add_node(author_id, type="Author", label=name)
            self._g.add_edge(paper_id, author_id, relation="AUTHORED_BY", source_doc=doc_id)

        # Concept 节点 + 边
        for c in data.get("concepts", []):
            name = c.get("name", "")
            if not name:
                continue
            cid = f"concept:{name}"
            self._g.add_node(cid, type="Concept", label=name, alias_of=c.get("alias_of"))
            self._g.add_edge(paper_id, cid, relation="MENTIONS", source_doc=doc_id)

        # Method 节点 + 边
        for m in data.get("methods", []):
            name = m.get("name", "")
            if not name:
                continue
            mid = f"method:{name}"
            self._g.add_node(mid, type="Method", label=name, category=m.get("category"))
            self._g.add_edge(paper_id, mid, relation="USES_METHOD", source_doc=doc_id)

        # Dataset 节点 + 边
        for d in data.get("datasets", []):
            name = d.get("name", "")
            if not name:
                continue
            did = f"dataset:{name}"
            self._g.add_node(did, type="Dataset", label=name)
            self._g.add_edge(paper_id, did, relation="USES_DATASET", source_doc=doc_id)

        # 概念间关系边
        for r in data.get("relations", []):
            src = r.get("source", "")
            tgt = r.get("target", "")
            rel = r.get("relation", "CO_OCCUR")
            if not src or not tgt:
                continue
            sid = f"concept:{src}"
            tid = f"concept:{tgt}"
            # 确保概念节点存在
            if not self._g.has_node(sid):
                self._g.add_node(sid, type="Concept", label=src)
            if not self._g.has_node(tid):
                self._g.add_node(tid, type="Concept", label=tgt)
            ev = r.get("evidence", {})
            if isinstance(ev, str):
                ev = {"evidence": ev}
            self._g.add_edge(
                sid, tid, relation=rel,
                source_doc=r.get("source_doc", doc_id),
                confidence=r.get("confidence", 1.0),
                evidence=ev.get("evidence", ""),
                snippet=ev.get("snippet", ""),
            )

    def _build_index(self) -> None:
        """构建小写实体名 → (节点id, 类型) 索引。"""
        self._entity_index.clear()
        for nid, attrs in self._g.nodes(data=True):
            label = attrs.get("label", "") or nid.split(":", 1)[-1]
            ntype = attrs.get("type", "Unknown")
            # 全名 + 分词片段
            key = label.lower().strip()
            if key:
                self._entity_index.setdefault(key, []).append((nid, ntype))
            # 英文按空格分词索引
            for token in re.split(r"[\s,;:()\[\]{}]+", key):
                if len(token) >= 2:
                    self._entity_index.setdefault(token, []).append((nid, ntype))

    # ---------------- 检索 ----------------
    def search_entity(self, query: str, top_k: int = 10) -> List[Tuple[str, str, str, float]]:
        """模糊搜索实体名。

        返回 [(节点id, 类型, 标签, 得分), ...] 按相关性降序。
        """
        q = query.lower().strip()
        if not q:
            return []

        candidates: Dict[str, Tuple[str, str, str, float]] = {}

        # 精确匹配
        if q in self._entity_index:
            for nid, ntype in self._entity_index[q]:
                label = self._g.nodes[nid].get("label", nid)
                candidates[nid] = (nid, ntype, label, 1.0)

        # 子串匹配（词级 + 词内子串）
        tokens = set(re.split(r"[\s,;:()\[\]{}]+", q))
        # 再加完整 query 做子串匹配
        all_query_grams = [q]
        # 对每个 token 也做子串匹配
        for token in tokens:
            if len(token) < 2:
                continue
            all_query_grams.append(token)
            # 中文双字滑动
            for j in range(len(token) - 1):
                all_query_grams.append(token[j:j + 2])

        for gram in all_query_grams:
            if len(gram) < 2:
                continue
            # 精确 token 匹配
            for nid, ntype in self._entity_index.get(gram, []):
                if nid in candidates:
                    continue
                label = self._g.nodes[nid].get("label", nid)
                score = len(gram) / max(len(label), 1)
                candidates[nid] = (nid, ntype, label, round(score, 2))
            # 子串模糊匹配（对每个已索引的 key）
            for key, entries in self._entity_index.items():
                if gram in key:
                    for nid, ntype in entries:
                        if nid in candidates:
                            continue
                        label = self._g.nodes[nid].get("label", nid)
                        score = 0.5 + 0.3 * len(gram) / max(len(key), 1)
                        candidates[nid] = (nid, ntype, label, round(min(score, 1.0), 2))

        # 排序
        result = sorted(candidates.values(), key=lambda x: -x[3])
        return result[:top_k]

    def get_neighborhood(self, node_id: str, depth: int = 1,
                         max_nodes: int = 30) -> nx.DiGraph:
        """获取节点邻域子图（指定深度）。"""
        if not self._g.has_node(node_id):
            return nx.DiGraph()

        visited = {node_id}
        frontier = {node_id}
        for _ in range(depth):
            if len(visited) >= max_nodes:
                break
            next_frontier = set()
            for n in frontier:
                neighbors = set(self._g.successors(n)) | set(self._g.predecessors(n))
                for nb in neighbors:
                    if nb not in visited:
                        visited.add(nb)
                        next_frontier.add(nb)
                        if len(visited) >= max_nodes:
                            break
                if len(visited) >= max_nodes:
                    break
            frontier = next_frontier

        return self._g.subgraph(visited)

    def get_concept_relations(self, concept_name: str) -> List[dict]:
        """获取某个概念的所有关系边（因果 + 共现）。

        返回 [{"source", "target", "relation", "confidence", "evidence", "source_doc"}, ...]
        """
        cid = f"concept:{concept_name}"
        if not self._g.has_node(cid):
            # 尝试模糊查找
            hits = self.search_entity(concept_name, top_k=3)
            for nid, ntype, _, _ in hits:
                if ntype == "Concept":
                    cid = nid
                    break
            if not self._g.has_node(cid):
                return []

        results = []
        for _, tgt, attrs in self._g.edges(cid, data=True):
            rel = attrs.get("relation", "CO_OCCUR")
            if rel != "CO_OCCUR" or True:  # 全部返回，上层筛选
                results.append({
                    "source": concept_name,
                    "target": tgt.split(":", 1)[-1],
                    "target_type": self._g.nodes[tgt].get("type", "Unknown"),
                    "relation": rel,
                    "confidence": attrs.get("confidence", 1.0),
                    "evidence": attrs.get("evidence", ""),
                    "source_doc": attrs.get("source_doc", ""),
                })
        for src, _, attrs in self._g.in_edges(cid, data=True):
            rel = attrs.get("relation", "CO_OCCUR")
            results.append({
                "source": src.split(":", 1)[-1],
                "source_type": self._g.nodes[src].get("type", "Unknown"),
                "target": concept_name,
                "relation": rel,
                "confidence": attrs.get("confidence", 1.0),
                "evidence": attrs.get("evidence", ""),
                "source_doc": attrs.get("source_doc", ""),
            })
        return results

    def get_paper_concepts(self, doc_id: str) -> List[str]:
        """获取一篇论文涉及的所有概念。"""
        pid = f"paper:{doc_id}"
        if not self._g.has_node(pid):
            return []
        concepts = []
        for _, tgt, attrs in self._g.out_edges(pid, data=True):
            if attrs.get("relation") == "MENTIONS":
                concepts.append(tgt.split(":", 1)[-1])
        return concepts

    def get_paper_methods(self, doc_id: str) -> List[str]:
        """获取一篇论文使用的方法。"""
        pid = f"paper:{doc_id}"
        if not self._g.has_node(pid):
            return []
        methods = []
        for _, tgt, attrs in self._g.out_edges(pid, data=True):
            if attrs.get("relation") == "USES_METHOD":
                methods.append(tgt.split(":", 1)[-1])
        return methods

    # ---------------- 实体链接（轻量级 LLM） ----------------
    def extract_entities(self, question: str) -> Dict[str, List[str]]:
        """从用户问题中提取研究实体（概念/方法/论文）。

        用轻量级 LLM 调用（qwen-max），返回结构化实体列表。
        """
        prompt = (
            f"你是一个绿色金融论文的实体抽取助手。请从以下问题中提取研究实体，"
            f"分为 concepts（概念/变量）、methods（方法/模型）两类。\n\n"
            f"问题：{question}\n\n"
            f"输出严格 JSON（不要多余文字）：\n"
            f'{{"concepts": ["概念1", "概念2"], "methods": ["方法1"]}}\n\n'
            f"如果没有某类实体，返回空数组。实体名尽量简洁、规范。"
        )
        try:
            content = chat_json([{"role": "user", "content": prompt}], max_tokens=256)
            if not content:
                return {"concepts": [], "methods": []}
            import json as j
            parsed = j.loads(content)
            return {
                "concepts": [c for c in parsed.get("concepts", []) if c],
                "methods": [m for m in parsed.get("methods", []) if m],
            }
        except Exception as e:
            print(f"  ⚠️  实体链接异常: {e}")
            return {"concepts": [], "methods": []}

    # ---------------- 属性 ----------------
    @property
    def graph(self) -> nx.DiGraph:
        return self._g

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def node_count(self) -> int:
        return self._g.number_of_nodes()

    def edge_count(self) -> int:
        return self._g.number_of_edges()


# 全局单例
_retriever: Optional[GraphRetriever] = None


def get_graph_retriever() -> GraphRetriever:
    """获取全局图谱遍历器（单例，懒加载）。"""
    global _retriever
    if _retriever is None:
        _retriever = GraphRetriever()
        _retriever.load()
    return _retriever


if __name__ == "__main__":
    # 冒烟测试
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    gr = get_graph_retriever()
    print(f"节点: {gr.node_count()}, 边: {gr.edge_count()}")

    # 测试实体搜索
    print("\n=== 搜索 '绿色金融' ===")
    for nid, ntype, label, score in gr.search_entity("绿色金融", top_k=5):
        print(f"  {ntype}: {label} (score={score}) [{nid}]")

    # 测试概念关系
    print("\n=== 绿色金融政策 的关系 ===")
    rels = gr.get_concept_relations("绿色金融政策")
    for r in rels[:5]:
        print(f"  {r['source']} -{r['relation']}-> {r['target']} (conf={r['confidence']})")

    # 测试实体链接
    print("\n=== 实体链接: '绿色金融的DID方法' ===")
    ents = gr.extract_entities("绿色金融的DID方法")
    print(f"  concepts={ents['concepts']}, methods={ents['methods']}")