"""Dependency-free local vector retrieval for GreenFin chunks."""

from .vector_index import (
    ChunkRecord,
    EmbeddingBackend,
    HashingEmbeddingBackend,
    LocalVectorIndex,
    SearchResponse,
    SearchResult,
    build_index,
    read_chunks_jsonl,
)

__all__ = [
    "ChunkRecord",
    "EmbeddingBackend",
    "HashingEmbeddingBackend",
    "LocalVectorIndex",
    "SearchResponse",
    "SearchResult",
    "build_index",
    "read_chunks_jsonl",
]
