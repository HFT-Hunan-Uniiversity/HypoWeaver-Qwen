"""Draft 2020-12 JSON Schema gate used by the graph pipeline.

The semantic validator checks graph-specific invariants.  This module checks the
machine contract first so missing fields, unknown properties, invalid enums and
date formats cannot slip through to semantic validation.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError as exc:  # pragma: no cover - exercised only in a broken environment
    Draft202012Validator = None  # type: ignore[assignment]
    FormatChecker = None  # type: ignore[assignment]
    _IMPORT_ERROR: ImportError | None = exc
else:
    _IMPORT_ERROR = None


ROOT = Path(__file__).resolve().parents[2]
PROFILE_SCHEMA_PATH = ROOT / "schemas" / "paper_profile.graph_input.schema.json"
GRAPH_SCHEMA_PATH = ROOT / "schemas" / "research_graph.schema.json"
GRAPH_BUILD_MANIFEST_SCHEMA_PATH = ROOT / "schemas" / "graph_build_manifest.schema.json"


@lru_cache(maxsize=16)
def _load_schema(schema_path: str) -> dict[str, Any]:
    return json.loads(Path(schema_path).read_text(encoding="utf-8"))


def _format_path(parts: list[object]) -> str:
    path = "$"
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        else:
            path += f".{part}"
    return path


def validate_instance(instance: Any, schema_path: Path) -> list[str]:
    """Return deterministic, human-readable JSON Schema errors."""

    if Draft202012Validator is None or FormatChecker is None:
        raise RuntimeError(
            "jsonschema is required for the release gate; install requirements.txt"
        ) from _IMPORT_ERROR

    schema = _load_schema(str(schema_path.resolve()))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(
        validator.iter_errors(instance),
        key=lambda item: (_format_path(list(item.absolute_path)), item.message),
    )
    return [f"{_format_path(list(item.absolute_path))}: {item.message}" for item in errors]


def require_valid_instance(instance: Any, schema_path: Path, label: str) -> None:
    errors = validate_instance(instance, schema_path)
    if not errors:
        return
    preview = "\n".join(f"- {error}" for error in errors[:20])
    suffix = "" if len(errors) <= 20 else f"\n- ... {len(errors) - 20} more error(s)"
    raise ValueError(f"{label} failed JSON Schema validation:\n{preview}{suffix}")
