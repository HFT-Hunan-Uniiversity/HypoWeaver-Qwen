"""JATS full-text parsing and deterministic chunk generation."""

from .jats import (
    CHUNK_SCHEMA_VERSION,
    PARSED_DOCUMENT_SCHEMA_VERSION,
    PARSER_VERSION,
    build_parsed_batch,
    make_chunks,
    parse_jats_article,
)

__all__ = [
    "CHUNK_SCHEMA_VERSION",
    "PARSED_DOCUMENT_SCHEMA_VERSION",
    "PARSER_VERSION",
    "build_parsed_batch",
    "make_chunks",
    "parse_jats_article",
]
