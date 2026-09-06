from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent
RUNTIME_ENV_KEYS = (
    "DASHSCOPE_API_KEY",
    "QWEN_MODEL",
    "QWEN_BASE_URL",
    "RESEARCH_ENGINE_URL",
    "RESEARCH_ENGINE_TOKEN",
    "HYPOWEAVER_RUNTIME_CONFIG_PATH",
    "HYPOWEAVER_API_TOKEN",
    "KNOWLEDGE_SERVICE_URL",
    "KNOWLEDGE_SERVICE_TOKEN",
    "HYPOWEAVER_KNOWLEDGE_CATALOG_PATH",
    "HYPOWEAVER_KNOWLEDGE_CHUNK_CATALOG_PATH",
    "HYPOWEAVER_KNOWLEDGE_CLEANED_DIR",
    "HYPOWEAVER_KNOWLEDGE_METADATA_DIR",
    "HYPOWEAVER_KNOWLEDGE_DOCUMENT_REGISTRY_PATH",
    "HYPOWEAVER_KNOWLEDGE_VECTOR_PATH",
    "HYPOWEAVER_KNOWLEDGE_GRAPH_DIR",
    "HYPOWEAVER_KNOWLEDGE_MANIFEST_PATH",
    "HYPOWEAVER_KNOWLEDGE_CORPUS_SNAPSHOT_ID",
    "HYPOWEAVER_KNOWLEDGE_EMBEDDING_BACKEND",
    "HYPOWEAVER_KNOWLEDGE_EMBEDDING_MODEL",
    "HYPOWEAVER_KNOWLEDGE_EMBEDDING_REVISION",
)


def main() -> int:
    """Run the backend suite without inheriting live runtime credentials."""

    sys.path.insert(0, str(BACKEND_ROOT / "src"))
    for key in RUNTIME_ENV_KEYS:
        os.environ.pop(key, None)
    test_temp = BACKEND_ROOT.parent / ".test-tmp" / "system-temp"
    test_temp.mkdir(parents=True, exist_ok=True)
    os.environ["HYPOWEAVER_TEST_TMP"] = str(BACKEND_ROOT.parent / ".test-tmp")
    os.environ["TEMP"] = str(test_temp)
    os.environ["TMP"] = str(test_temp)
    tempfile.tempdir = str(test_temp)
    suite = unittest.defaultTestLoader.discover(
        str(BACKEND_ROOT / "tests"),
        pattern="test_*.py",
    )
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
