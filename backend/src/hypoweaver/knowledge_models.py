"""Contracts shared by the knowledge service and the discovery workflow.

The knowledge graph is a retrieval aid.  Only ``EvidenceHit`` objects with a
stable source locator and content hash may cross into the scientific discovery
graph as evidence candidates.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


EvidenceStatus = Literal[
    "metadata_only",
    "candidate_unverified",
    "fulltext_located",
    "fulltext_verified",
]


def canonical_sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SourceLocator(BaseModel):
    """A stable location inside a source document."""

    model_config = ConfigDict(extra="forbid")

    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    section: str | None = Field(default=None, max_length=500)
    paragraph: int | None = Field(default=None, ge=1)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_ranges(self) -> "SourceLocator":
        if self.page_start is not None and self.page_end is not None:
            if self.page_end < self.page_start:
                raise ValueError("page_end must not precede page_start")
        if self.char_start is not None and self.char_end is not None:
            if self.char_end < self.char_start:
                raise ValueError("char_end must not precede char_start")
        if not any(
            value is not None
            for value in (
                self.page_start,
                self.section,
                self.paragraph,
                self.char_start,
            )
        ):
            raise ValueError("at least one source locator field is required")
        return self


class KnowledgeSearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_types: list[str] = Field(default_factory=list, max_length=20)
    publication_year_min: int | None = Field(default=None, ge=1500, le=3000)
    publication_year_max: int | None = Field(default=None, ge=1500, le=3000)
    fulltext_only: bool = True

    @model_validator(mode="after")
    def validate_years(self) -> "KnowledgeSearchFilters":
        if (
            self.publication_year_min is not None
            and self.publication_year_max is not None
            and self.publication_year_max < self.publication_year_min
        ):
            raise ValueError("publication_year_max must not precede publication_year_min")
        return self


class KnowledgeSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=2, max_length=4000)
    filters: KnowledgeSearchFilters = Field(default_factory=KnowledgeSearchFilters)
    top_k: int = Field(default=12, ge=1, le=100)
    max_graph_edges: int = Field(default=20, ge=0, le=100)
    diversity_mode: Literal["none", "per_document_cap"] = "per_document_cap"
    max_hits_per_document: int = Field(default=2, ge=1, le=20)
    min_unique_documents: int = Field(default=3, ge=1, le=100)
    as_of: date | None = None


class RetrievalDiagnostics(BaseModel):
    """Observable retrieval-gate result carried with every evidence bundle."""

    model_config = ConfigDict(extra="forbid")

    requested_top_k: int = Field(ge=1, le=100)
    returned_hits: int = Field(ge=0, le=100)
    unique_document_count: int = Field(ge=0, le=100)
    max_hits_from_one_document: int = Field(ge=0, le=100)
    diversity_mode: Literal["none", "per_document_cap"]
    max_hits_per_document: int = Field(ge=1, le=20)
    effective_min_unique_documents: int = Field(ge=1, le=100)
    diversity_gate_passed: bool
    skipped_by_document_cap: int = Field(default=0, ge=0)


class EvidenceHit(BaseModel):
    """Retrieval result that can be audited before scientific use."""

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=500)
    document_version: str = Field(min_length=1, max_length=200)
    chunk_id: str = Field(min_length=1, max_length=700)
    text: str = Field(min_length=1, max_length=100_000)
    title: str = Field(min_length=1, max_length=2000)
    source_type: str = Field(min_length=1, max_length=100)
    source_locator: SourceLocator
    source_url: str | None = Field(default=None, max_length=4000)
    doi: str | None = Field(default=None, max_length=500)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    retrieval_score: float = Field(ge=-1.0, le=1.0)
    has_fulltext: bool
    evidence_status: EvidenceStatus
    publication_year: int | None = Field(default=None, ge=1500, le=3000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content_sha256")
    @classmethod
    def normalize_hash(cls, value: str) -> str:
        return value.casefold()

    @model_validator(mode="after")
    def validate_evidence_status(self) -> "EvidenceHit":
        actual = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
        if actual != self.content_sha256:
            raise ValueError("content_sha256 does not match evidence text")
        if self.evidence_status in {"fulltext_located", "fulltext_verified"}:
            if not self.has_fulltext:
                raise ValueError("located or verified evidence must have full text")
        return self


class GraphEdgeCandidate(BaseModel):
    """Non-authoritative relation candidate returned by the RAG graph."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=1000)
    relation: str = Field(min_length=1, max_length=200)
    target: str = Field(min_length=1, max_length=1000)
    evidence_refs: list[str] = Field(default_factory=list, max_length=100)
    source_document_ids: list[str] = Field(default_factory=list, max_length=100)
    confidence: float = Field(ge=0.0, le=1.0)
    extraction_model: str | None = Field(default=None, max_length=300)
    extraction_version: str | None = Field(default=None, max_length=200)


class EvidenceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["evidence-bundle/1.0.0"] = "evidence-bundle/1.0.0"
    bundle_id: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=2, max_length=4000)
    as_of: date
    generated_at: datetime
    generator: str = Field(min_length=1, max_length=300)
    corpus_snapshot_id: str = Field(min_length=1, max_length=500)
    evidence_hits: list[EvidenceHit]
    graph_edges: list[GraphEdgeCandidate] = Field(default_factory=list)
    retrieval_diagnostics: RetrievalDiagnostics
    warnings: list[str] = Field(default_factory=list, max_length=100)

    @classmethod
    def build(
        cls,
        *,
        request: KnowledgeSearchRequest,
        corpus_snapshot_id: str,
        evidence_hits: list[EvidenceHit],
        graph_edges: list[GraphEdgeCandidate] | None = None,
        warnings: list[str] | None = None,
        skipped_by_document_cap: int = 0,
        generated_at: datetime | None = None,
        generator: str = "hypoweaver-knowledge@1.0.0",
    ) -> "EvidenceBundle":
        timestamp = generated_at or datetime.now(timezone.utc)
        as_of = request.as_of or timestamp.date()
        document_counts: dict[str, int] = {}
        for hit in evidence_hits:
            document_counts[hit.document_id] = document_counts.get(hit.document_id, 0) + 1
        effective_minimum = min(request.top_k, request.min_unique_documents)
        diagnostics = RetrievalDiagnostics(
            requested_top_k=request.top_k,
            returned_hits=len(evidence_hits),
            unique_document_count=len(document_counts),
            max_hits_from_one_document=max(document_counts.values(), default=0),
            diversity_mode=request.diversity_mode,
            max_hits_per_document=request.max_hits_per_document,
            effective_min_unique_documents=effective_minimum,
            diversity_gate_passed=(
                len(document_counts) >= effective_minimum
                and (
                    request.diversity_mode == "none"
                    or max(document_counts.values(), default=0)
                    <= request.max_hits_per_document
                )
            ),
            skipped_by_document_cap=skipped_by_document_cap,
        )
        identity = {
            "schema_version": "evidence-bundle/1.0.0",
            "question": request.question,
            "as_of": as_of.isoformat(),
            "corpus_snapshot_id": corpus_snapshot_id,
            "evidence": [
                [hit.document_id, hit.document_version, hit.chunk_id, hit.content_sha256]
                for hit in evidence_hits
            ],
            "graph_edges": [edge.model_dump(mode="json") for edge in graph_edges or []],
            "retrieval_diagnostics": diagnostics.model_dump(mode="json"),
        }
        return cls(
            bundle_id=f"evidence-bundle:{canonical_sha256(identity)[:24]}",
            question=request.question,
            as_of=as_of,
            generated_at=timestamp,
            generator=generator,
            corpus_snapshot_id=corpus_snapshot_id,
            evidence_hits=evidence_hits,
            graph_edges=graph_edges or [],
            retrieval_diagnostics=diagnostics,
            warnings=warnings or [],
        )


class KnowledgeServiceStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "degraded", "empty"]
    corpus_snapshot_id: str
    vector_backend: str
    vector_count: int = Field(ge=0)
    graph_document_count: int = Field(ge=0)
    graph_edge_count: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)


class KnowledgeCatalogDocument(BaseModel):
    """One browseable record from the mounted knowledge snapshot.

    Catalog records are inventory metadata.  ``indexed_fulltext`` means the
    service can retrieve source-located text from the cleaned corpus; it does
    not mean that an original PDF is present.
    """

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=2000)
    title_source: Literal["metadata", "derived", "identifier"]
    authors: list[str] = Field(default_factory=list, max_length=200)
    abstract: str | None = Field(default=None, max_length=20_000)
    journal: str | None = Field(default=None, max_length=1000)
    doi: str | None = Field(default=None, max_length=500)
    publication_year: int | None = Field(default=None, ge=1500, le=3000)
    has_fulltext: bool
    content_kind: Literal["indexed_fulltext", "metadata_only"]
    source_format: str = Field(min_length=1, max_length=100)
    access_level: str | None = Field(default=None, max_length=300)
    original_pdf_available: bool = False
    reading_available: bool = False


class KnowledgeCatalogPage(BaseModel):
    """Corpus inventory plus one bounded page of document metadata."""

    model_config = ConfigDict(extra="forbid")

    corpus_snapshot_id: str = Field(min_length=1, max_length=500)
    total_documents: int = Field(ge=0)
    fulltext_documents: int = Field(ge=0)
    readable_documents: int = Field(ge=0)
    metadata_only_documents: int = Field(ge=0)
    declared_source_asset_documents: int = Field(ge=0)
    available_source_asset_documents: int = Field(ge=0)
    original_pdf_documents: int = Field(ge=0)
    vector_count: int = Field(ge=0)
    graph_document_count: int = Field(ge=0)
    graph_edge_count: int = Field(ge=0)
    matched_documents: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    next_offset: int | None = Field(default=None, ge=0)
    data_updated_at: str | None = Field(default=None, max_length=200)
    access_level: str | None = Field(default=None, max_length=300)
    source_format_counts: dict[str, int] = Field(default_factory=dict)
    collection_status: Literal["snapshot_only", "connected"] = "snapshot_only"
    collection_message: str = Field(min_length=1, max_length=1000)
    items: list[KnowledgeCatalogDocument]
    warnings: list[str] = Field(default_factory=list, max_length=100)


class KnowledgeDocumentTextSlice(BaseModel):
    """One bounded slice of a cleaned system-library document.

    This is readable corpus text, not an original PDF or page-faithful source.
    """

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=2000)
    source_format: str = Field(min_length=1, max_length=100)
    access_level: str | None = Field(default=None, max_length=300)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    total_characters: int = Field(ge=1)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=50_000)
    next_offset: int | None = Field(default=None, ge=0)
    text: str = Field(min_length=1, max_length=50_000)


class KnowledgeAnswerRequest(KnowledgeSearchRequest):
    max_answer_chars: int = Field(default=6000, ge=500, le=20_000)


class KnowledgeAnswerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    answer: str
    conclusion: str
    confidence: Literal["low", "medium", "high"]
    evidence_bundle: EvidenceBundle
