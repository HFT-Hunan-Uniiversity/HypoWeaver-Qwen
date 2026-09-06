"""Semantic validation for GreenFin's v0.2 temporal research graph."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:  # Support both ``python file.py`` and ``python -m src.reason...``.
    from .schema_gate import GRAPH_SCHEMA_PATH, validate_instance
except ImportError:  # pragma: no cover - direct script execution path
    from schema_gate import GRAPH_SCHEMA_PATH, validate_instance


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

SOURCE_RELATIONS = {
    "AUTHORED_BY",
    "AFFILIATED_WITH",
    "PUBLISHED_IN",
    "CITES",
    "REFERENCES_POLICY",
    "AMENDS",
    "SUPERSEDES",
}
ANALYTICS_RELATIONS = {
    "ASSIGNED_TO_STREAM",
    "STREAM_IN_FIELD",
    "STREAM_FOCUSES_ON",
    "STREAM_USES_THEORY",
    "STREAM_USES_METHOD",
    "STREAM_USES_MODEL",
    "EVOLVES_INTO",
    "TREND_OF",
    "INDICATES_CONTROVERSY",
}
DISCOVERY_RELATIONS = {
    "INDICATES_GAP",
    "GAP_CONCERNS",
    "ENABLED_BY",
    "ADDRESSES_GAP",
    "SUPPORTED_BY_EVIDENCE",
    "CHALLENGED_BY_EVIDENCE",
    "RECOMMENDS_METHOD",
    "RECOMMENDS_MODEL",
    "RECOMMENDS_IDENTIFICATION_STRATEGY",
    "RECOMMENDS_DATASET",
}

SCIENTIFIC_SOURCE_TYPES = {"paper_fulltext", "policy_text", "report_text"}
SCIENTIFIC_EVIDENCE_TYPES = {"direct_quote", "table_cell"}
VERIFIED_EVIDENCE_STATUSES = {"source_located", "cross_checked"}
FULLTEXT_NODE_TYPES = {
    "theory",
    "mechanism",
    "variable",
    "measure",
    "method",
    "model",
    "identification_strategy",
    "finding",
    "limitation",
}
FULLTEXT_EDGE_TYPES = {
    "USES_THEORY",
    "PROPOSES_MECHANISM",
    "USES_VARIABLE",
    "USES_MEASURE",
    "USES_METHOD",
    "USES_MODEL",
    "USES_IDENTIFICATION_STRATEGY",
    "REPORTS_FINDING",
    "REPORTS_LIMITATION",
    "HAS_PREDICTOR",
    "HAS_OUTCOME",
    "HAS_MEDIATOR",
    "HAS_MODERATOR",
    "HAS_MECHANISM",
    "MEASURED_BY",
    "DERIVED_FROM",
    "PROXIED_BY",
    "SUPPORTS",
    "CONTRADICTS",
}


EndpointRule = tuple[set[str] | None, set[str] | None]
ENDPOINT_RULES: dict[str, EndpointRule] = {
    "AUTHORED_BY": ({"paper"}, {"author"}),
    "AFFILIATED_WITH": ({"author"}, {"institution"}),
    "PUBLISHED_IN": ({"paper"}, {"venue"}),
    "CITES": ({"paper"}, {"paper"}),
    "REFERENCES_POLICY": ({"paper", "report"}, {"policy_document"}),
    "AMENDS": ({"policy_document"}, {"policy_document"}),
    "SUPERSEDES": ({"policy_document"}, {"policy_document"}),
    "CONTAINS_INSTRUMENT": ({"policy_document"}, {"policy_instrument"}),
    "TARGETS": ({"policy_instrument"}, {"research_field", "topic", "variable", "population", "context"}),
    "IMPLEMENTED_IN": ({"policy_document", "policy_instrument"}, {"context"}),
    "STUDIES_FIELD": ({"paper"}, {"research_field"}),
    "STUDIES_TOPIC": ({"paper"}, {"topic"}),
    "USES_THEORY": ({"paper"}, {"theory"}),
    "PROPOSES_MECHANISM": ({"paper"}, {"mechanism"}),
    "USES_VARIABLE": ({"paper"}, {"variable"}),
    "USES_MEASURE": ({"paper"}, {"measure"}),
    "USES_METHOD": ({"paper"}, {"method"}),
    "USES_MODEL": ({"paper"}, {"model"}),
    "USES_IDENTIFICATION_STRATEGY": ({"paper"}, {"identification_strategy"}),
    "USES_DATASET": ({"paper"}, {"dataset"}),
    "EVALUATES_POLICY": ({"paper"}, {"policy_document", "policy_instrument"}),
    "REPORTS_FINDING": ({"paper"}, {"finding"}),
    "REPORTS_LIMITATION": ({"paper"}, {"limitation"}),
    "STUDIES_POPULATION": ({"paper"}, {"population"}),
    "STUDIES_CONTEXT": ({"paper"}, {"context"}),
    "HAS_PREDICTOR": ({"finding", "hypothesis"}, {"variable", "policy_document", "policy_instrument"}),
    "HAS_OUTCOME": ({"finding", "hypothesis"}, {"variable"}),
    "HAS_MEDIATOR": ({"finding", "hypothesis"}, {"variable"}),
    "HAS_MODERATOR": ({"finding", "hypothesis"}, {"variable"}),
    "HAS_MECHANISM": ({"finding", "hypothesis"}, {"mechanism"}),
    "MEASURED_BY": ({"variable"}, {"measure"}),
    "DERIVED_FROM": ({"measure"}, {"dataset"}),
    "PROXIED_BY": ({"variable"}, {"variable", "measure", "dataset"}),
    "SUPPORTS": ({"finding"}, {"finding"}),
    "CONTRADICTS": ({"finding"}, {"finding"}),
    "ASSIGNED_TO_STREAM": ({"paper"}, {"research_stream"}),
    "STREAM_IN_FIELD": ({"research_stream"}, {"research_field"}),
    "STREAM_FOCUSES_ON": ({"research_stream"}, {"topic", "mechanism", "variable", "policy_instrument"}),
    "STREAM_USES_THEORY": ({"research_stream"}, {"theory"}),
    "STREAM_USES_METHOD": ({"research_stream"}, {"method", "identification_strategy"}),
    "STREAM_USES_MODEL": ({"research_stream"}, {"model"}),
    "EVOLVES_INTO": ({"research_stream"}, {"research_stream"}),
    "TREND_OF": ({"trend_snapshot"}, {"research_stream", "research_field", "topic", "method", "model", "identification_strategy", "policy_instrument"}),
    "INDICATES_CONTROVERSY": ({"finding"}, {"controversy"}),
    "INDICATES_GAP": ({"finding", "limitation", "trend_snapshot", "controversy", "policy_document"}, {"research_gap"}),
    "GAP_CONCERNS": ({"research_gap"}, {"research_field", "topic", "theory", "mechanism", "variable", "measure", "method", "model", "identification_strategy", "policy_instrument", "population", "context", "research_stream", "controversy"}),
    "ENABLED_BY": ({"research_gap", "hypothesis"}, {"dataset", "measure", "policy_document", "policy_instrument"}),
    "ADDRESSES_GAP": ({"hypothesis"}, {"research_gap"}),
    "SUPPORTED_BY_EVIDENCE": ({"research_gap", "hypothesis"}, {"finding", "policy_document", "trend_snapshot", "controversy"}),
    "CHALLENGED_BY_EVIDENCE": ({"research_gap", "hypothesis"}, {"finding", "policy_document", "trend_snapshot", "controversy"}),
    "RECOMMENDS_METHOD": ({"hypothesis"}, {"method"}),
    "RECOMMENDS_MODEL": ({"hypothesis"}, {"model"}),
    "RECOMMENDS_IDENTIFICATION_STRATEGY": ({"hypothesis"}, {"identification_strategy"}),
    "RECOMMENDS_DATASET": ({"hypothesis"}, {"dataset"}),
    "SUBTOPIC_OF": ({"topic", "research_field"}, {"topic", "research_field"}),
    "SAME_AS": (None, None),
    "RELATED_TO": (None, None),
    "APPLIES_TO": ({"method", "model", "identification_strategy"}, {"research_field", "topic", "policy_document", "policy_instrument", "context", "variable"}),
    "SUITABLE_FOR": ({"method", "model", "identification_strategy"}, {"research_field", "topic", "policy_document", "policy_instrument", "finding", "context", "research_gap", "hypothesis"}),
}


def _duplicates(values: list[str]) -> set[str]:
    seen: set[str] = set()
    repeated: set[str] = set()
    for value in values:
        if value in seen:
            repeated.add(value)
        seen.add(value)
    return repeated


def _expected_edge_layer(relation: str) -> str:
    if relation in SOURCE_RELATIONS:
        return "source"
    if relation in ANALYTICS_RELATIONS:
        return "analytics"
    if relation in DISCOVERY_RELATIONS:
        return "discovery"
    return "knowledge"


def _content_hash(content: Any) -> str:
    material = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def validate_graph(graph: dict[str, Any]) -> tuple[list[str], list[str]]:
    try:
        schema_errors = validate_instance(graph, GRAPH_SCHEMA_PATH)
    except RuntimeError as exc:
        schema_errors = [str(exc)]
    errors: list[str] = [f"schema {error}" for error in schema_errors]
    warnings: list[str] = []

    if graph.get("schema_version") != "0.2.0":
        errors.append("schema_version must be 0.2.0")
    if graph.get("domain") != "green_finance":
        errors.append("domain must be green_finance")
    if not graph.get("snapshot_id"):
        errors.append("snapshot_id is required")
    if not graph.get("as_of"):
        errors.append("as_of is required")
    if graph.get("build", {}).get("graph_schema_version") != "0.2.0":
        errors.append("build.graph_schema_version must be 0.2.0")

    nodes = graph.get("nodes")
    edges = graph.get("edges")
    evidence = graph.get("evidence")
    if not isinstance(nodes, list):
        errors.append("nodes must be an array")
        nodes = []
    if not isinstance(edges, list):
        errors.append("edges must be an array")
        edges = []
    if not isinstance(evidence, list):
        errors.append("evidence must be an array")
        evidence = []

    node_ids = [item.get("id") for item in nodes if isinstance(item, dict)]
    edge_ids = [item.get("id") for item in edges if isinstance(item, dict)]
    evidence_ids = [item.get("id") for item in evidence if isinstance(item, dict)]
    for label, values in (("node", node_ids), ("edge", edge_ids), ("evidence", evidence_ids)):
        repeated = _duplicates([str(value) for value in values if value is not None])
        if repeated:
            errors.append(f"duplicate {label} ids: {sorted(repeated)}")
        if any(value is None for value in values):
            errors.append(f"one or more {label}s have no id")

    node_by_id = {item["id"]: item for item in nodes if isinstance(item, dict) and item.get("id")}
    edge_by_id = {item["id"]: item for item in edges if isinstance(item, dict) and item.get("id")}
    evidence_by_id = {item["id"]: item for item in evidence if isinstance(item, dict) and item.get("id")}

    for item in evidence:
        if not isinstance(item, dict):
            errors.append("evidence entries must be objects")
            continue
        if item.get("verification_status") == "rejected":
            warnings.append(f"rejected evidence retained for audit: {item.get('id')}")
        if "content" in item and item.get("content_hash") != _content_hash(item["content"]):
            errors.append(f"evidence {item.get('id')} content_hash does not match content")
        source_type = item.get("source_type")
        evidence_type = item.get("evidence_type")
        evidence_level = item.get("evidence_level")
        content = item.get("content")
        if evidence_type == "direct_quote" and (
            not isinstance(content, str) or not content.strip()
        ):
            errors.append(
                f"evidence {item.get('id')} direct_quote content must be a non-blank string"
            )
        if evidence_type == "table_cell" and (
            content is None
            or (isinstance(content, str) and not content.strip())
            or (isinstance(content, (list, dict)) and not content)
        ):
            errors.append(
                f"evidence {item.get('id')} table_cell content must not be empty"
            )
        if source_type in SCIENTIFIC_SOURCE_TYPES:
            if evidence_type not in SCIENTIFIC_EVIDENCE_TYPES:
                errors.append(
                    f"evidence {item.get('id')} {source_type} requires direct_quote or table_cell"
                )
            if evidence_level != "primary_source":
                errors.append(
                    f"evidence {item.get('id')} {source_type} must be primary_source"
                )
        elif source_type == "metadata_api":
            if (evidence_type, evidence_level) != ("metadata_record", "metadata"):
                errors.append(
                    f"evidence {item.get('id')} metadata_api requires metadata_record + metadata"
                )
        elif source_type == "paper_abstract" and evidence_level != "metadata":
            errors.append(
                f"evidence {item.get('id')} paper_abstract must be metadata level"
            )
        locator = item.get("locator") or {}
        for locator_field, locator_value in (
            ("chunk_id", item.get("chunk_id")),
            ("section", locator.get("section")),
        ):
            if isinstance(locator_value, str) and not locator_value.strip():
                errors.append(
                    f"evidence {item.get('id')} {locator_field} must not be blank"
                )
        start = locator.get("start_char")
        end = locator.get("end_char")
        if (start is None) != (end is None) or (
            isinstance(start, int)
            and isinstance(end, int)
            and start >= end
        ):
            errors.append(
                f"evidence {item.get('id')} character locator must satisfy "
                "0 <= start_char < end_char"
            )

    def has_text_locator(item: dict[str, Any]) -> bool:
        locator = item.get("locator") or {}
        for value in (
            item.get("chunk_id"),
            locator.get("page"),
            locator.get("section"),
            locator.get("table_id"),
        ):
            if isinstance(value, str) and value.strip():
                return True
            if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
                return True
        start = locator.get("start_char")
        end = locator.get("end_char")
        return (
            isinstance(start, int)
            and not isinstance(start, bool)
            and isinstance(end, int)
            and not isinstance(end, bool)
            and 0 <= start < end
        )

    def is_located_scientific(
        item: dict[str, Any], *, allowed_source_types: set[str] | None = None
    ) -> bool:
        source_types = allowed_source_types or SCIENTIFIC_SOURCE_TYPES
        return (
            item.get("source_type") in source_types
            and item.get("evidence_type") in SCIENTIFIC_EVIDENCE_TYPES
            and item.get("evidence_level") == "primary_source"
            and item.get("verification_status") in VERIFIED_EVIDENCE_STATUSES
            and has_text_locator(item)
        )

    def is_paper_semantic(item: dict[str, Any]) -> bool:
        if is_located_scientific(
            item, allowed_source_types={"paper_fulltext"}
        ):
            return True
        return (
            item.get("source_type") == "paper_abstract"
            and item.get("evidence_type") == "direct_quote"
            and item.get("evidence_level") == "metadata"
            and item.get("verification_status") in VERIFIED_EVIDENCE_STATUSES
        )

    def is_generic_semantic(item: dict[str, Any]) -> bool:
        if is_located_scientific(item):
            return True
        if is_paper_semantic(item):
            return True
        return (
            item.get("source_type") == "dataset_registry"
            and item.get("evidence_type") == "metadata_record"
            and item.get("evidence_level") == "metadata"
            and item.get("verification_status")
            in {*VERIFIED_EVIDENCE_STATUSES, "not_applicable"}
        )

    def check_owner(owner_kind: str, owner: dict[str, Any]) -> None:
        owner_id = owner.get("id")
        refs = owner.get("evidence_ids")
        if not isinstance(refs, list) or not refs:
            errors.append(f"{owner_kind} {owner_id} has no evidence_ids")
            return
        levels: set[str] = set()
        owner_evidence: list[dict[str, Any]] = []
        for evidence_id in refs:
            item = evidence_by_id.get(evidence_id)
            if item is None:
                errors.append(f"{owner_kind} {owner_id} references missing evidence {evidence_id}")
                continue
            if item.get("verification_status") == "rejected":
                errors.append(f"{owner_kind} {owner_id} references rejected evidence {evidence_id}")
            levels.add(str(item.get("evidence_level")))
            owner_evidence.append(item)
        if owner.get("review_status") == "rejected":
            errors.append(f"rejected {owner_kind} {owner_id} must not be in an active graph snapshot")
        origin = owner.get("origin")
        if origin == "extracted" and not levels.intersection({"primary_source", "metadata"}):
            errors.append(f"{owner_kind} {owner_id} is extracted but has no primary/metadata evidence")
        if owner_kind == "node" and origin == "extracted":
            source_profiles = set(owner.get("source_profile_ids") or [])
            if not source_profiles:
                errors.append(f"node {owner_id} is extracted but has no source_profile_ids")
            for item in owner_evidence:
                if item.get("profile_id") not in source_profiles:
                    errors.append(
                        f"node {owner_id} evidence {item.get('id')} belongs to profile "
                        f"{item.get('profile_id')}, expected one of {sorted(source_profiles)}"
                    )
        if (
            owner_kind == "node"
            and origin == "extracted"
            and owner.get("type") in FULLTEXT_NODE_TYPES
            and not any(
                is_located_scientific(
                    item, allowed_source_types={"paper_fulltext"}
                )
                for item in owner_evidence
            )
        ):
            errors.append(
                f"node {owner_id} type {owner.get('type')} requires located, verified fulltext evidence"
            )
        if (
            owner_kind == "node"
            and origin == "extracted"
            and owner.get("layer") == "knowledge"
            and owner.get("type") not in FULLTEXT_NODE_TYPES
            and not any(is_generic_semantic(item) for item in owner_evidence)
        ):
            errors.append(
                f"node {owner_id} type {owner.get('type')} requires verified "
                "semantic source evidence"
            )
        if origin in {"computed", "inferred"} and owner.get("derivation") is None:
            errors.append(f"{owner_kind} {owner_id} is {origin} but has no derivation")

    def paper_property_evidence_ids(node: dict[str, Any]) -> set[str]:
        """Collect evidence referenced by auditable paper subfields.

        Research questions and future-work statements stay as paper properties
        in v0.2, so their evidence mappings must participate in integrity and
        unused-evidence checks just like top-level owner references.
        """

        properties = node.get("properties") or {}
        referenced: set[str] = set()
        research_question_refs = properties.get("research_question_evidence_ids")
        if isinstance(research_question_refs, list):
            referenced.update(str(value) for value in research_question_refs)
        future_work_items = properties.get("future_work_items")
        if isinstance(future_work_items, list):
            for item in future_work_items:
                if isinstance(item, dict) and isinstance(item.get("evidence_ids"), list):
                    referenced.update(str(value) for value in item["evidence_ids"])
        return referenced

    for node in nodes:
        if not isinstance(node, dict):
            errors.append("node entries must be objects")
            continue
        node_type = node.get("type")
        expected_layer = NODE_LAYERS.get(node_type)
        if expected_layer is None:
            errors.append(f"node {node.get('id')} has unknown type {node_type}")
        elif node.get("layer") != expected_layer:
            errors.append(f"node {node.get('id')} type {node_type} must be in {expected_layer} layer")
        if node.get("layer") == "analytics" and node.get("origin") == "extracted":
            errors.append(f"analytics node {node.get('id')} cannot be extracted directly")
        if node.get("layer") == "discovery" and node.get("origin") == "extracted":
            errors.append(f"discovery node {node.get('id')} cannot be extracted directly")
        check_owner("node", node)
        if node_type == "paper":
            properties = node.get("properties") or {}
            is_stub = bool(properties.get("stub", False))
            paper_document_id = properties.get("document_id")
            paper_profile_ids = set(node.get("source_profile_ids") or [])

            def belongs_to_this_paper(evidence_id: str) -> bool:
                item = evidence_by_id.get(evidence_id)
                return bool(
                    item is not None
                    and item.get("source_document_id") == paper_document_id
                    and item.get("profile_id") in paper_profile_ids
                )

            property_refs = paper_property_evidence_ids(node)
            for evidence_id in sorted(property_refs):
                item = evidence_by_id.get(evidence_id)
                if item is None:
                    errors.append(
                        f"paper {node.get('id')} properties reference missing evidence {evidence_id}"
                    )
                elif item.get("verification_status") == "rejected":
                    errors.append(
                        f"paper {node.get('id')} properties reference rejected evidence {evidence_id}"
                    )
                elif not is_stub and not belongs_to_this_paper(evidence_id):
                    errors.append(
                        f"paper {node.get('id')} property evidence {evidence_id} "
                        "does not belong to this paper document/profile"
                    )
            if not is_stub:
                document_id = paper_document_id
                if not isinstance(document_id, str) or not document_id.strip():
                    errors.append(f"paper {node.get('id')} has no properties.document_id")
                for evidence_id in node.get("evidence_ids", []):
                    item = evidence_by_id.get(evidence_id)
                    if item is not None and item.get("source_document_id") != document_id:
                        errors.append(
                            f"paper {node.get('id')} evidence {evidence_id} belongs to "
                            f"{item.get('source_document_id')}, expected {document_id}"
                        )
                    elif item is not None and item.get("profile_id") not in paper_profile_ids:
                        errors.append(
                            f"paper {node.get('id')} evidence {evidence_id} belongs to "
                            f"profile {item.get('profile_id')}, expected one of "
                            f"{sorted(paper_profile_ids)}"
                        )

                if properties.get("research_question") is not None:
                    question_refs = properties.get("research_question_evidence_ids")
                    if not isinstance(question_refs, list) or not question_refs:
                        errors.append(
                            f"paper {node.get('id')} research_question has no evidence mapping"
                        )
                    elif not any(
                        evidence_id in evidence_by_id
                        and belongs_to_this_paper(evidence_id)
                        and is_located_scientific(
                            evidence_by_id[evidence_id],
                            allowed_source_types={"paper_fulltext"},
                        )
                        for evidence_id in question_refs
                    ):
                        errors.append(
                            f"paper {node.get('id')} research_question requires "
                            "located, verified paper fulltext evidence"
                        )

                future_work = properties.get("future_work")
                future_items = properties.get("future_work_items")
                if future_work is not None or future_items is not None:
                    if not isinstance(future_work, list) or not isinstance(future_items, list):
                        errors.append(
                            f"paper {node.get('id')} future_work mapping must use arrays"
                        )
                    elif [item.get("text") for item in future_items if isinstance(item, dict)] != future_work:
                        errors.append(
                            f"paper {node.get('id')} future_work and future_work_items do not align"
                        )
                    else:
                        for position, future_item in enumerate(future_items):
                            refs = future_item.get("evidence_ids") if isinstance(future_item, dict) else None
                            if not isinstance(refs, list) or not refs or not any(
                                evidence_id in evidence_by_id
                                and belongs_to_this_paper(evidence_id)
                                and is_located_scientific(
                                    evidence_by_id[evidence_id],
                                    allowed_source_types={"paper_fulltext"},
                                )
                                for evidence_id in refs
                            ):
                                errors.append(
                                    f"paper {node.get('id')} future_work_items[{position}] "
                                    "requires located, verified paper fulltext evidence"
                                )
        if (
            node_type in {"policy_document", "report"}
            and node.get("origin") == "extracted"
            and not (node.get("properties") or {}).get("stub", False)
        ):
            source_kind = str(node_type)
            properties = node.get("properties") or {}
            document_id = properties.get("document_id")
            if not isinstance(document_id, str) or not document_id.strip():
                errors.append(
                    f"{source_kind} {node.get('id')} has no properties.document_id"
                )
            for evidence_id in node.get("evidence_ids", []):
                item = evidence_by_id.get(evidence_id)
                if item is not None and item.get("source_document_id") != document_id:
                    errors.append(
                        f"{source_kind} {node.get('id')} evidence {evidence_id} "
                        f"belongs to {item.get('source_document_id')}, expected {document_id}"
                    )

    incoming_findings: dict[str, int] = {}
    outcome_edges: dict[str, int] = {}
    gap_evidence_edges: dict[str, int] = {}
    hypothesis_gap_edges: dict[str, int] = {}

    for edge in edges:
        if not isinstance(edge, dict):
            errors.append("edge entries must be objects")
            continue
        edge_id = edge.get("id")
        source_id = edge.get("source")
        target_id = edge.get("target")
        source_node = node_by_id.get(source_id)
        target_node = node_by_id.get(target_id)
        if source_node is None:
            errors.append(f"edge {edge_id} has missing source {source_id}")
        if target_node is None:
            errors.append(f"edge {edge_id} has missing target {target_id}")

        relation = edge.get("type")
        rule = ENDPOINT_RULES.get(relation)
        if rule is None:
            errors.append(f"edge {edge_id} has unknown relation {relation}")
        elif source_node is not None and target_node is not None:
            allowed_sources, allowed_targets = rule
            source_type = source_node.get("type")
            target_type = target_node.get("type")
            if allowed_sources is not None and source_type not in allowed_sources:
                errors.append(f"edge {edge_id} relation {relation} cannot start at {source_type}")
            if allowed_targets is not None and target_type not in allowed_targets:
                errors.append(f"edge {edge_id} relation {relation} cannot end at {target_type}")
            if relation == "SAME_AS" and source_type != target_type:
                errors.append(f"edge {edge_id} SAME_AS endpoints must have the same node type")

        expected_layer = _expected_edge_layer(str(relation))
        if edge.get("layer") != expected_layer:
            errors.append(f"edge {edge_id} relation {relation} must be in {expected_layer} layer")
        if edge.get("layer") in {"analytics", "discovery"} and edge.get("origin") == "extracted":
            errors.append(
                f"{edge.get('layer')} edge {edge_id} cannot be extracted directly"
            )

        context = edge.get("context") or {}
        paper_id = context.get("paper_id")
        policy_document_id = context.get("policy_document_id")
        report_id = context.get("report_id")
        if edge.get("origin") == "extracted":
            profile_context = context.get("profile_id")
            if not isinstance(profile_context, str) or not profile_context.strip():
                errors.append(
                    f"extracted edge {edge_id} requires context.profile_id"
                )
            provenance_contexts = [
                value
                for value in (paper_id, policy_document_id, report_id)
                if value is not None
            ]
            if len(provenance_contexts) != 1:
                errors.append(
                    f"extracted edge {edge_id} requires exactly one provenance "
                    "context: paper_id, policy_document_id or report_id"
                )
            if source_node is not None:
                source_type = source_node.get("type")
                if source_type == "paper" and paper_id != source_id:
                    errors.append(
                        f"extracted edge {edge_id} from paper {source_id} must set "
                        "context.paper_id to that paper"
                    )
                if source_type == "policy_document" and policy_document_id != source_id:
                    errors.append(
                        f"extracted edge {edge_id} from policy_document {source_id} "
                        "must set context.policy_document_id to that document"
                    )
                if source_type == "report" and report_id != source_id:
                    errors.append(
                        f"extracted edge {edge_id} from report {source_id} must set "
                        "context.report_id to that report"
                    )
                if profile_context not in set(source_node.get("source_profile_ids") or []):
                    errors.append(
                        f"extracted edge {edge_id} profile {profile_context} is not "
                        f"recorded on source node {source_id}"
                    )
            if target_node is not None and profile_context not in set(
                target_node.get("source_profile_ids") or []
            ):
                errors.append(
                    f"extracted edge {edge_id} profile {profile_context} is not "
                    f"recorded on target node {target_id}"
                )
            for evidence_id in edge.get("evidence_ids", []):
                item = evidence_by_id.get(evidence_id)
                if (
                    item is not None
                    and isinstance(profile_context, str)
                    and item.get("profile_id") != profile_context
                ):
                    errors.append(
                        f"edge {edge_id} evidence {evidence_id} belongs to profile "
                        f"{item.get('profile_id')}, expected {profile_context}"
                    )
        if paper_id is not None:
            paper = node_by_id.get(paper_id)
            if paper is None or paper.get("type") != "paper":
                errors.append(f"edge {edge_id} context.paper_id is not a paper node: {paper_id}")
            elif (paper.get("properties") or {}).get("stub", False):
                errors.append(
                    f"extracted edge {edge_id} cannot use stub paper {paper_id} "
                    "as provenance context"
                )
            else:
                if edge.get("origin") == "extracted" and context.get("profile_id") not in set(
                    paper.get("source_profile_ids") or []
                ):
                    errors.append(
                        f"edge {edge_id} provenance profile is not recorded on paper {paper_id}"
                    )
                expected_document_id = (paper.get("properties") or {}).get("document_id")
                for evidence_id in edge.get("evidence_ids", []):
                    item = evidence_by_id.get(evidence_id)
                    if item is not None and item.get("source_document_id") != expected_document_id:
                        errors.append(
                            f"edge {edge_id} evidence {evidence_id} belongs to "
                            f"{item.get('source_document_id')}, expected paper document "
                            f"{expected_document_id}"
                        )
        if policy_document_id is not None:
            policy = node_by_id.get(policy_document_id)
            if policy is None or policy.get("type") != "policy_document":
                errors.append(f"edge {edge_id} context.policy_document_id is invalid: {policy_document_id}")
            elif (policy.get("properties") or {}).get("stub", False):
                errors.append(
                    f"extracted edge {edge_id} cannot use stub policy_document "
                    f"{policy_document_id} as provenance context"
                )
            elif edge.get("origin") == "extracted":
                if context.get("profile_id") not in set(
                    policy.get("source_profile_ids") or []
                ):
                    errors.append(
                        f"edge {edge_id} provenance profile is not recorded on "
                        f"policy_document {policy_document_id}"
                    )
                expected_document_id = (policy.get("properties") or {}).get(
                    "document_id"
                )
                if not isinstance(expected_document_id, str) or not expected_document_id.strip():
                    errors.append(
                        f"edge {edge_id} context policy_document "
                        f"{policy_document_id} has no document_id"
                    )
                for evidence_id in edge.get("evidence_ids", []):
                    item = evidence_by_id.get(evidence_id)
                    if item is not None and item.get("source_document_id") != expected_document_id:
                        errors.append(
                            f"edge {edge_id} evidence {evidence_id} belongs to "
                            f"{item.get('source_document_id')}, expected policy document "
                            f"{expected_document_id}"
                        )
        if report_id is not None:
            report = node_by_id.get(report_id)
            if report is None or report.get("type") != "report":
                errors.append(
                    f"edge {edge_id} context.report_id is invalid: {report_id}"
                )
            elif edge.get("origin") == "extracted":
                if (report.get("properties") or {}).get("stub", False):
                    errors.append(
                        f"extracted edge {edge_id} cannot use stub report {report_id} "
                        "as provenance context"
                    )
                if context.get("profile_id") not in set(
                    report.get("source_profile_ids") or []
                ):
                    errors.append(
                        f"edge {edge_id} provenance profile is not recorded on report {report_id}"
                    )
                expected_document_id = (report.get("properties") or {}).get(
                    "document_id"
                )
                if not isinstance(expected_document_id, str) or not expected_document_id.strip():
                    errors.append(
                        f"edge {edge_id} context report {report_id} has no document_id"
                    )
                for evidence_id in edge.get("evidence_ids", []):
                    item = evidence_by_id.get(evidence_id)
                    if item is not None and item.get("source_document_id") != expected_document_id:
                        errors.append(
                            f"edge {edge_id} evidence {evidence_id} belongs to "
                            f"{item.get('source_document_id')}, expected report document "
                            f"{expected_document_id}"
                        )

        check_owner("edge", edge)
        requires_fulltext = relation in FULLTEXT_EDGE_TYPES
        if relation == "CITES":
            citation_relation = (edge.get("properties") or {}).get("citation_relation")
            requires_fulltext = citation_relation not in {None, "cites"}
        if edge.get("origin") == "extracted" and requires_fulltext:
            edge_evidence = [
                evidence_by_id[evidence_id]
                for evidence_id in edge.get("evidence_ids", [])
                if evidence_id in evidence_by_id
            ]
            if not any(
                is_located_scientific(
                    item, allowed_source_types={"paper_fulltext"}
                )
                for item in edge_evidence
            ):
                errors.append(
                    f"edge {edge_id} relation {relation} requires located, verified fulltext evidence"
                )
        elif (
            edge.get("origin") == "extracted"
            and edge.get("layer") == "knowledge"
        ):
            edge_evidence = [
                evidence_by_id[evidence_id]
                for evidence_id in edge.get("evidence_ids", [])
                if evidence_id in evidence_by_id
            ]
            if paper_id is not None:
                has_semantic_evidence = any(
                    is_paper_semantic(item) for item in edge_evidence
                )
                source_label = "paper abstract or paper fulltext"
            elif policy_document_id is not None:
                has_semantic_evidence = any(
                    is_located_scientific(
                        item, allowed_source_types={"policy_text"}
                    )
                    for item in edge_evidence
                )
                source_label = "policy text"
            elif report_id is not None:
                has_semantic_evidence = any(
                    is_located_scientific(
                        item, allowed_source_types={"report_text"}
                    )
                    for item in edge_evidence
                )
                source_label = "report text"
            else:
                has_semantic_evidence = any(
                    is_generic_semantic(item) for item in edge_evidence
                )
                source_label = "semantic source"
            if not has_semantic_evidence:
                errors.append(
                    f"edge {edge_id} relation {relation} requires verified "
                    f"{source_label} evidence"
                )
        if relation == "REPORTS_FINDING" and target_id:
            incoming_findings[target_id] = incoming_findings.get(target_id, 0) + 1
        if relation == "HAS_OUTCOME" and source_id:
            outcome_edges[source_id] = outcome_edges.get(source_id, 0) + 1
        if relation == "INDICATES_GAP" and target_node and target_node.get("type") == "research_gap":
            gap_evidence_edges[target_id] = gap_evidence_edges.get(target_id, 0) + 1
        if relation in {"SUPPORTED_BY_EVIDENCE", "CHALLENGED_BY_EVIDENCE"} and source_node and source_node.get("type") == "research_gap":
            gap_evidence_edges[source_id] = gap_evidence_edges.get(source_id, 0) + 1
        if relation == "ADDRESSES_GAP" and source_id:
            hypothesis_gap_edges[source_id] = hypothesis_gap_edges.get(source_id, 0) + 1

    for owner_kind, owners in (("node", nodes), ("edge", edges)):
        for owner in owners:
            if not isinstance(owner, dict) or owner.get("origin") not in {"computed", "inferred"}:
                continue
            derivation = owner.get("derivation") or {}
            if (
                owner.get("layer") in {"analytics", "discovery"}
                and not derivation.get("input_node_ids")
                and not derivation.get("input_edge_ids")
            ):
                errors.append(
                    f"{owner_kind} {owner.get('id')} derivation has no graph inputs"
                )
            for node_id in derivation.get("input_node_ids", []):
                if node_id not in node_by_id:
                    errors.append(f"{owner_kind} {owner.get('id')} derivation references missing node {node_id}")
            for edge_id in derivation.get("input_edge_ids", []):
                if edge_id not in edge_by_id:
                    errors.append(f"{owner_kind} {owner.get('id')} derivation references missing edge {edge_id}")

    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = node.get("id")
        if node.get("type") == "finding":
            if incoming_findings.get(node_id, 0) == 0:
                errors.append(f"finding {node_id} is not linked from a paper with REPORTS_FINDING")
            if outcome_edges.get(node_id, 0) == 0:
                warnings.append(f"finding {node_id} has no HAS_OUTCOME edge")
        elif node.get("type") == "research_gap" and gap_evidence_edges.get(node_id, 0) == 0:
            errors.append(f"research_gap {node_id} has no evidence relation")
        elif node.get("type") == "hypothesis":
            if hypothesis_gap_edges.get(node_id, 0) == 0:
                errors.append(f"hypothesis {node_id} does not ADDRESSES_GAP")
            if outcome_edges.get(node_id, 0) == 0:
                errors.append(f"hypothesis {node_id} has no HAS_OUTCOME edge")

    used_evidence: set[str] = set()
    for owner in [*nodes, *edges]:
        if isinstance(owner, dict):
            used_evidence.update(owner.get("evidence_ids") or [])
            if owner.get("type") == "paper":
                used_evidence.update(paper_property_evidence_ids(owner))
    unused = sorted(set(evidence_by_id) - used_evidence)
    if unused:
        warnings.append(f"unused evidence ids: {unused}")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a GreenFin research_graph v0.2 JSON file")
    parser.add_argument("graph", type=Path)
    args = parser.parse_args()
    try:
        graph = json.loads(args.graph.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read graph: {exc}")
        return 2

    errors, warnings = validate_graph(graph)
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        print(f"FAILED: {len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    print(f"OK: {len(graph.get('nodes', []))} nodes, {len(graph.get('edges', []))} edges, {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
