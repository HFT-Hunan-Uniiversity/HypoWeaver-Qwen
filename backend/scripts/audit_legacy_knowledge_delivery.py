from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import h5py
import numpy as np


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT / "src"))

from hypoweaver.legacy_rag import LegacyChunkResolver  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_manifest(root: Path) -> int:
    manifest_path = root / "manifests" / "SHA256SUMS"
    checked = 0
    for line_number, line in enumerate(
        manifest_path.read_text(encoding="utf-8-sig").splitlines(),
        1,
    ):
        if not line.strip():
            continue
        try:
            expected, relative = line.split(maxsplit=1)
        except ValueError as error:
            raise ValueError(f"invalid SHA256SUMS line {line_number}") from error
        relative_path = Path(relative.strip())
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError(f"unsafe SHA256SUMS path: {relative}")
        path = (root / relative_path).resolve()
        if root.resolve() not in path.parents:
            raise ValueError(f"SHA256SUMS path escapes delivery root: {relative}")
        if not path.is_file():
            raise FileNotFoundError(f"manifested file is missing: {relative}")
        actual = _sha256(path)
        if actual != expected.casefold():
            raise ValueError(f"SHA-256 mismatch for {relative}: {actual}")
        checked += 1
    return checked


def _verify_model(root: Path, model_root: Path) -> dict[str, Any]:
    lines = (root / "manifests" / "model-SHA256.txt").read_text(
        encoding="utf-8-sig"
    ).splitlines()
    descriptors: dict[str, str] = {}
    checked = 0
    resolved_model_root = model_root.resolve()
    for line in lines:
        if line.startswith("huggingface_repo: ") or line.startswith("revision: "):
            key, value = line.split(": ", 1)
            descriptors[key] = value
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or len(parts[0]) != 64:
            continue
        expected, relative = parts
        relative_path = Path(relative.strip())
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError(f"unsafe model manifest path: {relative}")
        path = (resolved_model_root / relative_path).resolve()
        if resolved_model_root not in path.parents:
            raise ValueError(f"model manifest path escapes model root: {relative}")
        if not path.is_file():
            raise FileNotFoundError(f"model file is missing: {relative}")
        actual = _sha256(path)
        if actual != expected.casefold():
            raise ValueError(f"model SHA-256 mismatch for {relative}: {actual}")
        checked += 1
    return {
        "root": str(resolved_model_root),
        "files_verified": checked,
        **descriptors,
    }


def _declared_stats(root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for line in (root / "manifests" / "dataset-stats.txt").read_text(
        encoding="utf-8-sig"
    ).splitlines():
        if ": " not in line:
            continue
        key, value = line.split(": ", 1)
        if value.isdigit():
            result[key] = int(value)
        elif key == "doc_type_dist":
            result[key] = json.loads(value)
        else:
            result[key] = value
    return result


def _registry(path: Path) -> dict[str, dict[str, str | bool]]:
    records: dict[str, dict[str, str | bool]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not {"doc_id", "has_fulltext"}.issubset(reader.fieldnames or []):
            raise ValueError("doc_registry.csv requires doc_id and has_fulltext")
        for line_number, row in enumerate(reader, 2):
            document_id = str(row.get("doc_id") or "").strip()
            if not document_id or document_id in records:
                raise ValueError(f"invalid or duplicate registry row {line_number}")
            fulltext_value = str(row.get("has_fulltext") or "").strip().casefold()
            if fulltext_value not in {"true", "false"}:
                raise ValueError(f"invalid has_fulltext at registry row {line_number}")
            normalized: dict[str, str | bool] = {
                key: str(value or "").strip()
                for key, value in row.items()
                if key is not None
            }
            normalized["has_fulltext"] = fulltext_value == "true"
            records[document_id] = normalized
    return records


def _audit_vectors(
    root: Path,
    registry: dict[str, dict[str, str | bool]],
) -> dict[str, Any]:
    resolver = LegacyChunkResolver(
        root / "cleaned",
        root / "cleaned_meta",
        root / "manifests" / "doc_registry.csv",
    )
    levels: Counter[str] = Counter()
    document_vector_classes: Counter[str] = Counter()
    document_ids: set[str] = set()
    chunk_ids: set[str] = set()
    missing_registry: set[str] = set()
    missing_hydration: list[str] = []
    non_finite_vectors = 0
    zero_norm_vectors = 0
    vector_path = root / "all_store.h5"
    with h5py.File(vector_path, "r") as handle:
        if set(handle.keys()) != {"metas", "vectors"}:
            raise ValueError(f"unexpected HDF5 datasets: {sorted(handle.keys())}")
        vectors = handle["vectors"]
        metas = handle["metas"]
        if len(vectors.shape) != 2 or vectors.shape[0] != metas.shape[0]:
            raise ValueError("HDF5 vector/meta dimensions are inconsistent")
        for start in range(0, int(vectors.shape[0]), 4096):
            end = min(start + 4096, int(vectors.shape[0]))
            batch = np.asarray(vectors[start:end], dtype=np.float32)
            non_finite_vectors += int((~np.isfinite(batch)).any(axis=1).sum())
            zero_norm_vectors += int((np.linalg.norm(batch, axis=1) == 0).sum())
            for index in range(start, end):
                meta = json.loads(metas[index])
                document_id = str(meta.get("doc_id") or "")
                chunk_id = str(meta.get("chunk_id") or "")
                level = str(meta.get("chunk_level") or "unknown")
                if not document_id or not chunk_id:
                    raise ValueError(f"HDF5 metadata row {index} lacks identifiers")
                if chunk_id in chunk_ids:
                    raise ValueError(f"duplicate HDF5 chunk_id: {chunk_id}")
                chunk_ids.add(chunk_id)
                document_ids.add(document_id)
                levels[level] += 1
                registry_row = registry.get(document_id)
                if registry_row is None:
                    missing_registry.add(document_id)
                elif bool(registry_row["has_fulltext"]):
                    document_vector_classes["fulltext_document"] += 1
                    if level != "metadata":
                        document_vector_classes["evidence_capable_chunk"] += 1
                else:
                    document_vector_classes["metadata_only_document"] += 1
                if not resolver.resolve(meta):
                    missing_hydration.append(chunk_id)

        result = {
            "shape": [int(value) for value in vectors.shape],
            "dtype": str(vectors.dtype),
            "metadata_rows": int(metas.shape[0]),
            "unique_chunks": len(chunk_ids),
            "unique_documents": len(document_ids),
            "chunk_levels": dict(sorted(levels.items())),
            "document_vector_classes": dict(sorted(document_vector_classes.items())),
            "missing_registry_documents": sorted(missing_registry),
            "missing_hydration_chunks": missing_hydration[:20],
            "missing_hydration_count": len(missing_hydration),
            "non_finite_vector_rows": non_finite_vectors,
            "zero_norm_vector_rows": zero_norm_vectors,
        }
    if missing_registry or missing_hydration or non_finite_vectors or zero_norm_vectors:
        raise ValueError(f"HDF5 audit failed: {json.dumps(result, ensure_ascii=False)}")
    return result


def _audit_graph(root: Path) -> dict[str, int]:
    files = sorted((root / "kg").glob("*.kg.json"))
    nodes: set[tuple[str, str]] = set()
    edges: set[tuple[str, str]] = set()
    extracted_relation_rows = 0
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        document_id = str(payload.get("doc_id") or payload.get("paper", {}).get("doc_id") or "")
        paper_key = ("Paper", document_id)
        if not document_id or paper_key in nodes:
            raise ValueError(f"invalid or duplicate KG document: {path.name}")
        nodes.add(paper_key)
        entity_types = {
            "authors": "Author",
            "concepts": "Concept",
            "methods": "Method",
            "datasets": "Dataset",
        }
        for key, node_type in entity_types.items():
            values = payload.get(key, [])
            if not isinstance(values, list):
                raise ValueError(f"invalid KG {key} list: {path.name}")
            for value in values:
                name = str(value.get("name") or "").strip()
                if not name:
                    continue
                nodes.add((node_type, name))
                edges.add((f"Paper:{document_id}", f"{node_type}:{name}"))
        relations = payload.get("relations", [])
        if not isinstance(relations, list):
            raise ValueError(f"invalid KG relations list: {path.name}")
        extracted_relation_rows += len(relations)
        for relation in relations:
            source = str(relation.get("source") or "").strip()
            target = str(relation.get("target") or "").strip()
            if source and target:
                nodes.add(("Concept", source))
                nodes.add(("Concept", target))
                edges.add((f"Concept:{source}", f"Concept:{target}"))
    return {
        "documents": len(files),
        "nodes": len(nodes),
        "edges": len(edges),
        "extracted_relation_rows": extracted_relation_rows,
    }


def audit(root: Path, model_root: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    required = (
        root / "all_store.h5",
        root / "cleaned",
        root / "cleaned_meta",
        root / "kg",
        root / "manifests" / "doc_registry.csv",
        root / "manifests" / "SHA256SUMS",
    )
    for path in required:
        if not path.exists():
            raise FileNotFoundError(f"required delivery asset is missing: {path}")
    registry = _registry(root / "manifests" / "doc_registry.csv")
    registry_classes = Counter(
        "fulltext" if bool(row["has_fulltext"]) else "metadata_only"
        for row in registry.values()
    )
    vectors = _audit_vectors(root, registry)
    graph = _audit_graph(root)
    declared = _declared_stats(root)
    actual_counts = {
        "cleaned_md": len(list((root / "cleaned").glob("*.md"))),
        "cleaned_meta": len(list((root / "cleaned_meta").glob("*.json"))),
        "kg_json_files": graph["documents"],
        "fulltext_docs(has_fulltext=true)": registry_classes["fulltext"],
        "metadata_only_docs(has_fulltext=false)": registry_classes["metadata_only"],
        "vectors": vectors["metadata_rows"],
        "graph_nodes": graph["nodes"],
        "graph_edges": graph["edges"],
    }
    mismatches = {
        key: {"declared": declared.get(key), "actual": actual}
        for key, actual in actual_counts.items()
        if declared.get(key) != actual
    }
    if mismatches:
        raise ValueError(
            "delivery counts differ from dataset-stats.txt: "
            + json.dumps(mismatches, ensure_ascii=False, sort_keys=True)
        )
    result = {
        "delivery_root": str(root),
        "manifest_files_verified": _verify_manifest(root),
        "declared_counts_verified": actual_counts,
        "registry": {
            "documents": len(registry),
            **dict(sorted(registry_classes.items())),
        },
        "vectors": vectors,
        "graph": graph,
        "graph_policy": "candidate_only_not_scientific_evidence",
    }
    if model_root is not None:
        result["embedding_model"] = _verify_model(root, model_root)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit an extracted Aug-23 knowledge-data delivery read-only."
    )
    parser.add_argument("delivery_root", type=Path)
    parser.add_argument("--model-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.delivery_root, args.model_root)
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
