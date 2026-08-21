# ============================================================================
# 抽样质检 — scripts/sample_check.py
# ============================================================================
# 从已处理的文档中随机抽样，输出质检报告。
# 检查维度：KG 实体数、关系数、向量 chunk 数、有无错误。
#
# 用法:
#   python scripts/sample_check.py 10          # 抽 10 篇
#   python scripts/sample_check.py 10 --seed 42  # 固定随机种子
# ============================================================================

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.status import load_status, STATUS_PATH


def get_kg_stats(doc_id: str, kg_dir: Path) -> Optional[dict]:
    """读取单篇 KG JSON 的统计信息。"""
    path = kg_dir / f"{doc_id}.kg.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            "concepts": len(data.get("concepts", [])),
            "methods": len(data.get("methods", [])),
            "datasets": len(data.get("datasets", [])),
            "relations": len(data.get("relations", [])),
            "kg_size_kb": round(path.stat().st_size / 1024, 1),
        }
    except (json.JSONDecodeError, OSError) as e:
        return {"error": str(e)}


def get_vector_stats(doc_id: str, store_path: Path) -> Optional[dict]:
    """读取 hdf5 中某篇文档的向量统计。"""
    try:
        import h5py
        import numpy as np
    except ImportError:
        return None

    if not store_path.exists():
        return None
    try:
        with h5py.File(str(store_path), "r") as f:
            if "metas" not in f:
                return None
            metas = f["metas"][:]
            chunks = []
            for m in metas:
                try:
                    meta = json.loads(m)
                    if meta.get("doc_id") == doc_id:
                        chunks.append(meta)
                except (json.JSONDecodeError, TypeError):
                    pass
            if not chunks:
                return None
            return {
                "chunks": len(chunks),
                "levels": {
                    "metadata": sum(1 for c in chunks if c.get("chunk_level") == "metadata"),
                    "semantic": sum(1 for c in chunks if c.get("chunk_level") == "semantic"),
                    "sliding": sum(1 for c in chunks if c.get("chunk_level") == "sliding"),
                },
            }
    except (OSError, KeyError):
        return None


def main():
    import argparse

    parser = argparse.ArgumentParser(description="抽样质检")
    parser.add_argument("n", type=int, nargs="?", default=10, help="抽样数量")
    parser.add_argument("--seed", type=int, default=None, help="随机种子")
    args = parser.parse_args()

    cleaned_dir = PROJECT_ROOT / "cleaned"
    kg_dir = PROJECT_ROOT / "artifacts" / "kg"
    vector_store = PROJECT_ROOT / "artifacts" / "vector" / "all_store.h5"

    status = load_status()

    # 收集全部 doc_id
    all_doc_ids = sorted(p.stem for p in cleaned_dir.glob("*.md"))
    if not all_doc_ids:
        print("❌ cleaned/ 为空，无可抽样的文档")
        return 1

    # 抽样
    if args.seed is not None:
        random.seed(args.seed)
    sample_size = min(args.n, len(all_doc_ids))
    sampled = random.sample(all_doc_ids, sample_size)
    sampled.sort()

    print("=" * 70)
    print(f"🔍 抽样质检报告")
    print(f"   总数: {len(all_doc_ids)} 篇, 抽样: {sample_size} 篇")
    print(f"   种子: {args.seed or 'random'}")
    print("=" * 70)

    # 统计
    total_kg_ok = 0
    total_vector_ok = 0
    total_errors = 0
    results = []

    for doc_id in sampled:
        entry = status.get(doc_id, {})
        kg_status = entry.get("kg", "unknown")
        vector_status = entry.get("vector", "unknown")

        kg_stats = get_kg_stats(doc_id, kg_dir)
        vector_stats = get_vector_stats(doc_id, vector_store)

        row = {
            "doc_id": doc_id[:60],
            "kg": kg_status,
            "vector": vector_status,
            "kg_concepts": kg_stats.get("concepts", "?") if kg_stats else "?",
            "kg_relations": kg_stats.get("relations", "?") if kg_stats else "?",
            "chunks": vector_stats.get("chunks", "?") if vector_stats else "?",
            "error": entry.get("error", ""),
        }
        results.append(row)

        if kg_status == "done":
            total_kg_ok += 1
        if vector_status == "done":
            total_vector_ok += 1
        if kg_status == "failed" or vector_status == "failed":
            total_errors += 1

    # 表格输出
    print(f"\n{'doc_id':<50} {'KG':<8} {'Vec':<8} {'概念':<6} {'关系':<6} {'Chunks':<8}")
    print("-" * 90)
    for r in results:
        kg_icon = "✅" if r["kg"] == "done" else "❌" if r["kg"] == "failed" else "⏳"
        vec_icon = "✅" if r["vector"] == "done" else "❌" if r["vector"] == "failed" else "⏳"
        print(f"{r['doc_id'][:48]:<48} {kg_icon:<4} {vec_icon:<4} "
              f"{str(r['kg_concepts']):<6} {str(r['kg_relations']):<6} {str(r['chunks']):<8}")

    # 汇总
    print(f"\n{'=' * 70}")
    print(f"汇总: 抽样 {sample_size} 篇")
    print(f"  KG 完成:     {total_kg_ok}/{sample_size} ({100*total_kg_ok/sample_size:.0f}%)")
    print(f"  向量化完成:  {total_vector_ok}/{sample_size} ({100*total_vector_ok/sample_size:.0f}%)")
    print(f"  含错误:      {total_errors} 篇")
    if total_errors:
        print(f"\n  错误详情:")
        for r in results:
            if r["kg"] == "failed" or r["vector"] == "failed":
                print(f"    - {r['doc_id']}: {r['error'][:80]}")


if __name__ == "__main__":
    main()