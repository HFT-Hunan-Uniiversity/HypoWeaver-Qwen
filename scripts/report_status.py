# ============================================================================
# 系统状态报告 — scripts/report_status.py
# ============================================================================
# 动态扫描论文目录 + 状态文件，输出系统状态报告。
# 不做任何写操作，只读。
#
# 用法:
#   python scripts/report_status.py
# ============================================================================

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.status import load_status, STATUS_PATH
from src.vector.store import get_store


def get_vector_count() -> int:
    """读取 hdf5 向量存储的条数。"""
    try:
        store = get_store().open()
        n = store.count()
        store.close()
        return n
    except Exception:
        return 0


def main():
    cleaned_dir = PROJECT_ROOT / "cleaned"
    all_doc_ids = sorted(p.stem for p in cleaned_dir.glob("*.md"))
    status = load_status()

    total = len(all_doc_ids)
    kg_done = sum(1 for d in all_doc_ids if status.get(d, {}).get("kg") == "done")
    kg_failed = sum(1 for d in all_doc_ids if status.get(d, {}).get("kg") == "failed")
    kg_pending = total - kg_done - kg_failed
    vector_done = sum(1 for d in all_doc_ids if status.get(d, {}).get("vector") == "done")
    vector_failed = sum(1 for d in all_doc_ids if status.get(d, {}).get("vector") == "failed")

    # 向量存储统计
    vector_count = get_vector_count()

    print("=" * 60)
    print("📊 RAG-Graph 系统状态报告")
    print("=" * 60)
    print(f"cleaned 论文数: {total} 篇（动态扫描 cleaned/）")
    print(f"状态文件: {STATUS_PATH}")

    if total:
        print()
        print(f"KG 抽取:")
        print(f"  ✅ 完成: {kg_done}/{total} ({100*kg_done/total:.1f}%)")
        print(f"  ❌ 失败: {kg_failed} 篇")
        print(f"  ⏳ 待处理: {kg_pending} 篇")
        print()
        print(f"向量化:")
        print(f"  ✅ 完成: {vector_done}/{total} ({100*vector_done/total:.1f}%)")
        print(f"  ❌ 失败: {vector_failed} 篇")
        print(f"  ⏳ 待处理: {total - vector_done - vector_failed} 篇")
        print()
        print(f"向量存储 hdf5:")
        print(f"  总向量数: {vector_count} 条")
        if vector_count and kg_done:
            print(f"  平均每篇: {vector_count / max(kg_done, 1):.0f} chunks")
    else:
        print("    （cleaned/ 为空，无数据）")

    # 失败清单
    failed = [
        (d, status[d].get("error", "unknown"))
        for d in all_doc_ids
        if status.get(d, {}).get("kg") == "failed"
        or status.get(d, {}).get("vector") == "failed"
    ]
    if failed:
        print()
        print(f"❌ 失败文档 ({len(failed)} 篇):")
        for doc_id, err in failed[:15]:
            print(f"  - {doc_id[:60]}: {str(err)[:60]}")
        if len(failed) > 15:
            print(f"  ... 还有 {len(failed) - 15} 篇")

    # KG 图谱规模
    kg_dir = PROJECT_ROOT / "artifacts" / "kg"
    kg_files = list(kg_dir.glob("*.kg.json")) if kg_dir.exists() else []
    print()
    print(f"📚 知识图谱文件: {len(kg_files)} 个 (.kg.json)")


if __name__ == "__main__":
    main()