from __future__ import annotations

import os
import sys
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
)


def main() -> int:
    """Run the backend suite without inheriting live runtime credentials."""

    sys.path.insert(0, str(BACKEND_ROOT / "src"))
    for key in RUNTIME_ENV_KEYS:
        os.environ.pop(key, None)
    suite = unittest.defaultTestLoader.discover(
        str(BACKEND_ROOT / "tests"),
        pattern="test_*.py",
    )
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
