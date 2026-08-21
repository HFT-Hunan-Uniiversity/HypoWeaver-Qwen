# ============================================================================
# 状态文件重建 — scripts/rebuild_status.py
# ============================================================================
# 从已有产出（cleaned/ + artifacts/kg/ + artifacts/vector/）重建
# processed_docs.json。用于换环境、状态文件丢失、首次 clone 后。
#
# 用法:
#   python scripts/rebuild_status.py
# ============================================================================

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.status import (
    rebuild_from_artifacts,
    STATUS_PATH,
)
from src.vector.store import _DEFAULT_STORE_PATH


def main():
    cleaned_dir = PROJECT_ROOT / "cleaned"
    kg_dir = PROJECT_ROOT / "artifacts" / "kg"
    vector_store = PROJECT_ROOT / _DEFAULT_STORE_PATH

    print("♻️  从已有产出重建状态文件")
    print(f"  cleaned/: {cleaned_dir}")
    print(f"  artifacts/kg/: {kg_dir}")
    print(f"  向量存储: {vector_store}")

    n = rebuild_from_artifacts(cleaned_dir, kg_dir, vector_store)
    print(f"✅ 重建完成: {n} 个 doc_id")
    print(f"  状态文件: {STATUS_PATH}")


if __name__ == "__main__":
    main()