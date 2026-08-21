# ============================================================================
# 端到端问答 CLI — src/qa_runner.py
# ============================================================================
# 用法:
#   python src/qa_runner.py "绿色金融政策如何影响绿色技术创新"
#   python src/qa_runner.py                          # 交互模式
# ============================================================================

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.reason.answer_engine import AnswerEngine


def print_result(result: dict, verbose: bool = False) -> None:
    """格式化输出回答结果。"""
    print(f"\n{'='*60}")
    print(f"Q: {result['question']}")
    print(f"✅ {result['answer']}")
    if result.get("conclusion"):
        print(f"\n核心结论: {result['conclusion']}")
    print(f"置信度: {result.get('confidence', 'medium')}")

    # 图谱路径
    if result.get("graph_paths"):
        print(f"\n🔗 知识图谱路径 ({len(result['graph_paths'])} 条):")
        for p in result["graph_paths"][:5]:
            print(f"  {p['source']} --{p['relation']}--> {p['target']}  [{p['source_doc'][:25]}]")
        if len(result["graph_paths"]) > 5:
            print(f"  ... 还有 {len(result['graph_paths']) - 5} 条")

    # 证据源
    if result.get("evidence"):
        print(f"\n📎 原文证据 ({len(result['evidence'])} 条):")
        for e in result["evidence"][:3]:
            print(f"  [{e['source_doc'][:25]}] {e['snippet'][:80]}...")
        if len(result["evidence"]) > 3:
            print(f"  ... 还有 {len(result['evidence']) - 3} 条")

    # 涉及论文
    if result.get("source_papers"):
        print(f"\n📚 涉及论文 ({len(result['source_papers'])} 篇):")
        for p in result["source_papers"][:5]:
            print(f"  - {p[:40]}")
        if len(result["source_papers"]) > 5:
            print(f"  ... 还有 {len(result['source_papers']) - 5} 篇")

    if verbose:
        print(f"\n\n--- 原始上下文（调试）---")
        print(result.get("raw_context", "")[:500])
    print()


def main():
    engine = AnswerEngine()
    print("📚 绿色金融论文 RAG 问答系统 (混合检索: 向量+知识图谱)")
    print("  输入 'q' 退出, '--verbose' 显示调试信息")
    print()

    # 命令行参数模式
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        q = " ".join(a for a in sys.argv[1:] if not a.startswith("--"))
        verbose = "--verbose" in sys.argv
        t0 = time.time()
        result = engine.answer(q)
        elapsed = time.time() - t0
        print_result(result, verbose)
        print(f"⏱️  {elapsed:.1f}s")
        return

    # 交互模式
    while True:
        try:
            q = input("🔍 请输入问题: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n退出")
            break

        if not q:
            continue
        if q.lower() == "q":
            print("退出")
            break

        verbose = q.endswith(" --verbose")
        if verbose:
            q = q.replace(" --verbose", "").strip()

        t0 = time.time()
        try:
            result = engine.answer(q)
            elapsed = time.time() - t0
            print_result(result, verbose)
            print(f"⏱️  {elapsed:.1f}s")
        except Exception as e:
            print(f"❌ 错误: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()