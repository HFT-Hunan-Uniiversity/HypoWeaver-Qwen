# ============================================================================
# 单篇文档向量化测试 — scripts/vectorize_one.py
# ============================================================================
# 选一篇代表性论文，跑通全链路：
#   cleaned md → chunker 切片 → BGE 嵌入 → hdf5 存储 → 相似度检索自检
# ============================================================================

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.embedding import get_embedder
from src.retrieve.chunker import chunk_markdown
from src.vector.store import VectorStoreH5
from src.kg.pipeline import load_meta

import numpy as np


def vectorize_one(doc_id: str, store_path: str = "artifacts/vector/test_store.h5") -> dict:
    """
    单篇论文向量化全流程。

    返回统计信息 dict。
    """
    print(f"📄 单篇向量化: {doc_id}")

    # 1. 加载元数据
    meta_path = Path(f"cleaned_meta/{doc_id}.json")
    meta = load_meta(meta_path)
    if "_error" in meta:
        print(f"  ❌ 元数据加载失败: {meta['_error']}")
        return {"error": meta["_error"]}

    # 2. 加载正文
    md_path = Path(f"cleaned/{doc_id}.md")
    md_text = md_path.read_text(encoding="utf-8")
    print(f"  正文: {len(md_text)} 字符")

    # 3. Chunk 切片
    title = meta.get("title") or doc_id
    chunks = chunk_markdown(doc_id, md_text, {"title": title, "source_type": "paper"})
    print(f"  切片: {len(chunks)} 个 chunk (metadata=1, semantic={sum(1 for c in chunks if c.chunk_level=='semantic')}, sliding={sum(1 for c in chunks if c.chunk_level=='sliding')})")

    # 4. BGE 嵌入
    embedder = get_embedder()
    texts = [c.chunk_text for c in chunks]
    t0 = time.time()
    vectors = embedder.embed_texts(texts, batch_size=32)
    elapsed = time.time() - t0
    print(f"  嵌入: {len(vectors)} 个向量, dim={vectors.shape[1] if len(vectors) else 0}, 耗时 {elapsed:.1f}s")

    # 5. 写入 hdf5
    metadatas = [
        {
            "doc_id": doc_id,
            "chunk_id": c.chunk_id,
            "chunk_level": c.chunk_level,
            "chunk_seq": c.chunk_seq,
            "section_title": c.section_title or "",
            "token_count": c.token_count,
            "title": title,
        }
        for c in chunks
    ]
    store = VectorStoreH5(store_path).open()
    store.add(vectors, metadatas)
    store.close()
    print(f"  存储: {store_path} (共 {len(vectors)} 条)")

    # 6. 自检：用摘要向量检索，看 Top-K 是否合理
    if len(vectors) > 0:
        # 取 metadata chunk (seq=0) 作为查询
        q_vec = vectors[0]
        store = VectorStoreH5(store_path).open()
        results = store.search(q_vec, top_k=5)
        store.close()
        print(f"\n🔍 自检：用 metadata chunk 检索 Top-5:")
        for score, m in results:
            level = m.get("chunk_level", "?")
            sect = m.get("section_title", "?")[:30]
            chunk_id = m.get("chunk_id", "?")
            print(f"  score={score:.4f}  [{level}] {sect}  ({chunk_id[:40]})")

    # 7. 基础统计
    summary = {
        "doc_id": doc_id,
        "chunks": len(chunks),
        "vectors": len(vectors),
        "dim": vectors.shape[1] if len(vectors) else 0,
        "elapsed_s": round(elapsed, 1),
        "store_path": store_path,
    }
    print(f"\n✅ 完成: {json.dumps(summary, ensure_ascii=False)}")
    return summary


if __name__ == "__main__":
    doc_id = sys.argv[1] if len(sys.argv) > 1 else \
        "绿色金融政策如何影响绿色技术创新基于高耗能企业的经验证据_周莹莹"
    vectorize_one(doc_id)