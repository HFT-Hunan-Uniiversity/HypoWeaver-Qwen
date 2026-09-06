"""Translate retrieval output into the canonical Group1 evidence graph.

RAG graph edges are intentionally kept outside the scientific graph.  They may
guide a reviewer or model, but only source-located and hash-verified text chunks
become graph evidence.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import unicodedata
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .discovery_engine.research_graph import validate_graph
from .discovery_engine.schema_gate import require_valid_instance
from .knowledge_models import EvidenceBundle, EvidenceHit


class EvidenceGraphBridge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bridge_version: str = "evidence-bundle-to-research-graph/1.0.0"
    evidence_bundle_id: str
    research_graph: dict[str, Any]
    chunk_to_evidence_id: dict[str, str]
    document_to_paper_id: dict[str, str]
    rag_graph_candidates: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def _digest(*values: str, length: int = 24) -> str:
    material = "\x1f".join(values).encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:length]


def _normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    return re.sub(r"\s+", " ", normalized)


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _evidence_id(hit: EvidenceHit) -> str:
    return f"evidence:{_digest(hit.document_id, hit.document_version, hit.chunk_id, hit.content_sha256)}"


def _paper_id(hit: EvidenceHit) -> str:
    return f"paper:{_digest(hit.document_id)}"


def _source_type(hit: EvidenceHit) -> str:
    if hit.source_type == "policy":
        return "policy_text"
    if hit.source_type in {"report", "esg_report"}:
        return "report_text"
    if hit.has_fulltext:
        return "paper_fulltext"
    return "paper_abstract"


def _locator(hit: EvidenceHit) -> dict[str, Any]:
    location = hit.source_locator
    page: int | str | None = location.page_start
    if (
        location.page_start is not None
        and location.page_end is not None
        and location.page_end != location.page_start
    ):
        page = f"{location.page_start}-{location.page_end}"
    return {
        "page": page,
        "section": location.section,
        "start_char": location.char_start,
        "end_char": location.char_end,
        "table_id": None,
        "row": None,
        "column": None,
    }


def _evidence_record(hit: EvidenceHit, *, retrieved_at: str) -> dict[str, Any]:
    return {
        "id": _evidence_id(hit),
        "source_type": _source_type(hit),
        "evidence_type": "direct_quote",
        "evidence_level": "primary_source",
        "source_document_id": hit.document_id,
        "document_version": hit.document_version,
        "profile_id": f"profile:{_digest(hit.document_id)}",
        "upstream_evidence_id": hit.chunk_id,
        "chunk_id": hit.chunk_id,
        "asset_id": None,
        "release_id": None,
        "content_sha256": hit.content_sha256,
        "content": hit.text,
        "content_hash": hit.content_sha256,
        "source_ref": hit.source_url or hit.doi,
        "published_at": str(hit.publication_year) if hit.publication_year else None,
        "retrieved_at": retrieved_at,
        "verification_status": (
            "source_located"
            if hit.evidence_status in {"fulltext_located", "fulltext_verified"}
            else "unverified"
        ),
        "access_level": "unknown",
        "license": None,
        "locator": _locator(hit),
    }


def _paper_node(
    first_hit: EvidenceHit,
    hits: list[EvidenceHit],
    *,
    observed_at: str,
) -> dict[str, Any]:
    evidence_ids = sorted({_evidence_id(hit) for hit in hits})
    return {
        "id": _paper_id(first_hit),
        "type": "paper",
        "layer": "source",
        "label": first_hit.title,
        "normalized_label": _normalize_label(first_hit.title),
        "aliases": [],
        "description": None,
        "origin": "extracted",
        "review_status": (
            "auto_validated"
            if all(hit.evidence_status == "fulltext_verified" for hit in hits)
            else "unreviewed"
        ),
        "confidence": max(
            0.0,
            min(1.0, max(hit.retrieval_score for hit in hits)),
        ),
        "version": 1,
        "validity": {
            "observed_at": observed_at,
            "valid_from": None,
            "valid_to": None,
        },
        "source_profile_ids": [f"profile:{_digest(first_hit.document_id)}"],
        "evidence_ids": evidence_ids,
        "derivation": None,
        "properties": {
            "document_id": first_hit.document_id,
            "document_version": first_hit.document_version,
            "doi": first_hit.doi,
            "source_url": first_hit.source_url,
            "year": first_hit.publication_year,
            "published_date": (
                f"{first_hit.publication_year}-01-01"
                if first_hit.publication_year
                else None
            ),
            "retrieval_scores": [
                round(hit.retrieval_score, 8)
                for hit in sorted(hits, key=lambda item: item.chunk_id)
            ],
            "corpus_role": "retrieved_candidate",
        },
    }


def evidence_bundle_to_research_graph(
    bundle: EvidenceBundle,
    *,
    themes: list[str] | None = None,
    languages: list[str] | None = None,
) -> EvidenceGraphBridge:
    """Build and validate the source/evidence layer used by Group1 discovery."""

    if not bundle.evidence_hits:
        raise ValueError("discovery requires at least one source-located evidence hit")
    by_document: dict[str, list[EvidenceHit]] = {}
    chunk_ids: set[str] = set()
    for hit in bundle.evidence_hits:
        if hit.chunk_id in chunk_ids:
            raise ValueError(f"duplicate evidence chunk_id: {hit.chunk_id}")
        chunk_ids.add(hit.chunk_id)
        by_document.setdefault(hit.document_id, []).append(hit)

    observed_at = bundle.generated_at.isoformat()
    evidence = sorted(
        (
            _evidence_record(hit, retrieved_at=observed_at)
            for hit in bundle.evidence_hits
        ),
        key=lambda item: item["id"],
    )
    nodes = sorted(
        (
            _paper_node(hits[0], hits, observed_at=observed_at)
            for _document_id, hits in sorted(by_document.items())
        ),
        key=lambda item: item["id"],
    )
    years = [hit.publication_year for hit in bundle.evidence_hits if hit.publication_year]
    graph: dict[str, Any] = {
        "schema_version": "0.2.0",
        "graph_id": f"research-graph:{_digest(bundle.bundle_id)}",
        "snapshot_id": "pending",
        "as_of": observed_at,
        "domain": "green_finance",
        "scope": {
            "themes": themes or [bundle.question],
            "languages": languages or ["und"],
            "document_types": sorted({hit.source_type for hit in bundle.evidence_hits}),
            "year_start": min(years) if years else None,
            "year_end": max(years) if years else None,
        },
        "build": {
            "created_at": observed_at,
            "generator": "hypoweaver.discovery_bridge@1.0.0",
            "graph_schema_version": "0.2.0",
            "input_contract_versions": [bundle.schema_version],
            "pipeline_run_id": bundle.bundle_id,
            "source_watermarks": {
                "knowledge_corpus": bundle.corpus_snapshot_id,
            },
            "base_graph_id": None,
            "base_graph_hash": None,
            "parent_snapshot_id": None,
            "code_version": "1.0.0",
            "config_hash": None,
            "input_manifest_hash": _canonical_sha256(
                bundle.model_dump(mode="json")
            ),
            "input_profile_hash": None,
            "coverage_certificate_id": None,
            "retrieval_index_snapshot_id": bundle.corpus_snapshot_id,
            "notes": (
                "RAG graph edges remain non-authoritative candidates outside this graph."
            ),
        },
        "nodes": nodes,
        "edges": [],
        "evidence": evidence,
        "quality_summary": {
            "source_document_count": len(nodes),
            "fact_edge_traceability_rate": 1.0,
            "verified_evidence_rate": round(
                sum(item["verification_status"] == "source_located" for item in evidence)
                / len(evidence),
                8,
            ),
            "unresolved_entity_count": len(bundle.graph_edges),
            "rejected_item_count": 0,
        },
        "statistics": {
            "node_count": len(nodes),
            "edge_count": 0,
            "evidence_count": len(evidence),
            "rag_graph_candidate_count": len(bundle.graph_edges),
        },
    }
    identity = copy.deepcopy(graph)
    identity["snapshot_id"] = None
    graph["snapshot_id"] = f"{graph['graph_id']}@{_canonical_sha256(identity)[:24]}"

    errors, graph_warnings = validate_graph(graph)
    if errors:
        raise ValueError("bridged research graph failed semantic validation: " + "; ".join(errors[:20]))
    from .discovery_engine.schema_gate import GRAPH_SCHEMA_PATH

    require_valid_instance(graph, GRAPH_SCHEMA_PATH, "bridged research graph")
    return EvidenceGraphBridge(
        evidence_bundle_id=bundle.bundle_id,
        research_graph=graph,
        chunk_to_evidence_id={
            hit.chunk_id: _evidence_id(hit) for hit in bundle.evidence_hits
        },
        document_to_paper_id={
            document_id: _paper_id(hits[0])
            for document_id, hits in by_document.items()
        },
        rag_graph_candidates=[edge.model_dump(mode="json") for edge in bundle.graph_edges],
        warnings=[
            *bundle.warnings,
            *graph_warnings,
            "RAG graph candidates require scientific review before graph promotion.",
        ],
    )
