"""Read-only vector and graph retrieval for the HypoWeaver knowledge service.

The service accepts either a portable JSONL evidence catalog or the HDF5
artifact produced by the historical ``feature/rag-graph`` branch.  HDF5 files
are opened read-only inside a lock for each search, avoiding the unsafe shared
handle used by the prototype.
"""

from __future__ import annotations

from dataclasses import dataclass
import csv
import hashlib
import heapq
import json
import os
from pathlib import Path
import re
import threading
from typing import Any, Iterable, Protocol

import numpy as np

from .knowledge_models import (
    EvidenceBundle,
    EvidenceHit,
    GraphEdgeCandidate,
    KnowledgeCatalogDocument,
    KnowledgeCatalogPage,
    KnowledgeDocumentTextSlice,
    KnowledgeSearchFilters,
    KnowledgeSearchRequest,
    KnowledgeServiceStatus,
    SourceLocator,
)
from .legacy_rag import LegacyChunkResolver, legacy_embedding_preprocess


_TOKEN_PATTERN = re.compile(r"[\u3400-\u9fff]|[A-Za-z0-9_\-]+")


def _optional_path(value: str | None) -> Path | None:
    if not value or not value.strip():
        return None
    return Path(value).expanduser().resolve()


def _query_terms(text: str) -> set[str]:
    raw = [item.casefold() for item in _TOKEN_PATTERN.findall(text)]
    terms = {item for item in raw if len(item) > 1}
    cjk = "".join(item for item in raw if len(item) == 1)
    terms.update(cjk[index : index + 2] for index in range(max(0, len(cjk) - 1)))
    return {item for item in terms if item}


@dataclass(frozen=True)
class KnowledgeSettings:
    catalog_path: Path | None = None
    vector_path: Path | None = None
    chunk_catalog_path: Path | None = None
    cleaned_dir: Path | None = None
    metadata_dir: Path | None = None
    document_registry_path: Path | None = None
    graph_dir: Path | None = None
    corpus_manifest_path: Path | None = None
    corpus_snapshot_id: str | None = None
    embedding_backend: str = "hashing"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_revision: str | None = None
    max_catalog_records: int = 250_000
    max_graph_files: int = 20_000
    max_graph_edges: int = 1_000_000

    @classmethod
    def from_environment(cls) -> "KnowledgeSettings":
        return cls(
            catalog_path=_optional_path(os.getenv("HYPOWEAVER_KNOWLEDGE_CATALOG_PATH")),
            vector_path=_optional_path(os.getenv("HYPOWEAVER_KNOWLEDGE_VECTOR_PATH")),
            chunk_catalog_path=_optional_path(
                os.getenv("HYPOWEAVER_KNOWLEDGE_CHUNK_CATALOG_PATH")
            ),
            cleaned_dir=_optional_path(os.getenv("HYPOWEAVER_KNOWLEDGE_CLEANED_DIR")),
            metadata_dir=_optional_path(os.getenv("HYPOWEAVER_KNOWLEDGE_METADATA_DIR")),
            document_registry_path=_optional_path(
                os.getenv("HYPOWEAVER_KNOWLEDGE_DOCUMENT_REGISTRY_PATH")
            ),
            graph_dir=_optional_path(os.getenv("HYPOWEAVER_KNOWLEDGE_GRAPH_DIR")),
            corpus_manifest_path=_optional_path(
                os.getenv("HYPOWEAVER_KNOWLEDGE_MANIFEST_PATH")
            ),
            corpus_snapshot_id=os.getenv("HYPOWEAVER_KNOWLEDGE_CORPUS_SNAPSHOT_ID"),
            embedding_backend=os.getenv(
                "HYPOWEAVER_KNOWLEDGE_EMBEDDING_BACKEND", "auto"
            ).strip(),
            embedding_model=os.getenv(
                "HYPOWEAVER_KNOWLEDGE_EMBEDDING_MODEL",
                "BAAI/bge-small-zh-v1.5",
            ).strip(),
            embedding_revision=(
                os.getenv("HYPOWEAVER_KNOWLEDGE_EMBEDDING_REVISION") or ""
            ).strip()
            or None,
            max_catalog_records=int(
                os.getenv("HYPOWEAVER_KNOWLEDGE_MAX_CATALOG_RECORDS", "250000")
            ),
            max_graph_files=int(
                os.getenv("HYPOWEAVER_KNOWLEDGE_MAX_GRAPH_FILES", "20000")
            ),
            max_graph_edges=int(
                os.getenv("HYPOWEAVER_KNOWLEDGE_MAX_GRAPH_EDGES", "1000000")
            ),
        )


class Embedder(Protocol):
    name: str

    def embed(self, text: str, *, dimensions: int) -> np.ndarray: ...


class HashingEmbedder:
    """Deterministic dependency-free fallback for local tests and small catalogs."""

    name = "hashing-sha256-ngrams-v1"

    def embed(self, text: str, *, dimensions: int) -> np.ndarray:
        output = np.zeros(dimensions, dtype=np.float32)
        tokens = [item.casefold() for item in _TOKEN_PATTERN.findall(text)]
        grams = [*tokens]
        grams.extend(
            f"{tokens[index]}\x1f{tokens[index + 1]}"
            for index in range(max(0, len(tokens) - 1))
        )
        for gram in grams:
            digest = hashlib.sha256(gram.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:8], "big") % dimensions
            output[bucket] += 1.0
        norm = float(np.linalg.norm(output))
        if norm:
            output /= norm
        return output


class SentenceTransformerEmbedder:
    """Lazy BGE-compatible embedder; never downloads a model during startup."""

    def __init__(self, model_name: str, revision: str | None = None) -> None:
        suffix = f"@{revision}" if revision else ""
        self.name = f"sentence-transformers:{model_name}{suffix}"
        self.model_name = model_name
        self.revision = revision
        self._model: Any | None = None
        self._lock = threading.Lock()

    def _load(self) -> Any:
        with self._lock:
            if self._model is not None:
                return self._model
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as error:
                raise RuntimeError(
                    "sentence-transformers is required for the configured knowledge vector space"
                ) from error
            model_path = Path(self.model_name).expanduser()
            kwargs = (
                {"revision": self.revision}
                if self.revision and not model_path.exists()
                else {}
            )
            self._model = SentenceTransformer(self.model_name, **kwargs)
            return self._model

    def embed(self, text: str, *, dimensions: int) -> np.ndarray:
        vector = np.asarray(
            self._load().encode(
                [text],
                normalize_embeddings=True,
                show_progress_bar=False,
            )[0],
            dtype=np.float32,
        )
        if vector.shape != (dimensions,):
            raise RuntimeError(
                f"embedding dimension mismatch: model={vector.shape} index={dimensions}"
            )
        return vector


class LegacyBgeEmbedder(SentenceTransformerEmbedder):
    """Query adapter matching the Aug-23 BGE preprocessing exactly."""

    def __init__(self, model_name: str, revision: str | None = None) -> None:
        super().__init__(model_name, revision)
        suffix = f"@{revision}" if revision else ""
        self.name = f"legacy-bge:{model_name}{suffix}"

    def embed(self, text: str, *, dimensions: int) -> np.ndarray:
        return super().embed(
            legacy_embedding_preprocess(text),
            dimensions=dimensions,
        )


class LegacyRuleEmbedder:
    """Exact fallback vectorizer used when the Aug-23 BGE model failed to load."""

    name = "legacy-md5-char-ngrams-v1"

    def embed(self, text: str, *, dimensions: int) -> np.ndarray:
        value = legacy_embedding_preprocess(text).casefold()
        grams = [character for character in value if character.strip()]
        grams.extend(
            value[index : index + 2]
            for index in range(max(0, len(value) - 1))
            if value[index : index + 2].strip()
        )
        output = np.zeros(dimensions, dtype=np.float32)
        for gram in grams:
            digest = hashlib.md5(gram.encode("utf-8")).hexdigest()
            output[int(digest[:8], 16) % dimensions] += 1.0
        norm = float(np.linalg.norm(output))
        if norm:
            output /= norm
        return output


def _build_embedder(settings: KnowledgeSettings) -> Embedder:
    if settings.embedding_backend == "auto":
        if settings.vector_path is not None and settings.vector_path.is_file():
            return LegacyBgeEmbedder(
                settings.embedding_model,
                settings.embedding_revision,
            )
        return HashingEmbedder()
    if settings.embedding_backend == "hashing":
        return HashingEmbedder()
    if settings.embedding_backend == "sentence_transformers":
        return SentenceTransformerEmbedder(
            settings.embedding_model,
            settings.embedding_revision,
        )
    if settings.embedding_backend == "legacy_bge":
        return LegacyBgeEmbedder(
            settings.embedding_model,
            settings.embedding_revision,
        )
    if settings.embedding_backend == "legacy_rule":
        return LegacyRuleEmbedder()
    raise ValueError(
        "HYPOWEAVER_KNOWLEDGE_EMBEDDING_BACKEND must be auto, hashing, "
        "sentence_transformers, legacy_bge, or legacy_rule"
    )


def _read_json_lines(path: Path, *, limit: int) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"knowledge catalog does not exist: {path}")
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            if len(records) >= limit:
                raise ValueError(
                    f"knowledge catalog exceeds configured record limit {limit}"
                )
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"invalid JSONL at {path.name}:{line_number}: {error.msg}"
                ) from error
            if not isinstance(value, dict):
                raise ValueError(f"catalog entry {line_number} must be an object")
            records.append(value)
    return records


def _source_locator(value: object, metadata: dict[str, Any]) -> SourceLocator:
    locator = value if isinstance(value, dict) else {}
    if not locator:
        page_range = metadata.get("page_range")
        if isinstance(page_range, list) and page_range:
            locator = {
                "page_start": page_range[0],
                "page_end": page_range[-1],
            }
        elif metadata.get("section_title"):
            locator = {"section": str(metadata["section_title"])}
        else:
            locator = {"section": "unresolved legacy chunk location"}
    return SourceLocator.model_validate(locator)


def _evidence_from_record(record: dict[str, Any], score: float) -> EvidenceHit:
    metadata = record.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    text = str(record.get("text") or record.get("chunk_text") or "").strip()
    if not text:
        raise ValueError("retrieved chunk has no text and cannot become evidence")
    content_sha256 = str(record.get("content_sha256") or "").casefold()
    if not content_sha256:
        content_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    has_fulltext = bool(record.get("has_fulltext", True))
    status = str(
        record.get("evidence_status")
        or ("fulltext_located" if has_fulltext else "candidate_unverified")
    )
    year = record.get("publication_year")
    if year in (None, ""):
        year = metadata.get("year")
    try:
        publication_year = int(year) if year not in (None, "") else None
    except (TypeError, ValueError):
        publication_year = None
    if publication_year is not None and not 1500 <= publication_year <= 3000:
        publication_year = None
    return EvidenceHit(
        document_id=str(record.get("document_id") or record.get("doc_id") or ""),
        document_version=str(record.get("document_version") or "legacy-v1"),
        chunk_id=str(record.get("chunk_id") or ""),
        text=text,
        title=str(record.get("title") or metadata.get("title") or "Untitled source"),
        source_type=str(record.get("source_type") or metadata.get("source_type") or "paper"),
        source_locator=_source_locator(record.get("source_locator"), {**metadata, **record}),
        source_url=record.get("source_url") or metadata.get("source_url"),
        doi=record.get("doi") or metadata.get("doi"),
        content_sha256=content_sha256,
        retrieval_score=max(-1.0, min(1.0, float(score))),
        has_fulltext=has_fulltext,
        evidence_status=status,
        publication_year=publication_year,
        metadata=metadata,
    )


def _matches_filters(record: dict[str, Any], filters: KnowledgeSearchFilters) -> bool:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    source_type = str(record.get("source_type") or metadata.get("source_type") or "paper")
    if filters.source_types and source_type not in filters.source_types:
        return False
    has_fulltext = bool(record.get("has_fulltext", True))
    if filters.fulltext_only and not has_fulltext:
        return False
    year = record.get("publication_year") or metadata.get("year")
    try:
        year_value = int(year) if year is not None else None
    except (TypeError, ValueError):
        year_value = None
    if filters.publication_year_min is not None:
        if year_value is None or year_value < filters.publication_year_min:
            return False
    if filters.publication_year_max is not None:
        if year_value is None or year_value > filters.publication_year_max:
            return False
    return True


class JsonlVectorIndex:
    backend_name = "jsonl-vector"

    def __init__(self, path: Path, *, embedder: Embedder, max_records: int) -> None:
        self.path = path
        self.embedder = embedder
        self.records = _read_json_lines(path, limit=max_records)
        self.dimensions = self._dimensions()
        self.vectors = self._vectors()

    def _dimensions(self) -> int:
        for record in self.records:
            vector = record.get("embedding")
            if isinstance(vector, list) and vector:
                return len(vector)
        return 512

    def _vectors(self) -> np.ndarray:
        vectors: list[np.ndarray] = []
        for record in self.records:
            value = record.get("embedding")
            if isinstance(value, list):
                vector = np.asarray(value, dtype=np.float32)
                if vector.shape != (self.dimensions,):
                    raise ValueError("catalog contains inconsistent embedding dimensions")
            else:
                vector = self.embedder.embed(
                    str(record.get("text") or record.get("chunk_text") or ""),
                    dimensions=self.dimensions,
                )
            norm = float(np.linalg.norm(vector))
            vectors.append(vector / norm if norm else vector)
        if not vectors:
            return np.empty((0, self.dimensions), dtype=np.float32)
        return np.asarray(vectors, dtype=np.float32)

    def count(self) -> int:
        return len(self.records)

    def search(self, request: KnowledgeSearchRequest) -> tuple[list[EvidenceHit], list[str]]:
        if not self.records:
            return [], []
        query = self.embedder.embed(request.question, dimensions=self.dimensions)
        norm = float(np.linalg.norm(query))
        if norm:
            query = query / norm
        scores = self.vectors @ query
        order = np.argsort(scores)[::-1]
        hits: list[EvidenceHit] = []
        warnings: list[str] = []
        document_counts: dict[str, int] = {}
        skipped_by_cap = 0
        for raw_index in order:
            record = self.records[int(raw_index)]
            if not _matches_filters(record, request.filters):
                continue
            try:
                hit = _evidence_from_record(record, float(scores[int(raw_index)]))
            except ValueError as error:
                warnings.append(
                    f"skipped non-evidence chunk {record.get('chunk_id', raw_index)}: {error}"
                )
                continue
            if (
                request.diversity_mode == "per_document_cap"
                and document_counts.get(hit.document_id, 0)
                >= request.max_hits_per_document
            ):
                skipped_by_cap += 1
                continue
            hits.append(hit)
            document_counts[hit.document_id] = document_counts.get(hit.document_id, 0) + 1
            if len(hits) >= request.top_k:
                break
        if skipped_by_cap:
            warnings.append(
                f"diversity gate skipped {skipped_by_cap} hits above the per-document cap"
            )
        return hits, warnings


class LegacyHdf5VectorIndex:
    """Compatibility reader for the Aug-23 RAG vector artifact."""

    backend_name = "legacy-hdf5-readonly"

    def __init__(
        self,
        path: Path,
        *,
        embedder: Embedder,
        chunk_records: dict[str, dict[str, Any]],
        chunk_resolver: LegacyChunkResolver | None,
    ) -> None:
        self.path = path
        self.embedder = embedder
        self.chunk_records = chunk_records
        self.chunk_resolver = chunk_resolver
        self._lock = threading.RLock()

    def _h5py(self) -> Any:
        try:
            import h5py
        except ImportError as error:
            raise RuntimeError("h5py is required to read the legacy RAG vector store") from error
        return h5py

    def count(self) -> int:
        if not self.path.is_file():
            return 0
        with self._lock, self._h5py().File(self.path, "r") as handle:
            return int(handle["vectors"].shape[0])

    def search(self, request: KnowledgeSearchRequest) -> tuple[list[EvidenceHit], list[str]]:
        if not self.path.is_file():
            return [], [f"legacy vector store is missing: {self.path}"]
        candidates: list[tuple[float, int, dict[str, Any]]] = []
        with self._lock, self._h5py().File(self.path, "r") as handle:
            vectors = handle["vectors"]
            metas = handle["metas"]
            dimensions = int(vectors.shape[1])
            query = self.embedder.embed(request.question, dimensions=dimensions)
            query_norm = float(np.linalg.norm(query)) or 1.0
            for start in range(0, int(vectors.shape[0]), 4096):
                end = min(start + 4096, int(vectors.shape[0]))
                batch = np.asarray(vectors[start:end], dtype=np.float32)
                norms = np.linalg.norm(batch, axis=1)
                scores = (batch @ query) / (norms * query_norm + 1e-8)
                for offset, score in enumerate(scores):
                    index = start + offset
                    meta = json.loads(metas[index])
                    if (
                        request.filters.fulltext_only
                        and (
                            str(meta.get("chunk_level") or "") == "metadata"
                            or (
                                self.chunk_resolver is not None
                                and not self.chunk_resolver.document_has_fulltext(meta)
                            )
                        )
                    ):
                        continue
                    candidate = (float(score), index, meta)
                    candidate_limit = max(request.top_k * 20, 200)
                    if len(candidates) < candidate_limit:
                        heapq.heappush(candidates, candidate)
                    elif score > candidates[0][0]:
                        heapq.heapreplace(candidates, candidate)

        hits: list[EvidenceHit] = []
        warnings: list[str] = []
        seen_evidence: set[tuple[str, str]] = set()
        document_counts: dict[str, int] = {}
        duplicate_count = 0
        skipped_by_cap = 0
        for score, _index, meta in sorted(candidates, reverse=True):
            chunk_id = str(meta.get("chunk_id") or "")
            hydrated = self.chunk_records.get(chunk_id, {})
            if not hydrated and self.chunk_resolver is not None:
                hydrated = self.chunk_resolver.resolve(meta)
            merged = {**meta, **hydrated}
            if not _matches_filters(merged, request.filters):
                continue
            try:
                hit = _evidence_from_record(merged, score)
            except ValueError as error:
                warnings.append(f"skipped legacy chunk {chunk_id}: {error}")
                continue
            evidence_key = (hit.document_version, hit.content_sha256)
            if evidence_key in seen_evidence:
                duplicate_count += 1
                continue
            seen_evidence.add(evidence_key)
            if (
                request.diversity_mode == "per_document_cap"
                and document_counts.get(hit.document_id, 0)
                >= request.max_hits_per_document
            ):
                skipped_by_cap += 1
                continue
            hits.append(hit)
            document_counts[hit.document_id] = document_counts.get(hit.document_id, 0) + 1
            if len(hits) >= request.top_k:
                break
        if duplicate_count:
            warnings.append(
                f"deduplicated {duplicate_count} legacy hits with identical source version and content"
            )
        if skipped_by_cap:
            warnings.append(
                f"diversity gate skipped {skipped_by_cap} hits above the per-document cap"
            )
        return hits, warnings


class JsonGraphIndex:
    def __init__(self, directory: Path | None, *, max_files: int, max_edges: int) -> None:
        self.directory = directory
        self.max_files = max_files
        self.max_edges = max_edges
        self.document_count = 0
        self.edges: list[dict[str, Any]] = []
        self.warnings: list[str] = []
        self._load()

    def _load(self) -> None:
        if self.directory is None:
            return
        if not self.directory.is_dir():
            self.warnings.append(f"knowledge graph directory is missing: {self.directory}")
            return
        files = sorted(self.directory.glob("*.kg.json"))
        if len(files) > self.max_files:
            raise ValueError(
                f"knowledge graph file count exceeds configured limit {self.max_files}"
            )
        for path in files:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                self.warnings.append(f"skipped graph file {path.name}: {error}")
                continue
            self.document_count += 1
            paper = payload.get("paper") if isinstance(payload.get("paper"), dict) else {}
            document_id = str(
                paper.get("doc_id") or payload.get("doc_id") or path.name.removesuffix(".kg.json")
            )
            for edge in payload.get("relations", []):
                if not isinstance(edge, dict):
                    continue
                if len(self.edges) >= self.max_edges:
                    raise ValueError(
                        f"knowledge graph edge count exceeds configured limit {self.max_edges}"
                    )
                self.edges.append({**edge, "_document_id": document_id})

    def search(self, question: str, max_edges: int) -> list[GraphEdgeCandidate]:
        if max_edges <= 0:
            return []
        tokens = _query_terms(question)
        ranked: list[tuple[float, int, dict[str, Any]]] = []
        for index, edge in enumerate(self.edges):
            source = str(edge.get("source") or "")
            target = str(edge.get("target") or "")
            relation = str(edge.get("relation") or "RELATED_TO")
            haystack = f"{source} {target} {relation}".casefold()
            overlap = sum(token in haystack for token in tokens)
            if not overlap:
                continue
            confidence = max(0.0, min(1.0, float(edge.get("confidence", 0.5))))
            score = overlap + confidence
            ranked.append((score, index, edge))
        ranked.sort(reverse=True)
        result: list[GraphEdgeCandidate] = []
        seen: set[tuple[str, str, str]] = set()
        for _score, _index, edge in ranked:
            key = (
                str(edge.get("source") or ""),
                str(edge.get("relation") or "RELATED_TO"),
                str(edge.get("target") or ""),
            )
            if not key[0] or not key[2] or key in seen:
                continue
            seen.add(key)
            evidence_refs = edge.get("evidence_refs")
            if not isinstance(evidence_refs, list):
                evidence_refs = []
            result.append(
                GraphEdgeCandidate(
                    source=key[0],
                    relation=key[1],
                    target=key[2],
                    evidence_refs=[str(value) for value in evidence_refs],
                    source_document_ids=[str(edge.get("source_doc") or edge["_document_id"])],
                    confidence=max(
                        0.0, min(1.0, float(edge.get("confidence", 0.5)))
                    ),
                    extraction_model=edge.get("extraction_model"),
                    extraction_version=edge.get("extraction_version") or "legacy-rag-graph",
                )
            )
            if len(result) >= max_edges:
                break
        return result


class KnowledgeCatalogIndex:
    """Bounded, metadata-only browser for a mounted knowledge snapshot."""

    def __init__(self, settings: KnowledgeSettings) -> None:
        self.settings = settings
        self.warnings: list[str] = []
        self.data_updated_at: str | None = None
        self.access_level: str | None = None
        self.declared_source_asset_documents = 0
        self.available_source_asset_documents = 0
        self.original_pdf_documents = 0
        self.documents = self._load_documents()
        self.source_format_counts: dict[str, int] = {}
        for document in self.documents:
            self.source_format_counts[document.source_format] = (
                self.source_format_counts.get(document.source_format, 0) + 1
            )
        self._load_manifest_metadata()

    @staticmethod
    def _json_object(path: Path | None) -> dict[str, Any]:
        if path is None or not path.is_file():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _year(*values: object) -> int | None:
        for value in values:
            match = re.search(
                r"(?:15|16|17|18|19|20|21|22|23|24|25|26|27|28|29)\d{2}",
                str(value or ""),
            )
            if match:
                year = int(match.group(0))
                if 1500 <= year <= 3000:
                    return year
        return None

    @staticmethod
    def _authors(value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()][:200]
        if isinstance(value, str) and value.strip():
            return [
                item.strip()
                for item in re.split(r"[,;，；]", value)
                if item.strip()
            ][:200]
        return []

    @staticmethod
    def _usable_title(value: object, document_id: str) -> str | None:
        title = re.sub(r"\s+", " ", str(value or "")).strip()
        if not title:
            return None
        normalized = title.casefold()
        identifiers = {
            document_id.casefold(),
            f"{document_id}.txt".casefold(),
            f"{document_id}.xml".casefold(),
            f"{document_id}.md".casefold(),
        }
        if normalized in identifiers:
            return None
        if (
            "-fulltext-" in normalized or "legacy-fulltext" in normalized
        ) and " " not in title:
            return None
        return title[:2000]

    @classmethod
    def _derived_title(cls, path: Path | None, document_id: str) -> str | None:
        if path is None or not path.is_file():
            return None
        try:
            with path.open("r", encoding="utf-8") as handle:
                lines = [handle.readline() for _ in range(100)]
        except (OSError, UnicodeDecodeError):
            return None
        for raw in lines:
            line = re.sub(r"\s+", " ", raw.replace("\f", " ")).strip(" #|\t")
            if not line:
                continue
            marker = re.match(r"【标题】\s*(.+)", line)
            if marker:
                candidate = cls._usable_title(marker.group(1), document_id)
                if candidate:
                    return candidate
            if len(line) < 5 or len(line) > 240:
                continue
            if re.search(
                r"年第|总第|第\s*\d+\s*卷|第\s*\d+\s*期|General\s*No|Vol\.?\s*\d|ISSN|DOI|JOU.?NAL\s+OF",
                line,
                re.IGNORECASE,
            ):
                continue
            if line.casefold() in {"abstract", "摘要", "摘 要"}:
                continue
            letters = len(re.findall(r"[\u3400-\u9fffA-Za-z]", line))
            if letters < 4 or letters / max(1, len(line)) < 0.35:
                continue
            candidate = cls._usable_title(line, document_id)
            if candidate:
                return candidate
        return None

    def _metadata_for(self, document_id: str) -> dict[str, Any]:
        if self.settings.metadata_dir is None or Path(document_id).name != document_id:
            return {}
        return self._json_object(self.settings.metadata_dir / f"{document_id}.json")

    def _source_asset_available(self, source_asset: str) -> bool:
        if not source_asset or Path(source_asset).name != source_asset:
            return False
        if self.settings.cleaned_dir is None:
            return False
        source_root = self.settings.cleaned_dir.parent / "input" / "fulltexts"
        candidate = (source_root / source_asset).resolve()
        return candidate.parent == source_root.resolve() and candidate.is_file()

    def _reading_available(self, document_id: str, has_fulltext: bool) -> bool:
        if not has_fulltext or self.settings.cleaned_dir is None:
            return False
        path = self.settings.cleaned_dir / f"{document_id}.md"
        try:
            return path.is_file() and path.stat().st_size >= 1_000
        except OSError:
            return False

    def _from_registry(self, path: Path) -> list[KnowledgeCatalogDocument]:
        result: list[KnowledgeCatalogDocument] = []
        missing_source_assets = 0
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row_number, row in enumerate(reader, 2):
                if len(result) >= self.settings.max_catalog_records:
                    raise ValueError(
                        "knowledge catalog exceeds configured record limit "
                        f"{self.settings.max_catalog_records}"
                    )
                document_id = str(row.get("doc_id") or "").strip()
                if not document_id or Path(document_id).name != document_id:
                    raise ValueError(
                        f"invalid doc_id in document registry row {row_number}"
                    )
                metadata = self._metadata_for(document_id)
                extra = metadata.get("extra_info")
                extra = extra if isinstance(extra, dict) else {}
                title = self._usable_title(row.get("title"), document_id)
                title = title or self._usable_title(extra.get("title"), document_id)
                title = title or self._usable_title(metadata.get("title"), document_id)
                title_source = "metadata"
                if title is None:
                    cleaned_path = (
                        self.settings.cleaned_dir / f"{document_id}.md"
                        if self.settings.cleaned_dir is not None
                        else None
                    )
                    title = self._derived_title(cleaned_path, document_id)
                    title_source = "derived" if title else "identifier"
                title = title or document_id
                has_fulltext = (
                    str(row.get("has_fulltext") or "").strip().casefold() == "true"
                )
                source_asset = str(row.get("source_asset") or "").strip()
                source_available = self._source_asset_available(source_asset)
                if source_asset:
                    self.declared_source_asset_documents += 1
                    if source_available:
                        self.available_source_asset_documents += 1
                    else:
                        missing_source_assets += 1
                original_pdf = source_available and source_asset.casefold().endswith(".pdf")
                if original_pdf:
                    self.original_pdf_documents += 1
                source_format = str(
                    metadata.get("doc_type") or extra.get("doc_type") or ""
                ).strip()
                if not source_format and source_asset:
                    source_format = Path(source_asset).suffix.lstrip(".")
                source_format = source_format or (
                    "indexed_text" if has_fulltext else "metadata"
                )
                abstract = str(
                    extra.get("abstract") or metadata.get("abstract") or ""
                ).strip()
                journal = str(
                    row.get("journal") or extra.get("journal") or ""
                ).strip()
                doi = str(row.get("doi") or extra.get("doi") or "").strip()
                result.append(
                    KnowledgeCatalogDocument(
                        document_id=document_id,
                        title=title,
                        title_source=title_source,
                        authors=self._authors(
                            extra.get("authors") or metadata.get("authors")
                        ),
                        abstract=abstract[:20_000] or None,
                        journal=journal or None,
                        doi=doi or None,
                        publication_year=self._year(
                            row.get("publication_year"),
                            extra.get("year"),
                            extra.get("date"),
                        ),
                        has_fulltext=has_fulltext,
                        content_kind=(
                            "indexed_fulltext" if has_fulltext else "metadata_only"
                        ),
                        source_format=source_format[:100],
                        access_level=(
                            str(row.get("access_level") or "").strip() or None
                        ),
                        original_pdf_available=original_pdf,
                        reading_available=self._reading_available(
                            document_id,
                            has_fulltext,
                        ),
                    )
                )
        if missing_source_assets:
            self.warnings.append(
                f"{missing_source_assets} registered source assets are absent; "
                "only cleaned indexed text is available"
            )
        return result

    def _from_jsonl(self, path: Path) -> list[KnowledgeCatalogDocument]:
        records = _read_json_lines(path, limit=self.settings.max_catalog_records)
        documents: dict[str, KnowledgeCatalogDocument] = {}
        for record in records:
            document_id = str(
                record.get("document_id") or record.get("doc_id") or ""
            ).strip()
            if not document_id or document_id in documents:
                continue
            metadata = record.get("metadata")
            metadata = metadata if isinstance(metadata, dict) else {}
            has_fulltext = bool(record.get("has_fulltext"))
            title = self._usable_title(record.get("title"), document_id) or document_id
            documents[document_id] = KnowledgeCatalogDocument(
                document_id=document_id,
                title=title,
                title_source="metadata" if title != document_id else "identifier",
                authors=self._authors(metadata.get("authors")),
                abstract=str(metadata.get("abstract") or "")[:20_000] or None,
                journal=str(metadata.get("journal") or "") or None,
                doi=str(record.get("doi") or metadata.get("doi") or "") or None,
                publication_year=self._year(
                    record.get("publication_year"), metadata.get("year")
                ),
                has_fulltext=has_fulltext,
                content_kind=(
                    "indexed_fulltext" if has_fulltext else "metadata_only"
                ),
                source_format=str(record.get("source_type") or "catalog")[:100],
                access_level=str(metadata.get("access_level") or "") or None,
                reading_available=self._reading_available(
                    document_id,
                    has_fulltext,
                ),
            )
        return list(documents.values())

    def _load_documents(self) -> list[KnowledgeCatalogDocument]:
        registry = self.settings.document_registry_path
        if registry is not None and registry.is_file():
            documents = self._from_registry(registry)
        elif self.settings.catalog_path is not None and self.settings.catalog_path.is_file():
            documents = self._from_jsonl(self.settings.catalog_path)
            self.warnings.append(
                "document registry is not configured; catalog inventory is derived "
                "from evidence records"
            )
        else:
            documents = []
            self.warnings.append("no browseable knowledge document catalog is configured")
        return sorted(
            documents,
            key=lambda item: (
                not item.has_fulltext,
                item.title_source == "identifier",
                -(item.publication_year or 0),
                item.title.casefold(),
            ),
        )

    def _load_manifest_metadata(self) -> None:
        manifest = self._json_object(self.settings.corpus_manifest_path)
        self.data_updated_at = str(
            manifest.get("data_updated_at")
            or manifest.get("generated_at_utc")
            or manifest.get("downloaded_at")
            or ""
        ).strip() or None
        self.access_level = str(
            manifest.get("access") or manifest.get("access_policy") or ""
        ).strip() or None
        counts = manifest.get("counts")
        counts = counts if isinstance(counts, dict) else {}
        declared_assets = counts.get("input_fulltext_assets") or counts.get("assets")
        try:
            self.declared_source_asset_documents = max(
                self.declared_source_asset_documents,
                int(declared_assets or 0),
            )
        except (TypeError, ValueError):
            pass
        self.warnings = [
            warning
            for warning in self.warnings
            if "registered source assets are absent" not in warning
        ]
        missing_assets = (
            self.declared_source_asset_documents
            - self.available_source_asset_documents
        )
        if missing_assets > 0:
            self.warnings.append(
                f"{missing_assets} declared source assets are absent; "
                "only cleaned indexed text is available"
            )

    def page(
        self,
        *,
        query: str = "",
        fulltext_only: bool = False,
        readable_only: bool = False,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[KnowledgeCatalogDocument], int, int | None]:
        query = query.strip()
        terms = _query_terms(query)
        ranked: list[tuple[int, KnowledgeCatalogDocument]] = []
        for document in self.documents:
            if readable_only and not document.reading_available:
                continue
            if fulltext_only and not document.has_fulltext:
                continue
            score = 0
            if query:
                haystack = " ".join(
                    [
                        document.title,
                        " ".join(document.authors),
                        document.abstract or "",
                        document.journal or "",
                        document.doi or "",
                    ]
                ).casefold()
                if query.casefold() in haystack:
                    score += max(4, len(terms))
                score += len(terms.intersection(_query_terms(haystack)))
                if score == 0:
                    continue
            ranked.append((score, document))
        if query:
            ranked.sort(
                key=lambda item: (
                    -item[0],
                    not item[1].reading_available,
                    -(item[1].publication_year or 0),
                    item[1].title.casefold(),
                )
            )
        else:
            ranked.sort(
                key=lambda item: (
                    not item[1].reading_available,
                    -(item[1].publication_year or 0),
                    item[1].title.casefold(),
                )
            )
        matched = len(ranked)
        items = [item for _, item in ranked[offset : offset + limit]]
        next_offset = offset + limit if offset + limit < matched else None
        return items, matched, next_offset

    def document_text(
        self,
        document_id: str,
        *,
        offset: int = 0,
        limit: int = 30_000,
    ) -> KnowledgeDocumentTextSlice:
        if Path(document_id).name != document_id:
            raise ValueError("invalid knowledge document id")
        document = next(
            (item for item in self.documents if item.document_id == document_id),
            None,
        )
        if document is None:
            raise ValueError("knowledge document was not found")
        if not document.has_fulltext:
            raise ValueError("this knowledge record has metadata only")
        if not document.reading_available:
            raise ValueError("this knowledge record does not contain readable body text")
        if self.settings.cleaned_dir is None:
            raise ValueError("cleaned knowledge text is not configured")
        path = (self.settings.cleaned_dir / f"{document_id}.md").resolve()
        cleaned_root = self.settings.cleaned_dir.resolve()
        if path.parent != cleaned_root or not path.is_file():
            raise ValueError("cleaned knowledge text is unavailable")
        raw = path.read_bytes()
        if len(raw) > 5 * 1024 * 1024:
            raise ValueError("cleaned knowledge text exceeds the 5 MiB reading limit")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("cleaned knowledge text is not valid UTF-8") from error
        if not text:
            raise ValueError("cleaned knowledge text is empty")
        if offset >= len(text):
            raise ValueError("knowledge document reading offset is out of range")
        end = min(len(text), offset + limit)
        return KnowledgeDocumentTextSlice(
            document_id=document.document_id,
            title=document.title,
            source_format=document.source_format,
            access_level=document.access_level,
            content_sha256=hashlib.sha256(raw).hexdigest(),
            total_characters=len(text),
            offset=offset,
            limit=limit,
            next_offset=end if end < len(text) else None,
            text=text[offset:end],
        )


class KnowledgeService:
    """Coordinates bounded retrieval without promoting graph edges to evidence."""

    def __init__(self, settings: KnowledgeSettings | None = None) -> None:
        self.settings = settings or KnowledgeSettings.from_environment()
        self.embedder = _build_embedder(self.settings)
        self.warnings: list[str] = []
        chunk_records: dict[str, dict[str, Any]] = {}
        if self.settings.chunk_catalog_path is not None:
            if self.settings.chunk_catalog_path.is_file():
                records = _read_json_lines(
                    self.settings.chunk_catalog_path,
                    limit=self.settings.max_catalog_records,
                )
                chunk_records = {
                    str(item.get("chunk_id")): item
                    for item in records
                    if item.get("chunk_id")
                }
            else:
                self.warnings.append(
                    f"knowledge chunk catalog is missing: {self.settings.chunk_catalog_path}"
                )
        chunk_resolver: LegacyChunkResolver | None = None
        document_registry_path: Path | None = None
        if self.settings.document_registry_path is not None:
            if self.settings.document_registry_path.is_file():
                document_registry_path = self.settings.document_registry_path
            else:
                self.warnings.append(
                    "knowledge document registry is missing: "
                    f"{self.settings.document_registry_path}"
                )
        elif self.settings.vector_path is not None and self.settings.vector_path.is_file():
            self.warnings.append(
                "legacy HDF5 has no authoritative has_fulltext field; configure the document registry"
            )
        if self.settings.cleaned_dir is not None:
            if self.settings.cleaned_dir.is_dir():
                chunk_resolver = LegacyChunkResolver(
                    self.settings.cleaned_dir,
                    self.settings.metadata_dir,
                    document_registry_path,
                    max_registry_records=self.settings.max_catalog_records,
                )
            else:
                self.warnings.append(
                    f"legacy cleaned document directory is missing: {self.settings.cleaned_dir}"
                )
        if self.settings.metadata_dir is not None and not self.settings.metadata_dir.is_dir():
            self.warnings.append(
                f"legacy metadata directory is missing: {self.settings.metadata_dir}"
            )
        if self.settings.catalog_path is not None and self.settings.catalog_path.is_file():
            self.vector_index: JsonlVectorIndex | LegacyHdf5VectorIndex | None = (
                JsonlVectorIndex(
                    self.settings.catalog_path,
                    embedder=self.embedder,
                    max_records=self.settings.max_catalog_records,
                )
            )
        elif self.settings.vector_path is not None and self.settings.vector_path.is_file():
            self.vector_index = LegacyHdf5VectorIndex(
                self.settings.vector_path,
                embedder=self.embedder,
                chunk_records=chunk_records,
                chunk_resolver=chunk_resolver,
            )
            if not isinstance(self.embedder, SentenceTransformerEmbedder):
                self.warnings.append(
                    "legacy HDF5 vectors normally require sentence_transformers with the original BGE model"
                )
            if not chunk_records and chunk_resolver is None:
                self.warnings.append(
                    "legacy HDF5 metadata has no chunk text; configure a chunk catalog or mounted cleaned documents"
                )
        else:
            self.vector_index = None
            if self.settings.catalog_path is not None:
                self.warnings.append(
                    f"knowledge evidence catalog is missing: {self.settings.catalog_path}"
                )
            if self.settings.vector_path is not None:
                self.warnings.append(
                    f"knowledge vector store is missing: {self.settings.vector_path}"
                )
            if self.settings.catalog_path is None and self.settings.vector_path is None:
                self.warnings.append("no knowledge vector catalog is configured")
        self.graph_index = JsonGraphIndex(
            self.settings.graph_dir,
            max_files=self.settings.max_graph_files,
            max_edges=self.settings.max_graph_edges,
        )
        self.warnings.extend(self.graph_index.warnings)
        self.catalog_index = KnowledgeCatalogIndex(self.settings)
        self.catalog_documents_by_id = {
            item.document_id: item for item in self.catalog_index.documents
        }
        self.corpus_snapshot_id = self._corpus_snapshot_id()

    def _corpus_snapshot_id(self) -> str:
        if self.settings.corpus_snapshot_id:
            return self.settings.corpus_snapshot_id
        manifest = self.settings.corpus_manifest_path
        if manifest is not None and manifest.is_file():
            digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
            return f"manifest-sha256:{digest}"
        descriptors = []
        for path in (
            self.settings.catalog_path,
            self.settings.vector_path,
            self.settings.chunk_catalog_path,
        ):
            if path is not None and path.is_file():
                stat = path.stat()
                descriptors.append([path.name, stat.st_size, stat.st_mtime_ns])
        digest = hashlib.sha256(
            json.dumps(descriptors, sort_keys=True).encode("utf-8")
        ).hexdigest()
        self.warnings.append(
            "corpus snapshot is derived from local file metadata; configure a hash-bound manifest for release use"
        )
        return f"local-unverified:{digest[:24]}"

    def status(self) -> KnowledgeServiceStatus:
        vector_count = self.vector_index.count() if self.vector_index is not None else 0
        if vector_count:
            state = "ok" if not self.warnings else "degraded"
        else:
            state = "empty"
        return KnowledgeServiceStatus(
            status=state,
            corpus_snapshot_id=self.corpus_snapshot_id,
            vector_backend=(
                self.vector_index.backend_name if self.vector_index is not None else "none"
            ),
            vector_count=vector_count,
            graph_document_count=self.graph_index.document_count,
            graph_edge_count=len(self.graph_index.edges),
            warnings=sorted(set(self.warnings)),
        )

    def catalog(
        self,
        *,
        query: str = "",
        fulltext_only: bool = False,
        readable_only: bool = False,
        offset: int = 0,
        limit: int = 20,
    ) -> KnowledgeCatalogPage:
        items, matched, next_offset = self.catalog_index.page(
            query=query,
            fulltext_only=fulltext_only,
            readable_only=readable_only,
            offset=offset,
            limit=limit,
        )
        status = self.status()
        fulltext_documents = sum(
            1 for item in self.catalog_index.documents if item.has_fulltext
        )
        readable_documents = sum(
            1 for item in self.catalog_index.documents if item.reading_available
        )
        total_documents = len(self.catalog_index.documents)
        return KnowledgeCatalogPage(
            corpus_snapshot_id=self.corpus_snapshot_id,
            total_documents=total_documents,
            fulltext_documents=fulltext_documents,
            readable_documents=readable_documents,
            metadata_only_documents=total_documents - fulltext_documents,
            declared_source_asset_documents=(
                self.catalog_index.declared_source_asset_documents
            ),
            available_source_asset_documents=(
                self.catalog_index.available_source_asset_documents
            ),
            original_pdf_documents=self.catalog_index.original_pdf_documents,
            vector_count=status.vector_count,
            graph_document_count=status.graph_document_count,
            graph_edge_count=status.graph_edge_count,
            matched_documents=matched,
            offset=offset,
            limit=limit,
            next_offset=next_offset,
            data_updated_at=self.catalog_index.data_updated_at,
            access_level=self.catalog_index.access_level,
            source_format_counts=self.catalog_index.source_format_counts,
            collection_status="snapshot_only",
            collection_message=(
                "当前展示已交付的离线索引快照；在线学术采集器尚未接入主线。"
            ),
            items=items,
            warnings=sorted(set([*self.warnings, *self.catalog_index.warnings])),
        )

    def document_text(
        self,
        document_id: str,
        *,
        offset: int = 0,
        limit: int = 30_000,
    ) -> KnowledgeDocumentTextSlice:
        return self.catalog_index.document_text(
            document_id,
            offset=offset,
            limit=limit,
        )

    def search(self, request: KnowledgeSearchRequest) -> EvidenceBundle:
        warnings = list(self.warnings)
        if self.vector_index is None:
            evidence_hits: list[EvidenceHit] = []
        else:
            evidence_hits, search_warnings = self.vector_index.search(request)
            warnings.extend(search_warnings)
        evidence_hits = [
            hit.model_copy(update={"title": catalog.title})
            if (catalog := self.catalog_documents_by_id.get(hit.document_id)) is not None
            and catalog.title_source != "identifier"
            else hit
            for hit in evidence_hits
        ]
        graph_edges = self.graph_index.search(
            request.question,
            request.max_graph_edges,
        )
        if not evidence_hits:
            warnings.append("no source-located evidence matched the request")
        document_counts: dict[str, int] = {}
        for hit in evidence_hits:
            document_counts[hit.document_id] = document_counts.get(hit.document_id, 0) + 1
        effective_minimum = min(request.top_k, request.min_unique_documents)
        if len(document_counts) < effective_minimum:
            warnings.append(
                "retrieval diversity gate failed: "
                f"{len(document_counts)} unique documents returned; "
                f"{effective_minimum} required"
            )
        skipped_by_cap = 0
        for warning in warnings:
            match = re.search(r"diversity gate skipped (\d+) hits", warning)
            if match:
                skipped_by_cap += int(match.group(1))
        return EvidenceBundle.build(
            request=request,
            corpus_snapshot_id=self.corpus_snapshot_id,
            evidence_hits=evidence_hits,
            graph_edges=graph_edges,
            warnings=sorted(set(warnings)),
            skipped_by_document_cap=skipped_by_cap,
        )
