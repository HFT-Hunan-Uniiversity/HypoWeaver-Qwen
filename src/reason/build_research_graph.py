"""Build a deterministic v0.2 GreenFin graph from evidence-grounded PaperProfiles."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:  # Support both ``python file.py`` and ``python -m src.reason...``.
    from .schema_gate import (
        GRAPH_BUILD_MANIFEST_SCHEMA_PATH,
        GRAPH_SCHEMA_PATH,
        PROFILE_SCHEMA_PATH,
        require_valid_instance,
    )
    from .validate_research_graph import validate_graph
except ImportError:  # pragma: no cover - direct script execution path
    from schema_gate import (
        GRAPH_BUILD_MANIFEST_SCHEMA_PATH,
        GRAPH_SCHEMA_PATH,
        PROFILE_SCHEMA_PATH,
        require_valid_instance,
    )
    from validate_research_graph import validate_graph


NODE_LAYERS = {
    "paper": "source",
    "policy_document": "source",
    "report": "source",
    "dataset": "source",
    "author": "source",
    "institution": "source",
    "venue": "source",
    "research_field": "knowledge",
    "topic": "knowledge",
    "theory": "knowledge",
    "mechanism": "knowledge",
    "variable": "knowledge",
    "measure": "knowledge",
    "method": "knowledge",
    "model": "knowledge",
    "identification_strategy": "knowledge",
    "policy_instrument": "knowledge",
    "finding": "knowledge",
    "limitation": "knowledge",
    "population": "knowledge",
    "context": "knowledge",
    "research_stream": "analytics",
    "trend_snapshot": "analytics",
    "controversy": "analytics",
    "research_gap": "discovery",
    "hypothesis": "discovery",
}

SCIENTIFIC_SOURCE_TYPES = {"paper_fulltext", "policy_text", "report_text"}
SCIENTIFIC_EVIDENCE_TYPES = {"direct_quote", "table_cell"}
VERIFIED_EVIDENCE_STATUSES = {"source_located", "cross_checked"}
PAPER_SEMANTIC_SOURCE_TYPES = {"paper_fulltext", "paper_abstract"}


def _profile_semantic_evidence_refs(profile: dict[str, Any]) -> set[str]:
    refs = set(profile.get("research_question", {}).get("evidence_refs", []))
    for collection in (
        "research_fields",
        "topics",
        "theories",
        "mechanisms",
        "variables",
        "measures",
        "methods",
        "models",
        "identification_strategies",
        "datasets",
        "policies",
        "citations",
        "findings",
        "limitations",
        "future_work",
    ):
        for item in profile.get(collection, []):
            refs.update(item.get("evidence_refs", []))
    return refs


def _evidence_classification(
    profile: dict[str, Any], item: dict[str, Any]
) -> tuple[str, str, str]:
    """Return source/type/level, preferring explicit v0.2 fields.

    Legacy profiles are still accepted.  Legacy metadata-only evidence is
    classified as metadata.  A legacy evidence item reused by a semantic owner
    keeps the older locator-based inference so existing pilot fixtures continue
    to load while they are migrated to explicit fields.
    """

    explicit = (
        item.get("source_type"),
        item.get("evidence_type"),
        item.get("evidence_level"),
    )
    if any(value is not None for value in explicit):
        if not all(value is not None for value in explicit):
            raise ValueError(
                f"evidence {item.get('evidence_id')} must set source_type, "
                "evidence_type and evidence_level together"
            )
        return explicit  # type: ignore[return-value]

    evidence_id = item.get("evidence_id")
    metadata_refs = set(profile["document"].get("metadata_evidence_refs", []))
    semantic_refs = _profile_semantic_evidence_refs(profile)
    if evidence_id in metadata_refs and evidence_id not in semantic_refs:
        return "metadata_api", "metadata_record", "metadata"
    if item.get("chunk_id") or item.get("page"):
        return "paper_fulltext", "direct_quote", "primary_source"
    return "paper_abstract", "direct_quote", "metadata"


def _has_text_locator(item: dict[str, Any]) -> bool:
    for field in ("chunk_id", "page", "section"):
        value = item.get(field)
        if isinstance(value, str) and value.strip():
            return True
        if field == "page" and isinstance(value, int) and not isinstance(value, bool):
            return value >= 1
    start = item.get("start_char")
    end = item.get("end_char")
    return (
        isinstance(start, int)
        and not isinstance(start, bool)
        and isinstance(end, int)
        and not isinstance(end, bool)
        and 0 <= start < end
    )


def _is_scientific_profile_evidence(
    profile: dict[str, Any], item: dict[str, Any]
) -> bool:
    source_type, evidence_type, evidence_level = _evidence_classification(profile, item)
    return (
        source_type == "paper_fulltext"
        and evidence_type in SCIENTIFIC_EVIDENCE_TYPES
        and evidence_level == "primary_source"
        and item.get("verification_status") in VERIFIED_EVIDENCE_STATUSES
        and _has_text_locator(item)
    )


def _is_semantic_profile_evidence(
    profile: dict[str, Any], item: dict[str, Any]
) -> bool:
    source_type, evidence_type, evidence_level = _evidence_classification(profile, item)
    if source_type == "paper_fulltext":
        return _is_scientific_profile_evidence(profile, item)
    return (
        source_type == "paper_abstract"
        and evidence_type == "direct_quote"
        and evidence_level == "metadata"
        and item.get("verification_status") in VERIFIED_EVIDENCE_STATUSES
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_label(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip().casefold()
    return re.sub(r"\s+", " ", value)


def stable_id(prefix: str, *parts: object) -> str:
    material = "\x1f".join(normalize_label(str(part)) for part in parts)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}:{digest}"


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def profile_set_sha256(profiles: list[dict[str, Any]]) -> str:
    ordered = sorted(profiles, key=lambda item: str(item.get("profile_id", "")))
    return _canonical_sha256(ordered)


def _normalize_graph_order(graph: dict[str, Any]) -> None:
    """Canonicalize set-like arrays before hashing or publication."""

    for key in ("themes", "languages", "document_types"):
        values = graph.get("scope", {}).get(key)
        if isinstance(values, list):
            graph["scope"][key] = sorted(set(values))
    build = graph.get("build") or {}
    if isinstance(build.get("input_contract_versions"), list):
        build["input_contract_versions"] = sorted(
            set(build["input_contract_versions"])
        )
    for node in graph.get("nodes", []):
        for key in ("aliases", "source_profile_ids", "evidence_ids"):
            if isinstance(node.get(key), list):
                node[key] = sorted(set(node[key]))
        origins_seen = (node.get("properties") or {}).get("origins_seen")
        if isinstance(origins_seen, list):
            node["properties"]["origins_seen"] = sorted(set(origins_seen))
        properties = node.get("properties") or {}
        if isinstance(properties.get("research_question_evidence_ids"), list):
            properties["research_question_evidence_ids"] = sorted(
                set(properties["research_question_evidence_ids"])
            )
        if isinstance(properties.get("future_work_items"), list):
            for item in properties["future_work_items"]:
                if isinstance(item, dict) and isinstance(item.get("evidence_ids"), list):
                    item["evidence_ids"] = sorted(set(item["evidence_ids"]))
    for edge in graph.get("edges", []):
        if isinstance(edge.get("evidence_ids"), list):
            edge["evidence_ids"] = sorted(set(edge["evidence_ids"]))
    graph["nodes"] = sorted(graph.get("nodes", []), key=lambda item: item["id"])
    graph["edges"] = sorted(graph.get("edges", []), key=lambda item: item["id"])
    graph["evidence"] = sorted(
        graph.get("evidence", []), key=lambda item: item["id"]
    )


def _content_addressed_snapshot_id(graph: dict[str, Any]) -> str:
    payload = copy.deepcopy(graph)
    payload["snapshot_id"] = None
    return f"{graph['graph_id']}@{_canonical_sha256(payload)[:24]}"


def _review_status(profile: dict[str, Any]) -> str:
    status = profile["quality"]["human_review_status"]
    if status == "fully_reviewed":
        return "human_verified"
    if status == "sampled":
        return "auto_validated"
    return "unreviewed"


def _paper_identity_key(document: dict[str, Any]) -> str:
    if document.get("doi"):
        return f"doi:{document['doi']}"
    if document.get("document_id"):
        return f"document:{document['document_id']}"
    return f"title:{document['title']}|{document['year']}"


def new_graph(
    graph_id: str = "research-graph-v0",
    *,
    as_of: str | None = None,
    scope: dict[str, Any] | None = None,
    build_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    build_metadata = build_metadata or {}
    created_at = build_metadata.get("build_timestamp") or utc_now()
    return {
        "schema_version": "0.2.0",
        "graph_id": graph_id,
        "snapshot_id": f"{graph_id}@pending",
        "as_of": as_of or created_at,
        "domain": "green_finance",
        "scope": scope
        or {
            "themes": [],
            "languages": [],
            "document_types": ["paper"],
            "year_start": None,
            "year_end": None,
        },
        "build": {
            "created_at": created_at,
            "generator": "src/reason/build_research_graph.py",
            "graph_schema_version": "0.2.0",
            "input_contract_versions": ["paper-profile-graph-input/0.2.0"],
            "pipeline_run_id": build_metadata.get("pipeline_run_id")
            or stable_id("run", created_at),
            "source_watermarks": build_metadata.get("source_watermarks", {}),
            "base_graph_id": None,
            "base_graph_hash": build_metadata.get("base_graph_hash"),
            "parent_snapshot_id": None,
            "code_version": build_metadata.get("code_version"),
            "config_hash": build_metadata.get("config_hash"),
            "input_manifest_hash": build_metadata.get("input_manifest_hash"),
            "input_profile_hash": build_metadata.get("input_profile_hash"),
            "coverage_certificate_id": build_metadata.get("coverage_certificate_id"),
            "retrieval_index_snapshot_id": build_metadata.get(
                "retrieval_index_snapshot_id"
            ),
            "notes": build_metadata.get("notes"),
        },
        "nodes": [],
        "edges": [],
        "evidence": [],
        "quality_summary": {},
        "statistics": {},
    }


class GraphBuilder:
    def __init__(
        self,
        graph: dict[str, Any] | None = None,
        *,
        require_explicit_evidence: bool = False,
    ) -> None:
        has_prior_content = bool(
            graph
            and any(graph.get(key) for key in ("nodes", "edges", "evidence"))
        )
        self.parent_snapshot_id = graph.get("snapshot_id") if has_prior_content else None
        self.graph = copy.deepcopy(graph) if graph is not None else new_graph()
        self.require_explicit_evidence = require_explicit_evidence
        self.profile_fingerprints: dict[str, str] = {}
        self.node_by_id = {item["id"]: item for item in self.graph.get("nodes", [])}
        self.edge_by_id = {item["id"]: item for item in self.graph.get("edges", [])}
        self.evidence_by_id = {item["id"]: item for item in self.graph.get("evidence", [])}
        self.entity_index: dict[tuple[str, str], str] = {
            (item["type"], item["normalized_label"]): item["id"]
            for item in self.graph.get("nodes", [])
            if item.get("type") not in {"paper", "finding", "limitation"}
        }

    @staticmethod
    def _validate_profile(
        profile: dict[str, Any], *, require_explicit_evidence: bool = False
    ) -> None:
        require_valid_instance(profile, PROFILE_SCHEMA_PATH, "PaperProfile")
        required = {
            "schema_version",
            "profile_id",
            "document",
            "research_question",
            "research_fields",
            "topics",
            "theories",
            "mechanisms",
            "variables",
            "measures",
            "methods",
            "models",
            "identification_strategies",
            "datasets",
            "policies",
            "citations",
            "findings",
            "limitations",
            "future_work",
            "evidence",
            "quality",
        }
        missing = sorted(required - set(profile))
        if missing:
            raise ValueError(f"profile missing required fields: {missing}")
        if profile.get("schema_version") != "0.2.0":
            raise ValueError("profile schema_version must be 0.2.0")
        if profile.get("quality", {}).get("citation_verification_status") == "rejected":
            raise ValueError(f"profile {profile.get('profile_id')} has rejected document identity")

        local_evidence = {item.get("evidence_id"): item for item in profile["evidence"]}
        if None in local_evidence:
            raise ValueError("every profile evidence item needs evidence_id")
        if len(local_evidence) != len(profile["evidence"]):
            raise ValueError("profile contains duplicate evidence_id values")

        document = profile["document"]
        wrong_documents = sorted(
            item["evidence_id"] for item in profile["evidence"]
            if item.get("document_id") != document["document_id"]
        )
        if wrong_documents:
            raise ValueError(f"evidence has wrong document_id: {wrong_documents}")
        wrong_versions = sorted(
            item["evidence_id"] for item in profile["evidence"]
            if item.get("document_version") != document["document_version"]
        )
        if wrong_versions:
            raise ValueError(f"evidence has wrong document_version: {wrong_versions}")

        rejected_evidence = {
            evidence_id for evidence_id, item in local_evidence.items()
            if item.get("verification_status") == "rejected"
        }

        for evidence_id, item in local_evidence.items():
            if not isinstance(item.get("quote"), str) or not item["quote"].strip():
                raise ValueError(f"evidence {evidence_id} quote must not be blank")
            explicit_values = (
                item.get("source_type"),
                item.get("evidence_type"),
                item.get("evidence_level"),
            )
            if require_explicit_evidence and not all(explicit_values):
                raise ValueError(
                    f"formal build requires explicit source_type, evidence_type "
                    f"and evidence_level for evidence {evidence_id}"
                )
            source_type, evidence_type, evidence_level = _evidence_classification(profile, item)
            if source_type in SCIENTIFIC_SOURCE_TYPES:
                if evidence_type not in SCIENTIFIC_EVIDENCE_TYPES:
                    raise ValueError(
                        f"evidence {evidence_id} source_type={source_type} requires "
                        "direct_quote or table_cell"
                    )
                if evidence_level != "primary_source":
                    raise ValueError(
                        f"evidence {evidence_id} source_type={source_type} requires "
                        "evidence_level=primary_source"
                    )
            elif source_type == "metadata_api":
                if (evidence_type, evidence_level) != ("metadata_record", "metadata"):
                    raise ValueError(
                        f"evidence {evidence_id} metadata_api requires "
                        "metadata_record + metadata"
                    )
            elif source_type == "paper_abstract" and evidence_level != "metadata":
                raise ValueError(
                    f"evidence {evidence_id} paper_abstract requires evidence_level=metadata"
                )
            for locator_field in ("chunk_id", "section"):
                locator_value = item.get(locator_field)
                if isinstance(locator_value, str) and not locator_value.strip():
                    raise ValueError(
                        f"evidence {evidence_id} {locator_field} must not be blank"
                    )
            start = item.get("start_char")
            end = item.get("end_char")
            if (start is None) != (end is None) or (
                isinstance(start, int)
                and isinstance(end, int)
                and start >= end
            ):
                raise ValueError(
                    f"evidence {evidence_id} character locator must satisfy "
                    "0 <= start_char < end_char"
                )

        def check_refs(owner: str, refs: list[str] | None) -> None:
            if not refs:
                raise ValueError(f"{owner} has no evidence_refs")
            missing_refs = sorted(set(refs) - set(local_evidence))
            if missing_refs:
                raise ValueError(f"{owner} references missing evidence: {missing_refs}")
            rejected_refs = sorted(set(refs) & rejected_evidence)
            if rejected_refs:
                raise ValueError(f"{owner} references rejected evidence: {rejected_refs}")

        def check_scientific_refs(owner: str, refs: list[str] | None) -> None:
            check_refs(owner, refs)
            assert refs is not None
            if not any(
                _is_scientific_profile_evidence(profile, local_evidence[evidence_id])
                for evidence_id in refs
            ):
                raise ValueError(
                    f"{owner} requires located, verified fulltext evidence"
                )

        def check_semantic_refs(owner: str, refs: list[str] | None) -> None:
            check_refs(owner, refs)
            assert refs is not None
            if not any(
                _is_semantic_profile_evidence(profile, local_evidence[evidence_id])
                for evidence_id in refs
            ):
                raise ValueError(
                    f"{owner} requires verified paper abstract or paper fulltext evidence"
                )

        check_refs("document_metadata", document.get("metadata_evidence_refs"))
        check_refs("research_question", profile["research_question"].get("evidence_refs"))
        collections = (
            "research_fields",
            "topics",
            "theories",
            "mechanisms",
            "variables",
            "measures",
            "methods",
            "models",
            "identification_strategies",
            "datasets",
            "policies",
            "citations",
            "findings",
            "limitations",
            "future_work",
        )
        for collection in collections:
            for item in profile[collection]:
                identity = (
                    item.get("local_id")
                    or item.get("finding_id")
                    or item.get("limitation_id")
                    or item.get("target_document_id")
                    or item.get("target_title")
                    or collection
                )
                check_refs(f"{collection}:{identity}", item.get("evidence_refs"))

        check_scientific_refs(
            "research_question", profile["research_question"].get("evidence_refs")
        )
        for collection in (
            "theories",
            "mechanisms",
            "variables",
            "measures",
            "methods",
            "models",
            "identification_strategies",
            "findings",
            "limitations",
            "future_work",
        ):
            for item in profile[collection]:
                identity = (
                    item.get("local_id")
                    or item.get("finding_id")
                    or item.get("limitation_id")
                    or collection
                )
                check_scientific_refs(
                    f"{collection}:{identity}", item.get("evidence_refs")
                )
        for collection in ("research_fields", "topics", "datasets", "policies"):
            for item in profile[collection]:
                check_semantic_refs(
                    f"{collection}:{item.get('local_id')}",
                    item.get("evidence_refs"),
                )
        for citation in profile["citations"]:
            if citation.get("relation") != "cites":
                check_scientific_refs(
                    f"citations:{citation.get('target_title')}",
                    citation.get("evidence_refs"),
                )

        def local_ids(collection: str) -> set[str]:
            values = [item["local_id"] for item in profile[collection]]
            if len(values) != len(set(values)):
                raise ValueError(f"{collection} contains duplicate local_id values")
            return set(values)

        variable_ids = local_ids("variables")
        mechanism_ids = local_ids("mechanisms")
        measure_ids = local_ids("measures")
        dataset_ids = local_ids("datasets")
        method_ids = local_ids("methods")
        model_ids = local_ids("models")
        identification_ids = local_ids("identification_strategies")

        for variable in profile["variables"]:
            unknown = sorted(set(variable.get("measure_refs", [])) - measure_ids)
            if unknown:
                raise ValueError(f"variable {variable['local_id']} has unknown measure_refs: {unknown}")
        for measure in profile["measures"]:
            unknown = sorted(set(measure.get("data_source_refs", [])) - dataset_ids)
            if unknown:
                raise ValueError(f"measure {measure['local_id']} has unknown data_source_refs: {unknown}")
        for finding in profile["findings"]:
            for field in ("predictor_refs", "outcome_refs", "mediator_refs", "moderator_refs"):
                unknown = sorted(set(finding.get(field, [])) - variable_ids)
                if unknown:
                    raise ValueError(f"finding {finding['finding_id']} has unknown {field}: {unknown}")
            reference_sets = (
                ("mechanism_refs", mechanism_ids),
                ("method_refs", method_ids),
                ("model_refs", model_ids),
                ("identification_strategy_refs", identification_ids),
            )
            for field, valid_ids in reference_sets:
                unknown = sorted(set(finding.get(field, [])) - valid_ids)
                if unknown:
                    raise ValueError(f"finding {finding['finding_id']} has unknown {field}: {unknown}")

        rejected_citations = [
            item["target_title"] for item in profile["citations"]
            if item["identity_status"] == "rejected"
        ]
        if rejected_citations:
            raise ValueError(f"profile contains rejected citation identities: {rejected_citations}")

    def _add_evidence(self, profile: dict[str, Any]) -> dict[str, str]:
        profile_id = profile["profile_id"]
        document = profile["document"]
        mapping: dict[str, str] = {}
        for item in profile["evidence"]:
            local_id = item["evidence_id"]
            global_id = stable_id("ev", profile_id, local_id)
            mapping[local_id] = global_id
            content = item["quote"]
            source_type, evidence_type, evidence_level = _evidence_classification(
                profile, item
            )
            graph_item = {
                "id": global_id,
                "source_type": source_type,
                "evidence_type": evidence_type,
                "evidence_level": evidence_level,
                "source_document_id": item["document_id"],
                "document_version": item["document_version"],
                "profile_id": profile_id,
                "upstream_evidence_id": local_id,
                "chunk_id": item.get("chunk_id"),
                "asset_id": item.get("asset_id") or document.get("asset_id"),
                "release_id": item.get("release_id") or document.get("release_id"),
                "content_sha256": item.get("content_sha256")
                or document.get("content_sha256"),
                "content": content,
                "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "source_ref": item.get("source_uri") or document.get("source_uri"),
                "published_at": document.get("published_date") or str(document["year"]),
                "retrieved_at": item["retrieved_at"],
                "verification_status": item["verification_status"],
                "access_level": item.get("access_level", "unknown"),
                "license": item.get("license"),
                "locator": {
                    "page": item.get("page"),
                    "section": item.get("section"),
                    "start_char": item.get("start_char"),
                    "end_char": item.get("end_char"),
                    "table_id": None,
                    "row": None,
                    "column": None,
                },
            }
            existing = self.evidence_by_id.get(global_id)
            if existing is not None:
                if existing != graph_item:
                    raise ValueError(
                        f"evidence id collision for {global_id}: profile_id/local "
                        "evidence ID resolves to different content or provenance"
                    )
                continue
            self.graph["evidence"].append(graph_item)
            self.evidence_by_id[global_id] = graph_item
        return mapping

    def _add_or_merge_node(
        self,
        *,
        node_type: str,
        label: str,
        evidence_ids: list[str],
        profile_id: str,
        confidence: float,
        review_status: str,
        observed_at: str,
        description: str | None = None,
        aliases: list[str] | None = None,
        properties: dict[str, Any] | None = None,
        scoped_key: str | None = None,
    ) -> str:
        normalized = normalize_label(label)
        if scoped_key is None and node_type not in {"paper", "finding", "limitation"}:
            node_id = self.entity_index.get((node_type, normalized))
        else:
            node_id = stable_id(node_type, scoped_key or profile_id)

        if node_id and node_id in self.node_by_id:
            node = self.node_by_id[node_id]
            incoming_properties = properties or {}
            merge_evidence = True
            if node_type == "paper":
                existing_properties = node.get("properties") or {}
                existing_stub = bool(existing_properties.get("stub", False))
                incoming_stub = bool(incoming_properties.get("stub", False))
                if not existing_stub and not incoming_stub:
                    existing_document_id = existing_properties.get("document_id")
                    incoming_document_id = incoming_properties.get("document_id")
                    if (
                        existing_document_id
                        and incoming_document_id
                        and existing_document_id != incoming_document_id
                    ):
                        raise ValueError(
                            f"paper identity collision for {node_id}: DOI/title identity "
                            f"maps to both {existing_document_id} and {incoming_document_id}"
                        )
                if existing_stub and not incoming_stub:
                    previous_label = node.get("label")
                    node["properties"] = copy.deepcopy(incoming_properties)
                    node["label"] = label
                    node["normalized_label"] = normalized
                    node["description"] = description
                    node["evidence_ids"] = _unique(evidence_ids)
                    if previous_label and previous_label != label:
                        aliases = [*(aliases or []), str(previous_label)]
                    merge_evidence = False
                elif not existing_stub and incoming_stub:
                    # A citation mention belongs on the CITES edge.  Keeping its
                    # evidence on an already materialized paper node would make
                    # another paper's text look like evidence for this document.
                    if label != node.get("label"):
                        aliases = [*(aliases or []), label]
                    merge_evidence = False
            if merge_evidence:
                node["evidence_ids"] = _unique([*node["evidence_ids"], *evidence_ids])
            node["source_profile_ids"] = _unique([*node["source_profile_ids"], profile_id])
            node["aliases"] = _unique([*node.get("aliases", []), *(aliases or [])])
            node["confidence"] = max(float(node.get("confidence", 0)), confidence)
            if review_status == "human_verified" or (
                review_status == "auto_validated" and node.get("review_status") == "unreviewed"
            ):
                node["review_status"] = review_status
            origins = node.setdefault("properties", {}).setdefault("origins_seen", [])
            if "extracted" not in origins:
                origins.append("extracted")
            return node_id

        if node_id is None:
            node_id = stable_id(node_type, normalized)
        node = {
            "id": node_id,
            "type": node_type,
            "layer": NODE_LAYERS[node_type],
            "label": label,
            "normalized_label": normalized,
            "aliases": _unique(aliases or []),
            "description": description,
            "origin": "extracted",
            "review_status": review_status,
            "confidence": confidence,
            "version": 1,
            "validity": {"observed_at": observed_at, "valid_from": None, "valid_to": None},
            "source_profile_ids": [profile_id],
            "evidence_ids": _unique(evidence_ids),
            "derivation": None,
            "properties": properties or {},
        }
        self.graph["nodes"].append(node)
        self.node_by_id[node_id] = node
        if node_type not in {"paper", "finding", "limitation"}:
            self.entity_index[(node_type, normalized)] = node_id
        return node_id

    def _add_edge(
        self,
        *,
        source: str,
        target: str,
        relation: str,
        evidence_ids: list[str],
        profile_id: str,
        paper_id: str,
        confidence: float,
        review_status: str,
        observed_at: str,
        context: dict[str, Any] | None = None,
        properties: dict[str, Any] | None = None,
        discriminator: str = "",
        layer: str = "knowledge",
    ) -> str:
        edge_id = stable_id("edge", source, relation, target, profile_id, discriminator)
        if edge_id in self.edge_by_id:
            edge = self.edge_by_id[edge_id]
            edge["evidence_ids"] = _unique([*edge["evidence_ids"], *evidence_ids])
            edge["confidence"] = max(float(edge.get("confidence", 0)), confidence)
            return edge_id
        edge_context = {"profile_id": profile_id, "paper_id": paper_id}
        edge_context.update(context or {})
        edge = {
            "id": edge_id,
            "source": source,
            "target": target,
            "type": relation,
            "layer": layer,
            "origin": "extracted",
            "review_status": review_status,
            "confidence": confidence,
            "version": 1,
            "validity": {"observed_at": observed_at, "valid_from": None, "valid_to": None},
            "evidence_ids": _unique(evidence_ids),
            "derivation": None,
            "context": edge_context,
            "properties": properties or {},
        }
        self.graph["edges"].append(edge)
        self.edge_by_id[edge_id] = edge
        return edge_id

    def add_profile(self, profile: dict[str, Any]) -> None:
        self._validate_profile(
            profile, require_explicit_evidence=self.require_explicit_evidence
        )
        profile_id = profile["profile_id"]
        profile_fingerprint = hashlib.sha256(
            json.dumps(
                profile,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        previous_fingerprint = self.profile_fingerprints.get(profile_id)
        if previous_fingerprint is not None:
            if previous_fingerprint != profile_fingerprint:
                raise ValueError(
                    f"duplicate profile_id {profile_id} has different content"
                )
            return
        self.profile_fingerprints[profile_id] = profile_fingerprint
        document = profile["document"]
        observed_at = document["retrieved_at"]
        review_status = _review_status(profile)
        default_confidence = float(profile["quality"]["extraction_confidence"])
        evidence_map = self._add_evidence(profile)

        def refs(item: dict[str, Any]) -> list[str]:
            return [evidence_map[value] for value in item.get("evidence_refs", [])]

        metadata_evidence = [evidence_map[value] for value in document["metadata_evidence_refs"]]
        research_question_evidence = refs(profile["research_question"])
        future_work_items = [
            {"text": item["text"], "evidence_ids": refs(item)}
            for item in profile["future_work"]
        ]
        paper_id = self._add_or_merge_node(
            node_type="paper",
            label=document["title"],
            evidence_ids=metadata_evidence,
            profile_id=profile_id,
            confidence=default_confidence,
            review_status=review_status,
            observed_at=observed_at,
            scoped_key=_paper_identity_key(document),
            properties={
                "document_id": document["document_id"],
                "document_version": document["document_version"],
                "doi": document.get("doi"),
                "openalex_id": document.get("openalex_id"),
                "semantic_scholar_id": document.get("semantic_scholar_id"),
                "release_id": document.get("release_id"),
                "asset_id": document.get("asset_id"),
                "content_sha256": document.get("content_sha256"),
                "rights_status": document.get("rights_status"),
                "authors": document["authors"],
                "year": document["year"],
                "published_date": document.get("published_date"),
                "journal_or_source": document["journal_or_source"],
                "language": document["language"],
                "research_question": profile["research_question"]["text"],
                "research_question_evidence_ids": research_question_evidence,
                "future_work": [item["text"] for item in profile["future_work"]],
                "future_work_items": future_work_items,
                "quality": profile["quality"],
                "sample": profile.get("sample"),
                "stub": False,
            },
        )

        for author_name in document["authors"]:
            author_id = self._add_or_merge_node(
                node_type="author",
                label=author_name,
                evidence_ids=metadata_evidence,
                profile_id=profile_id,
                confidence=default_confidence,
                review_status=review_status,
                observed_at=observed_at,
                properties={"identity_resolution_status": "unresolved"},
                scoped_key=f"{paper_id}|author|{author_name}",
            )
            self._add_edge(
                source=paper_id,
                target=author_id,
                relation="AUTHORED_BY",
                evidence_ids=metadata_evidence,
                profile_id=profile_id,
                paper_id=paper_id,
                confidence=default_confidence,
                review_status=review_status,
                observed_at=observed_at,
                discriminator=author_name,
                layer="source",
            )

        venue_id = self._add_or_merge_node(
            node_type="venue",
            label=document["journal_or_source"],
            evidence_ids=metadata_evidence,
            profile_id=profile_id,
            confidence=default_confidence,
            review_status=review_status,
            observed_at=observed_at,
            properties={"external_venue_id": document.get("venue_id")},
        )
        self._add_edge(
            source=paper_id,
            target=venue_id,
            relation="PUBLISHED_IN",
            evidence_ids=metadata_evidence,
            profile_id=profile_id,
            paper_id=paper_id,
            confidence=default_confidence,
            review_status=review_status,
            observed_at=observed_at,
            discriminator=document["journal_or_source"],
            layer="source",
        )

        entity_maps: dict[str, dict[str, str]] = {}
        specs = (
            ("research_fields", "research_field", "STUDIES_FIELD"),
            ("topics", "topic", "STUDIES_TOPIC"),
            ("theories", "theory", "USES_THEORY"),
            ("mechanisms", "mechanism", "PROPOSES_MECHANISM"),
            ("measures", "measure", "USES_MEASURE"),
            ("methods", "method", "USES_METHOD"),
            ("models", "model", "USES_MODEL"),
            ("identification_strategies", "identification_strategy", "USES_IDENTIFICATION_STRATEGY"),
            ("datasets", "dataset", "USES_DATASET"),
            ("policies", "policy_document", "EVALUATES_POLICY"),
        )
        identity_fields = {"local_id", "name", "canonical_name", "aliases", "description", "evidence_refs", "confidence"}
        for collection, node_type, relation in specs:
            local_map: dict[str, str] = {}
            for item in profile[collection]:
                confidence = float(item.get("confidence", default_confidence))
                canonical = item.get("canonical_name") or item["name"]
                profile_attributes = {key: value for key, value in item.items() if key not in identity_fields}
                node_id = self._add_or_merge_node(
                    node_type=node_type,
                    label=canonical,
                    evidence_ids=refs(item),
                    profile_id=profile_id,
                    confidence=confidence,
                    review_status=review_status,
                    observed_at=observed_at,
                    description=item.get("description"),
                    aliases=_unique([item["name"], *item.get("aliases", [])]) if canonical != item["name"] else item.get("aliases", []),
                    properties={
                        "entity_kind": node_type,
                        **(
                            {"stub": True, "referenced_from_paper": True}
                            if node_type == "policy_document"
                            else {}
                        ),
                    },
                )
                local_map[item["local_id"]] = node_id
                edge_context: dict[str, Any] = {}
                if node_type in {"method", "identification_strategy"}:
                    edge_context["identification_strength"] = _identification_strength(item)
                self._add_edge(
                    source=paper_id,
                    target=node_id,
                    relation=relation,
                    evidence_ids=refs(item),
                    profile_id=profile_id,
                    paper_id=paper_id,
                    confidence=confidence,
                    review_status=review_status,
                    observed_at=observed_at,
                    context=edge_context,
                    properties={"profile_attributes": profile_attributes},
                    discriminator=item["local_id"],
                )
            entity_maps[collection] = local_map

        variable_map: dict[str, str] = {}
        for item in profile["variables"]:
            confidence = float(item.get("confidence", default_confidence))
            canonical = item.get("canonical_name") or item["name"]
            node_id = self._add_or_merge_node(
                node_type="variable",
                label=canonical,
                evidence_ids=refs(item),
                profile_id=profile_id,
                confidence=confidence,
                review_status=review_status,
                observed_at=observed_at,
                aliases=_unique([item["name"], *item.get("aliases", [])]) if canonical != item["name"] else item.get("aliases", []),
                properties={"entity_kind": "research_variable"},
            )
            variable_map[item["local_id"]] = node_id
            self._add_edge(
                source=paper_id,
                target=node_id,
                relation="USES_VARIABLE",
                evidence_ids=refs(item),
                profile_id=profile_id,
                paper_id=paper_id,
                confidence=confidence,
                review_status=review_status,
                observed_at=observed_at,
                context={"variable_roles": item["roles"]},
                properties={
                    "definition": item.get("definition"),
                    "operationalization": item.get("operationalization"),
                    "unit": item.get("unit"),
                },
                discriminator=item["local_id"],
            )
        entity_maps["variables"] = variable_map

        for variable in profile["variables"]:
            for measure_ref in variable.get("measure_refs", []):
                self._add_edge(
                    source=variable_map[variable["local_id"]],
                    target=entity_maps["measures"][measure_ref],
                    relation="MEASURED_BY",
                    evidence_ids=refs(variable),
                    profile_id=profile_id,
                    paper_id=paper_id,
                    confidence=float(variable.get("confidence", default_confidence)),
                    review_status=review_status,
                    observed_at=observed_at,
                    discriminator=f"{variable['local_id']}|{measure_ref}",
                )
        for measure in profile["measures"]:
            for dataset_ref in measure["data_source_refs"]:
                self._add_edge(
                    source=entity_maps["measures"][measure["local_id"]],
                    target=entity_maps["datasets"][dataset_ref],
                    relation="DERIVED_FROM",
                    evidence_ids=refs(measure),
                    profile_id=profile_id,
                    paper_id=paper_id,
                    confidence=float(measure.get("confidence", default_confidence)),
                    review_status=review_status,
                    observed_at=observed_at,
                    discriminator=f"{measure['local_id']}|{dataset_ref}",
                )

        for citation in profile["citations"]:
            cited_key = _paper_identity_key(
                {
                    "doi": citation.get("target_doi"),
                    "document_id": citation.get("target_document_id"),
                    "title": citation["target_title"],
                    "year": citation.get("target_year"),
                }
            )
            cited_id = self._add_or_merge_node(
                node_type="paper",
                label=citation["target_title"],
                evidence_ids=refs(citation),
                profile_id=profile_id,
                confidence=default_confidence,
                review_status="auto_validated" if citation["identity_status"] == "verified" else "unreviewed",
                observed_at=observed_at,
                scoped_key=cited_key,
                properties={
                    "document_id": citation.get("target_document_id"),
                    "document_version": "metadata-only",
                    "doi": citation.get("target_doi"),
                    "year": citation.get("target_year"),
                    "stub": True,
                    "citation_identity_status": citation["identity_status"],
                },
            )
            self._add_edge(
                source=paper_id,
                target=cited_id,
                relation="CITES",
                evidence_ids=refs(citation),
                profile_id=profile_id,
                paper_id=paper_id,
                confidence=default_confidence,
                review_status="auto_validated" if citation["identity_status"] == "verified" else "unreviewed",
                observed_at=observed_at,
                properties={"citation_relation": citation["relation"]},
                discriminator=cited_key,
                layer="source",
            )

        for finding in profile["findings"]:
            confidence = float(finding.get("confidence", default_confidence))
            finding_id = self._add_or_merge_node(
                node_type="finding",
                label=finding["claim"],
                evidence_ids=refs(finding),
                profile_id=profile_id,
                confidence=confidence,
                review_status=review_status,
                observed_at=observed_at,
                scoped_key=f"{profile_id}|finding|{finding['finding_id']}",
                properties={
                    "effect_direction": finding["effect_direction"],
                    "significance": finding["significance"],
                    "population_or_subsample": finding.get("population_or_subsample"),
                    "conditions": finding.get("conditions"),
                    "method_refs": finding.get("method_refs", []),
                    "model_refs": finding.get("model_refs", []),
                    "identification_strategy_refs": finding.get("identification_strategy_refs", []),
                },
            )
            finding_context = {
                "effect_direction": finding["effect_direction"],
                "significance": finding["significance"],
                "population_or_subsample": finding.get("population_or_subsample"),
                "conditions": finding.get("conditions"),
            }
            self._add_edge(
                source=paper_id,
                target=finding_id,
                relation="REPORTS_FINDING",
                evidence_ids=refs(finding),
                profile_id=profile_id,
                paper_id=paper_id,
                confidence=confidence,
                review_status=review_status,
                observed_at=observed_at,
                context=finding_context,
                discriminator=finding["finding_id"],
            )
            relation_fields = (
                ("predictor_refs", "HAS_PREDICTOR", variable_map),
                ("outcome_refs", "HAS_OUTCOME", variable_map),
                ("mediator_refs", "HAS_MEDIATOR", variable_map),
                ("moderator_refs", "HAS_MODERATOR", variable_map),
                ("mechanism_refs", "HAS_MECHANISM", entity_maps["mechanisms"]),
            )
            for field, relation, local_map in relation_fields:
                for local_id in finding.get(field, []):
                    self._add_edge(
                        source=finding_id,
                        target=local_map[local_id],
                        relation=relation,
                        evidence_ids=refs(finding),
                        profile_id=profile_id,
                        paper_id=paper_id,
                        confidence=confidence,
                        review_status=review_status,
                        observed_at=observed_at,
                        context=finding_context,
                        discriminator=f"{finding['finding_id']}|{field}|{local_id}",
                    )

        for limitation in profile["limitations"]:
            confidence = float(limitation.get("confidence", default_confidence))
            limitation_id = self._add_or_merge_node(
                node_type="limitation",
                label=limitation["text"],
                evidence_ids=refs(limitation),
                profile_id=profile_id,
                confidence=confidence,
                review_status=review_status,
                observed_at=observed_at,
                properties={"category": limitation["category"]},
                scoped_key=f"{profile_id}|limitation|{limitation['limitation_id']}",
            )
            self._add_edge(
                source=paper_id,
                target=limitation_id,
                relation="REPORTS_LIMITATION",
                evidence_ids=refs(limitation),
                profile_id=profile_id,
                paper_id=paper_id,
                confidence=confidence,
                review_status=review_status,
                observed_at=observed_at,
                discriminator=limitation["limitation_id"],
            )

    def finish(
        self,
        *,
        as_of: str | None = None,
        pipeline_run_id: str | None = None,
        build_timestamp: str | None = None,
    ) -> dict[str, Any]:
        completed_at = build_timestamp or utc_now()
        graph_id = self.graph.get("graph_id", "research-graph-v0")
        self.graph["schema_version"] = "0.2.0"
        self.graph["as_of"] = as_of or (
            completed_at if self.parent_snapshot_id else self.graph.get("as_of", completed_at)
        )
        build = self.graph.setdefault("build", {})
        build.update(
            {
                "created_at": completed_at,
                "generator": "src/reason/build_research_graph.py",
                "graph_schema_version": "0.2.0",
                "input_contract_versions": _unique([*build.get("input_contract_versions", []), "paper-profile-graph-input/0.2.0"]),
                "pipeline_run_id": pipeline_run_id or stable_id("run", completed_at),
                "source_watermarks": build.get("source_watermarks", {}),
                "base_graph_id": build.get("base_graph_id") or (graph_id if self.parent_snapshot_id else None),
                "base_graph_hash": build.get("base_graph_hash"),
                "parent_snapshot_id": self.parent_snapshot_id,
                "code_version": build.get("code_version"),
                "config_hash": build.get("config_hash"),
                "input_manifest_hash": build.get("input_manifest_hash"),
                "input_profile_hash": build.get("input_profile_hash"),
                "coverage_certificate_id": build.get("coverage_certificate_id"),
                "retrieval_index_snapshot_id": build.get(
                    "retrieval_index_snapshot_id"
                ),
                "notes": build.get("notes"),
            }
        )

        node_counts: dict[str, int] = {}
        for node in self.graph["nodes"]:
            node_counts[node["type"]] = node_counts.get(node["type"], 0) + 1
        self.graph["statistics"] = {
            "node_count": len(self.graph["nodes"]),
            "edge_count": len(self.graph["edges"]),
            "evidence_count": len(self.graph["evidence"]),
            **{f"nodes_{key}": value for key, value in sorted(node_counts.items())},
        }
        verified_count = sum(
            item.get("verification_status") in {"source_located", "cross_checked"}
            for item in self.graph["evidence"]
        )
        extracted_edges = [edge for edge in self.graph["edges"] if edge.get("origin") == "extracted"]
        traced_edges = [edge for edge in extracted_edges if edge.get("evidence_ids")]
        self.graph["quality_summary"] = {
            "source_document_count": sum(
                node["type"] in {"paper", "policy_document", "report"} and not node.get("properties", {}).get("stub", False)
                for node in self.graph["nodes"]
            ),
            "fact_edge_traceability_rate": len(traced_edges) / len(extracted_edges) if extracted_edges else 0.0,
            "verified_evidence_rate": verified_count / len(self.graph["evidence"]) if self.graph["evidence"] else 0.0,
            "unresolved_entity_count": sum(
                node.get("properties", {}).get("identity_resolution_status") == "unresolved"
                for node in self.graph["nodes"]
            ),
            "rejected_item_count": 0,
        }
        _normalize_graph_order(self.graph)
        self.graph["snapshot_id"] = _content_addressed_snapshot_id(self.graph)
        return self.graph


def _identification_strength(method: dict[str, Any]) -> str:
    text = normalize_label(" ".join(filter(None, [method.get("name"), method.get("identification_strategy") or "", method.get("description") or ""])))
    if any(token in text for token in ("randomized", "randomised", "随机对照", "rct")):
        return "experimental"
    if any(token in text for token in ("difference-in-differences", "difference in differences", "did", "断点", "rdd", "instrumental variable", "工具变量", "event study", "事件研究")):
        return "quasi_experimental"
    if any(token in text for token in ("regression", "回归", "correlation", "相关")):
        return "associational"
    if any(token in text for token in ("descriptive", "描述性")):
        return "descriptive"
    return "unknown"


def _load_profiles(paths: list[Path], input_dir: Path | None) -> list[dict[str, Any]]:
    candidates = list(paths)
    if input_dir is not None:
        candidates.extend(sorted(input_dir.glob("*.json")))
    if not candidates:
        raise ValueError("provide at least one --input or --input-dir")
    profiles = [json.loads(path.read_text(encoding="utf-8")) for path in candidates]
    return sorted(profiles, key=lambda item: str(item.get("profile_id", "")))


def _load_run_manifest(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    manifest = json.loads(path.read_text(encoding="utf-8"))
    return _validate_run_manifest(manifest)


def _validate_run_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    require_valid_instance(
        manifest, GRAPH_BUILD_MANIFEST_SCHEMA_PATH, "Graph build manifest"
    )
    year_start = manifest["scope"].get("year_start")
    year_end = manifest["scope"].get("year_end")
    if year_start is not None and year_end is not None and year_start > year_end:
        raise ValueError("Graph build manifest scope.year_start must not exceed year_end")
    return manifest


def _manifest_build_metadata(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "build_timestamp": manifest["build_timestamp"],
        "source_watermarks": manifest["source_watermarks"],
        "input_manifest_hash": manifest["input_manifest_hash"],
        "input_profile_hash": manifest["profile_set_sha256"],
        "base_graph_hash": manifest.get("base_graph_sha256"),
        "coverage_certificate_id": manifest.get("coverage_certificate_id"),
        "retrieval_index_snapshot_id": manifest.get("retrieval_index_snapshot_id"),
        "pipeline_run_id": manifest.get("pipeline_run_id"),
        "code_version": manifest.get("code_version"),
        "config_hash": manifest.get("config_hash"),
        "notes": manifest.get("notes"),
    }


def build_graph_from_profiles(
    profiles: list[dict[str, Any]],
    *,
    manifest: dict[str, Any] | None = None,
    base: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Build and validate a graph from in-memory inputs.

    Supplying a run manifest activates the formal release gate: explicit
    evidence classification, canonical input hashing and a fixed build time.
    """

    ordered_profiles = sorted(
        profiles, key=lambda item: str(item.get("profile_id", ""))
    )
    profile_ids = [str(profile.get("profile_id")) for profile in ordered_profiles]
    duplicate_profile_ids = sorted(
        profile_id
        for profile_id in set(profile_ids)
        if profile_ids.count(profile_id) > 1
    )
    if duplicate_profile_ids:
        raise ValueError(
            f"input set contains duplicate profile_id values: {duplicate_profile_ids}"
        )

    if manifest is not None:
        _validate_run_manifest(manifest)
        actual_profile_hash = profile_set_sha256(ordered_profiles)
        if actual_profile_hash != manifest["profile_set_sha256"]:
            raise ValueError(
                "run manifest profile_set_sha256 does not match inputs; "
                f"actual={actual_profile_hash}"
            )

    if base is not None:
        require_valid_instance(base, GRAPH_SCHEMA_PATH, "Base research graph")
        base_errors, _base_warnings = validate_graph(base)
        if base_errors:
            preview = "; ".join(base_errors[:10])
            raise ValueError(
                f"base research graph failed semantic validation: {preview}"
            )
        if manifest and manifest["graph_id"] != base.get("graph_id"):
            raise ValueError("run manifest graph_id must match base graph graph_id")
        if manifest and manifest.get("base_snapshot_id") != base.get("snapshot_id"):
            raise ValueError(
                "run manifest base_snapshot_id must match base graph snapshot_id"
            )
        actual_base_hash = _canonical_sha256(base)
        if manifest and manifest.get("base_graph_sha256") != actual_base_hash:
            raise ValueError(
                "run manifest base_graph_sha256 does not match base graph; "
                f"actual={actual_base_hash}"
            )
        builder = GraphBuilder(
            base, require_explicit_evidence=manifest is not None
        )
        if manifest:
            builder.graph["scope"] = copy.deepcopy(manifest["scope"])
            build_metadata = _manifest_build_metadata(manifest)
            build_metadata.pop("build_timestamp", None)
            builder.graph.setdefault("build", {}).update(build_metadata)
    elif manifest:
        if (
            manifest.get("base_snapshot_id") is not None
            or manifest.get("base_graph_sha256") is not None
        ):
            raise ValueError(
                "run manifest base_snapshot_id/base_graph_sha256 require a base graph"
            )
        builder = GraphBuilder(
            new_graph(
                manifest["graph_id"],
                as_of=manifest["as_of"],
                scope=copy.deepcopy(manifest["scope"]),
                build_metadata=_manifest_build_metadata(manifest),
            ),
            require_explicit_evidence=True,
        )
    else:
        builder = GraphBuilder()

    for profile in ordered_profiles:
        builder.add_profile(profile)
    graph = builder.finish(
        as_of=manifest["as_of"] if manifest else None,
        pipeline_run_id=manifest["pipeline_run_id"] if manifest else None,
        build_timestamp=manifest["build_timestamp"] if manifest else None,
    )
    graph_errors, graph_warnings = validate_graph(graph)
    if graph_errors:
        preview = "; ".join(graph_errors[:10])
        raise ValueError(f"built research graph failed validation: {preview}")
    return graph, graph_warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Build research_graph v0.2 from PaperProfile v0.2 inputs")
    parser.add_argument("--input", type=Path, action="append", default=[])
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--base-graph", type=Path)
    parser.add_argument(
        "--run-manifest",
        type=Path,
        help="versioned graph build manifest; required for a formal release",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        profiles = _load_profiles(args.input, args.input_dir)
        manifest = _load_run_manifest(args.run_manifest)
        base = json.loads(args.base_graph.read_text(encoding="utf-8")) if args.base_graph else None
        graph, graph_warnings = build_graph_from_profiles(
            profiles, manifest=manifest, base=base
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1

    for warning in graph_warnings:
        print(f"WARNING: {warning}")
    print(
        f"WROTE: {args.output} ({len(graph['nodes'])} nodes, "
        f"{len(graph['edges'])} edges, {len(graph_warnings)} warning(s))"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
