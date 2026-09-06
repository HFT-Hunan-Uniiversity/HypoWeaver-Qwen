from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src" / "reason"))

from build_research_graph import (  # noqa: E402
    GraphBuilder,
    _canonical_sha256,
    _load_run_manifest,
    _validate_run_manifest,
    build_graph_from_profiles,
    new_graph,
    profile_set_sha256,
)
from validate_research_graph import validate_graph  # noqa: E402
from src.retrieve.vector_index import (  # noqa: E402
    ChunkRecord,
    HashingEmbeddingBackend,
    LocalVectorIndex,
)


def sample_profile() -> dict:
    return {
        "schema_version": "0.2.0",
        "profile_id": "profile:test-paper",
        "document": {
            "document_id": "doc:test-paper",
            "document_version": "v1",
            "title": "Graph pipeline test fixture (not a real paper)",
            "authors": ["Test Author"],
            "year": 2025,
            "published_date": "2025-01-01",
            "updated_at": None,
            "journal_or_source": "Test fixture",
            "venue_id": None,
            "doi": None,
            "openalex_id": None,
            "semantic_scholar_id": None,
            "language": "en",
            "source_uri": None,
            "checksum": None,
            "parsed_doc_version": "test",
            "retrieved_at": "2026-07-15T00:00:00+08:00",
            "metadata_evidence_refs": ["e1"],
        },
        "research_question": {"text": "Does X affect Y?", "evidence_refs": ["e1"]},
        "research_fields": [
            {"local_id": "rf1", "name": "绿色金融", "canonical_name": "绿色金融", "aliases": ["green finance"], "description": None, "evidence_refs": ["e1"], "confidence": 0.99}
        ],
        "topics": [
            {"local_id": "t1", "name": "ESG", "canonical_name": "ESG", "aliases": [], "description": None, "evidence_refs": ["e1"], "confidence": 0.99}
        ],
        "theories": [],
        "mechanisms": [
            {"local_id": "m1", "name": "信息不对称", "canonical_name": "信息不对称", "aliases": [], "description": None, "evidence_refs": ["e1"], "confidence": 0.9}
        ],
        "variables": [
            {"local_id": "x", "name": "X", "canonical_name": "X", "aliases": [], "roles": ["independent"], "definition": None, "operationalization": None, "unit": None, "measure_refs": ["mx"], "evidence_refs": ["e1"], "confidence": 0.9},
            {"local_id": "y", "name": "Y", "canonical_name": "Y", "aliases": [], "roles": ["dependent"], "definition": None, "operationalization": None, "unit": None, "measure_refs": ["my"], "evidence_refs": ["e1"], "confidence": 0.9},
        ],
        "measures": [
            {"local_id": "mx", "name": "X measure", "canonical_name": "X measure", "construction": "Test construction", "unit": None, "data_source_refs": ["d1"], "evidence_refs": ["e1"], "confidence": 0.9},
            {"local_id": "my", "name": "Y measure", "canonical_name": "Y measure", "construction": "Test construction", "unit": None, "data_source_refs": ["d1"], "evidence_refs": ["e1"], "confidence": 0.9},
        ],
        "methods": [
            {"local_id": "method1", "name": "Regression analysis", "canonical_name": "回归分析", "role": "primary", "identification_strategy": None, "specification": None, "evidence_refs": ["e1"], "confidence": 0.95}
        ],
        "models": [
            {"local_id": "model1", "name": "Fixed effects model", "canonical_name": "固定效应模型", "family": "econometric", "role": "baseline", "specification": None, "evidence_refs": ["e1"], "confidence": 0.95}
        ],
        "identification_strategies": [
            {"local_id": "id1", "name": "Difference-in-differences", "canonical_name": "双重差分法", "aliases": ["DID"], "description": "Quasi-experimental identification", "evidence_refs": ["e1"], "confidence": 0.95}
        ],
        "datasets": [
            {"local_id": "d1", "name": "Test dataset", "canonical_name": "Test dataset", "provider": "Test provider", "access_level": "open", "evidence_refs": ["e1"], "confidence": 0.9}
        ],
        "policies": [],
        "citations": [
            {"target_document_id": "doc:cited", "target_title": "Cited test fixture", "target_year": 2024, "target_doi": None, "relation": "cites", "identity_status": "verified", "evidence_refs": ["e1"]}
        ],
        "findings": [
            {
                "finding_id": "f1",
                "claim": "X significantly reduces Y.",
                "predictor_refs": ["x"],
                "outcome_refs": ["y"],
                "mediator_refs": [],
                "moderator_refs": [],
                "mechanism_refs": ["m1"],
                "method_refs": ["method1"],
                "model_refs": ["model1"],
                "identification_strategy_refs": ["id1"],
                "effect_direction": "negative",
                "significance": "significant",
                "population_or_subsample": None,
                "conditions": None,
                "evidence_refs": ["e1"],
                "confidence": 0.9,
            }
        ],
        "limitations": [
            {"limitation_id": "l1", "text": "The fixture has a small sample.", "category": "data", "evidence_refs": ["e1"], "confidence": 0.9}
        ],
        "future_work": [],
        "sample": {"unit_of_analysis": "firm-year", "geographies": ["CN"], "year_start": 2020, "year_end": 2024, "sample_size": 100, "notes": None},
        "evidence": [
            {
                "evidence_id": "e1",
                "document_id": "doc:test-paper",
                "document_version": "v1",
                "chunk_id": "chunk:test-1",
                "quote": "Test evidence for the graph pipeline.",
                "section": "Results",
                "page": 1,
                "start_char": 0,
                "end_char": 37,
                "source_uri": None,
                "retrieved_at": "2026-07-15T00:00:00+08:00",
                "verification_status": "source_located",
            }
        ],
        "quality": {
            "extraction_confidence": 0.9,
            "citation_verification_status": "verified",
            "human_review_status": "sampled",
            "extractor": "test",
            "extractor_version": "test",
            "notes": "Synthetic test fixture only.",
        },
    }


def explicit_sample_profile() -> dict:
    profile = sample_profile()
    profile["evidence"][0].update(
        {
            "source_type": "paper_fulltext",
            "evidence_type": "direct_quote",
            "evidence_level": "primary_source",
        }
    )
    return profile


class GraphPipelineTests(unittest.TestCase):
    def test_seed_graph_is_semantically_valid(self) -> None:
        seed = json.loads((ROOT / "samples" / "research_graph.seed.json").read_text(encoding="utf-8"))
        errors, _warnings = validate_graph(seed)
        self.assertEqual([], errors)

    def test_profile_builds_an_evidence_grounded_finding(self) -> None:
        builder = GraphBuilder(new_graph("test-graph"))
        builder.add_profile(sample_profile())
        graph = builder.finish()
        errors, warnings = validate_graph(graph)
        self.assertEqual([], errors)
        self.assertEqual([], warnings)
        self.assertEqual(1, sum(node["type"] == "finding" for node in graph["nodes"]))
        self.assertTrue(any(edge["type"] == "HAS_PREDICTOR" for edge in graph["edges"]))
        self.assertTrue(any(edge["type"] == "HAS_OUTCOME" for edge in graph["edges"]))
        self.assertTrue(all(item["evidence_level"] == "primary_source" for item in graph["evidence"]))
        self.assertTrue(any(edge["type"] == "CITES" for edge in graph["edges"]))

    def test_profile_merges_into_curated_seed_without_losing_provenance(self) -> None:
        seed = json.loads((ROOT / "samples" / "research_graph.seed.json").read_text(encoding="utf-8"))
        builder = GraphBuilder(seed)
        builder.add_profile(sample_profile())
        graph = builder.finish()
        errors, warnings = validate_graph(graph)
        self.assertEqual([], errors)
        self.assertEqual([], warnings)
        esg = next(node for node in graph["nodes"] if node["id"] == "topic:esg")
        self.assertEqual("curated", esg["origin"])
        self.assertIn("profile:test-paper", esg["source_profile_ids"])
        self.assertGreaterEqual(len(esg["evidence_ids"]), 2)
        self.assertIsNotNone(graph["build"]["parent_snapshot_id"])

    def test_citation_stub_and_full_paper_share_one_stable_identity(self) -> None:
        citing = sample_profile()
        citing["citations"][0].update(
            {
                "target_document_id": "doc:cited-paper",
                "target_title": "Cited paper with full profile",
                "target_doi": "10.1234/same",
            }
        )
        cited = sample_profile()
        cited["profile_id"] = "profile:cited-paper"
        cited["document"].update(
            {
                "document_id": "doc:cited-paper",
                "title": "Cited paper with full profile",
                "doi": "10.1234/same",
            }
        )
        cited["research_question"]["text"] = "What does the cited paper test?"
        cited["citations"] = []
        cited["findings"][0]["claim"] = "The cited fixture reports a distinct result."
        for evidence in cited["evidence"]:
            evidence["document_id"] = "doc:cited-paper"

        for label, profiles in (
            ("citation-first", [citing, cited]),
            ("full-paper-first", [cited, citing]),
        ):
            with self.subTest(order=label):
                builder = GraphBuilder(new_graph(f"test-paper-identity-{label}"))
                for profile in profiles:
                    builder.add_profile(profile)
                graph = builder.finish()
                matching = [
                    node
                    for node in graph["nodes"]
                    if node["type"] == "paper"
                    and (node.get("properties") or {}).get("doi") == "10.1234/same"
                ]
                self.assertEqual(1, len(matching))
                materialized = matching[0]
                self.assertFalse(materialized["properties"]["stub"])
                self.assertEqual(
                    "doc:cited-paper", materialized["properties"]["document_id"]
                )
                citation = next(edge for edge in graph["edges"] if edge["type"] == "CITES")
                self.assertEqual(materialized["id"], citation["target"])

                errors, warnings = validate_graph(graph)
                self.assertEqual([], errors)
                self.assertEqual([], warnings)

    def test_dangling_edge_is_rejected(self) -> None:
        seed = json.loads((ROOT / "samples" / "research_graph.seed.json").read_text(encoding="utf-8"))
        broken = copy.deepcopy(seed)
        broken["edges"][0]["target"] = "topic:missing"
        errors, _warnings = validate_graph(broken)
        self.assertTrue(any("missing target" in error for error in errors))

    def test_rejected_evidence_is_not_ingested(self) -> None:
        profile = sample_profile()
        profile["evidence"][0]["verification_status"] = "rejected"
        builder = GraphBuilder(new_graph("test-rejected"))
        with self.assertRaisesRegex(ValueError, "rejected evidence"):
            builder.add_profile(profile)

    def test_explicit_abstract_cannot_support_a_finding_even_with_chunk_id(self) -> None:
        profile = sample_profile()
        profile["evidence"][0].update(
            {
                "source_type": "paper_abstract",
                "evidence_type": "direct_quote",
                "evidence_level": "metadata",
            }
        )
        builder = GraphBuilder(new_graph("test-abstract"))
        with self.assertRaisesRegex(ValueError, "requires located, verified fulltext evidence"):
            builder.add_profile(profile)

    def test_explicit_fulltext_without_page_or_chunk_uses_section_locator(self) -> None:
        profile = sample_profile()
        profile["evidence"][0].update(
            {
                "source_type": "paper_fulltext",
                "evidence_type": "direct_quote",
                "evidence_level": "primary_source",
                "chunk_id": None,
                "page": None,
                "section": "Results",
            }
        )
        builder = GraphBuilder(new_graph("test-html-fulltext"))
        builder.add_profile(profile)
        graph = builder.finish()
        self.assertEqual("paper_fulltext", graph["evidence"][0]["source_type"])
        errors, _warnings = validate_graph(graph)
        self.assertEqual([], errors)

    def test_metadata_and_scientific_evidence_remain_separate(self) -> None:
        profile = sample_profile()
        profile["evidence"][0].update(
            {
                "source_type": "paper_fulltext",
                "evidence_type": "direct_quote",
                "evidence_level": "primary_source",
            }
        )
        profile["evidence"].append(
            {
                "evidence_id": "e-meta",
                "document_id": "doc:test-paper",
                "document_version": "v1",
                "chunk_id": None,
                "source_type": "metadata_api",
                "evidence_type": "metadata_record",
                "evidence_level": "metadata",
                "quote": "Graph pipeline test fixture (not a real paper)",
                "section": None,
                "page": None,
                "start_char": None,
                "end_char": None,
                "source_uri": "https://example.invalid/metadata",
                "retrieved_at": "2026-07-15T00:00:00+08:00",
                "verification_status": "source_located",
            }
        )
        profile["document"]["metadata_evidence_refs"] = ["e-meta"]
        builder = GraphBuilder(new_graph("test-metadata"))
        builder.add_profile(profile)
        graph = builder.finish()
        metadata = next(item for item in graph["evidence"] if item["source_type"] == "metadata_api")
        self.assertEqual("metadata", metadata["evidence_level"])
        paper = next(node for node in graph["nodes"] if node["type"] == "paper" and not node["properties"].get("stub"))
        self.assertEqual([metadata["id"]], paper["evidence_ids"])
        errors, _warnings = validate_graph(graph)
        self.assertEqual([], errors)

    def test_unverified_fulltext_cannot_support_semantic_objects(self) -> None:
        profile = sample_profile()
        profile["evidence"][0].update(
            {
                "source_type": "paper_fulltext",
                "evidence_type": "direct_quote",
                "evidence_level": "primary_source",
                "verification_status": "unverified",
            }
        )
        builder = GraphBuilder(new_graph("test-unverified"))
        with self.assertRaisesRegex(ValueError, "requires located, verified fulltext evidence"):
            builder.add_profile(profile)

    def test_policy_text_cannot_masquerade_as_paper_fulltext(self) -> None:
        profile = sample_profile()
        profile["evidence"][0].update(
            {
                "source_type": "policy_text",
                "evidence_type": "direct_quote",
                "evidence_level": "primary_source",
            }
        )
        builder = GraphBuilder(new_graph("test-policy-evidence"))
        with self.assertRaisesRegex(ValueError, "requires located, verified fulltext evidence"):
            builder.add_profile(profile)

    def test_blank_locator_cannot_support_fulltext_claim(self) -> None:
        profile = sample_profile()
        profile["evidence"][0].update(
            {
                "source_type": "paper_fulltext",
                "evidence_type": "direct_quote",
                "evidence_level": "primary_source",
                "chunk_id": None,
                "section": " ",
                "page": None,
                "start_char": None,
                "end_char": None,
            }
        )
        builder = GraphBuilder(new_graph("test-blank-locator"))
        with self.assertRaisesRegex(ValueError, "section must not be blank"):
            builder.add_profile(profile)

    def test_abstract_only_method_is_rejected(self) -> None:
        profile = sample_profile()
        abstract = copy.deepcopy(profile["evidence"][0])
        abstract.update(
            {
                "evidence_id": "e-abstract-method",
                "source_type": "paper_abstract",
                "evidence_type": "direct_quote",
                "evidence_level": "metadata",
                "section": "Abstract",
            }
        )
        profile["evidence"].append(abstract)
        profile["methods"][0]["evidence_refs"] = ["e-abstract-method"]
        builder = GraphBuilder(new_graph("test-abstract-method"))
        with self.assertRaisesRegex(ValueError, "methods:method1 requires located"):
            builder.add_profile(profile)

    def test_metadata_only_topic_is_rejected(self) -> None:
        profile = sample_profile()
        metadata = copy.deepcopy(profile["evidence"][0])
        metadata.update(
            {
                "evidence_id": "e-metadata-topic",
                "source_type": "metadata_api",
                "evidence_type": "metadata_record",
                "evidence_level": "metadata",
                "chunk_id": None,
                "section": None,
                "page": None,
                "start_char": None,
                "end_char": None,
            }
        )
        profile["evidence"].append(metadata)
        profile["topics"][0]["evidence_refs"] = ["e-metadata-topic"]
        builder = GraphBuilder(new_graph("test-metadata-topic"))
        with self.assertRaisesRegex(ValueError, "verified paper abstract or paper fulltext"):
            builder.add_profile(profile)

    def test_formal_build_rejects_legacy_evidence_inference(self) -> None:
        builder = GraphBuilder(
            new_graph("test-formal-evidence"), require_explicit_evidence=True
        )
        with self.assertRaisesRegex(ValueError, "formal build requires explicit"):
            builder.add_profile(sample_profile())

    def test_formal_build_entrypoint_activates_strict_evidence_gate(self) -> None:
        profile = sample_profile()
        manifest = json.loads(
            (ROOT / "samples" / "graph_build_manifest.seed.json").read_text(
                encoding="utf-8"
            )
        )
        manifest["profile_set_sha256"] = profile_set_sha256([profile])
        with self.assertRaisesRegex(ValueError, "formal build requires explicit"):
            build_graph_from_profiles([profile], manifest=manifest)

    def test_formal_build_is_content_deterministic(self) -> None:
        first = explicit_sample_profile()
        second = explicit_sample_profile()
        second["profile_id"] = "profile:z-test-paper"
        second["document"]["document_id"] = "doc:z-test-paper"
        second["document"]["title"] = "Second graph pipeline fixture"
        second["document"]["authors"] = ["Second Test Author"]
        for evidence in second["evidence"]:
            evidence["document_id"] = "doc:z-test-paper"

        manifest = json.loads(
            (ROOT / "samples" / "graph_build_manifest.seed.json").read_text(
                encoding="utf-8"
            )
        )
        manifest["profile_set_sha256"] = profile_set_sha256([first, second])
        graph_a, warnings_a = build_graph_from_profiles(
            [first, second], manifest=copy.deepcopy(manifest)
        )
        graph_b, warnings_b = build_graph_from_profiles(
            [second, first], manifest=copy.deepcopy(manifest)
        )

        self.assertEqual([], warnings_a)
        self.assertEqual(warnings_a, warnings_b)
        self.assertEqual(graph_a, graph_b)
        self.assertEqual(
            manifest["profile_set_sha256"],
            graph_a["build"]["input_profile_hash"],
        )

    def test_incremental_formal_build_pins_exact_base_snapshot(self) -> None:
        base_builder = GraphBuilder(new_graph("test-incremental-pin"))
        base_builder.add_profile(sample_profile())
        base = base_builder.finish()

        profile = explicit_sample_profile()
        profile["profile_id"] = "profile:incremental"
        profile["document"]["document_id"] = "doc:incremental"
        profile["document"]["title"] = "Incremental graph fixture"
        for evidence in profile["evidence"]:
            evidence["document_id"] = "doc:incremental"

        manifest = json.loads(
            (ROOT / "samples" / "graph_build_manifest.seed.json").read_text(
                encoding="utf-8"
            )
        )
        manifest["graph_id"] = base["graph_id"]
        manifest["profile_set_sha256"] = profile_set_sha256([profile])
        manifest["base_snapshot_id"] = base["snapshot_id"]
        manifest["base_graph_sha256"] = _canonical_sha256(base)

        graph, _warnings = build_graph_from_profiles(
            [profile], manifest=manifest, base=base
        )
        self.assertEqual(base["snapshot_id"], graph["build"]["parent_snapshot_id"])
        self.assertEqual(
            manifest["base_graph_sha256"], graph["build"]["base_graph_hash"]
        )

        wrong_manifest = copy.deepcopy(manifest)
        wrong_manifest["base_snapshot_id"] = "different-snapshot"
        with self.assertRaisesRegex(ValueError, "base_snapshot_id"):
            build_graph_from_profiles(
                [profile], manifest=wrong_manifest, base=base
            )

    def test_duplicate_profile_id_with_different_content_is_rejected(self) -> None:
        builder = GraphBuilder(new_graph("test-duplicate-profile"))
        builder.add_profile(sample_profile())
        conflicting = sample_profile()
        conflicting["document"]["document_id"] = "doc:other"
        for evidence in conflicting["evidence"]:
            evidence["document_id"] = "doc:other"
        with self.assertRaisesRegex(ValueError, "duplicate profile_id"):
            builder.add_profile(conflicting)

    def test_existing_evidence_collision_with_changed_content_is_rejected(self) -> None:
        first = GraphBuilder(new_graph("test-evidence-collision"))
        first.add_profile(sample_profile())
        base = first.finish()

        changed = sample_profile()
        changed["evidence"][0]["quote"] = "Different evidence content."
        changed["evidence"][0]["end_char"] = len("Different evidence content.")
        second = GraphBuilder(base)
        with self.assertRaisesRegex(ValueError, "evidence id collision"):
            second.add_profile(changed)

    def test_research_question_and_future_work_keep_evidence_mapping(self) -> None:
        profile = sample_profile()
        profile["future_work"] = [
            {"text": "Test the relationship in another setting.", "evidence_refs": ["e1"]}
        ]
        builder = GraphBuilder(new_graph("test-paper-properties"))
        builder.add_profile(profile)
        graph = builder.finish()
        paper = next(node for node in graph["nodes"] if node["type"] == "paper" and not node["properties"].get("stub"))
        self.assertEqual(1, len(paper["properties"]["research_question_evidence_ids"]))
        self.assertEqual(1, len(paper["properties"]["future_work_items"]))
        self.assertEqual(1, len(paper["properties"]["future_work_items"][0]["evidence_ids"]))
        self.assertEqual("e1", graph["evidence"][0]["upstream_evidence_id"])

        errors, warnings = validate_graph(graph)
        self.assertEqual([], errors)
        self.assertFalse(any("unused evidence" in warning for warning in warnings))

    def test_vector_result_ids_resolve_to_graph_evidence(self) -> None:
        profile = explicit_sample_profile()
        builder = GraphBuilder(new_graph("test-vector-graph-contract"))
        builder.add_profile(profile)
        graph = builder.finish()

        evidence = profile["evidence"][0]
        text_hash = hashlib.sha256(evidence["quote"].encode("utf-8")).hexdigest()
        record = ChunkRecord(
            chunk_id=evidence["chunk_id"],
            document_id=evidence["document_id"],
            evidence_id=evidence["evidence_id"],
            text=evidence["quote"],
            content_hash=text_hash,
            text_sha256=text_hash,
            content_sha256=None,
            locator={"section": evidence["section"], "page": evidence["page"]},
            document_version=evidence["document_version"],
            access_level="restricted",
            source_type="paper_fulltext",
        )
        backend = HashingEmbeddingBackend(dimensions=64)
        manifest = {
            "snapshot_id": "vector-index:test-vector-graph-contract",
            "embedding": {
                "backend_id": backend.backend_id,
                "model_id": backend.model_id,
                "algorithm": backend.algorithm,
                "dimensions": backend.dimensions,
            },
        }
        index = LocalVectorIndex(
            manifest=manifest,
            records=[record],
            vectors=backend.embed_documents([record.text]),
            backend=backend,
        )
        result = index.search("graph pipeline evidence", top_k=1).results[0]
        graph_evidence = next(
            item
            for item in graph["evidence"]
            if item.get("upstream_evidence_id") == result.evidence_id
        )

        self.assertEqual(result.chunk_id, graph_evidence["chunk_id"])
        self.assertEqual(result.document_id, graph_evidence["source_document_id"])
        self.assertEqual(
            result.document_version, graph_evidence["document_version"]
        )

    def test_paper_property_evidence_mapping_is_validated(self) -> None:
        builder = GraphBuilder(new_graph("test-paper-property-refs"))
        builder.add_profile(sample_profile())
        graph = builder.finish()
        paper = next(
            node
            for node in graph["nodes"]
            if node["type"] == "paper" and not node["properties"].get("stub")
        )
        paper["properties"]["research_question_evidence_ids"] = ["ev:missing"]

        errors, _warnings = validate_graph(graph)
        self.assertTrue(
            any(
                "properties reference missing evidence ev:missing" in error
                for error in errors
            )
        )

    def test_research_question_cannot_use_another_papers_evidence(self) -> None:
        builder = GraphBuilder(new_graph("test-cross-paper-question"))
        builder.add_profile(sample_profile())
        graph = builder.finish()
        other = copy.deepcopy(graph["evidence"][0])
        other.update(
            {
                "id": "ev:other-paper-question",
                "source_document_id": "doc:other-paper",
                "profile_id": "profile:other-paper",
                "upstream_evidence_id": "other-question",
            }
        )
        graph["evidence"].append(other)
        paper = next(
            node
            for node in graph["nodes"]
            if node["type"] == "paper" and not node["properties"].get("stub")
        )
        paper["properties"]["research_question_evidence_ids"] = [other["id"]]

        errors, _warnings = validate_graph(graph)
        self.assertTrue(
            any("does not belong to this paper" in error for error in errors)
        )
        self.assertTrue(
            any("research_question requires" in error for error in errors)
        )

    def test_future_work_cannot_use_another_papers_evidence(self) -> None:
        profile = sample_profile()
        profile["future_work"] = [
            {"text": "Test another setting.", "evidence_refs": ["e1"]}
        ]
        builder = GraphBuilder(new_graph("test-cross-paper-future-work"))
        builder.add_profile(profile)
        graph = builder.finish()
        other = copy.deepcopy(graph["evidence"][0])
        other.update(
            {
                "id": "ev:other-paper-future-work",
                "source_document_id": "doc:other-paper",
                "profile_id": "profile:other-paper",
                "upstream_evidence_id": "other-future-work",
            }
        )
        graph["evidence"].append(other)
        paper = next(
            node
            for node in graph["nodes"]
            if node["type"] == "paper" and not node["properties"].get("stub")
        )
        paper["properties"]["future_work_items"][0]["evidence_ids"] = [other["id"]]

        errors, _warnings = validate_graph(graph)
        self.assertTrue(
            any("future_work_items[0] requires" in error for error in errors)
        )

    def test_schema_gate_rejects_unknown_profile_fields(self) -> None:
        profile = sample_profile()
        profile["unexpected"] = True
        builder = GraphBuilder(new_graph("test-schema"))
        with self.assertRaisesRegex(ValueError, "JSON Schema validation"):
            builder.add_profile(profile)

    def test_semantic_validator_rejects_metadata_only_scientific_edges(self) -> None:
        builder = GraphBuilder(new_graph("test-metadata-edge"))
        builder.add_profile(sample_profile())
        graph = builder.finish()
        graph["evidence"][0].update(
            {
                "source_type": "metadata_api",
                "evidence_type": "metadata_record",
                "evidence_level": "metadata",
            }
        )
        errors, _warnings = validate_graph(graph)
        self.assertTrue(any("requires located, verified fulltext evidence" in error for error in errors))

    def test_semantic_validator_rejects_blank_direct_quote_content(self) -> None:
        builder = GraphBuilder(new_graph("test-blank-quote-content"))
        builder.add_profile(sample_profile())
        graph = builder.finish()
        graph["evidence"][0]["content"] = "   "
        graph["evidence"][0]["content_hash"] = hashlib.sha256(b"   ").hexdigest()

        errors, _warnings = validate_graph(graph)
        self.assertTrue(
            any("direct_quote content must be a non-blank string" in error for error in errors)
        )

    def test_validator_rejects_cross_document_paper_evidence(self) -> None:
        builder = GraphBuilder(new_graph("test-cross-document"))
        builder.add_profile(sample_profile())
        graph = builder.finish()
        graph["evidence"][0]["source_document_id"] = "doc:other"

        errors, _warnings = validate_graph(graph)
        self.assertTrue(any("expected doc:test-paper" in error for error in errors))

    def test_extracted_node_cannot_use_another_profiles_evidence(self) -> None:
        builder = GraphBuilder(new_graph("test-cross-profile-node"))
        builder.add_profile(sample_profile())
        graph = builder.finish()
        foreign = copy.deepcopy(graph["evidence"][0])
        foreign.update(
            {
                "id": "ev:foreign-profile-node",
                "source_document_id": "doc:foreign-paper",
                "profile_id": "profile:foreign-paper",
                "upstream_evidence_id": "foreign-node-evidence",
            }
        )
        graph["evidence"].append(foreign)
        finding = next(node for node in graph["nodes"] if node["type"] == "finding")
        finding["evidence_ids"] = [foreign["id"]]

        errors, _warnings = validate_graph(graph)
        self.assertTrue(
            any(
                f"node {finding['id']} evidence {foreign['id']} belongs to profile"
                in error
                for error in errors
            )
        )

    def test_finding_edge_cannot_bind_to_another_paper_profile(self) -> None:
        first = sample_profile()
        second = sample_profile()
        second["profile_id"] = "profile:second-paper"
        second["document"].update(
            {
                "document_id": "doc:second-paper",
                "title": "Second graph pipeline test fixture",
            }
        )
        second["research_question"]["text"] = "Does X affect Y elsewhere?"
        second["findings"][0]["claim"] = "X increases Y in the second fixture."
        for evidence in second["evidence"]:
            evidence["document_id"] = "doc:second-paper"

        builder = GraphBuilder(new_graph("test-cross-paper-finding-edge"))
        builder.add_profile(first)
        builder.add_profile(second)
        graph = builder.finish()
        second_paper = next(
            node
            for node in graph["nodes"]
            if node["type"] == "paper"
            and node["properties"].get("document_id") == "doc:second-paper"
        )
        second_evidence = next(
            item
            for item in graph["evidence"]
            if item.get("profile_id") == "profile:second-paper"
        )
        first_finding = next(
            node
            for node in graph["nodes"]
            if node["type"] == "finding"
            and node["label"] == "X significantly reduces Y."
        )
        edge = next(
            item
            for item in graph["edges"]
            if item["type"] == "HAS_OUTCOME" and item["source"] == first_finding["id"]
        )
        edge["context"] = {
            "profile_id": "profile:second-paper",
            "paper_id": second_paper["id"],
        }
        edge["evidence_ids"] = [second_evidence["id"]]

        errors, _warnings = validate_graph(graph)
        self.assertTrue(
            any(
                f"profile profile:second-paper is not recorded on source node {first_finding['id']}"
                in error
                for error in errors
            )
        )

    def test_extracted_edge_cannot_use_stub_paper_as_provenance(self) -> None:
        builder = GraphBuilder(new_graph("test-stub-paper-provenance"))
        builder.add_profile(sample_profile())
        graph = builder.finish()
        paper = next(
            node
            for node in graph["nodes"]
            if node["type"] == "paper" and not node["properties"].get("stub")
        )
        paper["properties"]["stub"] = True

        errors, _warnings = validate_graph(graph)
        self.assertTrue(
            any(
                f"cannot use stub paper {paper['id']} as provenance context" in error
                for error in errors
            )
        )

    def test_extracted_edge_cannot_drop_provenance_context(self) -> None:
        builder = GraphBuilder(new_graph("test-missing-edge-context"))
        builder.add_profile(sample_profile())
        graph = builder.finish()
        edge = next(
            item for item in graph["edges"] if item["type"] == "STUDIES_TOPIC"
        )
        edge["context"] = {}

        errors, _warnings = validate_graph(graph)
        self.assertTrue(
            any("requires context.profile_id" in error for error in errors)
        )
        self.assertTrue(
            any("requires exactly one provenance context" in error for error in errors)
        )

    def test_validator_rejects_cross_document_policy_evidence(self) -> None:
        builder = GraphBuilder(new_graph("test-cross-policy-document"))
        builder.add_profile(sample_profile())
        graph = builder.finish()

        policy_evidence = copy.deepcopy(graph["evidence"][0])
        policy_evidence.update(
            {
                "id": "ev:policy-cross-document",
                "source_type": "policy_text",
                "source_document_id": "doc:policy-b",
                "document_version": "v1",
                "profile_id": "profile:policy-a",
                "upstream_evidence_id": "policy-e1",
            }
        )
        graph["evidence"].append(policy_evidence)

        paper = next(node for node in graph["nodes"] if node["type"] == "paper")
        topic = next(node for node in graph["nodes"] if node["type"] == "topic")
        policy = copy.deepcopy(paper)
        policy.update(
            {
                "id": "policy_document:policy-a",
                "type": "policy_document",
                "label": "Policy A",
                "normalized_label": "policy a",
                "source_profile_ids": ["profile:policy-a"],
                "evidence_ids": [policy_evidence["id"]],
                "properties": {"document_id": "doc:policy-a", "stub": False},
            }
        )
        instrument = copy.deepcopy(topic)
        instrument.update(
            {
                "id": "policy_instrument:instrument-a",
                "type": "policy_instrument",
                "label": "Instrument A",
                "normalized_label": "instrument a",
                "source_profile_ids": ["profile:policy-a"],
                "evidence_ids": [policy_evidence["id"]],
            }
        )
        graph["nodes"].extend([policy, instrument])

        edge = copy.deepcopy(graph["edges"][0])
        edge.update(
            {
                "id": "edge:policy-cross-document",
                "source": policy["id"],
                "target": instrument["id"],
                "type": "CONTAINS_INSTRUMENT",
                "layer": "knowledge",
                "evidence_ids": [policy_evidence["id"]],
                "context": {
                    "profile_id": "profile:policy-a",
                    "paper_id": None,
                    "policy_document_id": policy["id"],
                },
            }
        )
        graph["edges"].append(edge)

        errors, _warnings = validate_graph(graph)
        self.assertTrue(
            any("policy_document:policy-a evidence" in error for error in errors)
        )
        self.assertTrue(
            any("expected policy document doc:policy-a" in error for error in errors)
        )

    def test_validator_rejects_cross_document_report_evidence(self) -> None:
        builder = GraphBuilder(new_graph("test-cross-report-document"))
        builder.add_profile(sample_profile())
        graph = builder.finish()

        report_evidence = copy.deepcopy(graph["evidence"][0])
        report_evidence.update(
            {
                "id": "ev:report-cross-document",
                "source_type": "report_text",
                "source_document_id": "doc:report-b",
                "document_version": "v1",
                "profile_id": "profile:report-a",
                "upstream_evidence_id": "report-e1",
            }
        )
        graph["evidence"].append(report_evidence)
        paper = next(node for node in graph["nodes"] if node["type"] == "paper")
        report = copy.deepcopy(paper)
        report.update(
            {
                "id": "report:report-a",
                "type": "report",
                "label": "Report A",
                "normalized_label": "report a",
                "source_profile_ids": ["profile:report-a"],
                "evidence_ids": [report_evidence["id"]],
                "properties": {"document_id": "doc:report-a", "stub": False},
            }
        )
        graph["nodes"].append(report)

        errors, _warnings = validate_graph(graph)
        self.assertTrue(
            any("report:report-a evidence" in error for error in errors)
        )

    def test_validator_rejects_ungrounded_discovery_node(self) -> None:
        builder = GraphBuilder(new_graph("test-ungrounded-gap"))
        builder.add_profile(sample_profile())
        graph = builder.finish()
        source = next(node for node in graph["nodes"] if node["type"] == "paper")
        gap = copy.deepcopy(source)
        gap.update(
            {
                "id": "research_gap:ungrounded",
                "type": "research_gap",
                "layer": "discovery",
                "label": "Ungrounded gap",
                "normalized_label": "ungrounded gap",
                "origin": "inferred",
                "source_profile_ids": [],
                "derivation": {
                    "method": "test",
                    "method_version": "1",
                    "input_snapshot_id": graph["snapshot_id"],
                    "input_node_ids": [],
                    "input_edge_ids": [],
                    "parameters": {},
                    "prompt_hash": None,
                    "code_ref": None,
                },
                "properties": {},
            }
        )
        graph["nodes"].append(gap)

        errors, _warnings = validate_graph(graph)
        self.assertTrue(any("derivation has no graph inputs" in error for error in errors))
        self.assertTrue(any("has no evidence relation" in error for error in errors))

    def test_graph_build_manifest_seed_is_valid(self) -> None:
        manifest = _load_run_manifest(ROOT / "samples" / "graph_build_manifest.seed.json")
        self.assertIsNotNone(manifest)
        self.assertEqual("greenfin-research-graph", manifest["graph_id"])

    def test_graph_build_manifest_rejects_reversed_year_window(self) -> None:
        manifest = json.loads(
            (ROOT / "samples" / "graph_build_manifest.seed.json").read_text(
                encoding="utf-8"
            )
        )
        manifest["scope"]["year_start"] = 2026
        manifest["scope"]["year_end"] = 2020
        with self.assertRaisesRegex(ValueError, "year_start"):
            _validate_run_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
