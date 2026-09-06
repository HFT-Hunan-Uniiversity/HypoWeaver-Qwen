"""Online orchestration around the migrated deterministic Group1 engine."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .discovery_bridge import EvidenceGraphBridge, evidence_bundle_to_research_graph
from .discovery_engine import build_discovery_outputs, validate_discovery_outputs
from .discovery_engine.research_graph import validate_graph
from .discovery_engine.schema_gate import GRAPH_SCHEMA_PATH, require_valid_instance
from .knowledge_models import EvidenceBundle


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


class ReviewedGraphPatch(BaseModel):
    """Human-reviewed scientific nodes and edges; evidence cannot be added here."""

    model_config = ConfigDict(extra="forbid")

    nodes: list[dict[str, Any]] = Field(default_factory=list, max_length=20_000)
    edges: list[dict[str, Any]] = Field(default_factory=list, max_length=100_000)
    review_note: str = Field(min_length=1, max_length=4000)


class DiscoveryBuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_bundle: EvidenceBundle
    reviewed_graph_patch: ReviewedGraphPatch
    discovery_config: dict[str, Any]
    novelty_search: dict[str, Any]


class DiscoveryReleasePreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "discovery-release-preview/1.0.0"
    evidence_bridge: EvidenceGraphBridge
    reviewed_base_graph: dict[str, Any]
    final_research_graph: dict[str, Any]
    research_landscape: dict[str, Any]
    gap_cards: list[dict[str, Any]]
    hypothesis_cards: list[dict[str, Any]]
    validation_warnings: list[str]
    reviewer: str
    review_note: str


def _validate_reviewed_patch(
    *,
    patch: ReviewedGraphPatch,
    graph: dict[str, Any],
) -> None:
    known_nodes = {item["id"] for item in graph["nodes"]}
    known_edges = {item["id"] for item in graph["edges"]}
    known_evidence = {item["id"] for item in graph["evidence"]}
    patch_node_ids: set[str] = set()
    for node in patch.nodes:
        node_id = str(node.get("id") or "")
        if not node_id:
            raise ValueError("reviewed graph node is missing id")
        if node_id in known_nodes or node_id in patch_node_ids:
            raise ValueError(f"reviewed graph node id is duplicated: {node_id}")
        patch_node_ids.add(node_id)
        if node.get("origin") != "curated" or node.get("review_status") != "human_verified":
            raise ValueError(
                f"reviewed graph node {node_id} must be curated and human_verified"
            )
        references = node.get("evidence_ids")
        if not isinstance(references, list) or not references:
            raise ValueError(f"reviewed graph node {node_id} requires evidence_ids")
        missing = sorted(set(map(str, references)) - known_evidence)
        if missing:
            raise ValueError(
                f"reviewed graph node {node_id} references unknown evidence: {missing}"
            )

    all_nodes = known_nodes | patch_node_ids
    patch_edge_ids: set[str] = set()
    for edge in patch.edges:
        edge_id = str(edge.get("id") or "")
        if not edge_id:
            raise ValueError("reviewed graph edge is missing id")
        if edge_id in known_edges or edge_id in patch_edge_ids:
            raise ValueError(f"reviewed graph edge id is duplicated: {edge_id}")
        patch_edge_ids.add(edge_id)
        if edge.get("origin") != "curated" or edge.get("review_status") != "human_verified":
            raise ValueError(
                f"reviewed graph edge {edge_id} must be curated and human_verified"
            )
        for endpoint in ("source", "target"):
            if str(edge.get(endpoint) or "") not in all_nodes:
                raise ValueError(
                    f"reviewed graph edge {edge_id} has unknown {endpoint}"
                )
        references = edge.get("evidence_ids")
        if not isinstance(references, list) or not references:
            raise ValueError(f"reviewed graph edge {edge_id} requires evidence_ids")
        missing = sorted(set(map(str, references)) - known_evidence)
        if missing:
            raise ValueError(
                f"reviewed graph edge {edge_id} references unknown evidence: {missing}"
            )


def apply_reviewed_graph_patch(
    bridge: EvidenceGraphBridge,
    patch: ReviewedGraphPatch,
    *,
    reviewer: str,
) -> dict[str, Any]:
    """Apply reviewed scientific interpretation without changing source evidence."""

    graph = copy.deepcopy(bridge.research_graph)
    _validate_reviewed_patch(patch=patch, graph=graph)
    parent_snapshot_id = graph["snapshot_id"]
    graph["nodes"].extend(copy.deepcopy(patch.nodes))
    graph["edges"].extend(copy.deepcopy(patch.edges))
    graph["nodes"].sort(key=lambda item: item["id"])
    graph["edges"].sort(key=lambda item: item["id"])
    graph["build"]["parent_snapshot_id"] = parent_snapshot_id
    graph["build"]["base_graph_id"] = bridge.research_graph["graph_id"]
    graph["build"]["base_graph_hash"] = _canonical_sha256(bridge.research_graph)
    graph["build"]["notes"] = (
        f"Human-reviewed graph patch by {reviewer}: {patch.review_note}"
    )
    graph["statistics"].update(
        {
            "node_count": len(graph["nodes"]),
            "edge_count": len(graph["edges"]),
            "evidence_count": len(graph["evidence"]),
        }
    )
    identity = copy.deepcopy(graph)
    identity["snapshot_id"] = None
    graph["snapshot_id"] = f"{graph['graph_id']}@{_canonical_sha256(identity)[:24]}"
    errors, _warnings = validate_graph(graph)
    if errors:
        raise ValueError("reviewed research graph is invalid: " + "; ".join(errors[:20]))
    require_valid_instance(graph, GRAPH_SCHEMA_PATH, "reviewed research graph")
    return graph


def build_discovery_release_preview(
    request: DiscoveryBuildRequest,
    *,
    reviewer: str,
) -> DiscoveryReleasePreview:
    bridge = evidence_bundle_to_research_graph(request.evidence_bundle)
    reviewed_graph = apply_reviewed_graph_patch(
        bridge,
        request.reviewed_graph_patch,
        reviewer=reviewer,
    )
    artifacts = build_discovery_outputs(
        reviewed_graph,
        request.discovery_config,
        request.novelty_search,
    )
    errors, warnings = validate_discovery_outputs(
        graph=artifacts.graph,
        landscape=artifacts.landscape,
        gap_cards=artifacts.gap_cards,
        hypothesis_cards=artifacts.hypothesis_cards,
        novelty_search=request.novelty_search,
        small_sample_threshold=request.discovery_config["run"][
            "small_sample_threshold"
        ],
    )
    if errors:
        raise ValueError("discovery release is invalid: " + "; ".join(errors[:20]))
    return DiscoveryReleasePreview(
        evidence_bridge=bridge,
        reviewed_base_graph=reviewed_graph,
        final_research_graph=artifacts.graph,
        research_landscape=artifacts.landscape,
        gap_cards=list(artifacts.gap_cards),
        hypothesis_cards=list(artifacts.hypothesis_cards),
        validation_warnings=sorted(
            set([*bridge.warnings, *artifacts.validation_warnings, *warnings])
        ),
        reviewer=reviewer,
        review_note=request.reviewed_graph_patch.review_note,
    )
