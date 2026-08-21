# ============================================================================
# FastAPI HTTP 服务 — src/api/server.py
# ============================================================================
# 提供 RESTful 接口给上层应用（HypoWeaver / 前端 / 脚本）。
#
# 端点:
#   GET  /health          — 健康检查（向量存储 + 图谱状态）
#   POST /query           — 端到端问答（混合检索 + LLM 生成）
#   POST /search/vector   — 仅向量检索（调试用）
#   POST /search/graph    — 仅图谱检索（调试用）
#   GET  /status          — 系统状态报告
#
# 用法:
#   uvicorn src.api.server:app --host 0.0.0.0 --port 8002
# ============================================================================

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.reason.answer_engine import AnswerEngine
from src.retrieve.graph_retriever import get_graph_retriever
from src.vector.store import get_store, VectorStoreH5
from src.status import get_stats

# ============================================================================
# 数据模型
# ============================================================================

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="用户问题")
    top_k: int = Field(default=8, ge=1, le=50, description="向量 Top-K 检索数")
    max_graph_edges: int = Field(default=10, ge=0, le=50, description="图谱每概念最大边数")


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="查询文本")
    top_k: int = Field(default=8, ge=1, le=50)


class GraphSearchRequest(BaseModel):
    entity: str = Field(..., min_length=1, description="实体名")
    max_edges: int = Field(default=10, ge=1, le=50)


class HealthResponse(BaseModel):
    status: str
    vector_store: bool
    graph_loaded: bool
    vector_count: int
    graph_nodes: int
    graph_edges: int


class StatusResponse(BaseModel):
    total_docs: int
    kg_done: int
    kg_failed: int
    vector_done: int
    vector_failed: int
    pending: int
    vector_count: int


# ============================================================================
# 应用
# ============================================================================

app = FastAPI(
    title="RAG-Graph API",
    description="绿色金融论文混合检索问答系统（向量 + 知识图谱）",
    version="1.0.0",
)

# 全局实例（懒加载）
_answer_engine: Optional[AnswerEngine] = None


def _get_engine() -> AnswerEngine:
    """获取 AnswerEngine 全局单例。"""
    global _answer_engine
    if _answer_engine is None:
        _answer_engine = AnswerEngine()
    return _answer_engine


# ============================================================================
# 端点
# ============================================================================

@app.get("/health", response_model=HealthResponse)
async def health():
    """健康检查。"""
    vector_ok = False
    vector_count = 0
    try:
        store = get_store().open()
        vector_count = store.count()
        vector_ok = True
        store.close()
    except Exception:
        pass

    gr = get_graph_retriever()
    graph_loaded = gr.is_loaded
    graph_nodes = gr.node_count() if graph_loaded else 0
    graph_edges = gr.edge_count() if graph_loaded else 0

    return HealthResponse(
        status="ok" if vector_ok else "degraded",
        vector_store=vector_ok,
        graph_loaded=graph_loaded,
        vector_count=vector_count,
        graph_nodes=graph_nodes,
        graph_edges=graph_edges,
    )


@app.get("/status", response_model=StatusResponse)
async def status():
    """系统状态报告。"""
    stats = get_stats()
    vector_count = 0
    try:
        store = get_store().open()
        vector_count = store.count()
        store.close()
    except Exception:
        pass
    return StatusResponse(
        total_docs=stats["total"],
        kg_done=stats["kg_done"],
        kg_failed=stats["kg_failed"],
        vector_done=stats["vector_done"],
        vector_failed=stats["vector_failed"],
        pending=stats["pending"],
        vector_count=vector_count,
    )


@app.post("/query")
async def query(req: QueryRequest):
    """端到端问答（混合检索 + LLM 生成）。"""
    t0 = time.time()
    try:
        engine = _get_engine()
        result = engine.answer(
            question=req.question,
            top_k=req.top_k,
            max_graph_edges=req.max_graph_edges,
        )
        elapsed = round(time.time() - t0, 2)
        result["elapsed_s"] = elapsed
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search/vector")
async def search_vector(req: SearchRequest):
    """仅向量检索（调试用）。"""
    from src.embedding import get_embedder
    embedder = get_embedder()
    qv = embedder.embed(req.query)

    try:
        store = get_store().open()
        results = store.search(qv, top_k=req.top_k)
        store.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    hits = [
        {
            "score": round(score, 4),
            "doc_id": meta.get("doc_id", ""),
            "chunk_id": meta.get("chunk_id", ""),
            "chunk_level": meta.get("chunk_level", ""),
            "section_title": meta.get("section_title", ""),
            "title": meta.get("title", ""),
        }
        for score, meta in results
    ]
    return {"query": req.query, "hits": hits, "total": len(hits)}


@app.post("/search/graph")
async def search_graph(req: GraphSearchRequest):
    """仅图谱检索（调试用）。"""
    try:
        gr = get_graph_retriever()
        if not gr.is_loaded:
            gr.load()
        rels = gr.get_concept_relations(req.entity)[:req.max_edges]
        return {
            "entity": req.entity,
            "relations": rels,
            "total": len(rels),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    """API 根路径。"""
    return {
        "service": "RAG-Graph API",
        "version": "1.0.0",
        "endpoints": {
            "/health": "GET - 健康检查",
            "/status": "GET - 系统状态",
            "/query": "POST - 端到端问答",
            "/search/vector": "POST - 向量检索（调试）",
            "/search/graph": "POST - 图谱检索（调试）",
        },
    }


# ============================================================================
# 启动入口
# ============================================================================
if __name__ == "__main__":
    import uvicorn
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8002
    uvicorn.run(app, host="0.0.0.0", port=port)