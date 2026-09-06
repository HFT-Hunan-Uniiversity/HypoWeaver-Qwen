#!/usr/bin/env python3
"""Build a deterministic formal source graph from aligned PaperProfiles."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.reason.build_research_graph import (
    build_graph_from_profiles,
    profile_set_sha256,
)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_object(value: object) -> str:
    return _sha256_bytes(_canonical_json(value).encode("utf-8"))


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value


def build_release(
    *,
    profiles_dir: Path,
    selection_path: Path,
    parsed_manifest_path: Path,
    metadata_manifest_path: Path,
    eligibility_audit_path: Path,
    vector_index_path: Path,
    output_graph: Path,
    output_manifest: Path,
    as_of: str,
    build_timestamp: str,
    coverage_certificate_id: str,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    profile_paths = sorted(profiles_dir.glob("PMC*.json"))
    if not profile_paths:
        raise ValueError(f"{profiles_dir}: no PMC*.json profiles")
    profiles = [_read_json(path) for path in profile_paths]
    selection = _read_json(selection_path)
    parsed = _read_json(parsed_manifest_path)
    metadata_manifest = _read_json(metadata_manifest_path)
    eligibility_audit = _read_json(eligibility_audit_path)
    vector_payload = _read_json(vector_index_path)
    vector_manifest = vector_payload.get("manifest")
    if not isinstance(vector_manifest, dict):
        raise ValueError(f"{vector_index_path}: no vector manifest")
    if parsed.get("document_count") != len(profiles):
        raise ValueError("parsed manifest document_count does not match profile count")
    if eligibility_audit.get("included_document_count") != len(profiles):
        raise ValueError("eligibility audit included count does not match profile count")
    if eligibility_audit.get("eligible_manifest_sha256") != parsed.get("source_manifest_sha256"):
        raise ValueError("parsed manifest is not bound to the audited eligible full-text manifest")
    if vector_manifest.get("chunk_count") != parsed.get("chunk_count"):
        raise ValueError("vector index chunk_count does not match parsed manifest")
    if vector_manifest.get("input_sha256") != parsed.get("chunks_sha256"):
        raise ValueError("vector index is not bound to the current parsed chunks")

    input_material = {
        "selection_sha256": _sha256_bytes(selection_path.read_bytes()),
        "parsed_manifest_sha256": _sha256_bytes(parsed_manifest_path.read_bytes()),
        "parsed_chunks_sha256": parsed["chunks_sha256"],
        "metadata_manifest_sha256": _sha256_bytes(metadata_manifest_path.read_bytes()),
        "eligibility_audit_sha256": _sha256_bytes(eligibility_audit_path.read_bytes()),
        "eligible_manifest_sha256": eligibility_audit["eligible_manifest_sha256"],
        "metadata_dataset_version": metadata_manifest.get("dataset_version"),
        "vector_snapshot_id": vector_manifest["snapshot_id"],
        "profile_set_sha256": profile_set_sha256(profiles),
    }
    input_manifest_hash = _sha256_object(input_material)
    scope = {
        "themes": [
            "green finance policy",
            "real environmental behavior",
            "carbon and pollution reduction",
            "digitalization and green innovation mechanisms",
        ],
        "languages": ["en"],
        "document_types": ["peer_reviewed_journal_article"],
        "year_start": min(int(profile["document"]["year"]) for profile in profiles),
        "year_end": max(int(profile["document"]["year"]) for profile in profiles),
    }
    config_hash = _sha256_object(
        {
            "scope": scope,
            "as_of": as_of,
            "builder": "source-graph-release/1.0.0",
        }
    )
    manifest: dict[str, Any] = {
        "schema_version": "0.1.0",
        "graph_id": "green-finance-decarbonization-research-graph",
        "as_of": as_of,
        "build_timestamp": build_timestamp,
        "scope": scope,
        "source_watermarks": {
            "fulltext_release": str(parsed["release_id"]),
            "parsed_chunks_sha256": str(parsed["chunks_sha256"]),
            "metadata_dataset_version": str(metadata_manifest.get("dataset_version") or "unknown"),
            "selection_schema_version": str(selection.get("schema_version") or "unknown"),
            "eligibility_audit": str(eligibility_audit.get("schema_version") or "unknown"),
            "eligible_manifest_sha256": str(eligibility_audit["eligible_manifest_sha256"]),
        },
        "input_manifest_hash": input_manifest_hash,
        "profile_set_sha256": profile_set_sha256(profiles),
        "base_snapshot_id": None,
        "base_graph_sha256": None,
        "coverage_certificate_id": coverage_certificate_id,
        "retrieval_index_snapshot_id": vector_manifest["snapshot_id"],
        "pipeline_run_id": f"run:source-graph:{input_manifest_hash[:24]}",
        "code_version": "source-graph-release/1.0.0",
        "config_hash": config_hash,
        "notes": (
            f"Formal source graph for a purposively selected {len(profiles)}-paper eligibility-gated deep corpus. "
            "Absence, trend and gap claims remain corpus-bounded."
        ),
    }
    graph, warnings = build_graph_from_profiles(profiles, manifest=manifest)
    output_manifest.parent.mkdir(parents=True, exist_ok=True)
    output_graph.parent.mkdir(parents=True, exist_ok=True)
    output_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    output_graph.write_text(
        json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return graph, manifest, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles-dir", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--parsed-manifest", type=Path, required=True)
    parser.add_argument("--metadata-manifest", type=Path, required=True)
    parser.add_argument("--eligibility-audit", type=Path, required=True)
    parser.add_argument("--vector-index", type=Path, required=True)
    parser.add_argument("--output-graph", type=Path, required=True)
    parser.add_argument("--output-manifest", type=Path, required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--build-timestamp", required=True)
    parser.add_argument("--coverage-certificate-id", required=True)
    args = parser.parse_args()
    try:
        graph, _manifest, warnings = build_release(
            profiles_dir=args.profiles_dir,
            selection_path=args.selection,
            parsed_manifest_path=args.parsed_manifest,
            metadata_manifest_path=args.metadata_manifest,
            eligibility_audit_path=args.eligibility_audit,
            vector_index_path=args.vector_index,
            output_graph=args.output_graph,
            output_manifest=args.output_manifest,
            as_of=args.as_of,
            build_timestamp=args.build_timestamp,
            coverage_certificate_id=args.coverage_certificate_id,
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1
    for warning in warnings:
        print(f"WARNING: {warning}")
    print(
        f"WROTE: {args.output_graph} ({len(graph['nodes'])} nodes, "
        f"{len(graph['edges'])} edges, {len(graph['evidence'])} evidence)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
