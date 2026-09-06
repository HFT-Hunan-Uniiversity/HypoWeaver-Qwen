from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from src.discovery.builder import (
    DiscoveryBuildError,
    build_discovery_outputs,
    write_discovery_release,
)
from src.discovery.validate import (
    validate_discovery_outputs,
    validate_release_directory,
)
from src.reason.validate_research_graph import validate_graph


ROOT = Path(__file__).resolve().parents[2]


def _content_hash(content: object) -> str:
    material = (
        content
        if isinstance(content, str)
        else json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _evidence(evidence_id: str, document_id: str, content: str) -> dict:
    return {
        "id": evidence_id,
        "source_type": "project_spec",
        "evidence_type": "design_decision",
        "evidence_level": "design",
        "source_document_id": document_id,
        "document_version": "fixture-v1",
        "profile_id": f"profile:{document_id.split(':', 1)[-1]}",
        "upstream_evidence_id": None,
        "chunk_id": None,
        "asset_id": None,
        "release_id": None,
        "content_sha256": None,
        "content": content,
        "content_hash": _content_hash(content),
        "source_ref": "tests/discovery/test_discovery_builder.py",
        "published_at": "2026-08-09",
        "retrieved_at": "2026-08-09T12:00:00+08:00",
        "verification_status": "not_applicable",
        "access_level": "open",
        "license": None,
        "locator": {
            "page": None,
            "section": "Synthetic fixture",
            "start_char": None,
            "end_char": None,
            "table_id": None,
            "row": None,
            "column": None,
        },
    }


def _node(
    node_id: str,
    node_type: str,
    label: str,
    evidence_id: str,
    *,
    properties: dict | None = None,
) -> dict:
    layers = {
        "paper": "source",
        "research_field": "knowledge",
        "model": "knowledge",
        "identification_strategy": "knowledge",
        "finding": "knowledge",
    }
    return {
        "id": node_id,
        "type": node_type,
        "layer": layers[node_type],
        "label": label,
        "normalized_label": label.casefold(),
        "aliases": [],
        "description": None,
        "origin": "curated",
        "review_status": "human_verified",
        "confidence": 1.0,
        "version": 1,
        "validity": {
            "observed_at": "2026-08-09T12:00:00+08:00",
            "valid_from": None,
            "valid_to": None,
        },
        "source_profile_ids": (
            [f"profile:{properties['document_id'].split(':', 1)[-1]}"]
            if node_type == "paper" and properties and properties.get("document_id")
            else []
        ),
        "evidence_ids": [evidence_id],
        "derivation": None,
        "properties": properties or {},
    }


def _edge(
    source: str,
    target: str,
    relation: str,
    evidence_id: str,
    discriminator: str,
) -> dict:
    digest = hashlib.sha256(
        f"{source}|{relation}|{target}|{discriminator}".encode("utf-8")
    ).hexdigest()[:20]
    return {
        "id": f"edge:{digest}",
        "source": source,
        "target": target,
        "type": relation,
        "layer": "knowledge",
        "origin": "curated",
        "review_status": "human_verified",
        "confidence": 1.0,
        "version": 1,
        "validity": {
            "observed_at": "2026-08-09T12:00:00+08:00",
            "valid_from": None,
            "valid_to": None,
        },
        "evidence_ids": [evidence_id],
        "derivation": None,
        "context": {},
        "properties": {"assertion_kind": "synthetic_fixture"},
    }


def base_graph() -> dict:
    graph = json.loads(
        (ROOT / "samples" / "research_graph.seed.json").read_text(encoding="utf-8")
    )
    graph["graph_id"] = "discovery-test-graph"
    graph["snapshot_id"] = "discovery-test-graph@base"
    graph["as_of"] = "2026-08-09T12:00:00+08:00"
    graph["build"]["created_at"] = graph["as_of"]
    graph["build"]["pipeline_run_id"] = "run:discovery_fixture"

    fixture_evidence = [
        _evidence("ev:paper_one", "doc:paper_one", "Synthetic paper one evidence."),
        _evidence("ev:paper_two", "doc:paper_two", "Synthetic paper two evidence."),
    ]
    graph["evidence"].extend(fixture_evidence)
    graph["nodes"].extend(
        [
            _node(
                "paper:one",
                "paper",
                "Synthetic current paper",
                "ev:paper_one",
                properties={
                    "document_id": "doc:paper_one",
                    "year": 2025,
                    "published_date": "2025-06-01",
                    "stub": False,
                },
            ),
            _node(
                "paper:two",
                "paper",
                "Synthetic baseline paper",
                "ev:paper_two",
                properties={
                    "document_id": "doc:paper_two",
                    "year": 2021,
                    "published_date": "2021-06-01",
                    "stub": False,
                },
            ),
            _node(
                "research_field:green_finance",
                "research_field",
                "Green finance",
                "ev:paper_one",
            ),
            _node("model:twfe", "model", "Two-way fixed effects", "ev:paper_one"),
            _node(
                "identification_strategy:did",
                "identification_strategy",
                "Difference in differences",
                "ev:paper_one",
            ),
            _node(
                "finding:positive",
                "finding",
                "Policy improves real green behaviour",
                "ev:paper_one",
            ),
            _node(
                "finding:negative",
                "finding",
                "Policy effect is null in a restricted subsample",
                "ev:paper_two",
            ),
        ]
    )
    graph["edges"].extend(
        [
            _edge("paper:one", "finding:positive", "REPORTS_FINDING", "ev:paper_one", "1"),
            _edge("finding:positive", "variable:real_green_behavior", "HAS_OUTCOME", "ev:paper_one", "2"),
            _edge("paper:two", "finding:negative", "REPORTS_FINDING", "ev:paper_two", "3"),
            _edge("finding:negative", "variable:real_green_behavior", "HAS_OUTCOME", "ev:paper_two", "4"),
            _edge("paper:one", "method:did", "USES_METHOD", "ev:paper_one", "5"),
            _edge("paper:two", "method:did", "USES_METHOD", "ev:paper_two", "6"),
            _edge("paper:one", "model:twfe", "USES_MODEL", "ev:paper_one", "7"),
            _edge("paper:two", "model:twfe", "USES_MODEL", "ev:paper_two", "8"),
            _edge("paper:one", "identification_strategy:did", "USES_IDENTIFICATION_STRATEGY", "ev:paper_one", "9"),
            _edge("paper:two", "identification_strategy:did", "USES_IDENTIFICATION_STRATEGY", "ev:paper_two", "10"),
            _edge("paper:one", "policy:green_finance_reform_pilot", "EVALUATES_POLICY", "ev:paper_one", "11"),
            _edge("paper:two", "policy:green_finance_reform_pilot", "EVALUATES_POLICY", "ev:paper_two", "12"),
        ]
    )
    graph["nodes"] = sorted(graph["nodes"], key=lambda item: item["id"])
    graph["edges"] = sorted(graph["edges"], key=lambda item: item["id"])
    graph["evidence"] = sorted(graph["evidence"], key=lambda item: item["id"])
    errors, _warnings = validate_graph(graph)
    assert errors == [], errors
    return graph


def novelty_search() -> dict:
    queries = [
        ("q-exact", "exact", "green finance digital capability real behaviour"),
        ("q-broad", "broad", "green finance environmental investment efficiency greenwashing"),
        ("q-adjacent", "adjacent", "green finance green innovation emissions"),
    ]
    searches = []
    for query_id, query_type, query_text in queries:
        sources = {}
        for source_name in ("local_metadata_snapshot", "europe-pmc", "openalex"):
            works = []
            if query_type == "broad" and source_name == "openalex":
                works = [
                    {
                        "paper_id": "paper:nearest",
                        "doi": "10.0000/synthetic",
                        "title": "Nearest synthetic work",
                        "year": 2025,
                        "source": "openalex",
                        "cited_by_count": 2,
                    }
                ]
            sources[source_name] = {
                "hit_count": len(works),
                "hit_count_semantics": "Synthetic bounded-search matches.",
                "evaluated_result_count": len(works),
                "top_results": works,
            }
        searches.append(
            {
                "query_id": query_id,
                "query_type": query_type,
                "query_text": query_text,
                "concept_groups": [[term] for term in query_text.split()[:2]],
                "sources": sources,
            }
        )
    return {
        "schema_version": "novelty-search/1.0.1",
        "search_id": "novelty:dual_outcome",
        "searched_at": "2026-08-09T12:00:00+08:00",
        "as_of": "2026-08-09T12:00:00+08:00",
        "candidate_gap": "The integrated mechanism and dual outcome may remain untested.",
        "query_protocol": {
            "local_semantics": "AND across concept groups.",
            "remote_semantics": "Source-specific bibliographic search.",
            "top_result_limit": 10,
        },
        "local_snapshot": {
            "path": "synthetic/articles.ndjson",
            "input_record_count": 2,
            "eligible_as_of_count": 2,
            "future_dated_excluded_count": 0,
            "input_sha256": "a" * 64,
        },
        "searches": searches,
        "warnings": ["Synthetic fixture only."],
    }


def config() -> dict:
    signal = {
        "signal_type": "cross_stream_bridge",
        "metric_name": "linked_stream_count",
        "metric_value": 2,
        "threshold": 2,
        "explanation": "Separate mechanism and outcome findings can be joined into a falsifiable chain.",
        "graph_refs": ["finding:positive", "trend_snapshot:policy_effects"],
        "evidence_ids": ["ev:paper_one"],
    }
    return {
        "schema_version": "0.1.0",
        "inferred_entities": [
            {
                "id": "variable:firm_emission_intensity",
                "type": "variable",
                "label": "Firm emission intensity",
                "description": "A firm-level design variable, kept distinct from city-level environmental outcomes.",
                "confidence": 0.6,
                "evidence_ids": ["ev:paper_one"],
                "derivation": {
                    "method": "construct_refinement",
                    "method_version": "0.1.0",
                    "input_refs": ["variable:real_green_behavior"],
                    "input_edge_refs": [],
                    "parameters": {"do_not_merge_across_granularity": True},
                    "prompt_hash": None,
                },
                "properties": {
                    "definition": "Firm greenhouse-gas emissions divided by an explicitly preregistered scale denominator.",
                    "granularity": "firm-year",
                    "unit": "tCO2e per scale unit",
                },
            }
        ],
        "run": {
            "as_of": "2026-08-09T12:00:00+08:00",
            "build_timestamp": "2026-08-09T12:00:00+08:00",
            "pipeline_run_id": "run:discovery_builder_test",
            "corpus_limit_statement": "Claims are limited to two synthetic papers in the test corpus.",
            "small_sample_threshold": 3,
            "generator": "discovery-builder-test/0.1.0",
            "code_version": "test",
        },
        "landscape": {
            "window": {
                "current_from": "2023-01-01",
                "current_to": "2026-08-09",
                "baseline_from": "2019-01-01",
                "baseline_to": "2022-12-31",
            },
            "methodology": {
                "eligibility_rule": "Non-stub papers explicitly assigned by reviewed node IDs.",
                "clustering": {
                    "features": ["graph_entities"],
                    "algorithm": "reviewed-membership",
                    "version": "0.1.0",
                    "parameters": {"automatic_clustering": False},
                },
                "trend_scoring": {
                    "formula_version": "bounded-weighted-components/0.1.0",
                    "component_weights": {
                        "recent_paper_share": 0.3,
                        "growth_rate": 0.2,
                        "policy_alignment": 0.3,
                        "method_diversity": 0.2,
                    },
                },
                "llm_labeling": {
                    "model": "human-configured",
                    "prompt_hash": "0123456789abcdef",
                    "temperature": 0,
                },
            },
            "cluster_stability": 0.7,
            "warnings": ["Synthetic fixture; not a substantive trend estimate."],
            "fields": [
                {
                    "field_id": "field:green_finance",
                    "graph_node_id": "research_field:green_finance",
                    "label": "Green finance",
                    "member_paper_ids": ["paper:one", "paper:two"],
                    "top_topic_ids": ["topic:green_finance"],
                    "top_model_ids": ["model:twfe"],
                    "evidence_ids": ["ev:paper_one", "ev:paper_two"],
                }
            ],
            "streams": [
                {
                    "stream_id": "research_stream:policy_effects",
                    "trend_id": "trend_snapshot:policy_effects",
                    "label": "Green-finance policy effects",
                    "description": "Studies policy effects on real environmental behaviour.",
                    "label_confidence": 0.9,
                    "confidence": 0.8,
                    "field_ids": ["field:green_finance"],
                    "member_paper_ids": ["paper:one", "paper:two"],
                    "core_paper_ids": ["paper:one"],
                    "top_topic_ids": ["topic:green_finance"],
                    "top_theory_ids": [],
                    "top_mechanism_ids": ["mechanism:information_asymmetry"],
                    "top_variable_ids": [
                        "variable:green_narrative_intensity",
                        "variable:real_green_behavior",
                    ],
                    "top_method_ids": [
                        "method:did",
                        "identification_strategy:did",
                    ],
                    "top_model_ids": ["model:twfe"],
                    "evidence_ids": ["ev:paper_one", "ev:paper_two"],
                }
            ],
            "controversies": [
                {
                    "controversy_id": "controversy:effect_heterogeneity",
                    "statement": "The policy effect differs across samples.",
                    "finding_ids": ["finding:positive", "finding:negative"],
                    "direction_distribution": {"positive": 1, "null": 1},
                    "evidence_ids": ["ev:paper_one", "ev:paper_two"],
                    "confidence": 0.75,
                }
            ],
            "frontier_signals": [
                {
                    "signal_id": "frontier:bridge",
                    "signal_type": "cross_stream_bridge",
                    "statement": "A mechanism-to-outcome bridge is visible in the bounded graph.",
                    "score": 60,
                    "graph_node_ids": [
                        "research_stream:policy_effects",
                        "finding:positive",
                    ],
                    "evidence_ids": ["ev:paper_one"],
                }
            ],
        },
        "gaps": [
            {
                "gap_id": "research_gap:dual_outcome_mechanism",
                "gap_type": "cross_stream",
                "title": "Integrated mechanism and dual-outcome test",
                "statement": "Within this corpus, no paper jointly tests the mechanism and dual outcome.",
                "current_state": "Separate papers cover the policy effect and its heterogeneity.",
                "missing_piece": "A joint design linking innovation to real behaviour and greenwashing.",
                "why_important": "It distinguishes real transition from disclosure-only responses.",
                "signals": [signal],
                "supporting_graph_refs": [
                    "finding:positive",
                    "trend_snapshot:policy_effects",
                ],
                "supporting_evidence_ids": ["ev:paper_one"],
                "counterevidence_ids": ["ev:paper_two"],
                "novelty_search_id": "novelty:dual_outcome",
                "data_feasibility": {
                    "status": "conditional",
                    "required_variable_ids": [
                        "variable:green_narrative_intensity",
                        "variable:firm_emission_intensity",
                    ],
                    "candidate_data_source_ids": [
                        "dataset:annual_reports",
                        "dataset:green_patents",
                    ],
                    "blocking_gaps": ["A firm-level policy exposure crosswalk is required."],
                    "assessment_as_of": "2026-08-09T12:00:00+08:00",
                },
                "candidate_research_questions": [
                    "Does digital capability convert policy exposure into real green behaviour?"
                ],
                "scores": {
                    "novelty": 3.0,
                    "importance": 4.0,
                    "evidence_strength": 2.5,
                    "data_feasibility": 3.0,
                    "method_feasibility": 4.0,
                    "policy_value": 4.0,
                    "overall": 3.4,
                },
                "status": "needs_human_review",
                "derivation": {
                    "workflow_version": "0.1.0",
                    "detector": "cross_stream_gap_detector",
                    "model": "human-configured",
                    "prompt_hash": "abcdef0123456789",
                    "input_refs": [
                        "finding:positive",
                        "finding:negative",
                        "trend_snapshot:policy_effects",
                    ],
                },
                "review": {
                    "review_status": "not_reviewed",
                    "reviewer": None,
                    "reviewed_at": None,
                    "comments": ["Synthetic test card."],
                },
                "confidence": 0.65,
                "graph_links": {
                    "indicator_node_ids": ["trend_snapshot:policy_effects"],
                    "support_node_ids": ["finding:positive"],
                    "challenge_node_ids": ["finding:negative"],
                    "concern_node_ids": [
                        "research_stream:policy_effects",
                        "variable:real_green_behavior",
                    ],
                    "enabled_by_node_ids": ["dataset:annual_reports"],
                },
            }
        ],
        "hypotheses": [
            {
                "hypothesis_id": "hypothesis:digital_mechanism",
                "gap_card_ids": ["research_gap:dual_outcome_mechanism"],
                "title": "Digital capability converts policy exposure into real action",
                "hypothesis_statement": "Digital capability strengthens the effect of green-finance policy on real green behaviour through green innovation.",
                "falsifiable_form": "The policy-by-digital-capability interaction is positive for real behaviour and the mediated effect through green innovation differs from zero.",
                "rationale": "The graph links policy effects, information mechanisms and observable behaviour but does not test them jointly.",
                "mechanism_chain": [
                    {
                        "order": 1,
                        "source_node_id": "variable:green_narrative_intensity",
                        "relation": "activates",
                        "target_node_id": "mechanism:information_asymmetry",
                        "statement": "Digital information reduces information asymmetry.",
                        "evidence_ids": ["ev:paper_one"],
                    },
                    {
                        "order": 2,
                        "source_node_id": "mechanism:information_asymmetry",
                        "relation": "changes",
                        "target_node_id": "variable:firm_emission_intensity",
                        "statement": "Lower information asymmetry reduces firm emission intensity.",
                        "evidence_ids": ["ev:paper_one"],
                    },
                ],
                "variables": {
                    "independent": [
                        {
                            "graph_node_id": "variable:green_narrative_intensity",
                            "name": "Digital capability",
                            "definition": "Firm capability to produce and process digital information.",
                            "role": "independent",
                            "expected_direction": "positive",
                            "measurement_candidates": [],
                        }
                    ],
                    "dependent": [
                        {
                            "graph_node_id": "variable:firm_emission_intensity",
                            "name": "Firm emission intensity",
                            "definition": "Firm-year emissions per preregistered scale unit; not a city-level proxy.",
                            "role": "dependent",
                            "expected_direction": "negative",
                            "measurement_candidates": [],
                        }
                    ],
                    "mediators": [
                        {
                            "graph_node_id": "variable:green_innovation",
                            "name": "Green innovation",
                            "definition": "Green technological innovation activity.",
                            "role": "mediator",
                            "expected_direction": "positive",
                            "measurement_candidates": [],
                        }
                    ],
                    "moderators": [],
                    "controls": [],
                },
                "boundary_conditions": ["Listed firms in the pilot-policy setting."],
                "predictions": [
                    {
                        "prediction_id": "prediction:interaction",
                        "statement": "The policy effect is larger at higher digital capability.",
                        "observable_pattern": "A positive policy-by-capability interaction coefficient.",
                        "would_falsify": "A precise zero or negative interaction under the preregistered specification.",
                    }
                ],
                "evidence_balance": {
                    "supporting_finding_ids": ["finding:positive"],
                    "challenging_finding_ids": ["finding:negative"],
                    "policy_document_ids": ["policy:green_finance_reform_pilot"],
                    "unresolved_conflicts": ["Subsample heterogeneity is unresolved."],
                },
                "novelty_check_ref": "novelty:dual_outcome",
                "feasibility": {
                    "data_status": "conditional",
                    "method_status": "feasible",
                    "citation_status": "partially_verified",
                    "blocking_items": ["Construct the policy exposure crosswalk."],
                    "assessed_at": "2026-08-09T12:00:00+08:00",
                },
                "recommended_design": {
                    "candidate_dataset_ids": ["dataset:annual_reports"],
                    "candidate_method_ids": ["method:did"],
                    "candidate_model_ids": ["model:twfe"],
                    "candidate_identification_strategy_ids": [
                        "identification_strategy:did"
                    ],
                    "unit_of_analysis": "firm-year",
                    "baseline_specification": "Staggered DID with firm and year effects and a mediated interaction test.",
                    "major_threats": ["Parallel trends", "Measurement error", "Policy spillovers"],
                },
                "scores": {
                    "novelty": 3.0,
                    "theory": 3.5,
                    "evidence": 2.5,
                    "data": 3.0,
                    "method": 4.0,
                    "policy_value": 4.0,
                    "overall": 3.3,
                },
                "handoff": {
                    "required_inputs": ["Firm-year panel", "Pilot exposure", "Digital capability measure"],
                    "blocking_questions": ["Which digital-capability measure has stable coverage?"],
                    "validation_acceptance_criteria": [
                        "Pre-trends pass the preregistered equivalence bound.",
                        "The mediated interaction is robust to alternative measures.",
                    ],
                    "evidence_bundle_refs": ["novelty:dual_outcome", "ev:paper_one", "ev:paper_two"],
                    "reproduction_seed": 42,
                },
                "status": "needs_scientific_review",
                "review": {
                    "green_finance_review": "pending",
                    "data_review": "pending",
                    "method_review": "pending",
                    "citation_review": "partial",
                    "final_decision": "revise",
                },
                "confidence": 0.6,
                "graph_links": {
                    "predictor_node_ids": ["variable:green_narrative_intensity"],
                    "outcome_node_ids": ["variable:firm_emission_intensity"],
                    "mediator_node_ids": ["variable:green_innovation"],
                    "moderator_node_ids": [],
                    "mechanism_node_ids": ["mechanism:information_asymmetry"],
                    "support_node_ids": ["finding:positive"],
                    "challenge_node_ids": ["finding:negative"],
                    "enabled_by_node_ids": ["dataset:annual_reports"],
                    "recommended_method_ids": ["method:did"],
                    "recommended_model_ids": ["model:twfe"],
                    "recommended_identification_strategy_ids": [
                        "identification_strategy:did"
                    ],
                    "recommended_dataset_ids": ["dataset:annual_reports"],
                },
            }
        ],
    }


class DiscoveryBuilderTests(unittest.TestCase):
    def test_end_to_end_artifacts_are_valid_and_corpus_limited(self) -> None:
        artifacts = build_discovery_outputs(base_graph(), config(), novelty_search())
        errors, warnings = validate_discovery_outputs(
            graph=artifacts.graph,
            landscape=artifacts.landscape,
            gap_cards=artifacts.gap_cards,
            hypothesis_cards=artifacts.hypothesis_cards,
            novelty_search=novelty_search(),
            small_sample_threshold=3,
        )
        self.assertEqual([], errors)
        self.assertEqual([], warnings)
        self.assertIsNone(artifacts.landscape["streams"][0]["metrics"]["growth_rate"])
        novelty = artifacts.gap_cards[0]["novelty_check"]
        self.assertEqual("partially_covered", novelty["coverage_status"])
        self.assertEqual(
            ["europe-pmc", "local_metadata_snapshot", "openalex"],
            novelty["sources"],
        )
        self.assertEqual("paper:nearest", novelty["nearest_works"][0]["paper_id"])
        self.assertEqual("unverified", novelty["nearest_works"][0]["verification_status"])
        self.assertTrue(
            any(
                warning.startswith("CORPUS_LIMIT:")
                for warning in artifacts.landscape["quality"]["warnings"]
            )
        )
        relations = {
            (edge["source"], edge["type"], edge["target"])
            for edge in artifacts.graph["edges"]
        }
        self.assertIn(
            (
                "trend_snapshot:policy_effects",
                "INDICATES_GAP",
                "research_gap:dual_outcome_mechanism",
            ),
            relations,
        )
        self.assertIn(
            (
                "research_gap:dual_outcome_mechanism",
                "SUPPORTED_BY_EVIDENCE",
                "finding:positive",
            ),
            relations,
        )
        self.assertIn(
            (
                "hypothesis:digital_mechanism",
                "ADDRESSES_GAP",
                "research_gap:dual_outcome_mechanism",
            ),
            relations,
        )
        self.assertIn(
            (
                "hypothesis:digital_mechanism",
                "HAS_OUTCOME",
                "variable:firm_emission_intensity",
            ),
            relations,
        )

    def test_build_and_release_bytes_are_deterministic(self) -> None:
        graph = base_graph()
        cfg = config()
        novelty = novelty_search()
        first = build_discovery_outputs(graph, cfg, novelty)
        second = build_discovery_outputs(graph, cfg, novelty)
        self.assertEqual(first.graph, second.graph)
        self.assertEqual(first.landscape, second.landscape)
        self.assertEqual(first.gap_cards, second.gap_cards)
        self.assertEqual(first.hypothesis_cards, second.hypothesis_cards)

        one = ROOT / "tmp" / "discovery_release_test_one"
        two = ROOT / "tmp" / "discovery_release_test_two"
        first_manifest = write_discovery_release(
            first,
            output_dir=one,
            config=cfg,
            base_graph_snapshot_id=graph["snapshot_id"],
        )
        second_manifest = write_discovery_release(
            second,
            output_dir=two,
            config=cfg,
            base_graph_snapshot_id=graph["snapshot_id"],
        )
        self.assertEqual(first_manifest, second_manifest)
        relative_files = [
            "final_research_graph.json",
            "research_landscape.json",
            "gap_cards/gap_001.json",
            "hypothesis_cards/hypothesis_001.json",
            "discovery_release_manifest.json",
        ]
        for relative in relative_files:
            self.assertEqual(
                (one / relative).read_bytes(),
                (two / relative).read_bytes(),
            )
        novelty_path = one / "novelty.json"
        novelty_path.write_text(
            json.dumps(novelty, ensure_ascii=False), encoding="utf-8"
        )
        errors, warnings = validate_release_directory(
            one, novelty_path, small_sample_threshold=3
        )
        self.assertEqual([], errors)
        self.assertEqual([], warnings)

    def test_invalid_indicator_type_is_rejected(self) -> None:
        cfg = config()
        cfg["gaps"][0]["graph_links"]["indicator_node_ids"] = [
            "dataset:annual_reports"
        ]
        with self.assertRaisesRegex(DiscoveryBuildError, "indicators expects"):
            build_discovery_outputs(base_graph(), cfg, novelty_search())

    def test_missing_novelty_search_is_rejected(self) -> None:
        novelty = novelty_search()
        novelty["search_id"] = "novelty:different"
        with self.assertRaisesRegex(DiscoveryBuildError, "missing novelty search"):
            build_discovery_outputs(base_graph(), config(), novelty)

    def test_inferred_design_entity_requires_explicit_granularity(self) -> None:
        cfg = config()
        del cfg["inferred_entities"][0]["properties"]["granularity"]
        with self.assertRaisesRegex(ValueError, "granularity"):
            build_discovery_outputs(base_graph(), cfg, novelty_search())

    def test_future_dated_member_paper_is_rejected(self) -> None:
        graph = base_graph()
        paper = next(node for node in graph["nodes"] if node["id"] == "paper:one")
        paper["properties"]["year"] = 2027
        paper["properties"]["published_date"] = "2027-01-01"
        with self.assertRaisesRegex(DiscoveryBuildError, "future-dated paper"):
            build_discovery_outputs(graph, config(), novelty_search())

    def test_real_protocol_101_novelty_file_is_supported(self) -> None:
        path = (
            ROOT
            / "output"
            / "real_pilot"
            / "2026-08-09_green_finance_decarbonization"
            / "F_discovery"
            / "novelty_search.json"
        )
        real_novelty = json.loads(path.read_text(encoding="utf-8"))
        cfg = config()
        cfg["run"]["as_of"] = real_novelty["as_of"]
        cfg["run"]["build_timestamp"] = real_novelty["searched_at"]
        cfg["gaps"][0]["novelty_search_id"] = real_novelty["search_id"]
        cfg["hypotheses"][0]["novelty_check_ref"] = real_novelty["search_id"]
        artifacts = build_discovery_outputs(base_graph(), cfg, real_novelty)
        novelty = artifacts.gap_cards[0]["novelty_check"]
        self.assertGreaterEqual(len(novelty["queries"]), 4)
        self.assertEqual(len(real_novelty["searches"]), len(novelty["queries"]))
        self.assertEqual(
            [
                "crossref",
                "europe-pmc",
                "green-finance-data-center-public-metadata",
                "openalex",
            ],
            novelty["sources"],
        )
        self.assertEqual("partially_covered", novelty["coverage_status"])
        self.assertTrue(novelty["nearest_works"])
        self.assertTrue(
            all(
                work["verification_status"] == "unverified"
                for work in novelty["nearest_works"]
            )
        )
        self.assertFalse(
            any(
                work["title"].casefold().startswith("retracted")
                for work in novelty["nearest_works"]
            )
        )

    def test_cross_validator_detects_removed_hypothesis_outcome(self) -> None:
        artifacts = build_discovery_outputs(base_graph(), config(), novelty_search())
        graph = copy.deepcopy(artifacts.graph)
        graph["edges"] = [
            edge
            for edge in graph["edges"]
            if not (
                edge["source"] == "hypothesis:digital_mechanism"
                and edge["type"] == "HAS_OUTCOME"
            )
        ]
        errors, _warnings = validate_discovery_outputs(
            graph=graph,
            landscape=artifacts.landscape,
            gap_cards=artifacts.gap_cards,
            hypothesis_cards=artifacts.hypothesis_cards,
            novelty_search=novelty_search(),
            small_sample_threshold=3,
        )
        self.assertTrue(any("HAS_OUTCOME" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
