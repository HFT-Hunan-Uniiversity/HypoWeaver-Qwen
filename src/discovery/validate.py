"""Schema, graph-semantic and cross-artifact validation for discovery releases."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from src.reason.schema_gate import validate_instance
from src.reason.validate_research_graph import validate_graph


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"
GRAPH_SCHEMA = SCHEMAS / "research_graph.schema.json"
LANDSCAPE_SCHEMA = SCHEMAS / "research_landscape.schema.json"
GAP_SCHEMA = SCHEMAS / "gap_card.schema.json"
HYPOTHESIS_SCHEMA = SCHEMAS / "hypothesis_card.schema.json"
NOVELTY_SCHEMA = SCHEMAS / "novelty_search.schema.json"
RELEASE_SCHEMA = SCHEMAS / "discovery_release_manifest.schema.json"


def _duplicates(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    repeated: set[str] = set()
    for value in values:
        if value in seen:
            repeated.add(value)
        seen.add(value)
    return sorted(repeated)


def _index_graph(graph: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    return (
        {item["id"]: item for item in graph.get("nodes", []) if isinstance(item, dict) and item.get("id")},
        {item["id"]: item for item in graph.get("edges", []) if isinstance(item, dict) and item.get("id")},
        {item["id"]: item for item in graph.get("evidence", []) if isinstance(item, dict) and item.get("id")},
    )


def _schema_errors(value: Any, path: Path, label: str) -> list[str]:
    try:
        return [f"{label} schema {item}" for item in validate_instance(value, path)]
    except RuntimeError as exc:
        return [f"{label} schema validation unavailable: {exc}"]


def _require_refs(
    errors: list[str],
    values: Iterable[str],
    index: dict[str, dict[str, Any]],
    *,
    label: str,
    types: set[str] | None = None,
) -> None:
    for value in values:
        item = index.get(value)
        if item is None:
            errors.append(f"{label} references missing id {value}")
        elif types is not None and item.get("type") not in types:
            errors.append(
                f"{label} expects {sorted(types)}, but {value} is {item.get('type')}"
            )


def _has_edge(
    edges: Iterable[dict[str, Any]], source: str, relation: str, target: str | None = None
) -> bool:
    return any(
        edge.get("source") == source
        and edge.get("type") == relation
        and (target is None or edge.get("target") == target)
        for edge in edges
    )


def _incoming_edge(
    edges: Iterable[dict[str, Any]], target: str, relation: str, source: str | None = None
) -> bool:
    return any(
        edge.get("target") == target
        and edge.get("type") == relation
        and (source is None or edge.get("source") == source)
        for edge in edges
    )


def _novelty_body(search: dict[str, Any]) -> dict[str, Any]:
    return {
        "searched_at": search["searched_at"],
        "queries": search["queries"],
        "sources": search["sources"],
        "nearest_works": search["nearest_works"],
        "coverage_status": search["coverage_status"],
        "remaining_difference": search["remaining_difference"],
    }


def _novelty_index(novelty_search: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if novelty_search.get("schema_version") == "novelty-search/1.0.1":
        search_id = novelty_search.get("search_id")
        return {search_id: novelty_search} if isinstance(search_id, str) else {}
    return {
        item["novelty_search_id"]: item
        for item in novelty_search.get("searches", [])
        if isinstance(item, dict) and item.get("novelty_search_id")
    }


def _protocol101_results(search: dict[str, Any]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for query in search.get("searches", []):
        for source_name, source in (query.get("sources") or {}).items():
            for work in source.get("top_results", []):
                paper_id = work.get("paper_id")
                if isinstance(paper_id, str) and paper_id and paper_id not in results:
                    results[paper_id] = {
                        **work,
                        "query_id": query.get("query_id"),
                        "query_type": query.get("query_type"),
                        "source_name": source_name,
                    }
    return results


def _protocol101_queries(search: dict[str, Any]) -> list[str]:
    return [
        query["query_text"]
        for query in search.get("searches", [])
        if isinstance(query.get("query_text"), str)
    ]


def _protocol101_sources(search: dict[str, Any]) -> list[str]:
    return sorted(
        {
            source_name
            for query in search.get("searches", [])
            for source_name in (query.get("sources") or {})
        }
    )


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_discovery_outputs(
    *,
    graph: dict[str, Any],
    landscape: dict[str, Any],
    gap_cards: Iterable[dict[str, Any]],
    hypothesis_cards: Iterable[dict[str, Any]],
    novelty_search: dict[str, Any],
    small_sample_threshold: int | None = None,
) -> tuple[list[str], list[str]]:
    """Return deterministic errors and warnings for a discovery artifact set."""

    gaps = list(gap_cards)
    hypotheses = list(hypothesis_cards)
    errors: list[str] = []
    warnings: list[str] = []
    errors.extend(_schema_errors(graph, GRAPH_SCHEMA, "graph"))
    graph_errors, graph_warnings = validate_graph(graph)
    errors.extend(f"graph semantic {item}" for item in graph_errors)
    warnings.extend(f"graph semantic {item}" for item in graph_warnings)
    errors.extend(_schema_errors(landscape, LANDSCAPE_SCHEMA, "landscape"))
    errors.extend(_schema_errors(novelty_search, NOVELTY_SCHEMA, "novelty_search"))
    for card in gaps:
        errors.extend(_schema_errors(card, GAP_SCHEMA, f"gap {card.get('gap_id')}"))
    for card in hypotheses:
        errors.extend(
            _schema_errors(
                card, HYPOTHESIS_SCHEMA, f"hypothesis {card.get('hypothesis_id')}"
            )
        )

    node_by_id, _edge_by_id, evidence_by_id = _index_graph(graph)
    edges = graph.get("edges", [])
    for node_id, node in node_by_id.items():
        properties = node.get("properties") or {}
        if not properties.get("design_candidate"):
            continue
        if node.get("origin") != "inferred":
            errors.append(f"design candidate {node_id} must have origin inferred")
        if node.get("type") not in {
            "variable",
            "measure",
            "dataset",
            "method",
            "model",
            "identification_strategy",
            "mechanism",
        }:
            errors.append(
                f"design candidate {node_id} has unsupported type {node.get('type')}"
            )
        if not isinstance(properties.get("definition"), str) or not properties["definition"].strip():
            errors.append(f"design candidate {node_id} must state properties.definition")
        if not isinstance(properties.get("granularity"), str) or not properties["granularity"].strip():
            errors.append(f"design candidate {node_id} must state properties.granularity")
        _require_refs(
            errors,
            node.get("evidence_ids", []),
            evidence_by_id,
            label=f"design candidate {node_id} evidence",
        )
        derivation = node.get("derivation") or {}
        if not derivation.get("input_node_ids"):
            errors.append(f"design candidate {node_id} derivation has no input_node_ids")
    gap_by_id = {item.get("gap_id"): item for item in gaps if item.get("gap_id")}
    hypothesis_by_id = {
        item.get("hypothesis_id"): item
        for item in hypotheses
        if item.get("hypothesis_id")
    }
    novelty_by_id = _novelty_index(novelty_search)
    try:
        graph_as_of = _timestamp(str(graph.get("as_of")))
    except ValueError:
        graph_as_of = None
    for search_id, search in novelty_by_id.items():
        try:
            searched_at = _timestamp(search["searched_at"])
            if graph_as_of is not None and searched_at > graph_as_of:
                errors.append(
                    f"novelty search {search_id} searched_at is later than graph as_of"
                )
        except (KeyError, TypeError, ValueError):
            pass
        if search.get("schema_version") == "novelty-search/1.0.1":
            try:
                search_as_of = _timestamp(search["as_of"])
                if graph_as_of is not None and search_as_of > graph_as_of:
                    errors.append(
                        f"novelty search {search_id} as_of is later than graph as_of"
                    )
            except (KeyError, TypeError, ValueError):
                pass
            local = search.get("local_snapshot") or {}
            counts = (
                local.get("eligible_as_of_count"),
                local.get("future_dated_excluded_count"),
                local.get("input_record_count"),
            )
            if all(isinstance(value, int) for value in counts) and counts[0] + counts[1] != counts[2]:
                errors.append(
                    f"novelty search {search_id} local snapshot counts do not reconcile"
                )
            query_types = {
                query.get("query_type") for query in search.get("searches", [])
            }
            missing_query_types = sorted({"exact", "broad", "adjacent"} - query_types)
            if missing_query_types:
                errors.append(
                    f"novelty search {search_id} lacks required query types {missing_query_types}"
                )
            source_names = _protocol101_sources(search)
            if len(source_names) < 3:
                errors.append(
                    f"novelty search {search_id} must cover at least three sources"
                )
            works = _protocol101_results(search).values()
            for query in search.get("searches", []):
                for source_name, source in (query.get("sources") or {}).items():
                    if source.get("evaluated_result_count") != len(source.get("top_results", [])):
                        errors.append(
                            f"novelty search {search_id} query {query.get('query_id')} source {source_name} evaluated_result_count does not match top_results length"
                        )
        else:
            works = search.get("nearest_works", [])
        if graph_as_of is not None:
            for work in works:
                year = work.get("year")
                if isinstance(year, int) and year > graph_as_of.year:
                    errors.append(
                        f"novelty search {search_id} includes future-dated work {work.get('paper_id')} ({year})"
                    )
    for label, values in (
        ("gap card", [str(item.get("gap_id")) for item in gaps]),
        ("hypothesis card", [str(item.get("hypothesis_id")) for item in hypotheses]),
        ("novelty search", [str(value) for value in novelty_by_id]),
    ):
        repeated = _duplicates(values)
        if repeated:
            errors.append(f"duplicate {label} ids: {repeated}")

    if landscape.get("graph_snapshot_id") != graph.get("snapshot_id"):
        errors.append("landscape.graph_snapshot_id does not match final graph snapshot_id")
    if landscape.get("as_of") != graph.get("as_of"):
        errors.append("landscape.as_of does not match final graph as_of")
    if not any(
        isinstance(value, str) and value.startswith("CORPUS_LIMIT:")
        for value in (landscape.get("quality") or {}).get("warnings", [])
    ):
        errors.append("landscape quality warnings must state the corpus limitation")

    field_ids = {
        item.get("field_id")
        for item in landscape.get("fields", [])
        if item.get("field_id")
    }
    for field in landscape.get("fields", []):
        field_id = str(field.get("field_id"))
        _require_refs(
            errors,
            [field.get("graph_node_id")],
            node_by_id,
            label=f"landscape field {field_id}",
            types={"research_field"},
        )
        _require_refs(
            errors,
            field.get("top_topic_ids", []),
            node_by_id,
            label=f"landscape field {field_id} topics",
            types={"topic"},
        )
        _require_refs(
            errors,
            field.get("top_model_ids", []),
            node_by_id,
            label=f"landscape field {field_id} models",
            types={"model"},
        )
        _require_refs(
            errors,
            field.get("evidence_ids", []),
            evidence_by_id,
            label=f"landscape field {field_id} evidence",
        )

    for stream in landscape.get("streams", []):
        stream_id = str(stream.get("stream_id"))
        if stream.get("graph_node_id") != stream_id:
            errors.append(
                f"landscape stream {stream_id} graph_node_id must equal stream_id"
            )
        _require_refs(
            errors,
            [stream_id],
            node_by_id,
            label=f"landscape stream {stream_id}",
            types={"research_stream"},
        )
        unknown_fields = sorted(set(stream.get("field_ids", [])) - field_ids)
        if unknown_fields:
            errors.append(
                f"landscape stream {stream_id} references unknown fields {unknown_fields}"
            )
        _require_refs(
            errors,
            stream.get("member_paper_ids", []),
            node_by_id,
            label=f"landscape stream {stream_id} members",
            types={"paper"},
        )
        if not set(stream.get("core_paper_ids", [])).issubset(
            stream.get("member_paper_ids", [])
        ):
            errors.append(
                f"landscape stream {stream_id} core papers are not a subset of members"
            )
        for paper_id in stream.get("member_paper_ids", []):
            if not _has_edge(edges, paper_id, "ASSIGNED_TO_STREAM", stream_id):
                errors.append(
                    f"landscape stream {stream_id} member {paper_id} has no ASSIGNED_TO_STREAM edge"
                )
        if not _incoming_edge(edges, stream_id, "TREND_OF"):
            errors.append(f"landscape stream {stream_id} has no TREND_OF snapshot")
        typed_lists = (
            ("top_topic_ids", {"topic"}),
            ("top_theory_ids", {"theory"}),
            ("top_mechanism_ids", {"mechanism"}),
            ("top_variable_ids", {"variable"}),
            ("top_method_ids", {"method", "identification_strategy"}),
            ("top_model_ids", {"model"}),
        )
        for key, types in typed_lists:
            _require_refs(
                errors,
                stream.get(key, []),
                node_by_id,
                label=f"landscape stream {stream_id} {key}",
                types=types,
            )
        _require_refs(
            errors,
            stream.get("evidence_ids", []),
            evidence_by_id,
            label=f"landscape stream {stream_id} evidence",
        )

    for controversy in landscape.get("controversies", []):
        controversy_id = str(controversy.get("controversy_id"))
        _require_refs(
            errors,
            [controversy_id],
            node_by_id,
            label=f"landscape controversy {controversy_id}",
            types={"controversy"},
        )
        _require_refs(
            errors,
            controversy.get("finding_ids", []),
            node_by_id,
            label=f"landscape controversy {controversy_id} findings",
            types={"finding"},
        )
        for finding_id in controversy.get("finding_ids", []):
            if not _has_edge(edges, finding_id, "INDICATES_CONTROVERSY", controversy_id):
                errors.append(
                    f"controversy {controversy_id} finding {finding_id} has no INDICATES_CONTROVERSY edge"
                )
        _require_refs(
            errors,
            controversy.get("evidence_ids", []),
            evidence_by_id,
            label=f"landscape controversy {controversy_id} evidence",
        )

    for signal in landscape.get("frontier_signals", []):
        signal_id = str(signal.get("signal_id"))
        _require_refs(
            errors,
            signal.get("graph_node_ids", []),
            node_by_id,
            label=f"frontier signal {signal_id}",
        )
        _require_refs(
            errors,
            signal.get("evidence_ids", []),
            evidence_by_id,
            label=f"frontier signal {signal_id} evidence",
        )

    threshold = small_sample_threshold
    eligible_count = (landscape.get("quality") or {}).get("eligible_paper_count")
    if isinstance(threshold, int) and isinstance(eligible_count, int) and eligible_count < threshold:
        for owner in [*landscape.get("fields", []), *landscape.get("streams", [])]:
            if (owner.get("metrics") or {}).get("growth_rate") is not None:
                errors.append(
                    f"small-sample landscape item {owner.get('field_id') or owner.get('stream_id')} must have null growth_rate"
                )

    for gap in gaps:
        gap_id = str(gap.get("gap_id"))
        if gap.get("graph_snapshot_id") != graph.get("snapshot_id"):
            errors.append(f"gap {gap_id} graph_snapshot_id does not match final graph")
        if gap.get("landscape_snapshot_id") != landscape.get("snapshot_id"):
            errors.append(f"gap {gap_id} landscape_snapshot_id does not match landscape")
        if gap.get("as_of") != graph.get("as_of"):
            errors.append(f"gap {gap_id} as_of does not match final graph")
        _require_refs(
            errors,
            [gap_id],
            node_by_id,
            label=f"gap card {gap_id}",
            types={"research_gap"},
        )
        _require_refs(
            errors,
            gap.get("supporting_graph_refs", []),
            node_by_id,
            label=f"gap {gap_id} supporting graph refs",
        )
        _require_refs(
            errors,
            gap.get("supporting_evidence_ids", []),
            evidence_by_id,
            label=f"gap {gap_id} supporting evidence",
        )
        _require_refs(
            errors,
            gap.get("counterevidence_ids", []),
            evidence_by_id,
            label=f"gap {gap_id} counterevidence",
        )
        for index, signal in enumerate(gap.get("signals", [])):
            _require_refs(
                errors,
                signal.get("graph_refs", []),
                node_by_id,
                label=f"gap {gap_id} signal[{index}] graph refs",
            )
            _require_refs(
                errors,
                signal.get("evidence_ids", []),
                evidence_by_id,
                label=f"gap {gap_id} signal[{index}] evidence",
            )
        feasibility = gap.get("data_feasibility") or {}
        _require_refs(
            errors,
            feasibility.get("required_variable_ids", []),
            node_by_id,
            label=f"gap {gap_id} required variables",
            types={"variable"},
        )
        _require_refs(
            errors,
            feasibility.get("candidate_data_source_ids", []),
            node_by_id,
            label=f"gap {gap_id} candidate data",
            types={"dataset"},
        )
        if not _incoming_edge(edges, gap_id, "INDICATES_GAP"):
            errors.append(f"gap {gap_id} has no incoming INDICATES_GAP edge")
        if not _has_edge(edges, gap_id, "SUPPORTED_BY_EVIDENCE"):
            errors.append(f"gap {gap_id} has no outgoing SUPPORTED_BY_EVIDENCE edge")
        novelty_id = (
            (node_by_id.get(gap_id) or {}).get("properties") or {}
        ).get("novelty_search_id")
        source_search = novelty_by_id.get(novelty_id)
        novelty_check = gap.get("novelty_check") or {}
        if source_search is None:
            errors.append(
                f"gap {gap_id} graph node references missing novelty search {novelty_id}"
            )
        elif source_search.get("schema_version") == "novelty-search/1.0.1":
            expected_queries = _protocol101_queries(source_search)
            expected_sources = _protocol101_sources(source_search)
            if novelty_check.get("searched_at") != source_search.get("searched_at"):
                errors.append(
                    f"gap {gap_id} novelty searched_at does not match {novelty_id}"
                )
            if novelty_check.get("queries") != expected_queries:
                errors.append(
                    f"gap {gap_id} novelty queries do not match {novelty_id}"
                )
            if novelty_check.get("sources") != expected_sources:
                errors.append(
                    f"gap {gap_id} novelty sources do not match {novelty_id}"
                )
            returned = _protocol101_results(source_search)
            for work in novelty_check.get("nearest_works", []):
                if work.get("paper_id") not in returned:
                    errors.append(
                        f"gap {gap_id} nearest work {work.get('paper_id')} was not returned by {novelty_id}"
                    )
                else:
                    returned_title = str(
                        returned[work["paper_id"]].get("title") or ""
                    )
                    if (
                        returned_title.strip().casefold().startswith("retracted")
                        and work.get("verification_status") != "rejected"
                    ):
                        errors.append(
                            f"gap {gap_id} nearest work {work.get('paper_id')} is titled as retracted and must be rejected"
                        )
            evaluated_count = sum(
                source.get("evaluated_result_count", 0)
                for query in source_search.get("searches", [])
                for source in (query.get("sources") or {}).values()
            )
            coverage = novelty_check.get("coverage_status")
            if coverage in {"partially_covered", "covered"} and evaluated_count == 0:
                errors.append(
                    f"gap {gap_id} novelty status {coverage} is inconsistent with zero evaluated results"
                )
            if coverage == "covered" and (
                not novelty_check.get("nearest_works")
                or any(
                    work.get("verification_status") != "verified"
                    for work in novelty_check.get("nearest_works", [])
                )
            ):
                errors.append(
                    f"gap {gap_id} coverage_status=covered requires verified nearest works"
                )
        elif _novelty_body(source_search) != novelty_check:
            errors.append(f"gap {gap_id} novelty_check is not present in novelty_search")
        if (gap.get("novelty_check") or {}).get("coverage_status") == "covered" and gap.get("status") not in {"rejected", "needs_human_review"}:
            warnings.append(
                f"gap {gap_id} is marked covered by novelty search but remains {gap.get('status')}"
            )

    for hypothesis in hypotheses:
        hypothesis_id = str(hypothesis.get("hypothesis_id"))
        if hypothesis.get("graph_snapshot_id") != graph.get("snapshot_id"):
            errors.append(
                f"hypothesis {hypothesis_id} graph_snapshot_id does not match final graph"
            )
        if hypothesis.get("as_of") != graph.get("as_of"):
            errors.append(f"hypothesis {hypothesis_id} as_of does not match final graph")
        _require_refs(
            errors,
            [hypothesis_id],
            node_by_id,
            label=f"hypothesis card {hypothesis_id}",
            types={"hypothesis"},
        )
        for gap_id in hypothesis.get("gap_card_ids", []):
            if gap_id not in gap_by_id:
                errors.append(
                    f"hypothesis {hypothesis_id} references missing GapCard {gap_id}"
                )
            if not _has_edge(edges, hypothesis_id, "ADDRESSES_GAP", gap_id):
                errors.append(
                    f"hypothesis {hypothesis_id} has no ADDRESSES_GAP edge to {gap_id}"
                )
        novelty_ref = hypothesis.get("novelty_check_ref")
        if novelty_ref not in novelty_by_id:
            errors.append(
                f"hypothesis {hypothesis_id} references missing novelty search {novelty_ref}"
            )
        for index, step in enumerate(hypothesis.get("mechanism_chain", [])):
            _require_refs(
                errors,
                [step.get("source_node_id"), step.get("target_node_id")],
                node_by_id,
                label=f"hypothesis {hypothesis_id} mechanism[{index}]",
            )
            _require_refs(
                errors,
                step.get("evidence_ids", []),
                evidence_by_id,
                label=f"hypothesis {hypothesis_id} mechanism[{index}] evidence",
            )
        role_relations = {
            "independent": "HAS_PREDICTOR",
            "dependent": "HAS_OUTCOME",
            "mediators": "HAS_MEDIATOR",
            "moderators": "HAS_MODERATOR",
            "controls": None,
        }
        variables = hypothesis.get("variables") or {}
        for group, relation in role_relations.items():
            for variable in variables.get(group, []):
                node_id = variable.get("graph_node_id")
                _require_refs(
                    errors,
                    [node_id],
                    node_by_id,
                    label=f"hypothesis {hypothesis_id} {group}",
                    types={"variable"},
                )
                if relation and not _has_edge(edges, hypothesis_id, relation, node_id):
                    errors.append(
                        f"hypothesis {hypothesis_id} {group} variable {node_id} has no {relation} edge"
                    )
                for measurement in variable.get("measurement_candidates", []):
                    _require_refs(
                        errors,
                        [measurement.get("measure_node_id")],
                        node_by_id,
                        label=f"hypothesis {hypothesis_id} measure",
                        types={"measure"},
                    )
                    _require_refs(
                        errors,
                        [measurement.get("data_source_id")],
                        node_by_id,
                        label=f"hypothesis {hypothesis_id} data source",
                        types={"dataset"},
                    )
                    _require_refs(
                        errors,
                        measurement.get("evidence_ids", []),
                        evidence_by_id,
                        label=f"hypothesis {hypothesis_id} measurement evidence",
                    )
        balance = hypothesis.get("evidence_balance") or {}
        _require_refs(
            errors,
            balance.get("supporting_finding_ids", []),
            node_by_id,
            label=f"hypothesis {hypothesis_id} supporting findings",
            types={"finding"},
        )
        for finding_id in balance.get("supporting_finding_ids", []):
            if not _has_edge(edges, hypothesis_id, "SUPPORTED_BY_EVIDENCE", finding_id):
                errors.append(
                    f"hypothesis {hypothesis_id} supporting finding {finding_id} has no SUPPORTED_BY_EVIDENCE edge"
                )
        _require_refs(
            errors,
            balance.get("challenging_finding_ids", []),
            node_by_id,
            label=f"hypothesis {hypothesis_id} challenging findings",
            types={"finding"},
        )
        for finding_id in balance.get("challenging_finding_ids", []):
            if not _has_edge(edges, hypothesis_id, "CHALLENGED_BY_EVIDENCE", finding_id):
                errors.append(
                    f"hypothesis {hypothesis_id} challenging finding {finding_id} has no CHALLENGED_BY_EVIDENCE edge"
                )
        _require_refs(
            errors,
            balance.get("policy_document_ids", []),
            node_by_id,
            label=f"hypothesis {hypothesis_id} policy documents",
            types={"policy_document"},
        )
        design = hypothesis.get("recommended_design") or {}
        design_relations = (
            ("candidate_dataset_ids", {"dataset"}, "RECOMMENDS_DATASET"),
            ("candidate_method_ids", {"method"}, "RECOMMENDS_METHOD"),
            ("candidate_model_ids", {"model"}, "RECOMMENDS_MODEL"),
            (
                "candidate_identification_strategy_ids",
                {"identification_strategy"},
                "RECOMMENDS_IDENTIFICATION_STRATEGY",
            ),
        )
        for key, types, relation in design_relations:
            _require_refs(
                errors,
                design.get(key, []),
                node_by_id,
                label=f"hypothesis {hypothesis_id} {key}",
                types=types,
            )
            for target in design.get(key, []):
                if not _has_edge(edges, hypothesis_id, relation, target):
                    errors.append(
                        f"hypothesis {hypothesis_id} design ref {target} has no {relation} edge"
                    )
        if not _has_edge(edges, hypothesis_id, "HAS_OUTCOME"):
            errors.append(f"hypothesis {hypothesis_id} has no HAS_OUTCOME edge")

    graph_gap_ids = {
        node_id for node_id, node in node_by_id.items() if node.get("type") == "research_gap"
    }
    graph_hypothesis_ids = {
        node_id for node_id, node in node_by_id.items() if node.get("type") == "hypothesis"
    }
    if graph_gap_ids != set(gap_by_id):
        errors.append(
            "graph research_gap ids and GapCard ids differ: "
            f"graph_only={sorted(graph_gap_ids - set(gap_by_id))}, "
            f"cards_only={sorted(set(gap_by_id) - graph_gap_ids)}"
        )
    if graph_hypothesis_ids != set(hypothesis_by_id):
        errors.append(
            "graph hypothesis ids and HypothesisCard ids differ: "
            f"graph_only={sorted(graph_hypothesis_ids - set(hypothesis_by_id))}, "
            f"cards_only={sorted(set(hypothesis_by_id) - graph_hypothesis_ids)}"
        )

    return sorted(set(errors)), sorted(set(warnings))


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_release_directory(
    release_dir: Path, novelty_search_path: Path, *, small_sample_threshold: int | None
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        manifest = _load(release_dir / "discovery_release_manifest.json")
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read release manifest: {exc}"], []
    errors.extend(_schema_errors(manifest, RELEASE_SCHEMA, "release manifest"))

    def read_artifact(entry: dict[str, Any], label: str) -> Any:
        path = release_dir / entry["path"]
        try:
            value = _load(path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"cannot read {label} {path}: {exc}")
            return {}
        actual = _sha(path)
        if actual != entry.get("sha256"):
            errors.append(
                f"{label} hash mismatch: manifest={entry.get('sha256')} actual={actual}"
            )
        return value

    artifacts = manifest.get("artifacts") or {}
    graph = read_artifact(artifacts.get("final_graph", {}), "final graph")
    landscape = read_artifact(
        artifacts.get("research_landscape", {}), "research landscape"
    )
    gaps = [
        read_artifact(entry, f"gap card {entry.get('id')}")
        for entry in artifacts.get("gap_cards", [])
    ]
    hypotheses = [
        read_artifact(entry, f"hypothesis card {entry.get('id')}")
        for entry in artifacts.get("hypothesis_cards", [])
    ]
    try:
        novelty = _load(novelty_search_path)
    except (OSError, json.JSONDecodeError) as exc:
        return [*errors, f"cannot read novelty search: {exc}"], warnings
    cross_errors, cross_warnings = validate_discovery_outputs(
        graph=graph,
        landscape=landscape,
        gap_cards=gaps,
        hypothesis_cards=hypotheses,
        novelty_search=novelty,
        small_sample_threshold=small_sample_threshold,
    )
    errors.extend(cross_errors)
    warnings.extend(cross_warnings)
    return sorted(set(errors)), sorted(set(warnings))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a discovery release directory")
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--novelty-search", type=Path, required=True)
    parser.add_argument("--small-sample-threshold", type=int)
    args = parser.parse_args()
    errors, warnings = validate_release_directory(
        args.release_dir,
        args.novelty_search,
        small_sample_threshold=args.small_sample_threshold,
    )
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        return 1
    print("OK: discovery release passed schema, graph-semantic, hash and cross-reference validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
