"""Build and search a small, dependency-free vector index over ``chunks.jsonl``.

The default embedding backend uses deterministic signed feature hashing.  It is
not intended to replace a learned embedding model, but it provides an offline
baseline with the same interface a future Qwen embedding adapter can implement.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Mapping, Protocol, Sequence, runtime_checkable
import unicodedata


INDEX_SCHEMA_VERSION = "greenfin-vector-index/1.0.0"
RESULT_SCHEMA_VERSION = "greenfin-retrieval-result/1.0.0"
CHUNK_ID_POLICY = "preserve-or-document-text-locator-sha256-v2"
_ASCII_TOKEN = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*")
_CJK_RUN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_FILTER_FIELDS = ("document_id", "source_type", "access_level")


@runtime_checkable
class EmbeddingBackend(Protocol):
    """Pluggable text embedding contract.

    A Qwen adapter only needs to expose these four metadata attributes and two
    methods.  Network/authentication concerns remain outside this module.
    """

    backend_id: str
    model_id: str
    algorithm: str
    dimensions: int

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed document texts in input order."""

    def embed_query(self, text: str) -> list[float]:
        """Embed one query in the same vector space as the documents."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).casefold()).strip()


def _features(text: str) -> list[str]:
    """Return language-agnostic lexical features for the offline baseline."""

    normalized = _normalize_text(text)
    words = _ASCII_TOKEN.findall(normalized)
    features = [f"w:{word}" for word in words]
    features.extend(f"w2:{left}_{right}" for left, right in zip(words, words[1:]))
    for run in _CJK_RUN.findall(normalized):
        features.extend(f"c:{char}" for char in run)
        features.extend(f"c2:{run[index:index + 2]}" for index in range(len(run) - 1))
    return features


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


@dataclass(frozen=True)
class HashingEmbeddingBackend:
    """Deterministic, local signed-feature-hashing embeddings."""

    dimensions: int = 384
    backend_id: str = "offline-hashing"
    model_id: str = "greenfin-lexical-hashing-v1"
    algorithm: str = "signed-feature-hashing-logtf-v1"

    def __post_init__(self) -> None:
        if self.dimensions < 32:
            raise ValueError("dimensions must be at least 32")

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for feature, count in Counter(_features(text)).items():
            digest = hashlib.sha256(feature.encode("utf-8")).digest()
            index = int.from_bytes(digest[:8], "big") % self.dimensions
            sign = 1.0 if digest[8] & 1 else -1.0
            vector[index] += sign * (1.0 + math.log(count))
        return _l2_normalize(vector)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


@dataclass(frozen=True)
class ChunkRecord:
    chunk_id: str
    document_id: str
    evidence_id: str
    text: str
    content_hash: str
    text_sha256: str
    content_sha256: str | None
    locator: dict[str, Any]
    release_id: str | None = None
    asset_id: str | None = None
    document_version: str | None = None
    access_level: str | None = None
    license: str | None = None
    source_type: str | None = None

    def to_dict(self, *, include_text: bool = True) -> dict[str, Any]:
        value = {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "evidence_id": self.evidence_id,
            "content_hash": self.content_hash,
            "text_sha256": self.text_sha256,
            "content_sha256": self.content_sha256,
            "locator": self.locator,
            "release_id": self.release_id,
            "asset_id": self.asset_id,
            "document_version": self.document_version,
            "access_level": self.access_level,
            "license": self.license,
            "source_type": self.source_type,
        }
        if include_text:
            value["text"] = self.text
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ChunkRecord":
        location = "index record"
        content_hash = _optional_sha256(value, "content_hash", location=location)
        text_sha256 = _optional_sha256(value, "text_sha256", location=location)
        if content_hash is None and text_sha256 is None:
            raise ValueError(f"{location}: content_hash or text_sha256 is required")
        if content_hash is not None and text_sha256 is not None and content_hash != text_sha256:
            raise ValueError(f"{location}: content_hash and text_sha256 must match")
        canonical_text_hash = text_sha256 or content_hash
        assert canonical_text_hash is not None
        text = str(value.get("text") or "")
        if text and _sha256_text(text) != canonical_text_hash:
            raise ValueError(f"{location}: text_sha256 does not match text")
        return cls(
            chunk_id=str(value["chunk_id"]),
            document_id=str(value["document_id"]),
            evidence_id=str(value["evidence_id"]),
            text=text,
            content_hash=canonical_text_hash,
            text_sha256=canonical_text_hash,
            content_sha256=_optional_sha256(value, "content_sha256", location=location),
            locator=dict(value.get("locator") or {}),
            release_id=_optional_string(value, "release_id"),
            asset_id=_optional_string(value, "asset_id"),
            document_version=_optional_string(value, "document_version"),
            access_level=_optional_string(value, "access_level"),
            license=_optional_string(value, "license"),
            source_type=_optional_string(value, "source_type"),
        )


@dataclass(frozen=True)
class SearchResult:
    chunk_id: str
    document_id: str
    evidence_id: str
    score: float
    rank: int
    locator: dict[str, Any]
    text: str
    release_id: str | None = None
    asset_id: str | None = None
    document_version: str | None = None
    content_hash: str | None = None
    content_sha256: str | None = None
    text_sha256: str | None = None
    access_level: str | None = None
    license: str | None = None
    source_type: str | None = None

    def to_dict(self, *, include_text: bool = False) -> dict[str, Any]:
        value: dict[str, Any] = {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "evidence_id": self.evidence_id,
            "score": self.score,
            "rank": self.rank,
            "locator": self.locator,
            "release_id": self.release_id,
            "asset_id": self.asset_id,
            "document_version": self.document_version,
            "content_hash": self.content_hash,
            "content_sha256": self.content_sha256,
            "text_sha256": self.text_sha256,
            "access_level": self.access_level,
            "license": self.license,
            "source_type": self.source_type,
        }
        if include_text and self.access_level == "open" and self.text:
            value["text"] = self.text
        elif include_text and self.access_level != "open":
            value["text_redacted"] = True
        return value


@dataclass(frozen=True)
class SearchResponse:
    index_snapshot_id: str
    query_hash: str
    filters: dict[str, list[str]]
    results: list[SearchResult]
    schema_version: str = RESULT_SCHEMA_VERSION

    def to_dict(self, *, include_text: bool = False) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "index_snapshot_id": self.index_snapshot_id,
            "query_hash": self.query_hash,
            "filter": self.filters,
            "results": [result.to_dict(include_text=include_text) for result in self.results],
        }


def _require_text(value: dict[str, Any], field: str, *, location: str) -> str:
    raw = value.get(field)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{location}: {field} must be a non-empty string")
    return raw.strip()


def _optional_string(value: Mapping[str, Any], field: str, *, location: str = "record") -> str | None:
    raw = value.get(field)
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{location}: {field} must be a non-empty string or null")
    return raw.strip()


def _optional_sha256(value: Mapping[str, Any], field: str, *, location: str) -> str | None:
    raw = _optional_string(value, field, location=location)
    if raw is None:
        return None
    normalized = raw.casefold()
    if not _SHA256.fullmatch(normalized):
        raise ValueError(f"{location}: {field} must be a 64-character hexadecimal SHA-256")
    return normalized


def _chunk_locator(value: dict[str, Any]) -> dict[str, Any]:
    raw_locator = value.get("locator")
    locator = dict(raw_locator) if isinstance(raw_locator, dict) else {}
    aliases = {
        "source_locator": value.get("source_locator"),
        "section": value.get("section"),
        "page": value.get("page"),
        "start_char": value.get("start_char", value.get("block_char_start")),
        "end_char": value.get("end_char", value.get("block_char_end")),
        "source_block_ids": value.get("source_block_ids"),
    }
    for key, item in aliases.items():
        if key not in locator and item is not None:
            locator[key] = item
    return locator


def _record_from_json(value: dict[str, Any], *, location: str) -> ChunkRecord:
    document_id = _require_text(value, "document_id", location=location)
    text = _require_text(value, "text", location=location)
    locator = _chunk_locator(value)
    actual_text_sha256 = _sha256_text(text)
    legacy_content_hash = _optional_sha256(value, "content_hash", location=location)
    supplied_text_sha256 = _optional_sha256(value, "text_sha256", location=location)
    content_sha256 = _optional_sha256(value, "content_sha256", location=location)
    for field, supplied in (
        ("content_hash", legacy_content_hash),
        ("text_sha256", supplied_text_sha256),
    ):
        if supplied is not None and supplied != actual_text_sha256:
            raise ValueError(f"{location}: {field} does not match text")
    if legacy_content_hash is not None and supplied_text_sha256 is not None:
        if legacy_content_hash != supplied_text_sha256:
            raise ValueError(f"{location}: content_hash and text_sha256 must match")
    # ``content_hash`` is retained as a backward-compatible alias for the
    # canonical chunk-text hash.  ``content_sha256`` is the optional upstream
    # asset/document-byte hash and therefore cannot be recomputed from a chunk.
    text_sha256 = actual_text_sha256
    content_hash = text_sha256

    raw_chunk_id = value.get("chunk_id")
    if isinstance(raw_chunk_id, str) and raw_chunk_id.strip():
        chunk_id = raw_chunk_id.strip()
    else:
        material = {
            "document_id": document_id,
            "document_version": _optional_string(value, "document_version", location=location),
            "text_sha256": text_sha256,
            "locator": locator,
        }
        chunk_id = f"chk_{_sha256_text(_canonical_json(material))[:20]}"

    raw_evidence_id = value.get("evidence_id")
    evidence_id = (
        raw_evidence_id.strip()
        if isinstance(raw_evidence_id, str) and raw_evidence_id.strip()
        else f"evd_{_sha256_text(chunk_id)[:20]}"
    )
    return ChunkRecord(
        chunk_id=chunk_id,
        document_id=document_id,
        evidence_id=evidence_id,
        text=text,
        content_hash=content_hash,
        text_sha256=text_sha256,
        content_sha256=content_sha256,
        locator=locator,
        release_id=_optional_string(value, "release_id", location=location),
        asset_id=_optional_string(value, "asset_id", location=location),
        document_version=_optional_string(value, "document_version", location=location),
        access_level=_optional_string(value, "access_level", location=location),
        license=_optional_string(value, "license", location=location),
        source_type=_optional_string(value, "source_type", location=location),
    )


def read_chunks_jsonl(path: Path | str) -> tuple[list[ChunkRecord], str]:
    """Read and validate chunks, returning records and the input SHA-256."""

    source = Path(path)
    raw = source.read_bytes()
    records: list[ChunkRecord] = []
    seen_ids: set[str] = set()
    for line_number, line in enumerate(raw.decode("utf-8-sig").splitlines(), start=1):
        if not line.strip():
            continue
        location = f"{source}:{line_number}"
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{location}: invalid JSON: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{location}: each JSONL record must be an object")
        record = _record_from_json(value, location=location)
        if record.chunk_id in seen_ids:
            raise ValueError(f"{location}: duplicate chunk_id {record.chunk_id}")
        seen_ids.add(record.chunk_id)
        records.append(record)
    if not records:
        raise ValueError(f"{source}: no chunk records found")
    return records, _sha256_bytes(raw)


def _backend_descriptor(backend: EmbeddingBackend) -> dict[str, Any]:
    descriptor = {
        "backend_id": backend.backend_id,
        "model_id": backend.model_id,
        "algorithm": backend.algorithm,
        "dimensions": backend.dimensions,
    }
    if not all(isinstance(descriptor[key], str) and descriptor[key] for key in ("backend_id", "model_id", "algorithm")):
        raise ValueError("embedding backend metadata must be non-empty strings")
    if not isinstance(descriptor["dimensions"], int) or descriptor["dimensions"] < 1:
        raise ValueError("embedding backend dimensions must be a positive integer")
    return descriptor


def _validate_vectors(vectors: Sequence[Sequence[float]], count: int, dimensions: int) -> list[list[float]]:
    if len(vectors) != count:
        raise ValueError(f"embedding backend returned {len(vectors)} vectors for {count} records")
    normalized: list[list[float]] = []
    for position, vector in enumerate(vectors):
        if len(vector) != dimensions:
            raise ValueError(f"vector {position} has {len(vector)} dimensions; expected {dimensions}")
        converted = [float(value) for value in vector]
        if not all(math.isfinite(value) for value in converted):
            raise ValueError(f"vector {position} contains a non-finite value")
        normalized.append(converted)
    return normalized


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("vectors must have the same dimensions")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


def _normalize_filters(
    filters: Mapping[str, str | Sequence[str] | None] | None,
) -> dict[str, list[str]]:
    if filters is None:
        return {}
    unknown = sorted(set(filters) - set(_FILTER_FIELDS))
    if unknown:
        raise ValueError(f"unsupported search filter(s): {', '.join(unknown)}")
    normalized: dict[str, list[str]] = {}
    for field in _FILTER_FIELDS:
        if field not in filters or filters[field] is None:
            continue
        raw = filters[field]
        items = [raw] if isinstance(raw, str) else list(raw)
        values: list[str] = []
        for item in items:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(f"search filter {field} values must be non-empty strings")
            candidate = item.strip()
            if candidate not in values:
                values.append(candidate)
        if values:
            normalized[field] = sorted(values)
    return normalized


def _matches_filters(record: ChunkRecord, filters: Mapping[str, Sequence[str]]) -> bool:
    for field, allowed in filters.items():
        value = getattr(record, field)
        candidate = value if value is not None else "unknown"
        if candidate not in allowed:
            return False
    return True


class LocalVectorIndex:
    """In-memory searchable index with a portable JSON representation."""

    def __init__(
        self,
        *,
        manifest: dict[str, Any],
        records: Sequence[ChunkRecord],
        vectors: Sequence[Sequence[float]],
        backend: EmbeddingBackend,
    ) -> None:
        self.manifest = dict(manifest)
        self.records = list(records)
        self.backend = backend
        descriptor = _backend_descriptor(backend)
        expected = self.manifest.get("embedding")
        if expected != descriptor:
            raise ValueError(f"embedding backend does not match index manifest: expected {expected}, got {descriptor}")
        self.vectors = _validate_vectors(vectors, len(self.records), descriptor["dimensions"])

    @property
    def snapshot_id(self) -> str:
        return str(self.manifest["snapshot_id"])

    def save(self, path: Path | str) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "manifest": self.manifest,
            # Absence of a positive ``open`` designation is treated as
            # restricted.  Vectors can still be sensitive and the index file
            # remains subject to the source access policy.
            "records": [
                record.to_dict(include_text=record.access_level == "open")
                for record in self.records
            ],
            "vectors": self.vectors,
        }
        target.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path | str, *, backend: EmbeddingBackend | None = None) -> "LocalVectorIndex":
        source = Path(path)
        value = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("manifest"), dict):
            raise ValueError(f"{source}: invalid vector index payload")
        manifest = dict(value["manifest"])
        descriptor = manifest.get("embedding")
        if not isinstance(descriptor, dict):
            raise ValueError(f"{source}: missing embedding manifest")
        if backend is None:
            if descriptor.get("backend_id") != "offline-hashing":
                raise ValueError("a matching embedding backend is required to load this index")
            backend = HashingEmbeddingBackend(dimensions=int(descriptor["dimensions"]))
        records_raw = value.get("records")
        vectors = value.get("vectors")
        if not isinstance(records_raw, list) or not isinstance(vectors, list):
            raise ValueError(f"{source}: records and vectors must be arrays")
        records = [ChunkRecord.from_dict(item) for item in records_raw]
        return cls(manifest=manifest, records=records, vectors=vectors, backend=backend)

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        min_score: float | None = None,
        filters: Mapping[str, str | Sequence[str] | None] | None = None,
    ) -> SearchResponse:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        normalized_filters = _normalize_filters(filters)
        descriptor = _backend_descriptor(self.backend)
        query_vector = _validate_vectors([self.backend.embed_query(query)], 1, descriptor["dimensions"])[0]
        if not any(query_vector):
            raise ValueError("query produced an empty vector")
        scored = [
            (cosine_similarity(query_vector, vector), record)
            for record, vector in zip(self.records, self.vectors)
            if _matches_filters(record, normalized_filters)
        ]
        scored.sort(key=lambda item: (-item[0], item[1].chunk_id))
        if min_score is not None:
            scored = [item for item in scored if item[0] >= min_score]
        results = []
        for rank, (score, record) in enumerate(scored[:top_k], start=1):
            results.append(
                SearchResult(
                    chunk_id=record.chunk_id,
                    document_id=record.document_id,
                    evidence_id=record.evidence_id,
                    score=round(score, 12),
                    rank=rank,
                    locator=record.locator,
                    text=record.text,
                    release_id=record.release_id,
                    asset_id=record.asset_id,
                    document_version=record.document_version,
                    content_hash=record.content_hash,
                    content_sha256=record.content_sha256,
                    text_sha256=record.text_sha256,
                    access_level=record.access_level,
                    license=record.license,
                    source_type=record.source_type,
                )
            )
        return SearchResponse(
            index_snapshot_id=self.snapshot_id,
            query_hash=_sha256_text(_normalize_text(query)),
            filters=normalized_filters,
            results=results,
        )


def build_index(
    chunks_path: Path | str,
    *,
    backend: EmbeddingBackend | None = None,
) -> LocalVectorIndex:
    """Build an index and a deterministic content/configuration snapshot ID."""

    source = Path(chunks_path)
    records, input_sha256 = read_chunks_jsonl(source)
    selected_backend = backend or HashingEmbeddingBackend()
    descriptor = _backend_descriptor(selected_backend)
    vectors = _validate_vectors(
        selected_backend.embed_documents([record.text for record in records]),
        len(records),
        descriptor["dimensions"],
    )
    snapshot_material = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "input_sha256": input_sha256,
        "embedding": descriptor,
        "similarity": "cosine",
        "chunk_id_policy": CHUNK_ID_POLICY,
    }
    snapshot_id = f"vector-index:{_sha256_text(_canonical_json(snapshot_material))[:24]}"
    access_level_counts = dict(
        sorted(Counter(record.access_level or "unknown" for record in records).items())
    )
    manifest = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_path": str(source.resolve()),
        "input_format": "chunks.jsonl",
        "input_sha256": input_sha256,
        "chunk_count": len(records),
        "chunk_id_policy": CHUNK_ID_POLICY,
        "model_id": descriptor["model_id"],
        "algorithm": descriptor["algorithm"],
        "embedding": descriptor,
        "similarity": {"metric": "cosine", "higher_is_better": True},
        "access_level_counts": access_level_counts,
        "contains_non_open_content": any(record.access_level != "open" for record in records),
        "text_persistence_policy": "open-only",
    }
    return LocalVectorIndex(manifest=manifest, records=records, vectors=vectors, backend=selected_backend)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dependency-free local vector retrieval over GreenFin chunks")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="build a portable JSON vector index")
    build.add_argument("--chunks", type=Path, required=True, help="input chunks.jsonl")
    build.add_argument("--index", type=Path, required=True, help="output index JSON")
    build.add_argument("--dimensions", type=int, default=384, help="offline hashing dimensions")

    search = subparsers.add_parser("search", help="search an existing index")
    search.add_argument("--index", type=Path, required=True, help="index JSON created by build")
    search.add_argument("--query", required=True)
    search.add_argument("--top-k", type=int, default=10)
    search.add_argument("--min-score", type=float)
    search.add_argument("--document-id", action="append", help="exact document_id filter; repeatable")
    search.add_argument("--source-type", action="append", help="exact source_type filter; repeatable")
    search.add_argument("--access-level", action="append", help="exact access_level filter; repeatable")
    search.add_argument(
        "--include-text",
        action="store_true",
        help="include text only for chunks explicitly marked access_level=open",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "build":
            index = build_index(args.chunks, backend=HashingEmbeddingBackend(dimensions=args.dimensions))
            index.save(args.index)
            print(json.dumps(index.manifest, ensure_ascii=False, indent=2))
            return 0
        index = LocalVectorIndex.load(args.index)
        filters = {
            "document_id": args.document_id,
            "source_type": args.source_type,
            "access_level": args.access_level,
        }
        response = index.search(
            args.query,
            top_k=args.top_k,
            min_score=args.min_score,
            filters=filters,
        )
        print(json.dumps(response.to_dict(include_text=args.include_text), ensure_ascii=False, indent=2))
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
