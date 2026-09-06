from __future__ import annotations

import copy
import hashlib
import json
import os
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

import httpx

import hypoweaver.api as api_module
if __package__:
    from .test_discovery_engine import base_graph, config, novelty_search
else:
    from test_discovery_engine import base_graph, config, novelty_search
from hypoweaver.discovery_bridge import evidence_bundle_to_research_graph
from hypoweaver.discovery_pipeline import (
    DiscoveryBuildRequest,
    ReviewedGraphPatch,
    build_discovery_release_preview,
)
from hypoweaver.knowledge_models import (
    EvidenceBundle,
    EvidenceHit,
    KnowledgeSearchRequest,
    SourceLocator,
)


def _replace_ids(value, mapping: dict[str, str]):
    if isinstance(value, dict):
        return {key: _replace_ids(item, mapping) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_ids(item, mapping) for item in value]
    if isinstance(value, str):
        return mapping.get(value, value)
    return value


def _online_build_request() -> DiscoveryBuildRequest:
    hits = []
    for number, (document_id, title, text, year) in enumerate(
        (
            (
                "doc:paper_one",
                "Synthetic current paper",
                "Synthetic paper one evidence.",
                2025,
            ),
            (
                "doc:paper_two",
                "Synthetic baseline paper",
                "Synthetic paper two evidence.",
                2021,
            ),
        ),
        1,
    ):
        hits.append(
            EvidenceHit(
                document_id=document_id,
                document_version="fixture-v1",
                chunk_id=f"chunk-{number}",
                text=text,
                title=title,
                source_type="paper",
                source_locator=SourceLocator(section="Synthetic fixture"),
                source_url=f"https://example.test/{number}",
                content_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                retrieval_score=1.0,
                has_fulltext=True,
                evidence_status="fulltext_verified",
                publication_year=year,
            )
        )
    bundle = EvidenceBundle.build(
        request=KnowledgeSearchRequest(
            question="Synthetic discovery integration question",
            as_of=date(2026, 8, 9),
        ),
        corpus_snapshot_id="corpus:discovery-integration-test",
        evidence_hits=hits,
        generated_at=datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc),
    )
    bridge = evidence_bundle_to_research_graph(bundle)
    mapping = {
        "paper:one": bridge.document_to_paper_id["doc:paper_one"],
        "paper:two": bridge.document_to_paper_id["doc:paper_two"],
        "ev:paper_one": bridge.chunk_to_evidence_id["chunk-1"],
        "ev:paper_two": bridge.chunk_to_evidence_id["chunk-2"],
        "ev:project_spec_graph_module": bridge.chunk_to_evidence_id["chunk-1"],
    }
    fixture_graph = base_graph()
    nodes = [
        _replace_ids(copy.deepcopy(node), mapping)
        for node in fixture_graph["nodes"]
        if node["type"] != "paper"
    ]
    edges = [_replace_ids(copy.deepcopy(edge), mapping) for edge in fixture_graph["edges"]]
    for item in [*nodes, *edges]:
        item["origin"] = "curated"
        item["review_status"] = "human_verified"
    return DiscoveryBuildRequest(
        evidence_bundle=bundle,
        reviewed_graph_patch=ReviewedGraphPatch(
            nodes=nodes,
            edges=edges,
            review_note="Synthetic human review for the online integration contract.",
        ),
        discovery_config=_replace_ids(config(), mapping),
        novelty_search=novelty_search(),
    )


class DiscoveryPipelineTests(unittest.TestCase):
    def test_evidence_to_reviewed_gap_and_hypothesis_release(self) -> None:
        result = build_discovery_release_preview(
            _online_build_request(),
            reviewer="test-reviewer",
        )

        self.assertEqual(len(result.gap_cards), 1)
        self.assertEqual(len(result.hypothesis_cards), 1)
        self.assertEqual(result.reviewer, "test-reviewer")
        self.assertEqual(
            result.hypothesis_cards[0]["status"],
            "needs_scientific_review",
        )
        self.assertTrue(
            result.final_research_graph["snapshot_id"].startswith(
                result.final_research_graph["graph_id"]
            )
        )

    def test_patch_cannot_invent_unbound_evidence(self) -> None:
        request = _online_build_request()
        request.reviewed_graph_patch.nodes[0]["evidence_ids"] = [
            "evidence:not_in_bundle"
        ]
        with self.assertRaisesRegex(ValueError, "unknown evidence"):
            build_discovery_release_preview(request, reviewer="test-reviewer")


class DiscoveryPipelineApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api_module.app),
            base_url="http://127.0.0.1",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    async def test_release_preview_uses_authenticated_actor_as_reviewer(self) -> None:
        request = _online_build_request()
        with patch.dict(
            os.environ,
            {
                "HYPOWEAVER_API_TOKEN": "workflow-secret",
                "HYPOWEAVER_ACTOR": "reviewer-chen",
            },
            clear=True,
        ):
            response = await self.client.post(
                "/api/v1/discovery/releases/preview",
                headers={"X-Hypoweaver-Token": "workflow-secret"},
                json=request.model_dump(mode="json"),
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["reviewer"], "reviewer-chen")


if __name__ == "__main__":
    unittest.main()
