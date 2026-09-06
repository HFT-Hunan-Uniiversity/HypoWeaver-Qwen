"""Build evidence-grounded discovery artifacts from a validated base graph.

The module deliberately does not infer scientific content from labels.  A run
configuration supplies the already-reviewed memberships, claims and graph
references.  This builder resolves those references, computes reproducible
landscape metrics, adds the required analytics/discovery relations and emits a
content-addressed release.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from src.reason.schema_gate import require_valid_instance
from src.reason.validate_research_graph import validate_graph


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"
CONFIG_SCHEMA = SCHEMAS / "discovery_config.schema.json"
NOVELTY_SCHEMA = SCHEMAS / "novelty_search.schema.json"
GRAPH_SCHEMA = SCHEMAS / "research_graph.schema.json"
LANDSCAPE_SCHEMA = SCHEMAS / "research_landscape.schema.json"
GAP_SCHEMA = SCHEMAS / "gap_card.schema.json"
HYPOTHESIS_SCHEMA = SCHEMAS / "hypothesis_card.schema.json"
RELEASE_SCHEMA = SCHEMAS / "discovery_release_manifest.schema.json"

GENERATOR = "src/discovery/builder.py@0.1.0"
KNOWN_TREND_COMPONENTS = {
    "recent_paper_share",
    "growth_rate",
    "citation_velocity",
    "policy_alignment",
    "method_diversity",
}


class DiscoveryBuildError(ValueError):
    """Raised when a configured scientific reference cannot be resolved."""


@dataclass(frozen=True)
class DiscoveryArtifacts:
    graph: dict[str, Any]
    landscape: dict[str, Any]
    gap_cards: tuple[dict[str, Any], ...]
    hypothesis_cards: tuple[dict[str, Any], ...]
    config_sha256: str
    novelty_search_sha256: str
    base_graph_sha256: str
    validation_warnings: tuple[str, ...]


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _pretty_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalize_label(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).strip().casefold()
    return re.sub(r"\s+", " ", value)


def _unique(values: Iterable[str]) -> list[str]:
    return sorted(set(value for value in values if value))


def _base_graph_hash(graph: dict[str, Any]) -> str:
    return canonical_sha256(graph)


def _content_snapshot_id(graph: dict[str, Any]) -> str:
    payload = copy.deepcopy(graph)
    payload["snapshot_id"] = None
    return f"{graph['graph_id']}@{canonical_sha256(payload)[:24]}"


def _landscape_snapshot_id(
    *, base_snapshot_id: str, landscape_config: dict[str, Any], as_of: str
) -> str:
    digest = canonical_sha256(
        {
            "base_snapshot_id": base_snapshot_id,
            "landscape": landscape_config,
            "as_of": as_of,
        }
    )
    return f"landscape:{digest[:24]}"


def _index_graph(graph: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    return (
        {item["id"]: item for item in graph["nodes"]},
        {item["id"]: item for item in graph["edges"]},
        {item["id"]: item for item in graph["evidence"]},
    )


def _require_prefixed_id(value: str, prefix: str, label: str) -> None:
    if not value.startswith(f"{prefix}:"):
        raise DiscoveryBuildError(f"{label} must start with {prefix}:; got {value}")


def _require_nodes(
    node_by_id: dict[str, dict[str, Any]],
    node_ids: Iterable[str],
    *,
    label: str,
    allowed_types: set[str] | None = None,
) -> None:
    for node_id in node_ids:
        node = node_by_id.get(node_id)
        if node is None:
            raise DiscoveryBuildError(f"{label} references missing graph node {node_id}")
        if allowed_types is not None and node.get("type") not in allowed_types:
            raise DiscoveryBuildError(
                f"{label} expects {sorted(allowed_types)}, but {node_id} is {node.get('type')}"
            )


def _require_evidence(
    evidence_by_id: dict[str, dict[str, Any]], evidence_ids: Iterable[str], *, label: str
) -> None:
    for evidence_id in evidence_ids:
        if evidence_id not in evidence_by_id:
            raise DiscoveryBuildError(
                f"{label} references missing graph evidence {evidence_id}"
            )


def _paper_date(node: dict[str, Any]) -> date | None:
    properties = node.get("properties") or {}
    published = properties.get("published_date")
    if isinstance(published, str) and published:
        try:
            if len(published) == 4:
                return date(int(published), 1, 1)
            if len(published) == 7:
                return date.fromisoformat(f"{published}-01")
            return date.fromisoformat(published[:10])
        except (ValueError, TypeError):
            pass
    year = properties.get("year")
    if isinstance(year, int):
        try:
            return date(year, 1, 1)
        except ValueError:
            return None
    return None


def _window_dates(window: dict[str, str]) -> tuple[date, date, date, date]:
    current_from = date.fromisoformat(window["current_from"])
    current_to = date.fromisoformat(window["current_to"])
    baseline_from = date.fromisoformat(window["baseline_from"])
    baseline_to = date.fromisoformat(window["baseline_to"])
    if current_from > current_to:
        raise DiscoveryBuildError("landscape current_from must not exceed current_to")
    if baseline_from > baseline_to:
        raise DiscoveryBuildError("landscape baseline_from must not exceed baseline_to")
    if baseline_to >= current_from:
        raise DiscoveryBuildError("baseline window must end before current window begins")
    return current_from, current_to, baseline_from, baseline_to


def _require_no_future_papers(
    node_by_id: dict[str, dict[str, Any]],
    paper_ids: Iterable[str],
    *,
    as_of: str,
    label: str,
) -> None:
    as_of_date = date.fromisoformat(as_of[:10])
    for paper_id in paper_ids:
        published = _paper_date(node_by_id[paper_id])
        if published is not None and published > as_of_date:
            raise DiscoveryBuildError(
                f"{label} includes future-dated paper {paper_id} ({published.isoformat()}) after as_of {as_of_date.isoformat()}"
            )


def _method_diversity(
    paper_ids: list[str], edge_by_id: dict[str, dict[str, Any]]
) -> float:
    if not paper_ids:
        return 0.0
    paper_set = set(paper_ids)
    method_targets = {
        edge["target"]
        for edge in edge_by_id.values()
        if edge.get("source") in paper_set
        and edge.get("type")
        in {"USES_METHOD", "USES_MODEL", "USES_IDENTIFICATION_STRATEGY"}
    }
    return round(min(1.0, len(method_targets) / len(paper_ids)), 6)


def _policy_alignment(
    paper_ids: list[str], edge_by_id: dict[str, dict[str, Any]]
) -> float:
    if not paper_ids:
        return 0.0
    aligned = {
        edge["source"]
        for edge in edge_by_id.values()
        if edge.get("source") in set(paper_ids)
        and edge.get("type") in {"EVALUATES_POLICY", "REFERENCES_POLICY"}
    }
    return round(len(aligned) / len(paper_ids), 6)


def _hotness(
    components: dict[str, float | None], weights: dict[str, float]
) -> float:
    unknown = sorted(set(weights) - KNOWN_TREND_COMPONENTS)
    if unknown:
        raise DiscoveryBuildError(f"unknown trend scoring components: {unknown}")
    available: list[tuple[float, float]] = []
    for name, weight in weights.items():
        value = components.get(name)
        if value is None or weight <= 0:
            continue
        normalized = max(0.0, min(1.0, float(value)))
        available.append((normalized, float(weight)))
    denominator = sum(weight for _, weight in available)
    if denominator <= 0:
        return 0.0
    return round(100.0 * sum(value * weight for value, weight in available) / denominator, 4)


def _metrics(
    *,
    paper_ids: list[str],
    node_by_id: dict[str, dict[str, Any]],
    edge_by_id: dict[str, dict[str, Any]],
    window: dict[str, str],
    small_sample_threshold: int,
    weights: dict[str, float],
    metric_inputs: dict[str, Any] | None,
) -> dict[str, Any]:
    current_from, current_to, baseline_from, baseline_to = _window_dates(window)
    dates = [_paper_date(node_by_id[paper_id]) for paper_id in paper_ids]
    current_count = sum(
        value is not None and current_from <= value <= current_to for value in dates
    )
    baseline_count = sum(
        value is not None and baseline_from <= value <= baseline_to for value in dates
    )
    paper_count = len(paper_ids)
    recent_share = round(current_count / paper_count, 6) if paper_count else 0.0
    growth_rate: float | None
    if paper_count < small_sample_threshold or baseline_count == 0:
        growth_rate = None
    else:
        growth_rate = round((current_count - baseline_count) / baseline_count, 6)
    inputs = metric_inputs or {}
    citation_velocity = inputs.get("citation_velocity")
    policy_alignment = _policy_alignment(paper_ids, edge_by_id)
    method_diversity = _method_diversity(paper_ids, edge_by_id)
    components = {
        "recent_paper_share": recent_share,
        "growth_rate": growth_rate,
        "citation_velocity": citation_velocity,
        "policy_alignment": policy_alignment,
        "method_diversity": method_diversity,
    }
    return {
        "paper_count": paper_count,
        "recent_paper_share": recent_share,
        "growth_rate": growth_rate,
        "citation_velocity": citation_velocity,
        "policy_alignment": policy_alignment,
        "method_diversity": method_diversity,
        "hotness_score": _hotness(components, weights),
    }


def _source_profiles(
    node_by_id: dict[str, dict[str, Any]], input_node_ids: Iterable[str]
) -> list[str]:
    values: set[str] = set()
    for node_id in input_node_ids:
        node = node_by_id.get(node_id)
        if node:
            values.update(node.get("source_profile_ids") or [])
    return sorted(values)


def _derivation(
    *,
    method: str,
    input_snapshot_id: str,
    input_node_ids: Iterable[str],
    input_edge_ids: Iterable[str] = (),
    parameters: dict[str, Any] | None = None,
    prompt_hash: str | None = None,
    method_version: str = "0.1.0",
) -> dict[str, Any]:
    return {
        "method": method,
        "method_version": method_version,
        "input_snapshot_id": input_snapshot_id,
        "input_node_ids": _unique(input_node_ids),
        "input_edge_ids": _unique(input_edge_ids),
        "parameters": parameters or {},
        "prompt_hash": prompt_hash,
        "code_ref": "src/discovery/builder.py",
    }


def _node(
    *,
    node_id: str,
    node_type: str,
    layer: str,
    label: str,
    description: str | None,
    origin: str,
    review_status: str,
    confidence: float,
    as_of: str,
    evidence_ids: Iterable[str],
    source_profile_ids: Iterable[str],
    derivation: dict[str, Any],
    properties: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": node_id,
        "type": node_type,
        "layer": layer,
        "label": label,
        "normalized_label": _normalize_label(label),
        "aliases": [],
        "description": description,
        "origin": origin,
        "review_status": review_status,
        "confidence": float(confidence),
        "version": 1,
        "validity": {"observed_at": as_of, "valid_from": None, "valid_to": None},
        "source_profile_ids": _unique(source_profile_ids),
        "evidence_ids": _unique(evidence_ids),
        "derivation": derivation,
        "properties": properties,
    }


def _edge_id(source: str, relation: str, target: str) -> str:
    digest = hashlib.sha256(f"{source}\x1f{relation}\x1f{target}".encode("utf-8")).hexdigest()
    return f"edge:{digest[:20]}"


def _add_edge(
    graph: dict[str, Any],
    *,
    source: str,
    target: str,
    relation: str,
    layer: str,
    origin: str,
    confidence: float,
    as_of: str,
    evidence_ids: Iterable[str],
    base_snapshot_id: str,
    input_node_ids: Iterable[str],
    properties: dict[str, Any] | None = None,
) -> None:
    edge_id = _edge_id(source, relation, target)
    existing = next((item for item in graph["edges"] if item["id"] == edge_id), None)
    if existing is not None:
        expected = (source, relation, target)
        actual = (existing.get("source"), existing.get("type"), existing.get("target"))
        if actual != expected:
            raise DiscoveryBuildError(f"edge id collision for {edge_id}")
        return
    graph["edges"].append(
        {
            "id": edge_id,
            "source": source,
            "target": target,
            "type": relation,
            "layer": layer,
            "origin": origin,
            "review_status": "auto_validated" if origin == "computed" else "unreviewed",
            "confidence": float(confidence),
            "version": 1,
            "validity": {"observed_at": as_of, "valid_from": None, "valid_to": None},
            "evidence_ids": _unique(evidence_ids),
            "derivation": _derivation(
                method=f"discovery_relation:{relation.lower()}",
                input_snapshot_id=base_snapshot_id,
                input_node_ids=input_node_ids,
                parameters={"relation": relation},
            ),
            "context": {"snapshot_id": base_snapshot_id},
            "properties": properties or {"assertion_kind": "derived_discovery_relation"},
        }
    )


def _new_ids(config: dict[str, Any]) -> list[str]:
    values: list[str] = [item["id"] for item in config.get("inferred_entities", [])]
    for stream in config["landscape"]["streams"]:
        values.extend([stream["stream_id"], stream["trend_id"]])
    values.extend(item["controversy_id"] for item in config["landscape"]["controversies"])
    values.extend(item["gap_id"] for item in config["gaps"])
    values.extend(item["hypothesis_id"] for item in config["hypotheses"])
    return values


def _prepare_graph(
    base_graph: dict[str, Any],
    config: dict[str, Any],
    *,
    config_hash: str,
    novelty_hash: str,
    landscape_snapshot_id: str,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    graph = copy.deepcopy(base_graph)
    run = config["run"]
    base_snapshot_id = base_graph["snapshot_id"]
    base_hash = _base_graph_hash(base_graph)
    graph["as_of"] = run["as_of"]
    graph["build"].update(
        {
            "created_at": run["build_timestamp"],
            "generator": run.get("generator", GENERATOR),
            "pipeline_run_id": run["pipeline_run_id"],
            "base_graph_id": base_graph["graph_id"],
            "base_graph_hash": base_hash,
            "parent_snapshot_id": base_snapshot_id,
            "code_version": run.get("code_version"),
            "config_hash": config_hash,
            "input_manifest_hash": canonical_sha256(
                {"base_graph": base_hash, "config": config_hash, "novelty": novelty_hash}
            ),
            "notes": run["corpus_limit_statement"],
        }
    )
    graph["build"]["input_contract_versions"] = _unique(
        [
            *graph["build"].get("input_contract_versions", []),
            "discovery-config/0.1.0",
            "novelty-search/0.1.0",
        ]
    )

    node_by_id, edge_by_id, evidence_by_id = _index_graph(graph)
    ids = _new_ids(config)
    if len(ids) != len(set(ids)):
        duplicates = sorted({value for value in ids if ids.count(value) > 1})
        raise DiscoveryBuildError(f"duplicate configured analytics/discovery ids: {duplicates}")
    collisions = sorted(set(ids).intersection(node_by_id))
    if collisions:
        raise DiscoveryBuildError(f"configured ids collide with base graph nodes: {collisions}")

    field_by_id = {item["field_id"]: item for item in config["landscape"]["fields"]}
    if len(field_by_id) != len(config["landscape"]["fields"]):
        raise DiscoveryBuildError("landscape fields contain duplicate field_id values")

    inferred_entities = config.get("inferred_entities", [])
    inferred_by_id = {item["id"]: item for item in inferred_entities}
    allowed_inferred_types = {
        "variable",
        "measure",
        "dataset",
        "method",
        "model",
        "identification_strategy",
        "mechanism",
    }
    for entity in inferred_entities:
        entity_id = entity["id"]
        entity_type = entity["type"]
        if entity_type not in allowed_inferred_types:
            raise DiscoveryBuildError(
                f"inferred entity {entity_id} has unsupported type {entity_type}"
            )
        _require_prefixed_id(entity_id, entity_type, "inferred entity id")
        _require_evidence(
            evidence_by_id,
            entity["evidence_ids"],
            label=f"inferred entity {entity_id}",
        )
        unknown_inputs = sorted(
            set(entity["derivation"]["input_refs"])
            - set(node_by_id)
            - set(inferred_by_id)
        )
        if unknown_inputs:
            raise DiscoveryBuildError(
                f"inferred entity {entity_id} references missing derivation nodes {unknown_inputs}"
            )
        unknown_edges = sorted(
            set(entity["derivation"]["input_edge_refs"]) - set(edge_by_id)
        )
        if unknown_edges:
            raise DiscoveryBuildError(
                f"inferred entity {entity_id} references missing derivation edges {unknown_edges}"
            )

    for entity in inferred_entities:
        entity_id = entity["id"]
        entity_type = entity["type"]
        input_refs = entity["derivation"]["input_refs"]
        inferred_node = _node(
            node_id=entity_id,
            node_type=entity_type,
            layer="source" if entity_type == "dataset" else "knowledge",
            label=entity["label"],
            description=entity["description"],
            origin="inferred",
            review_status="unreviewed",
            confidence=entity["confidence"],
            as_of=run["as_of"],
            evidence_ids=entity["evidence_ids"],
            source_profile_ids=_source_profiles(node_by_id, input_refs),
            derivation=_derivation(
                method=entity["derivation"]["method"],
                method_version=entity["derivation"]["method_version"],
                input_snapshot_id=base_snapshot_id,
                input_node_ids=input_refs,
                input_edge_ids=entity["derivation"]["input_edge_refs"],
                parameters={
                    **entity["derivation"]["parameters"],
                    "design_candidate": True,
                    "corpus_limit": run["corpus_limit_statement"],
                },
                prompt_hash=entity["derivation"]["prompt_hash"],
            ),
            properties={
                **entity["properties"],
                "design_candidate": True,
                "scientific_status": "needs_scientific_review",
                "corpus_limited": True,
            },
        )
        graph["nodes"].append(inferred_node)
        node_by_id[entity_id] = inferred_node

    weights = config["landscape"]["methodology"]["trend_scoring"]["component_weights"]
    prompt_hash = config["landscape"]["methodology"]["llm_labeling"]["prompt_hash"]
    window = config["landscape"]["window"]
    if date.fromisoformat(window["current_to"]) > date.fromisoformat(run["as_of"][:10]):
        raise DiscoveryBuildError("landscape current_to must not be later than run.as_of")
    threshold = run["small_sample_threshold"]

    field_outputs: list[dict[str, Any]] = []
    for field in config["landscape"]["fields"]:
        _require_nodes(node_by_id, [field["graph_node_id"]], label=f"field {field['field_id']}", allowed_types={"research_field"})
        _require_nodes(node_by_id, field["member_paper_ids"], label=f"field {field['field_id']} papers", allowed_types={"paper"})
        _require_no_future_papers(
            node_by_id,
            field["member_paper_ids"],
            as_of=run["as_of"],
            label=f"field {field['field_id']}",
        )
        _require_nodes(node_by_id, field["top_topic_ids"], label=f"field {field['field_id']} topics", allowed_types={"topic"})
        _require_nodes(node_by_id, field["top_model_ids"], label=f"field {field['field_id']} models", allowed_types={"model"})
        _require_evidence(evidence_by_id, field["evidence_ids"], label=f"field {field['field_id']}")
        field_outputs.append(
            {
                "field_id": field["field_id"],
                "graph_node_id": field["graph_node_id"],
                "label": field["label"],
                "metrics": _metrics(
                    paper_ids=field["member_paper_ids"],
                    node_by_id=node_by_id,
                    edge_by_id=edge_by_id,
                    window=window,
                    small_sample_threshold=threshold,
                    weights=weights,
                    metric_inputs=field.get("metric_inputs"),
                ),
                "top_topic_ids": _unique(field["top_topic_ids"]),
                "top_model_ids": _unique(field["top_model_ids"]),
                "evidence_ids": _unique(field["evidence_ids"]),
            }
        )

    stream_outputs: list[dict[str, Any]] = []
    for stream in config["landscape"]["streams"]:
        _require_prefixed_id(stream["stream_id"], "research_stream", "stream_id")
        _require_prefixed_id(stream["trend_id"], "trend_snapshot", "trend_id")
        unknown_fields = sorted(set(stream["field_ids"]) - set(field_by_id))
        if unknown_fields:
            raise DiscoveryBuildError(
                f"stream {stream['stream_id']} references unknown field_ids {unknown_fields}"
            )
        _require_nodes(node_by_id, stream["member_paper_ids"], label=f"stream {stream['stream_id']} papers", allowed_types={"paper"})
        _require_no_future_papers(
            node_by_id,
            stream["member_paper_ids"],
            as_of=run["as_of"],
            label=f"stream {stream['stream_id']}",
        )
        _require_nodes(node_by_id, stream["core_paper_ids"], label=f"stream {stream['stream_id']} core papers", allowed_types={"paper"})
        if not set(stream["core_paper_ids"]).issubset(stream["member_paper_ids"]):
            raise DiscoveryBuildError(
                f"stream {stream['stream_id']} core_paper_ids must be a subset of member_paper_ids"
            )
        typed_refs = (
            ("top_topic_ids", {"topic"}),
            ("top_theory_ids", {"theory"}),
            ("top_mechanism_ids", {"mechanism"}),
            ("top_variable_ids", {"variable"}),
            ("top_method_ids", {"method", "identification_strategy"}),
            ("top_model_ids", {"model"}),
        )
        for key, allowed in typed_refs:
            _require_nodes(node_by_id, stream[key], label=f"stream {stream['stream_id']} {key}", allowed_types=allowed)
        _require_evidence(evidence_by_id, stream["evidence_ids"], label=f"stream {stream['stream_id']}")

        stream_metrics = _metrics(
            paper_ids=stream["member_paper_ids"],
            node_by_id=node_by_id,
            edge_by_id=edge_by_id,
            window=window,
            small_sample_threshold=threshold,
            weights=weights,
            metric_inputs=stream.get("metric_inputs"),
        )
        stream_inputs = _unique(
            [
                *stream["member_paper_ids"],
                *(field_by_id[field_id]["graph_node_id"] for field_id in stream["field_ids"]),
                *stream["top_topic_ids"],
                *stream["top_theory_ids"],
                *stream["top_mechanism_ids"],
                *stream["top_variable_ids"],
                *stream["top_method_ids"],
                *stream["top_model_ids"],
            ]
        )
        stream_node = _node(
            node_id=stream["stream_id"],
            node_type="research_stream",
            layer="analytics",
            label=stream["label"],
            description=stream["description"],
            origin="computed",
            review_status="auto_validated",
            confidence=stream.get("confidence", stream["label_confidence"]),
            as_of=run["as_of"],
            evidence_ids=stream["evidence_ids"],
            source_profile_ids=_source_profiles(node_by_id, stream_inputs),
            derivation=_derivation(
                method="configured_research_stream",
                input_snapshot_id=base_snapshot_id,
                input_node_ids=stream_inputs,
                parameters={
                    "corpus_limit": run["corpus_limit_statement"],
                    "clustering": config["landscape"]["methodology"]["clustering"],
                },
                prompt_hash=prompt_hash,
            ),
            properties={
                "stream_id": stream["stream_id"],
                "member_paper_ids": _unique(stream["member_paper_ids"]),
                "core_paper_ids": _unique(stream["core_paper_ids"]),
                "metrics": stream_metrics,
                "corpus_limited": True,
            },
        )
        graph["nodes"].append(stream_node)
        node_by_id[stream_node["id"]] = stream_node

        trend_node = _node(
            node_id=stream["trend_id"],
            node_type="trend_snapshot",
            layer="analytics",
            label=f"{stream['label']} trend as of {run['as_of'][:10]}",
            description="A reproducible, corpus-limited trend measurement; it is not a global literature estimate.",
            origin="computed",
            review_status="auto_validated",
            confidence=stream.get("confidence", stream["label_confidence"]),
            as_of=run["as_of"],
            evidence_ids=stream["evidence_ids"],
            source_profile_ids=_source_profiles(node_by_id, stream_inputs),
            derivation=_derivation(
                method="corpus_limited_trend_scoring",
                input_snapshot_id=base_snapshot_id,
                input_node_ids=stream_inputs,
                parameters={
                    "window": window,
                    "small_sample_threshold": threshold,
                    "component_weights": weights,
                },
            ),
            properties={
                "stream_id": stream["stream_id"],
                "metrics": stream_metrics,
                "growth_suppressed_for_small_sample": stream_metrics["growth_rate"] is None,
                "corpus_limit_statement": run["corpus_limit_statement"],
            },
        )
        graph["nodes"].append(trend_node)
        node_by_id[trend_node["id"]] = trend_node

        for paper_id in stream["member_paper_ids"]:
            _add_edge(
                graph,
                source=paper_id,
                target=stream["stream_id"],
                relation="ASSIGNED_TO_STREAM",
                layer="analytics",
                origin="computed",
                confidence=stream.get("confidence", stream["label_confidence"]),
                as_of=run["as_of"],
                evidence_ids=stream["evidence_ids"],
                base_snapshot_id=base_snapshot_id,
                input_node_ids=[paper_id, *stream_inputs],
            )
        for field_id in stream["field_ids"]:
            field_node_id = field_by_id[field_id]["graph_node_id"]
            _add_edge(
                graph,
                source=stream["stream_id"],
                target=field_node_id,
                relation="STREAM_IN_FIELD",
                layer="analytics",
                origin="computed",
                confidence=stream.get("confidence", stream["label_confidence"]),
                as_of=run["as_of"],
                evidence_ids=stream["evidence_ids"],
                base_snapshot_id=base_snapshot_id,
                input_node_ids=stream_inputs,
            )
        relation_lists = (
            ("top_topic_ids", "STREAM_FOCUSES_ON"),
            ("top_mechanism_ids", "STREAM_FOCUSES_ON"),
            ("top_variable_ids", "STREAM_FOCUSES_ON"),
            ("top_theory_ids", "STREAM_USES_THEORY"),
            ("top_method_ids", "STREAM_USES_METHOD"),
            ("top_model_ids", "STREAM_USES_MODEL"),
        )
        for key, relation in relation_lists:
            for target in stream[key]:
                _add_edge(
                    graph,
                    source=stream["stream_id"],
                    target=target,
                    relation=relation,
                    layer="analytics",
                    origin="computed",
                    confidence=stream.get("confidence", stream["label_confidence"]),
                    as_of=run["as_of"],
                    evidence_ids=stream["evidence_ids"],
                    base_snapshot_id=base_snapshot_id,
                    input_node_ids=stream_inputs,
                )
        _add_edge(
            graph,
            source=stream["trend_id"],
            target=stream["stream_id"],
            relation="TREND_OF",
            layer="analytics",
            origin="computed",
            confidence=stream.get("confidence", stream["label_confidence"]),
            as_of=run["as_of"],
            evidence_ids=stream["evidence_ids"],
            base_snapshot_id=base_snapshot_id,
            input_node_ids=stream_inputs,
        )
        stream_outputs.append(
            {
                "stream_id": stream["stream_id"],
                "graph_node_id": stream["stream_id"],
                "label": stream["label"],
                "description": stream["description"],
                "label_confidence": stream["label_confidence"],
                "field_ids": _unique(stream["field_ids"]),
                "member_paper_ids": _unique(stream["member_paper_ids"]),
                "core_paper_ids": _unique(stream["core_paper_ids"]),
                "top_topic_ids": _unique(stream["top_topic_ids"]),
                "top_theory_ids": _unique(stream["top_theory_ids"]),
                "top_mechanism_ids": _unique(stream["top_mechanism_ids"]),
                "top_variable_ids": _unique(stream["top_variable_ids"]),
                "top_method_ids": _unique(stream["top_method_ids"]),
                "top_model_ids": _unique(stream["top_model_ids"]),
                "metrics": stream_metrics,
                "evidence_ids": _unique(stream["evidence_ids"]),
            }
        )

    controversy_outputs: list[dict[str, Any]] = []
    for controversy in config["landscape"]["controversies"]:
        _require_prefixed_id(controversy["controversy_id"], "controversy", "controversy_id")
        _require_nodes(node_by_id, controversy["finding_ids"], label=controversy["controversy_id"], allowed_types={"finding"})
        _require_evidence(evidence_by_id, controversy["evidence_ids"], label=controversy["controversy_id"])
        controversy_node = _node(
            node_id=controversy["controversy_id"],
            node_type="controversy",
            layer="analytics",
            label=controversy["statement"],
            description=controversy["statement"],
            origin="computed",
            review_status="auto_validated",
            confidence=controversy.get("confidence", 0.7),
            as_of=run["as_of"],
            evidence_ids=controversy["evidence_ids"],
            source_profile_ids=_source_profiles(node_by_id, controversy["finding_ids"]),
            derivation=_derivation(
                method="configured_direction_conflict",
                input_snapshot_id=base_snapshot_id,
                input_node_ids=controversy["finding_ids"],
                parameters={"direction_distribution": controversy["direction_distribution"]},
            ),
            properties={"direction_distribution": controversy["direction_distribution"]},
        )
        graph["nodes"].append(controversy_node)
        node_by_id[controversy_node["id"]] = controversy_node
        for finding_id in controversy["finding_ids"]:
            _add_edge(
                graph,
                source=finding_id,
                target=controversy["controversy_id"],
                relation="INDICATES_CONTROVERSY",
                layer="analytics",
                origin="computed",
                confidence=controversy.get("confidence", 0.7),
                as_of=run["as_of"],
                evidence_ids=controversy["evidence_ids"],
                base_snapshot_id=base_snapshot_id,
                input_node_ids=controversy["finding_ids"],
            )
        controversy_outputs.append(
            {
                "controversy_id": controversy["controversy_id"],
                "statement": controversy["statement"],
                "finding_ids": _unique(controversy["finding_ids"]),
                "direction_distribution": controversy["direction_distribution"],
                "evidence_ids": _unique(controversy["evidence_ids"]),
            }
        )

    for gap in config["gaps"]:
        _require_prefixed_id(gap["gap_id"], "research_gap", "gap_id")
        links = gap["graph_links"]
        _require_nodes(node_by_id, links["indicator_node_ids"], label=f"gap {gap['gap_id']} indicators", allowed_types={"finding", "limitation", "trend_snapshot", "controversy", "policy_document"})
        _require_nodes(node_by_id, links["support_node_ids"], label=f"gap {gap['gap_id']} supports", allowed_types={"finding", "policy_document", "trend_snapshot", "controversy"})
        _require_nodes(node_by_id, links["challenge_node_ids"], label=f"gap {gap['gap_id']} challenges", allowed_types={"finding", "policy_document", "trend_snapshot", "controversy"})
        _require_nodes(node_by_id, links["concern_node_ids"], label=f"gap {gap['gap_id']} concerns", allowed_types={"research_field", "topic", "theory", "mechanism", "variable", "measure", "method", "model", "identification_strategy", "policy_instrument", "population", "context", "research_stream", "controversy"})
        _require_nodes(node_by_id, links["enabled_by_node_ids"], label=f"gap {gap['gap_id']} enablers", allowed_types={"dataset", "measure", "policy_document", "policy_instrument"})
        _require_nodes(node_by_id, gap["supporting_graph_refs"], label=f"gap {gap['gap_id']} supporting_graph_refs")
        _require_evidence(evidence_by_id, gap["supporting_evidence_ids"], label=f"gap {gap['gap_id']}")
        _require_evidence(evidence_by_id, gap["counterevidence_ids"], label=f"gap {gap['gap_id']} counterevidence")
        gap_inputs = _unique(
            [
                *gap["supporting_graph_refs"],
                *gap["derivation"]["input_refs"],
                *(node_id for values in links.values() for node_id in values),
            ]
        )
        _require_nodes(node_by_id, gap_inputs, label=f"gap {gap['gap_id']} derivation")
        gap_node = _node(
            node_id=gap["gap_id"],
            node_type="research_gap",
            layer="discovery",
            label=gap["title"],
            description=gap["statement"],
            origin="inferred",
            review_status="unreviewed",
            confidence=gap.get("confidence", 0.65),
            as_of=run["as_of"],
            evidence_ids=gap["supporting_evidence_ids"],
            source_profile_ids=_source_profiles(node_by_id, gap_inputs),
            derivation=_derivation(
                method=gap["derivation"]["detector"],
                input_snapshot_id=base_snapshot_id,
                input_node_ids=gap_inputs,
                parameters={
                    "workflow_version": gap["derivation"]["workflow_version"],
                    "model": gap["derivation"]["model"],
                    "landscape_snapshot_id": landscape_snapshot_id,
                    "corpus_limit": run["corpus_limit_statement"],
                },
                prompt_hash=gap["derivation"]["prompt_hash"],
            ),
            properties={
                "gap_type": gap["gap_type"],
                "landscape_snapshot_id": landscape_snapshot_id,
                "novelty_search_id": gap["novelty_search_id"],
                "status": gap["status"],
                "corpus_limited": True,
            },
        )
        graph["nodes"].append(gap_node)
        node_by_id[gap_node["id"]] = gap_node
        for source in links["indicator_node_ids"]:
            _add_edge(graph, source=source, target=gap["gap_id"], relation="INDICATES_GAP", layer="discovery", origin="inferred", confidence=gap.get("confidence", 0.65), as_of=run["as_of"], evidence_ids=gap["supporting_evidence_ids"], base_snapshot_id=base_snapshot_id, input_node_ids=gap_inputs)
        for target in links["support_node_ids"]:
            _add_edge(graph, source=gap["gap_id"], target=target, relation="SUPPORTED_BY_EVIDENCE", layer="discovery", origin="inferred", confidence=gap.get("confidence", 0.65), as_of=run["as_of"], evidence_ids=gap["supporting_evidence_ids"], base_snapshot_id=base_snapshot_id, input_node_ids=gap_inputs)
        for target in links["challenge_node_ids"]:
            evidence_ids = gap["counterevidence_ids"] or gap["supporting_evidence_ids"]
            _add_edge(graph, source=gap["gap_id"], target=target, relation="CHALLENGED_BY_EVIDENCE", layer="discovery", origin="inferred", confidence=gap.get("confidence", 0.65), as_of=run["as_of"], evidence_ids=evidence_ids, base_snapshot_id=base_snapshot_id, input_node_ids=gap_inputs)
        for target in links["concern_node_ids"]:
            _add_edge(graph, source=gap["gap_id"], target=target, relation="GAP_CONCERNS", layer="discovery", origin="inferred", confidence=gap.get("confidence", 0.65), as_of=run["as_of"], evidence_ids=gap["supporting_evidence_ids"], base_snapshot_id=base_snapshot_id, input_node_ids=gap_inputs)
        for target in links["enabled_by_node_ids"]:
            _add_edge(graph, source=gap["gap_id"], target=target, relation="ENABLED_BY", layer="discovery", origin="inferred", confidence=gap.get("confidence", 0.65), as_of=run["as_of"], evidence_ids=gap["supporting_evidence_ids"], base_snapshot_id=base_snapshot_id, input_node_ids=gap_inputs)

    for hypothesis in config["hypotheses"]:
        _require_prefixed_id(hypothesis["hypothesis_id"], "hypothesis", "hypothesis_id")
        _require_nodes(node_by_id, hypothesis["gap_card_ids"], label=f"hypothesis {hypothesis['hypothesis_id']} gaps", allowed_types={"research_gap"})
        links = hypothesis["graph_links"]
        typed = (
            ("predictor_node_ids", {"variable", "policy_document", "policy_instrument"}),
            ("outcome_node_ids", {"variable"}),
            ("mediator_node_ids", {"variable"}),
            ("moderator_node_ids", {"variable"}),
            ("mechanism_node_ids", {"mechanism"}),
            ("support_node_ids", {"finding", "policy_document", "trend_snapshot", "controversy"}),
            ("challenge_node_ids", {"finding", "policy_document", "trend_snapshot", "controversy"}),
            ("enabled_by_node_ids", {"dataset", "measure", "policy_document", "policy_instrument"}),
            ("recommended_method_ids", {"method"}),
            ("recommended_model_ids", {"model"}),
            ("recommended_identification_strategy_ids", {"identification_strategy"}),
            ("recommended_dataset_ids", {"dataset"}),
        )
        for key, allowed in typed:
            _require_nodes(node_by_id, links[key], label=f"hypothesis {hypothesis['hypothesis_id']} {key}", allowed_types=allowed)
        mechanism_nodes: list[str] = []
        hypothesis_evidence: list[str] = []
        for index, step in enumerate(hypothesis["mechanism_chain"]):
            mechanism_nodes.extend([step["source_node_id"], step["target_node_id"]])
            hypothesis_evidence.extend(step["evidence_ids"])
            _require_nodes(node_by_id, [step["source_node_id"], step["target_node_id"]], label=f"hypothesis {hypothesis['hypothesis_id']} mechanism_chain[{index}]")
            _require_evidence(evidence_by_id, step["evidence_ids"], label=f"hypothesis {hypothesis['hypothesis_id']} mechanism_chain[{index}]")
        for finding_id in [
            *hypothesis["evidence_balance"]["supporting_finding_ids"],
            *hypothesis["evidence_balance"]["challenging_finding_ids"],
        ]:
            _require_nodes(node_by_id, [finding_id], label=f"hypothesis {hypothesis['hypothesis_id']} evidence balance", allowed_types={"finding"})
            hypothesis_evidence.extend(node_by_id[finding_id]["evidence_ids"])
        _require_nodes(node_by_id, hypothesis["evidence_balance"]["policy_document_ids"], label=f"hypothesis {hypothesis['hypothesis_id']} policies", allowed_types={"policy_document"})
        for variable_group in hypothesis["variables"].values():
            for variable in variable_group:
                _require_nodes(node_by_id, [variable["graph_node_id"]], label=f"hypothesis {hypothesis['hypothesis_id']} variable", allowed_types={"variable"})
                for measurement in variable["measurement_candidates"]:
                    _require_nodes(node_by_id, [measurement["measure_node_id"]], label=f"hypothesis {hypothesis['hypothesis_id']} measure", allowed_types={"measure"})
                    _require_nodes(node_by_id, [measurement["data_source_id"]], label=f"hypothesis {hypothesis['hypothesis_id']} data source", allowed_types={"dataset"})
                    _require_evidence(evidence_by_id, measurement["evidence_ids"], label=f"hypothesis {hypothesis['hypothesis_id']} measurement")
                    hypothesis_evidence.extend(measurement["evidence_ids"])
        hypothesis_evidence = _unique(hypothesis_evidence)
        if not hypothesis_evidence:
            raise DiscoveryBuildError(f"hypothesis {hypothesis['hypothesis_id']} has no graph evidence")
        hypothesis_inputs = _unique(
            [
                *hypothesis["gap_card_ids"],
                *mechanism_nodes,
                *(node_id for values in links.values() for node_id in values),
            ]
        )
        hypothesis_node = _node(
            node_id=hypothesis["hypothesis_id"],
            node_type="hypothesis",
            layer="discovery",
            label=hypothesis["title"],
            description=hypothesis["hypothesis_statement"],
            origin="inferred",
            review_status="unreviewed",
            confidence=hypothesis.get("confidence", 0.6),
            as_of=run["as_of"],
            evidence_ids=hypothesis_evidence,
            source_profile_ids=_source_profiles(node_by_id, hypothesis_inputs),
            derivation=_derivation(
                method="configured_falsifiable_hypothesis",
                input_snapshot_id=base_snapshot_id,
                input_node_ids=hypothesis_inputs,
                parameters={
                    "novelty_search_id": hypothesis["novelty_check_ref"],
                    "corpus_limit": run["corpus_limit_statement"],
                },
            ),
            properties={
                "falsifiable_form": hypothesis["falsifiable_form"],
                "status": hypothesis["status"],
                "corpus_limited": True,
            },
        )
        graph["nodes"].append(hypothesis_node)
        node_by_id[hypothesis_node["id"]] = hypothesis_node
        for gap_id in hypothesis["gap_card_ids"]:
            _add_edge(graph, source=hypothesis["hypothesis_id"], target=gap_id, relation="ADDRESSES_GAP", layer="discovery", origin="inferred", confidence=hypothesis.get("confidence", 0.6), as_of=run["as_of"], evidence_ids=hypothesis_evidence, base_snapshot_id=base_snapshot_id, input_node_ids=hypothesis_inputs)
        relation_lists = (
            ("predictor_node_ids", "HAS_PREDICTOR", "knowledge"),
            ("outcome_node_ids", "HAS_OUTCOME", "knowledge"),
            ("mediator_node_ids", "HAS_MEDIATOR", "knowledge"),
            ("moderator_node_ids", "HAS_MODERATOR", "knowledge"),
            ("mechanism_node_ids", "HAS_MECHANISM", "knowledge"),
            ("support_node_ids", "SUPPORTED_BY_EVIDENCE", "discovery"),
            ("challenge_node_ids", "CHALLENGED_BY_EVIDENCE", "discovery"),
            ("enabled_by_node_ids", "ENABLED_BY", "discovery"),
            ("recommended_method_ids", "RECOMMENDS_METHOD", "discovery"),
            ("recommended_model_ids", "RECOMMENDS_MODEL", "discovery"),
            ("recommended_identification_strategy_ids", "RECOMMENDS_IDENTIFICATION_STRATEGY", "discovery"),
            ("recommended_dataset_ids", "RECOMMENDS_DATASET", "discovery"),
        )
        for key, relation, layer in relation_lists:
            for target in links[key]:
                _add_edge(graph, source=hypothesis["hypothesis_id"], target=target, relation=relation, layer=layer, origin="inferred", confidence=hypothesis.get("confidence", 0.6), as_of=run["as_of"], evidence_ids=hypothesis_evidence, base_snapshot_id=base_snapshot_id, input_node_ids=hypothesis_inputs)

    graph["nodes"] = sorted(graph["nodes"], key=lambda item: item["id"])
    graph["edges"] = sorted(graph["edges"], key=lambda item: item["id"])
    graph["evidence"] = sorted(graph["evidence"], key=lambda item: item["id"])
    graph.setdefault("statistics", {})
    graph["statistics"].update(
        {
            "node_count": len(graph["nodes"]),
            "edge_count": len(graph["edges"]),
            "evidence_count": len(graph["evidence"]),
            "research_stream_count": len(config["landscape"]["streams"]),
            "trend_snapshot_count": len(config["landscape"]["streams"]),
            "research_gap_count": len(config["gaps"]),
            "hypothesis_count": len(config["hypotheses"]),
            "inferred_design_entity_count": len(config.get("inferred_entities", [])),
        }
    )
    graph["snapshot_id"] = _content_snapshot_id(graph)
    return graph, {item["field_id"]: item for item in field_outputs}, {item["stream_id"]: item for item in stream_outputs}


def _novelty_index(novelty_search: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if novelty_search.get("schema_version") == "novelty-search/1.0.1":
        return {novelty_search["search_id"]: novelty_search}
    items = {item["novelty_search_id"]: item for item in novelty_search["searches"]}
    if len(items) != len(novelty_search["searches"]):
        raise DiscoveryBuildError("novelty search bundle contains duplicate novelty_search_id values")
    return items


def _protocol101_candidates(item: dict[str, Any]) -> list[dict[str, Any]]:
    priority = {"exact": 0, "broad": 1, "mechanism": 2, "adjacent": 3, "other": 4}
    candidates: list[dict[str, Any]] = []
    for query in item["searches"]:
        for source_name in sorted(query["sources"]):
            source = query["sources"][source_name]
            for rank, work in enumerate(source["top_results"]):
                paper_id = work.get("paper_id")
                title = work.get("title")
                year = work.get("year")
                if not isinstance(paper_id, str) or not paper_id.strip():
                    continue
                if not isinstance(title, str) or not title.strip():
                    continue
                if title.strip().casefold().startswith("retracted"):
                    continue
                if not isinstance(year, int) or not 1900 <= year <= 2100:
                    continue
                candidates.append(
                    {
                        "paper_id": paper_id,
                        "title": title,
                        "year": year,
                        "query_id": query["query_id"],
                        "query_type": query["query_type"],
                        "source": source_name,
                        "rank": rank,
                        "sort_key": (
                            rank,
                            priority.get(query["query_type"], 3),
                            source_name,
                            paper_id.casefold(),
                        ),
                    }
                )
    candidates.sort(key=lambda value: value["sort_key"])
    deduplicated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        identity = candidate["paper_id"].casefold()
        if identity in seen:
            continue
        seen.add(identity)
        deduplicated.append(candidate)
    return deduplicated


def _card_novelty(
    item: dict[str, Any], assessment: dict[str, Any] | None = None
) -> dict[str, Any]:
    if item.get("schema_version") != "novelty-search/1.0.1":
        return {
            "searched_at": item["searched_at"],
            "queries": item["queries"],
            "sources": item["sources"],
            "nearest_works": item["nearest_works"],
            "coverage_status": item["coverage_status"],
            "remaining_difference": item["remaining_difference"],
        }

    assessment = assessment or {}
    queries = [query["query_text"] for query in item["searches"]]
    sources = sorted(
        {
            source_name
            for query in item["searches"]
            for source_name in query["sources"]
        }
    )
    candidates = _protocol101_candidates(item)
    candidate_by_id = {candidate["paper_id"]: candidate for candidate in candidates}
    reviewed = assessment.get("nearest_works")
    if reviewed is not None:
        missing = sorted(
            {
                work["paper_id"]
                for work in reviewed
                if work["paper_id"] not in candidate_by_id
            }
        )
        if missing:
            raise DiscoveryBuildError(
                "novelty_assessment.nearest_works contains works not returned by the referenced search: "
                f"{missing}"
            )
        nearest_works = reviewed
    else:
        limit = assessment.get(
            "max_nearest_works", item["query_protocol"]["top_result_limit"]
        )
        nearest_works = [
            {
                "paper_id": candidate["paper_id"],
                "title": candidate["title"],
                "year": candidate["year"],
                "overlap": (
                    f"Retrieved by the {candidate['query_type']} query "
                    f"{candidate['query_id']} from {candidate['source']}; overlap is "
                    "bibliographic/title-level only."
                ),
                "difference": (
                    "The bibliographic record does not establish whether the work tests "
                    "the full candidate mechanism and outcome chain; full-text review is required."
                ),
                "verification_status": "unverified",
            }
            for candidate in candidates[:limit]
        ]

    evaluated_count = sum(
        source["evaluated_result_count"]
        for query in item["searches"]
        for source in query["sources"].values()
    )
    coverage_status = assessment.get(
        "coverage_status", "partially_covered" if evaluated_count else "uncertain"
    )
    if coverage_status == "covered" and (
        not nearest_works
        or any(work["verification_status"] != "verified" for work in nearest_works)
    ):
        raise DiscoveryBuildError(
            "novelty coverage_status=covered requires at least one reviewed nearest work and all included works verified"
        )
    remaining_difference = assessment.get("remaining_difference")
    if not remaining_difference:
        status_text = (
            "returned bibliographic candidates"
            if evaluated_count
            else "returned no evaluated bibliographic candidates"
        )
        remaining_difference = (
            f"The declared searches {status_text}, but metadata alone cannot establish "
            f"coverage of the full candidate gap: {item['candidate_gap']} The judgment is "
            f"bounded to {len(queries)} queries, {len(sources)} sources and the declared "
            "as-of date; full-text scientific review remains required."
        )
    return {
        "searched_at": item["searched_at"],
        "queries": queries,
        "sources": sources,
        "nearest_works": nearest_works,
        "coverage_status": coverage_status,
        "remaining_difference": remaining_difference,
    }


def build_discovery_outputs(
    base_graph: dict[str, Any],
    config: dict[str, Any],
    novelty_search: dict[str, Any],
) -> DiscoveryArtifacts:
    """Construct and fully validate all discovery artifacts in memory."""

    require_valid_instance(config, CONFIG_SCHEMA, "Discovery config")
    require_valid_instance(novelty_search, NOVELTY_SCHEMA, "Novelty search")
    require_valid_instance(base_graph, GRAPH_SCHEMA, "Base research graph")
    base_errors, base_warnings = validate_graph(base_graph)
    if base_errors:
        raise DiscoveryBuildError(
            "base graph failed semantic validation:\n"
            + "\n".join(f"- {error}" for error in base_errors)
        )

    config_hash = canonical_sha256(config)
    novelty_hash = canonical_sha256(novelty_search)
    base_hash = _base_graph_hash(base_graph)
    run = config["run"]
    landscape_snapshot_id = _landscape_snapshot_id(
        base_snapshot_id=base_graph["snapshot_id"],
        landscape_config=config["landscape"],
        as_of=run["as_of"],
    )
    graph, fields, streams = _prepare_graph(
        base_graph,
        config,
        config_hash=config_hash,
        novelty_hash=novelty_hash,
        landscape_snapshot_id=landscape_snapshot_id,
    )
    node_by_id, _edge_by_id, evidence_by_id = _index_graph(graph)

    assigned_papers = sorted(
        {paper_id for stream in config["landscape"]["streams"] for paper_id in stream["member_paper_ids"]}
    )
    eligible_base_papers = {
        node["id"]
        for node in base_graph["nodes"]
        if node.get("type") == "paper" and not (node.get("properties") or {}).get("stub", False)
    }
    warnings = _unique(
        [
            *config["landscape"]["warnings"],
            f"CORPUS_LIMIT: {run['corpus_limit_statement']}",
            *(
                [
                    f"SMALL_SAMPLE: eligible paper count {len(assigned_papers)} is below threshold {run['small_sample_threshold']}; growth_rate is null."
                ]
                if len(assigned_papers) < run["small_sample_threshold"]
                else []
            ),
        ]
    )
    landscape = {
        "schema_version": "0.2.0",
        "snapshot_id": landscape_snapshot_id,
        "graph_snapshot_id": graph["snapshot_id"],
        "as_of": run["as_of"],
        "window": config["landscape"]["window"],
        "methodology": config["landscape"]["methodology"],
        "fields": sorted(fields.values(), key=lambda item: item["field_id"]),
        "streams": sorted(streams.values(), key=lambda item: item["stream_id"]),
        "controversies": sorted(
            [
                {
                    "controversy_id": item["controversy_id"],
                    "statement": item["statement"],
                    "finding_ids": _unique(item["finding_ids"]),
                    "direction_distribution": item["direction_distribution"],
                    "evidence_ids": _unique(item["evidence_ids"]),
                }
                for item in config["landscape"]["controversies"]
            ],
            key=lambda item: item["controversy_id"],
        ),
        "frontier_signals": sorted(
            [
                {
                    "signal_id": item["signal_id"],
                    "signal_type": item["signal_type"],
                    "statement": item["statement"],
                    "score": item["score"],
                    "graph_node_ids": _unique(item["graph_node_ids"]),
                    "evidence_ids": _unique(item["evidence_ids"]),
                }
                for item in config["landscape"]["frontier_signals"]
            ],
            key=lambda item: item["signal_id"],
        ),
        "quality": {
            "eligible_paper_count": len(assigned_papers),
            "unassigned_paper_count": len(eligible_base_papers - set(assigned_papers)),
            "cluster_stability": config["landscape"]["cluster_stability"],
            "warnings": warnings,
        },
    }

    novelty_by_id = _novelty_index(novelty_search)
    gap_cards: list[dict[str, Any]] = []
    for item in config["gaps"]:
        novelty = novelty_by_id.get(item["novelty_search_id"])
        if novelty is None:
            raise DiscoveryBuildError(
                f"gap {item['gap_id']} references missing novelty search {item['novelty_search_id']}"
            )
        card = {
            "schema_version": "0.2.0",
            "gap_id": item["gap_id"],
            "graph_snapshot_id": graph["snapshot_id"],
            "landscape_snapshot_id": landscape["snapshot_id"],
            "as_of": run["as_of"],
            "gap_type": item["gap_type"],
            "title": item["title"],
            "statement": item["statement"],
            "current_state": item["current_state"],
            "missing_piece": item["missing_piece"],
            "why_important": item["why_important"],
            "signals": item["signals"],
            "supporting_graph_refs": _unique(item["supporting_graph_refs"]),
            "supporting_evidence_ids": _unique(item["supporting_evidence_ids"]),
            "counterevidence_ids": _unique(item["counterevidence_ids"]),
            "novelty_check": _card_novelty(
                novelty, item.get("novelty_assessment")
            ),
            "data_feasibility": item["data_feasibility"],
            "candidate_research_questions": item.get("candidate_research_questions", []),
            "scores": item["scores"],
            "status": item["status"],
            "derivation": item["derivation"],
            "review": item["review"],
        }
        gap_cards.append(card)

    hypothesis_cards: list[dict[str, Any]] = []
    for item in config["hypotheses"]:
        if item["novelty_check_ref"] not in novelty_by_id:
            raise DiscoveryBuildError(
                f"hypothesis {item['hypothesis_id']} references missing novelty search {item['novelty_check_ref']}"
            )
        card = {
            "schema_version": "0.2.0",
            "hypothesis_id": item["hypothesis_id"],
            "graph_snapshot_id": graph["snapshot_id"],
            "gap_card_ids": _unique(item["gap_card_ids"]),
            "as_of": run["as_of"],
            "title": item["title"],
            "hypothesis_statement": item["hypothesis_statement"],
            "falsifiable_form": item["falsifiable_form"],
            "rationale": item["rationale"],
            "mechanism_chain": item["mechanism_chain"],
            "variables": item["variables"],
            "boundary_conditions": item["boundary_conditions"],
            "predictions": item["predictions"],
            "evidence_balance": item["evidence_balance"],
            "novelty_check_ref": item["novelty_check_ref"],
            "feasibility": item["feasibility"],
            "recommended_design": item["recommended_design"],
            "scores": item["scores"],
            "handoff": item["handoff"],
            "status": item["status"],
            "review": item["review"],
        }
        hypothesis_cards.append(card)

    for signal in landscape["frontier_signals"]:
        _require_nodes(node_by_id, signal["graph_node_ids"], label=f"frontier signal {signal['signal_id']}")
        _require_evidence(evidence_by_id, signal["evidence_ids"], label=f"frontier signal {signal['signal_id']}")

    require_valid_instance(graph, GRAPH_SCHEMA, "Final research graph")
    graph_errors, graph_warnings = validate_graph(graph)
    if graph_errors:
        raise DiscoveryBuildError(
            "final graph failed semantic validation:\n"
            + "\n".join(f"- {error}" for error in graph_errors)
        )
    require_valid_instance(landscape, LANDSCAPE_SCHEMA, "ResearchLandscape")
    for card in gap_cards:
        require_valid_instance(card, GAP_SCHEMA, f"GapCard {card['gap_id']}")
    for card in hypothesis_cards:
        require_valid_instance(
            card, HYPOTHESIS_SCHEMA, f"HypothesisCard {card['hypothesis_id']}"
        )

    from .validate import validate_discovery_outputs

    cross_errors, cross_warnings = validate_discovery_outputs(
        graph=graph,
        landscape=landscape,
        gap_cards=gap_cards,
        hypothesis_cards=hypothesis_cards,
        novelty_search=novelty_search,
        small_sample_threshold=run["small_sample_threshold"],
    )
    if cross_errors:
        raise DiscoveryBuildError(
            "discovery artifacts failed cross-reference validation:\n"
            + "\n".join(f"- {error}" for error in cross_errors)
        )

    return DiscoveryArtifacts(
        graph=graph,
        landscape=landscape,
        gap_cards=tuple(sorted(gap_cards, key=lambda item: item["gap_id"])),
        hypothesis_cards=tuple(
            sorted(hypothesis_cards, key=lambda item: item["hypothesis_id"])
        ),
        config_sha256=config_hash,
        novelty_search_sha256=novelty_hash,
        base_graph_sha256=base_hash,
        validation_warnings=tuple(_unique([*base_warnings, *graph_warnings, *cross_warnings])),
    )


def write_discovery_release(
    artifacts: DiscoveryArtifacts,
    *,
    output_dir: Path,
    config: dict[str, Any],
    base_graph_snapshot_id: str,
) -> dict[str, Any]:
    """Write a validated release using deterministic names and file bytes."""

    output_dir.mkdir(parents=True, exist_ok=True)
    gap_dir = output_dir / "gap_cards"
    hypothesis_dir = output_dir / "hypothesis_cards"
    gap_dir.mkdir(exist_ok=True)
    hypothesis_dir.mkdir(exist_ok=True)

    graph_path = output_dir / "final_research_graph.json"
    landscape_path = output_dir / "research_landscape.json"
    graph_path.write_text(_pretty_json(artifacts.graph), encoding="utf-8")
    landscape_path.write_text(_pretty_json(artifacts.landscape), encoding="utf-8")

    gap_entries: list[dict[str, Any]] = []
    for index, card in enumerate(artifacts.gap_cards, start=1):
        relative = Path("gap_cards") / f"gap_{index:03d}.json"
        path = output_dir / relative
        path.write_text(_pretty_json(card), encoding="utf-8")
        gap_entries.append(
            {
                "id": card["gap_id"],
                "path": relative.as_posix(),
                "sha256": _file_sha256(path),
                "schema_version": card["schema_version"],
            }
        )

    hypothesis_entries: list[dict[str, Any]] = []
    for index, card in enumerate(artifacts.hypothesis_cards, start=1):
        relative = Path("hypothesis_cards") / f"hypothesis_{index:03d}.json"
        path = output_dir / relative
        path.write_text(_pretty_json(card), encoding="utf-8")
        hypothesis_entries.append(
            {
                "id": card["hypothesis_id"],
                "path": relative.as_posix(),
                "sha256": _file_sha256(path),
                "schema_version": card["schema_version"],
            }
        )

    artifact_section = {
        "final_graph": {
            "path": graph_path.name,
            "sha256": _file_sha256(graph_path),
            "schema_version": artifacts.graph["schema_version"],
            "snapshot_id": artifacts.graph["snapshot_id"],
        },
        "research_landscape": {
            "path": landscape_path.name,
            "sha256": _file_sha256(landscape_path),
            "schema_version": artifacts.landscape["schema_version"],
            "snapshot_id": artifacts.landscape["snapshot_id"],
        },
        "gap_cards": gap_entries,
        "hypothesis_cards": hypothesis_entries,
    }
    release_material = {
        "inputs": {
            "base_graph": artifacts.base_graph_sha256,
            "config": artifacts.config_sha256,
            "novelty": artifacts.novelty_search_sha256,
        },
        "artifacts": artifact_section,
    }
    manifest = {
        "schema_version": "0.1.0",
        "release_id": f"discovery_release:{canonical_sha256(release_material)[:24]}",
        "created_at": config["run"]["build_timestamp"],
        "generator": config["run"].get("generator", GENERATOR),
        "corpus_limit_statement": config["run"]["corpus_limit_statement"],
        "inputs": {
            "base_graph_snapshot_id": base_graph_snapshot_id,
            "base_graph_sha256": artifacts.base_graph_sha256,
            "config_sha256": artifacts.config_sha256,
            "novelty_search_sha256": artifacts.novelty_search_sha256,
        },
        "artifacts": artifact_section,
        "verification": {
            "schema_validated": True,
            "semantic_graph_validated": True,
            "cross_references_validated": True,
            "errors": [],
            "warnings": list(artifacts.validation_warnings),
        },
    }
    require_valid_instance(manifest, RELEASE_SCHEMA, "Discovery release manifest")
    manifest_path = output_dir / "discovery_release_manifest.json"
    manifest_path.write_text(_pretty_json(manifest), encoding="utf-8")
    return manifest


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DiscoveryBuildError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DiscoveryBuildError(f"JSON root must be an object: {path}")
    return value
