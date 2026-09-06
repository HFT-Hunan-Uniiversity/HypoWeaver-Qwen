from __future__ import annotations

import hashlib
import os
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

import hypoweaver.api as api_module
from hypoweaver.discovery_bridge import evidence_bundle_to_research_graph
from hypoweaver.discovery_engine.research_graph import validate_graph
from hypoweaver.knowledge_models import (
    EvidenceBundle,
    EvidenceHit,
    GraphEdgeCandidate,
    KnowledgeSearchRequest,
    SourceLocator,
)


class DiscoveryBridgeTests(unittest.TestCase):
    def _bundle(self) -> EvidenceBundle:
        text = "绿色金融政策通过缓解融资约束促进企业绿色技术创新。"
        hit = EvidenceHit(
            document_id="doi:10.1000/example",
            document_version="publisher-2026-08-01",
            chunk_id="paper-1__semantic_0001",
            text=text,
            title="绿色金融与企业绿色技术创新",
            source_type="paper",
            source_locator=SourceLocator(page_start=7, section="Empirical results"),
            source_url="https://example.test/paper-1",
            doi="10.1000/example",
            content_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            retrieval_score=0.91,
            has_fulltext=True,
            evidence_status="fulltext_verified",
            publication_year=2025,
        )
        return EvidenceBundle.build(
            request=KnowledgeSearchRequest(
                question="绿色金融是否促进企业绿色创新？",
                as_of=date(2026, 8, 25),
            ),
            corpus_snapshot_id="corpus:verified-test",
            evidence_hits=[hit],
            graph_edges=[
                GraphEdgeCandidate(
                    source="绿色金融政策",
                    relation="PROMOTES",
                    target="绿色技术创新",
                    evidence_refs=[hit.chunk_id],
                    source_document_ids=[hit.document_id],
                    confidence=0.8,
                    extraction_version="test",
                )
            ],
            generated_at=datetime(2026, 8, 25, 8, 0, tzinfo=timezone.utc),
        )

    def test_bundle_becomes_valid_source_layer_without_promoting_rag_edges(self) -> None:
        bridge = evidence_bundle_to_research_graph(self._bundle())
        graph = bridge.research_graph

        errors, _warnings = validate_graph(graph)
        self.assertEqual(errors, [])
        self.assertEqual(len(graph["nodes"]), 1)
        self.assertEqual(len(graph["evidence"]), 1)
        self.assertEqual(graph["edges"], [])
        self.assertEqual(len(bridge.rag_graph_candidates), 1)
        self.assertEqual(
            graph["evidence"][0]["content_hash"],
            hashlib.sha256(
                graph["evidence"][0]["content"].encode("utf-8")
            ).hexdigest(),
        )

    def test_empty_bundle_cannot_enter_discovery(self) -> None:
        bundle = EvidenceBundle.build(
            request=KnowledgeSearchRequest(question="绿色金融研究空白"),
            corpus_snapshot_id="corpus:empty",
            evidence_hits=[],
        )
        with self.assertRaisesRegex(ValueError, "at least one"):
            evidence_bundle_to_research_graph(bundle)


class DiscoveryEvidenceApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api_module.app),
            base_url="http://127.0.0.1",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()

    async def test_preview_connects_knowledge_bundle_to_group1_graph(self) -> None:
        bundle = DiscoveryBridgeTests()._bundle()
        client = SimpleNamespace(search=AsyncMock(return_value=bundle))
        with (
            patch.object(api_module, "KnowledgeClient", return_value=client),
            patch.dict(os.environ, {}, clear=True),
        ):
            response = await self.client.post(
                "/api/v1/discovery/evidence-preview",
                json={"question": "绿色金融是否促进企业绿色创新？", "top_k": 12},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["evidence_bundle_id"], bundle.bundle_id)
        self.assertEqual(payload["research_graph"]["edges"], [])
        self.assertEqual(len(payload["rag_graph_candidates"]), 1)


if __name__ == "__main__":
    unittest.main()
