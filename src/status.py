# ============================================================================
# 统一状态管理 — src/status.py
# ============================================================================
# processed_docs.json 的读-改-写工具。
#
# 设计：
#   - 单文件追踪所有 doc_id 的处理状态（kg / vector 两阶段）
#   - 每步完成后立即更新，确保中断不丢失进度
#   - 不进 Git，是运行时产物
#   - 读-改-写模式：读取完整 JSON → 内存修改 → 写回整个文件
#
# 状态值:
#   kg:     pending / done / failed
#   vector: pending / done / failed
# ============================================================================

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATUS_DIR = PROJECT_ROOT / "artifacts" / "status"
STATUS_PATH = STATUS_DIR / "processed_docs.json"


def _ensure_dir() -> None:
    """确保状态目录存在。"""
    STATUS_DIR.mkdir(parents=True, exist_ok=True)


def load_status() -> Dict[str, dict]:
    """加载全部状态记录。"""
    _ensure_dir()
    try:
        return json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_status(status: Dict[str, dict]) -> None:
    """写回状态文件。"""
    _ensure_dir()
    STATUS_PATH.write_text(
        json.dumps(status, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _now() -> str:
    """返回 ISO 时间戳。"""
    return datetime.now(timezone.utc).isoformat()


def mark_kg_done(doc_id: str) -> None:
    """标记一篇文档的 KG 抽取完成。"""
    status = load_status()
    entry = status.setdefault(doc_id, {})
    entry["kg"] = "done"
    entry["updated_at"] = _now()
    save_status(status)


def mark_kg_failed(doc_id: str, error: str, stage: str = "extract") -> None:
    """标记一篇文档的 KG 抽取失败。"""
    status = load_status()
    entry = status.setdefault(doc_id, {})
    entry["kg"] = "failed"
    entry["error"] = str(error)[:500]
    entry["stage"] = stage
    entry["updated_at"] = _now()
    save_status(status)


def mark_vector_done(doc_id: str) -> None:
    """标记一篇文档的向量化完成。"""
    status = load_status()
    entry = status.setdefault(doc_id, {})
    entry["vector"] = "done"
    entry["updated_at"] = _now()
    save_status(status)


def mark_vector_failed(doc_id: str, error: str) -> None:
    """标记一篇文档的向量化失败。"""
    status = load_status()
    entry = status.setdefault(doc_id, {})
    entry["vector"] = "failed"
    entry["error"] = str(error)[:500]
    entry["stage"] = "vectorize"
    entry["updated_at"] = _now()
    save_status(status)


def mark_kg_pending(doc_id: str) -> None:
    """标记文档已解析完成，KG 待处理。

    parse_all.py 在解析完一篇文档后调用，确保 processed_docs.json 里有该 doc_id。
    """
    status = load_status()
    entry = status.setdefault(doc_id, {})
    if entry.get("kg") != "done":
        entry["kg"] = "pending"
    save_status(status)


def get_pending_kg_docs(all_doc_ids: list) -> list:
    """返回尚未完成 KG 抽取的 doc_id 列表。"""
    status = load_status()
    return [
        d for d in all_doc_ids
        if status.get(d, {}).get("kg") != "done"
    ]


def get_pending_vector_docs(all_doc_ids: list) -> list:
    """返回尚未完成向量化的 doc_id 列表。"""
    status = load_status()
    return [
        d for d in all_doc_ids
        if status.get(d, {}).get("vector") != "done"
    ]


def get_failed_docs() -> list:
    """返回所有失败的 doc_id 列表。"""
    status = load_status()
    return [
        d for d, v in status.items()
        if v.get("kg") == "failed" or v.get("vector") == "failed"
    ]


def get_stats() -> dict:
    """返回处理统计（用于报告）。"""
    status = load_status()
    total = len(status)
    kg_done = sum(1 for v in status.values() if v.get("kg") == "done")
    kg_failed = sum(1 for v in status.values() if v.get("kg") == "failed")
    vector_done = sum(1 for v in status.values() if v.get("vector") == "done")
    vector_failed = sum(1 for v in status.values() if v.get("vector") == "failed")
    return {
        "total": total,
        "kg_done": kg_done,
        "kg_failed": kg_failed,
        "vector_done": vector_done,
        "vector_failed": vector_failed,
        "pending": total - kg_done,
    }


def rebuild_from_artifacts(cleaned_dir: Path, kg_dir: Path, vector_store_path: Path) -> int:
    """从已有产出重建状态文件。

    参数:
      cleaned_dir: cleaned/*.md 目录
      kg_dir:      artifacts/kg/ 目录
      vector_store_path: hdf5 向量存储路径

    返回重建的 doc_id 数。
    """
    import h5py
    import numpy as np

    # 扫描 cleaned md
    all_doc_ids = sorted(p.stem for p in cleaned_dir.glob("*.md"))

    # 已完成的 KG
    kg_done = set()
    if kg_dir.exists():
        for f in kg_dir.glob("*.kg.json"):
            kg_done.add(f.stem.replace(".kg", ""))

    # 已完成的向量化
    vector_done = set()
    if vector_store_path.exists():
        try:
            with h5py.File(str(vector_store_path), "r") as f:
                if "metas" in f:
                    metas = f["metas"][:]
                    for m in metas:
                        try:
                            meta = json.loads(m)
                            did = meta.get("doc_id", "")
                            if did:
                                vector_done.add(did)
                        except (json.JSONDecodeError, TypeError):
                            pass
        except (OSError, KeyError):
            pass

    # 重建状态
    status = {}
    for doc_id in all_doc_ids:
        entry = {"updated_at": None}
        if doc_id in kg_done:
            entry["kg"] = "done"
        if doc_id in vector_done:
            entry["vector"] = "done"
        # 检查失败清单
        failed_path = kg_dir / "failed_docs.jsonl"
        if failed_path.exists():
            try:
                for line in failed_path.read_text(encoding="utf-8").strip().split("\n"):
                    if not line.strip():
                        continue
                    failed = json.loads(line)
                    if failed.get("doc_id") == doc_id:
                        entry["kg"] = "failed"
                        entry["error"] = failed.get("error", "unknown")
            except (json.JSONDecodeError, OSError):
                pass
        status[doc_id] = entry

    save_status(status)
    return len(status)


if __name__ == "__main__":
    # 冒烟测试
    print(f"状态文件: {STATUS_PATH}")
    stats = get_stats()
    print(f"统计: {stats}")
    print("✅ 状态模块正常")