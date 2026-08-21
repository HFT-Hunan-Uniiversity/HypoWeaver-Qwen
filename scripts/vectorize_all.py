# ============================================================================
# 全量向量化批处理 — scripts/vectorize_all.py
# ============================================================================
# 遍历 cleaned/ 全部 md，切片 → BGE 嵌入 → hdf5 存储。
#
# 功能:
#   - 断点续跑: 已向量化的 doc_id 跳过（状态记录在 processed_docs.json）
#   - 后端切换: get_store() 工厂（本地 hdf5 / 云上 qdrant）
#   - jsonl 结构化日志
#   - 分批中间报告（每 50 篇一个快照）
#
# 用法:
#   python scripts/vectorize_all.py
#   python scripts/vectorize_all.py --mode full
#   python scripts/vectorize_all.py --mode retry_failed
# ============================================================================

from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.embedding import get_embedder
from src.retrieve.chunker import chunk_markdown
from src.vector.store import get_store
from src.kg.pipeline import load_meta
from src.status import (
    load_status,
    save_status,
    get_pending_vector_docs,
)

# 路径
STORE = get_store()  # 通过工厂创建，不锁定具体后端
REPORT_PATH = PROJECT_ROOT / "artifacts" / "vector" / "batch_report.json"
ARTIFACT_DIR = PROJECT_ROOT / "artifacts" / "vector"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

# 分批报告阈值
BATCH_REPORT_EVERY = 50


# ============================================================================
# 结构化日志（jsonl）
# ============================================================================
def _append_log(event: str, **kwargs) -> None:
    """追加一条结构化日志到 logs/vector_YYYY-MM-DD.jsonl。"""
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"vector_{datetime.date.today().isoformat()}.jsonl"
    entry = {"time": datetime.datetime.now().isoformat(), "event": event, **kwargs}
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


# ============================================================================
# 状态快照（分批报告）
# ============================================================================
def _write_batch_report(report: dict) -> None:
    """写出当前批处理快照到 batch_report_*.json。"""
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    path = PROJECT_ROOT / "artifacts" / "vector" / f"batch_report_{timestamp}.json"
    try:
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def main():
    parser = argparse.ArgumentParser(description="全量向量化批处理")
    parser.add_argument("--mode", choices=["incremental", "full", "retry_failed"],
                        default="incremental", help="运行模式")
    parser.add_argument("--max", type=int, default=None, help="最多处理篇数")
    args = parser.parse_args()

    # 收集待处理文档对
    pairs: List[Tuple[str, Path]] = []
    for md_path in sorted((PROJECT_ROOT / "cleaned").glob("*.md")):
        doc_id = md_path.stem
        meta_path = PROJECT_ROOT / "cleaned_meta" / f"{doc_id}.json"
        if not meta_path.exists():
            continue
        pairs.append((doc_id, md_path))

    if not pairs:
        print("⚠️  cleaned/ 为空，无待向量化文档")
        return

    # 按模式过滤
    status = load_status()
    if args.mode == "full":
        pass  # 全量处理所有
    elif args.mode == "retry_failed":
        pairs = [
            (d, p) for d, p in pairs
            if status.get(d, {}).get("vector") == "failed"
        ]
        print(f"🔄 重试失败: {len(pairs)} 篇")
    else:  # incremental
        pending = set(get_pending_vector_docs([d for d, _ in pairs]))
        pairs = [(d, p) for d, p in pairs if d in pending]
        print(f"📂 待向量化: {len(pairs)} 篇 (断点续跑)")

    if args.max:
        pairs = pairs[:args.max]

    if not pairs:
        print("✅ 全部已完成，无需处理")
        return

    # 载入模型
    embedder = get_embedder()
    embedder._load()

    # 打开存储（工厂）
    store = STORE
    try:
        store.open()
    except Exception as e:
        print(f"❌ 打开向量存储失败: {e}")
        return
    print(f"  当前存储已有 {store.count()} 条向量\n")

    total_chunks = 0
    total_vectors = 0
    failed: List[str] = []
    t_start = time.time()

    report = {
        "mode": args.mode,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_docs": len(pairs),
        "success": 0,
        "failed": [],
        "total_chunks": 0,
        "total_vectors": 0,
        "elapsed_s": 0,
    }

    for i, (doc_id, md_path) in enumerate(pairs, 1):
        print(f"[{i}/{len(pairs)}] 📄 {doc_id[:50]}")
        t0 = time.time()

        try:
            # 元数据
            meta = load_meta(PROJECT_ROOT / "cleaned_meta" / f"{doc_id}.json")
            if "_error" in meta:
                raise RuntimeError(meta["_error"])

            # 正文
            md_text = md_path.read_text(encoding="utf-8")
            title = meta.get("title") or doc_id

            # 切片
            chunks = chunk_markdown(doc_id, md_text, {"title": title, "source_type": "paper"})
            if not chunks:
                raise RuntimeError("切片为空")

            # 嵌入
            texts = [c.chunk_text for c in chunks]
            vectors = embedder.embed_texts(texts, batch_size=32)

            # 元数据
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

            # 写入
            store.add(vectors, metadatas)
            total_chunks += len(chunks)
            total_vectors += len(vectors)

            # 标记完成（读-改-写）
            st = load_status()
            entry = st.setdefault(doc_id, {})
            entry["vector"] = "done"
            entry["updated_at"] = datetime.datetime.now().isoformat()
            save_status(st)

            elapsed = time.time() - t0
            print(f"  ✅ {len(chunks)} chunks → {len(vectors)} 向量 ({elapsed:.0f}s)")
            _append_log("vector_done", doc_id=doc_id, chunks=len(chunks),
                        vectors=len(vectors), elapsed_s=round(elapsed, 1))

        except Exception as e:
            elapsed = time.time() - t0
            print(f"  ❌ 失败: {e} ({elapsed:.0f}s)")
            failed.append(doc_id)
            # 标记失败
            st = load_status()
            entry = st.setdefault(doc_id, {})
            entry["vector"] = "failed"
            entry["error"] = str(e)[:500]
            save_status(st)
            _append_log("vector_failed", doc_id=doc_id, error=str(e)[:200])

        # 分批中间报告
        if i % BATCH_REPORT_EVERY == 0:
            report["success"] = i - len(failed)
            report["failed"] = failed
            report["total_chunks"] = total_chunks
            report["total_vectors"] = total_vectors
            report["elapsed_s"] = round(time.time() - t_start, 1)
            _write_batch_report(report)
            print(f"  📊 中间报告已写: 成功 {i - len(failed)} / 失败 {len(failed)}")

    store.close()
    t_total = time.time() - t_start

    # 最终报告
    report["success"] = len(pairs) - len(failed)
    report["failed"] = failed
    report["total_chunks"] = total_chunks
    report["total_vectors"] = total_vectors
    report["elapsed_s"] = round(t_total, 1)
    report["store_backend"] = type(STORE).__name__
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"✅ 完成: 成功 {report['success']} / 失败 {len(failed)}")
    print(f"   总向量: {total_vectors} 条")
    print(f"   总耗时: {t_total:.0f}s")
    print(f"   后端: {type(STORE).__name__}")
    if failed:
        print(f"   失败: {failed}")
    print(f"   报告: {REPORT_PATH}")


if __name__ == "__main__":
    sys.exit(main())