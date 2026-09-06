"""Read-only hydration for the Aug-23 RAG-Graph HDF5 metadata.

The historical vector store contains embeddings and chunk identifiers, but not
the chunk text.  This module reproduces that branch's deterministic chunking
rules against the mounted ``cleaned`` and ``cleaned_meta`` directories so a
retrieval hit can become a source-located, content-hashed EvidenceHit.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import threading
from typing import Any


_SEMANTIC_MARKER = re.compile(r"^#【(.+?)】\s*$")
_HEADING = re.compile(r"^(#{1,5})\s+(.*?)\s*$")
_SENTENCE_SPLIT = re.compile(r"(?<=[。；;！？])")
_WHITESPACE = re.compile(r"\s+")
_MARKDOWN_JUNK = re.compile(r"[#*_`|>~()\[\]{}]")


@dataclass(frozen=True)
class LegacyChunk:
    chunk_id: str
    chunk_level: str
    chunk_seq: int
    text: str
    section_title: str | None


def legacy_embedding_preprocess(text: str) -> str:
    """Reproduce the Aug-23 embedding adapter's text normalization."""

    if not text:
        return ""
    value = _MARKDOWN_JUNK.sub(" ", text)
    value = _WHITESPACE.sub(" ", value)
    value = value.replace("，", ",").replace("。", ".")
    value = value.replace("；", ";").replace("：", ":")
    value = value.replace("（", "(").replace("）", ")")
    value = value.replace("“", '"').replace("”", '"')
    return value.strip()


def _estimate_tokens(text: str) -> int:
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    words = len(re.findall(r"[A-Za-z0-9_\-]+", text))
    return cjk + words


def _split_long_paragraphs(paragraphs: list[str], max_tokens: int) -> list[str]:
    result: list[str] = []
    for paragraph in paragraphs:
        if _estimate_tokens(paragraph) <= max_tokens:
            result.append(paragraph)
            continue
        buffer = ""
        for sentence in [item for item in _SENTENCE_SPLIT.split(paragraph) if item.strip()]:
            if buffer and _estimate_tokens(buffer + sentence) > max_tokens:
                result.append(buffer.strip())
                buffer = sentence
            else:
                buffer += sentence
        if buffer.strip():
            result.append(buffer.strip())
    return result


def _sections(markdown: str) -> list[tuple[str | None, int | None, str, str]]:
    result: list[tuple[str | None, int | None, str, str]] = []
    semantic: str | None = None
    level: int | None = None
    title = ""
    body: list[str] = []

    def flush() -> None:
        if body or title:
            result.append((semantic, level, title, "\n".join(body)))
        body.clear()

    for line in markdown.split("\n"):
        marker = _SEMANTIC_MARKER.match(line.strip())
        if marker:
            semantic = marker.group(1)
            continue
        heading = _HEADING.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            title = heading.group(2).strip()
            continue
        body.append(line)
    flush()
    return result


def legacy_chunks(
    document_id: str,
    markdown: str,
    *,
    title: str,
    semantic_max_tokens: int = 1024,
    sliding_window_size: int = 512,
    sliding_overlap: int = 128,
    min_chunk_tokens: int = 50,
) -> list[LegacyChunk]:
    """Reproduce ``feature/rag-graph`` chunk IDs and chunk text."""

    chunks = [
        LegacyChunk(
            chunk_id=f"{document_id}__metadata_0000",
            chunk_level="metadata",
            chunk_seq=0,
            text=f"标题: {title}" if title else "",
            section_title="元数据",
        )
    ]
    sequence = 0
    for semantic, _level, heading, body in _sections(markdown):
        paragraphs = [item.strip() for item in re.split(r"\n\s*\n", body) if item.strip()]
        for paragraph in _split_long_paragraphs(paragraphs, semantic_max_tokens):
            if _estimate_tokens(paragraph) < min_chunk_tokens:
                continue
            sequence += 1
            section = f"{semantic} / {heading}" if semantic else heading
            chunks.append(
                LegacyChunk(
                    chunk_id=f"{document_id}__semantic_{sequence:04d}",
                    chunk_level="semantic",
                    chunk_seq=sequence,
                    text=paragraph,
                    section_title=section or None,
                )
            )

    body_lines = [
        line
        for line in markdown.split("\n")
        if not _SEMANTIC_MARKER.match(line.strip()) and not _HEADING.match(line)
    ]
    flattened = re.sub(r"\s+", " ", "\n".join(body_lines)).strip()
    window_chars = int(sliding_window_size * 1.5)
    overlap_chars = int(sliding_overlap * 1.5)
    start = 0
    while flattened and start < len(flattened):
        end = min(start + window_chars, len(flattened))
        text = flattened[start:end].strip()
        if _estimate_tokens(text) >= min_chunk_tokens:
            sequence += 1
            chunks.append(
                LegacyChunk(
                    chunk_id=f"{document_id}__sliding_{sequence:04d}",
                    chunk_level="sliding",
                    chunk_seq=sequence,
                    text=text,
                    section_title=f"滑动窗口 {sequence}",
                )
            )
        if end >= len(flattened):
            break
        start = end - overlap_chars
    return chunks


def _metadata(path: Path, *, expected_sha256: str | None = None) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        if expected_sha256:
            actual = hashlib.sha256(raw).hexdigest()
            if actual != expected_sha256.casefold():
                raise ValueError(f"metadata hash mismatch for {path.name}")
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(value, dict):
        return {}
    extra = value.get("extra_info")
    if isinstance(extra, dict) and extra:
        result = dict(extra)
        result["doc_id"] = value.get("doc_id") or result.get("doc_id")
        result["title"] = result.get("title") or value.get("title") or result.get("doc_id")
        result["doc_type"] = value.get("doc_type") or result.get("doc_type")
        return result
    return value


def _registry_boolean(value: object, *, document_id: str) -> bool:
    normalized = str(value or "").strip().casefold()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(
        f"document registry has invalid has_fulltext value for {document_id}"
    )


def _load_document_registry(
    path: Path,
    *,
    max_records: int,
) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"document registry does not exist: {path}")
    result: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        if not {"doc_id", "has_fulltext"}.issubset(fields):
            raise ValueError("document registry requires doc_id and has_fulltext columns")
        for row_number, row in enumerate(reader, 2):
            if len(result) >= max_records:
                raise ValueError(
                    f"document registry exceeds configured record limit {max_records}"
                )
            document_id = str(row.get("doc_id") or "").strip()
            if not document_id or Path(document_id).name != document_id:
                raise ValueError(f"invalid doc_id in document registry row {row_number}")
            if document_id in result:
                raise ValueError(f"duplicate doc_id in document registry: {document_id}")
            normalized = {
                key: str(value or "").strip()
                for key, value in row.items()
                if key is not None
            }
            normalized["has_fulltext"] = _registry_boolean(
                normalized.get("has_fulltext"),
                document_id=document_id,
            )
            result[document_id] = normalized
    return result


def _safe_document_path(root: Path, document_id: str, suffix: str) -> Path | None:
    if not document_id or Path(document_id).name != document_id:
        return None
    resolved_root = root.resolve()
    candidate = (resolved_root / f"{document_id}{suffix}").resolve()
    if candidate.parent != resolved_root:
        return None
    return candidate


class LegacyChunkResolver:
    """Lazily hydrate legacy HDF5 chunk metadata from read-only source files."""

    def __init__(
        self,
        cleaned_dir: Path,
        metadata_dir: Path | None = None,
        document_registry_path: Path | None = None,
        *,
        max_registry_records: int = 250_000,
    ) -> None:
        self.cleaned_dir = cleaned_dir
        self.metadata_dir = metadata_dir
        self.registry_configured = document_registry_path is not None
        self.document_registry = (
            _load_document_registry(
                document_registry_path,
                max_records=max_registry_records,
            )
            if document_registry_path is not None
            else {}
        )
        self._documents: dict[str, dict[str, dict[str, Any]]] = {}
        self._lock = threading.RLock()

    def document_has_fulltext(self, metadata: dict[str, Any]) -> bool:
        """Return the authoritative document-level full-text classification."""

        document_id = str(metadata.get("doc_id") or metadata.get("document_id") or "")
        registry = self.document_registry.get(document_id)
        if registry is not None:
            return bool(registry["has_fulltext"])
        if self.registry_configured:
            return False
        doc_type = str(metadata.get("doc_type") or "").strip().casefold()
        extraction_method = str(
            metadata.get("extraction_method") or ""
        ).strip().casefold()
        if doc_type == "feed_api" or extraction_method == "feed_api":
            return False
        return "-fulltext-" in document_id or "legacy-fulltext" in document_id

    def resolve(self, metadata: dict[str, Any]) -> dict[str, Any]:
        document_id = str(metadata.get("doc_id") or metadata.get("document_id") or "")
        chunk_id = str(metadata.get("chunk_id") or "")
        if not document_id or not chunk_id:
            return {}
        with self._lock:
            if document_id not in self._documents:
                self._documents[document_id] = self._load_document(document_id)
            return dict(self._documents[document_id].get(chunk_id, {}))

    def _load_document(self, document_id: str) -> dict[str, dict[str, Any]]:
        markdown_path = _safe_document_path(self.cleaned_dir, document_id, ".md")
        if markdown_path is None or not markdown_path.is_file():
            return {}
        raw = markdown_path.read_bytes()
        try:
            markdown = raw.decode("utf-8")
        except UnicodeDecodeError:
            return {}
        registry = self.document_registry.get(document_id, {})
        expected_cleaned_hash = str(registry.get("cleaned_md_sha256") or "").casefold()
        actual_cleaned_hash = hashlib.sha256(raw).hexdigest()
        if expected_cleaned_hash and expected_cleaned_hash != actual_cleaned_hash:
            raise ValueError(f"cleaned document hash mismatch for {document_id}")
        metadata: dict[str, Any] = {}
        if self.metadata_dir is not None:
            metadata_path = _safe_document_path(self.metadata_dir, document_id, ".json")
            if metadata_path is not None and metadata_path.is_file():
                metadata = _metadata(
                    metadata_path,
                    expected_sha256=str(registry.get("metadata_sha256") or "") or None,
                )
        title = str(registry.get("title") or metadata.get("title") or document_id)
        document_version = f"sha256:{actual_cleaned_hash}"
        document_has_fulltext = self.document_has_fulltext(
            {"document_id": document_id, **metadata}
        )
        result: dict[str, dict[str, Any]] = {}
        for chunk in legacy_chunks(document_id, markdown, title=title):
            text = chunk.text.strip()
            if not text:
                continue
            year = registry.get("publication_year") or metadata.get("year")
            try:
                publication_year = int(year) if year is not None else None
            except (TypeError, ValueError):
                publication_year = None
            if publication_year is not None and not 1500 <= publication_year <= 3000:
                publication_year = None
            chunk_has_fulltext = (
                document_has_fulltext and chunk.chunk_level != "metadata"
            )
            result[chunk.chunk_id] = {
                "document_id": document_id,
                "document_version": document_version,
                "chunk_id": chunk.chunk_id,
                "chunk_level": chunk.chunk_level,
                "chunk_seq": chunk.chunk_seq,
                "text": text,
                "title": title,
                "source_type": "paper",
                "source_locator": {
                    "section": chunk.section_title or f"legacy chunk {chunk.chunk_id}"
                },
                "doi": registry.get("doi") or metadata.get("doi"),
                "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "has_fulltext": chunk_has_fulltext,
                "evidence_status": (
                    "fulltext_located" if chunk_has_fulltext else "metadata_only"
                ),
                "publication_year": publication_year,
                "metadata": {
                    **metadata,
                    "registry_has_fulltext": document_has_fulltext,
                    "registry_access_level": registry.get("access_level"),
                    "registry_license_or_authorization": registry.get(
                        "license_or_authorization"
                    ),
                },
            }
        return result
