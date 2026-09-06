#!/usr/bin/env python3
"""Run deterministic query probes against a saved GreenFin vector index."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.reason.schema_gate import validate_instance  # noqa: E402
from src.retrieve.vector_index import LocalVectorIndex  # noqa: E402


RESULT_SCHEMA = ROOT / "schemas" / "retrieval_result.schema.json"


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", value.casefold()).strip("-") or "query"


def build_bundle(index_path: Path, config_path: Path, output_dir: Path) -> dict[str, Any]:
    index = LocalVectorIndex.load(index_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for query in config["queries"]:
        query_id = str(query["query_id"])
        response = index.search(
            str(query["text"]),
            top_k=int(query.get("top_k", 10)),
            min_score=query.get("min_score"),
            filters=query.get("filters"),
        )
        value = response.to_dict(include_text=False)
        errors = validate_instance(value, RESULT_SCHEMA)
        if errors:
            raise ValueError(f"{query_id}: retrieval result schema failed: {'; '.join(errors[:10])}")
        path = output_dir / f"{_safe_name(query_id)}.json"
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        entries.append(
            {
                "query_id": query_id,
                "purpose": query["purpose"],
                "query_text": query["text"],
                "query_hash": value["query_hash"],
                "result_count": len(value["results"]),
                "top_document_ids": [item["document_id"] for item in value["results"][:5]],
                "file": path.name,
                "file_sha256": _sha256_bytes(path.read_bytes()),
            }
        )
    material = {
        "index_snapshot_id": index.snapshot_id,
        "config_sha256": _sha256_bytes(config_path.read_bytes()),
        "queries": entries,
    }
    manifest = {
        "schema_version": "retrieval-probe-bundle/1.0.0",
        "bundle_id": f"retrieval-bundle:{_sha256_bytes(_canonical_json(material).encode('utf-8'))[:24]}",
        "index_snapshot_id": index.snapshot_id,
        "backend": index.manifest["embedding"],
        "purpose": (
            "Reproducible lexical-hashing baseline probes for chunk recall and evidence-location QA; "
            "not a semantic-model benchmark."
        ),
        "config_sha256": material["config_sha256"],
        "queries": entries,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = build_bundle(args.index, args.config, args.output_dir)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"WROTE: {args.output_dir} ({len(manifest['queries'])} query probes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
