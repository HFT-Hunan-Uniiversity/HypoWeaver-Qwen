from __future__ import annotations

import hashlib
import json
import os
import shutil
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
import numpy as np
from pydantic import ValidationError

import hypoweaver.knowledge_api as knowledge_api
from hypoweaver.knowledge_client import KnowledgeClient
from hypoweaver.knowledge_models import (
    EvidenceBundle,
    EvidenceHit,
    KnowledgeSearchRequest,
    SourceLocator,
)
from hypoweaver.knowledge_service import (
    HashingEmbedder,
    KnowledgeCatalogIndex,
    KnowledgeService,
    KnowledgeSettings,
    LegacyRuleEmbedder,
)
from hypoweaver.legacy_rag import LegacyChunkResolver


def _record(
    *,
    document_id: str,
    chunk_id: str,
    text: str,
    title: str,
    year: int,
) -> dict:
    return {
        "document_id": document_id,
        "document_version": "sha256:source-version",
        "chunk_id": chunk_id,
        "text": text,
        "title": title,
        "source_type": "paper",
        "source_locator": {"page_start": 3, "section": "Results"},
        "source_url": f"https://example.test/{document_id}",
        "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "has_fulltext": True,
        "evidence_status": "fulltext_verified",
        "publication_year": year,
        "metadata": {"journal": "Test Journal"},
    }


def _local_test_root() -> Path:
    base = Path(os.getenv("HYPOWEAVER_TEST_TMP", Path.cwd() / ".test-tmp"))
    root = base / uuid4().hex
    root.mkdir(parents=True, exist_ok=False)
    return root


class KnowledgeContractTests(unittest.TestCase):
    def test_evidence_hash_is_verified(self) -> None:
        with self.assertRaisesRegex(ValidationError, "content_sha256"):
            EvidenceHit(
                document_id="paper-1",
                document_version="v1",
                chunk_id="chunk-1",
                text="real text",
                title="Paper",
                source_type="paper",
                source_locator=SourceLocator(page_start=1),
                content_sha256="0" * 64,
                retrieval_score=0.8,
                has_fulltext=True,
                evidence_status="fulltext_verified",
            )

    def test_bundle_identity_does_not_depend_on_wall_clock(self) -> None:
        text = "A source-located result about green innovation."
        hit = EvidenceHit(
            **_record(
                document_id="paper-1",
                chunk_id="paper-1__semantic_0001",
                text=text,
                title="Green innovation",
                year=2025,
            ),
            retrieval_score=0.9,
        )
        request = KnowledgeSearchRequest(
            question="Does green finance affect innovation?",
            as_of=date(2026, 8, 25),
        )
        first = EvidenceBundle.build(
            request=request,
            corpus_snapshot_id="corpus:test",
            evidence_hits=[hit],
            generated_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
        )
        second = EvidenceBundle.build(
            request=request,
            corpus_snapshot_id="corpus:test",
            evidence_hits=[hit],
            generated_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
        )
        self.assertEqual(first.bundle_id, second.bundle_id)

    def test_aug23_rule_fallback_normalizes_queries_like_original_branch(self) -> None:
        embedder = LegacyRuleEmbedder()
        chinese_punctuation = embedder.embed("绿色，金融。", dimensions=512)
        ascii_punctuation = embedder.embed("绿色,金融.", dimensions=512)
        np.testing.assert_array_equal(chinese_punctuation, ascii_punctuation)


class KnowledgeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = _local_test_root()
        self.catalog = self.root / "evidence.jsonl"
        records = [
            _record(
                document_id="paper-green",
                chunk_id="paper-green__semantic_0001",
                text="绿色金融政策促进企业绿色技术创新，并降低融资约束。",
                title="绿色金融与绿色创新",
                year=2024,
            ),
            _record(
                document_id="paper-weather",
                chunk_id="paper-weather__semantic_0001",
                text="天气变化影响城市降水和日照时间。",
                title="城市天气研究",
                year=2023,
            ),
        ]
        self.catalog.write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records),
            encoding="utf-8",
        )
        self.cleaned = self.root / "catalog-cleaned"
        self.cleaned.mkdir()
        (self.cleaned / "paper-green.md").write_text(
            "绿色金融与绿色创新\n\n" + "这是可连续阅读的系统论文正文。" * 100,
            encoding="utf-8",
        )
        (self.cleaned / "paper-weather.md").write_text(
            "城市天气研究\n\n天气变化影响城市降水和日照时间。",
            encoding="utf-8",
        )
        self.graph_dir = self.root / "kg"
        self.graph_dir.mkdir()
        (self.graph_dir / "paper-green.kg.json").write_text(
            json.dumps(
                {
                    "paper": {"doc_id": "paper-green", "title": "绿色金融与绿色创新"},
                    "relations": [
                        {
                            "source": "绿色金融政策",
                            "relation": "PROMOTES",
                            "target": "绿色技术创新",
                            "confidence": 0.82,
                            "source_doc": "paper-green",
                            "evidence_refs": ["paper-green__semantic_0001"],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.service = KnowledgeService(
            KnowledgeSettings(
                catalog_path=self.catalog,
                cleaned_dir=self.cleaned,
                graph_dir=self.graph_dir,
                corpus_snapshot_id="corpus:test-v1",
            )
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def test_vector_and_graph_results_share_auditable_bundle(self) -> None:
        result = self.service.search(
            KnowledgeSearchRequest(
                question="绿色金融政策是否促进绿色技术创新？",
                top_k=1,
                max_graph_edges=5,
                as_of=date(2026, 8, 25),
            )
        )

        self.assertEqual(result.corpus_snapshot_id, "corpus:test-v1")
        self.assertEqual(result.evidence_hits[0].document_id, "paper-green")
        self.assertEqual(result.evidence_hits[0].source_locator.page_start, 3)
        self.assertEqual(result.graph_edges[0].relation, "PROMOTES")
        self.assertEqual(
            result.graph_edges[0].evidence_refs,
            ["paper-green__semantic_0001"],
        )

    def test_per_document_cap_replaces_single_document_top_k(self) -> None:
        catalog = self.root / "diversity.jsonl"
        common_text = "绿色金融 环境绩效 真实减排 识别策略"
        records = [
            _record(
                document_id=document_id,
                chunk_id=f"{document_id}__semantic_0001",
                text=common_text,
                title=document_id,
                year=2025,
            )
            for document_id in ("paper-b", "paper-c", "paper-d")
        ]
        records.extend(
            _record(
                document_id="paper-a",
                chunk_id=f"paper-a__semantic_{index:04d}",
                text=common_text,
                title="paper-a",
                year=2025,
            )
            for index in range(1, 7)
        )
        catalog.write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records),
            encoding="utf-8",
        )
        service = KnowledgeService(
            KnowledgeSettings(
                catalog_path=catalog,
                corpus_snapshot_id="corpus:diversity-test",
            )
        )

        baseline = service.search(
            KnowledgeSearchRequest(
                question=common_text,
                top_k=6,
                diversity_mode="none",
            )
        )
        diversified = service.search(
            KnowledgeSearchRequest(
                question=common_text,
                top_k=6,
                diversity_mode="per_document_cap",
                max_hits_per_document=2,
                min_unique_documents=3,
            )
        )

        self.assertEqual(len({item.document_id for item in baseline.evidence_hits}), 1)
        self.assertGreaterEqual(
            diversified.retrieval_diagnostics.unique_document_count,
            3,
        )
        self.assertLessEqual(
            diversified.retrieval_diagnostics.max_hits_from_one_document,
            2,
        )
        self.assertTrue(diversified.retrieval_diagnostics.diversity_gate_passed)
        self.assertGreater(diversified.retrieval_diagnostics.skipped_by_document_cap, 0)

    def test_catalog_browses_real_documents_without_promoting_them_to_evidence(self) -> None:
        result = self.service.catalog(query="绿色金融", fulltext_only=True, limit=10)

        self.assertEqual(result.total_documents, 2)
        self.assertEqual(result.fulltext_documents, 2)
        self.assertEqual(result.readable_documents, 1)
        self.assertEqual(result.metadata_only_documents, 0)
        self.assertEqual(result.matched_documents, 1)
        self.assertEqual(result.items[0].document_id, "paper-green")
        self.assertEqual(result.items[0].content_kind, "indexed_fulltext")
        self.assertTrue(result.items[0].reading_available)
        self.assertFalse(result.items[0].original_pdf_available)
        self.assertEqual(result.collection_status, "snapshot_only")

    def test_derived_catalog_title_skips_journal_masthead(self) -> None:
        source = self.root / "journal-paper.md"
        source.write_text(
            "第 29 卷第 5 期 管理科学学报 Vol. 29 No. 5\n"
            "2026 年 5 月 JOURNAL OF MANAGEMENT SCIENCES IN CHINA May 2026\n"
            "doi: 10.1000/example\n"
            "机构投资者与碳市场有效性\n",
            encoding="utf-8",
        )

        self.assertEqual(
            KnowledgeCatalogIndex._derived_title(source, "paper-carbon"),
            "机构投资者与碳市场有效性",
        )

    def test_reads_cleaned_document_text_in_bounded_slices(self) -> None:
        first = self.service.document_text("paper-green", limit=40)
        second = self.service.document_text(
            "paper-green",
            offset=first.next_offset or 0,
            limit=40,
        )

        self.assertEqual(first.document_id, "paper-green")
        self.assertEqual(first.limit, 40)
        self.assertEqual(len(first.content_sha256), 64)
        self.assertEqual(second.offset, 40)
        self.assertNotEqual(first.text, second.text)

        readable_page = self.service.catalog(readable_only=True, limit=10)
        self.assertEqual(readable_page.matched_documents, 1)
        self.assertEqual(readable_page.items[0].document_id, "paper-green")

    def test_year_filter_is_fail_closed_for_out_of_range_sources(self) -> None:
        result = self.service.search(
            KnowledgeSearchRequest.model_validate(
                {
                    "question": "绿色金融政策创新",
                    "top_k": 5,
                    "filters": {"publication_year_min": 2025},
                }
            )
        )
        self.assertEqual(result.evidence_hits, [])
        self.assertTrue(any("no source-located evidence" in item for item in result.warnings))

    def test_aug23_chunk_metadata_can_be_hydrated_without_mutating_sources(self) -> None:
        cleaned = self.root / "legacy-cleaned"
        metadata = self.root / "legacy-cleaned-meta"
        cleaned.mkdir()
        metadata.mkdir()
        document_id = "legacy-fulltext-source"
        paragraph = " ".join(
            ["Observed policy exposure changes financing and innovation outcomes" for _ in range(10)]
        ) + "."
        (cleaned / f"{document_id}.md").write_text(
            f"#【Results】\n## Main result\n\n{paragraph}\n",
            encoding="utf-8",
        )
        (metadata / f"{document_id}.json").write_text(
            json.dumps({"doc_id": document_id, "title": "Legacy source", "year": 2025}),
            encoding="utf-8",
        )

        resolver = LegacyChunkResolver(cleaned, metadata)
        record = resolver.resolve(
            {
                "doc_id": document_id,
                "chunk_id": f"{document_id}__semantic_0001",
            }
        )

        self.assertEqual(record["text"], paragraph)
        self.assertEqual(record["publication_year"], 2025)
        self.assertEqual(record["evidence_status"], "fulltext_located")
        self.assertEqual(record["source_locator"]["section"], "Results / Main result")

    def test_document_registry_prevents_metadata_only_document_from_becoming_evidence(self) -> None:
        cleaned = self.root / "registry-cleaned"
        metadata = self.root / "registry-cleaned-meta"
        manifests = self.root / "registry-manifests"
        cleaned.mkdir()
        metadata.mkdir()
        manifests.mkdir()
        document_id = "feed-record"
        paragraph = " ".join(
            ["Abstract-level policy and innovation association" for _ in range(12)]
        ) + "."
        markdown_path = cleaned / f"{document_id}.md"
        metadata_path = metadata / f"{document_id}.json"
        markdown_path.write_text(f"#【Abstract】\n\n{paragraph}\n", encoding="utf-8")
        metadata_path.write_text(
            json.dumps(
                {
                    "doc_id": document_id,
                    "doc_type": "feed_api",
                    "title": "Metadata-only source",
                    "year": 2025,
                }
            ),
            encoding="utf-8",
        )
        registry = manifests / "doc_registry.csv"
        registry.write_text(
            "doc_id,title,has_fulltext,cleaned_md_sha256,metadata_sha256\n"
            f"{document_id},Metadata-only source,false,"
            f"{hashlib.sha256(markdown_path.read_bytes()).hexdigest()},"
            f"{hashlib.sha256(metadata_path.read_bytes()).hexdigest()}\n",
            encoding="utf-8",
        )

        resolver = LegacyChunkResolver(cleaned, metadata, registry)
        record = resolver.resolve(
            {
                "doc_id": document_id,
                "chunk_id": f"{document_id}__semantic_0001",
            }
        )

        self.assertFalse(resolver.document_has_fulltext({"doc_id": document_id}))
        self.assertFalse(record["has_fulltext"])
        self.assertEqual(record["evidence_status"], "metadata_only")

    def test_document_registry_hash_mismatch_fails_closed(self) -> None:
        cleaned = self.root / "hash-cleaned"
        manifests = self.root / "hash-manifests"
        cleaned.mkdir()
        manifests.mkdir()
        document_id = "legacy-fulltext-hash-source"
        paragraph = " ".join(["Verified full-text result" for _ in range(30)]) + "."
        (cleaned / f"{document_id}.md").write_text(
            f"#【Results】\n\n{paragraph}\n",
            encoding="utf-8",
        )
        registry = manifests / "doc_registry.csv"
        registry.write_text(
            "doc_id,title,has_fulltext,cleaned_md_sha256\n"
            f"{document_id},Hash source,true,{'0' * 64}\n",
            encoding="utf-8",
        )

        resolver = LegacyChunkResolver(cleaned, document_registry_path=registry)
        with self.assertRaisesRegex(ValueError, "cleaned document hash mismatch"):
            resolver.resolve(
                {
                    "doc_id": document_id,
                    "chunk_id": f"{document_id}__semantic_0001",
                }
            )

    def test_aug23_hdf5_hit_is_hydrated_from_read_only_cleaned_source(self) -> None:
        try:
            import h5py
        except ImportError:
            self.skipTest("h5py is installed in the knowledge-service image only")
        cleaned = self.root / "cleaned"
        metadata = self.root / "cleaned_meta"
        cleaned.mkdir()
        metadata.mkdir()
        document_id = "legacy-fulltext-paper"
        paragraph = " ".join(
            [
                "The policy exposure changes financing constraints and innovation outcomes"
                for _ in range(10)
            ]
        ) + "."
        markdown = f"#【Results】\n## Empirical results\n\n{paragraph}\n"
        (cleaned / f"{document_id}.md").write_text(markdown, encoding="utf-8")
        (metadata / f"{document_id}.json").write_text(
            json.dumps(
                {
                    "doc_id": document_id,
                    "title": "Legacy HDF5 paper",
                    "year": 2024,
                    "doi": "10.0000/example",
                }
            ),
            encoding="utf-8",
        )
        registry = self.root / "doc_registry.csv"
        markdown_path = cleaned / f"{document_id}.md"
        metadata_path = metadata / f"{document_id}.json"
        duplicate_document_id = "legacy-fulltext-paper-copy"
        duplicate_markdown_path = cleaned / f"{duplicate_document_id}.md"
        duplicate_metadata_path = metadata / f"{duplicate_document_id}.json"
        duplicate_markdown_path.write_bytes(markdown_path.read_bytes())
        duplicate_metadata_path.write_bytes(metadata_path.read_bytes())
        registry.write_text(
            "doc_id,title,doi,has_fulltext,cleaned_md_sha256,metadata_sha256,publication_year\n"
            f"{document_id},Legacy HDF5 paper,10.0000/example,true,"
            f"{hashlib.sha256(markdown_path.read_bytes()).hexdigest()},"
            f"{hashlib.sha256(metadata_path.read_bytes()).hexdigest()},2024\n"
            f"{duplicate_document_id},Legacy HDF5 paper copy,10.0000/example,true,"
            f"{hashlib.sha256(duplicate_markdown_path.read_bytes()).hexdigest()},"
            f"{hashlib.sha256(duplicate_metadata_path.read_bytes()).hexdigest()},2024\n",
            encoding="utf-8",
        )
        vector_path = self.root / "all_store.h5"
        query = "financing constraints and innovation outcomes"
        vector = HashingEmbedder().embed(query, dimensions=512)
        legacy_meta = {
            "doc_id": document_id,
            "chunk_id": f"{document_id}__semantic_0001",
            "chunk_level": "semantic",
            "chunk_seq": 1,
            "section_title": "Results / Empirical results",
            "title": "Legacy HDF5 paper",
        }
        duplicate_meta = {
            **legacy_meta,
            "doc_id": duplicate_document_id,
            "chunk_id": f"{duplicate_document_id}__semantic_0001",
            "title": "Legacy HDF5 paper copy",
        }
        with h5py.File(vector_path, "w") as handle:
            handle.create_dataset(
                "vectors",
                data=np.asarray([vector, vector], dtype=np.float32),
            )
            handle.create_dataset(
                "metas",
                data=np.asarray(
                    [json.dumps(legacy_meta), json.dumps(duplicate_meta)],
                    dtype=h5py.string_dtype(encoding="utf-8"),
                ),
            )

        service = KnowledgeService(
            KnowledgeSettings(
                vector_path=vector_path,
                cleaned_dir=cleaned,
                metadata_dir=metadata,
                document_registry_path=registry,
                corpus_snapshot_id="corpus:legacy-test",
            )
        )
        result = service.search(
            KnowledgeSearchRequest(
                question=query,
                top_k=2,
                filters={"publication_year_min": 2024},
            )
        )

        self.assertEqual(len(result.evidence_hits), 1)
        hit = result.evidence_hits[0]
        self.assertEqual(hit.text, paragraph)
        self.assertEqual(hit.publication_year, 2024)
        self.assertEqual(hit.evidence_status, "fulltext_located")
        self.assertEqual(hit.source_locator.section, "Results / Empirical results")
        self.assertTrue(hit.document_version.startswith("sha256:"))
        self.assertTrue(any("deduplicated 1 legacy hits" in item for item in result.warnings))


class KnowledgeApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.service_case = KnowledgeServiceTests("test_vector_and_graph_results_share_auditable_bundle")
        self.service_case.setUp()
        self.service_patch = patch.object(
            knowledge_api,
            "_service",
            self.service_case.service,
        )
        self.service_patch.start()
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=knowledge_api.app),
            base_url="http://knowledge.test",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.service_patch.stop()
        self.service_case.tearDown()

    async def test_search_requires_and_accepts_internal_bearer_token(self) -> None:
        payload = {"question": "绿色金融政策与绿色创新", "top_k": 1}
        with patch.dict(os.environ, {"KNOWLEDGE_SERVICE_TOKEN": "secret"}, clear=True):
            denied = await self.client.post("/v1/search", json=payload)
            accepted = await self.client.post(
                "/v1/search",
                headers={"Authorization": "Bearer secret"},
                json=payload,
            )

        self.assertEqual(denied.status_code, 401)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["evidence_hits"][0]["document_id"], "paper-green")

    async def test_catalog_requires_internal_bearer_token(self) -> None:
        with patch.dict(os.environ, {"KNOWLEDGE_SERVICE_TOKEN": "secret"}, clear=True):
            denied = await self.client.get("/v1/catalog")
            accepted = await self.client.get(
                "/v1/catalog?query=绿色金融&limit=10",
                headers={"Authorization": "Bearer secret"},
            )

        self.assertEqual(denied.status_code, 401)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["matched_documents"], 1)
        self.assertEqual(accepted.json()["items"][0]["document_id"], "paper-green")

    async def test_document_text_requires_token_and_returns_one_slice(self) -> None:
        with patch.dict(os.environ, {"KNOWLEDGE_SERVICE_TOKEN": "secret"}, clear=True):
            denied = await self.client.get("/v1/catalog/paper-green/text")
            accepted = await self.client.get(
                "/v1/catalog/paper-green/text?limit=40",
                headers={"Authorization": "Bearer secret"},
            )

        self.assertEqual(denied.status_code, 401)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["document_id"], "paper-green")
        self.assertEqual(accepted.json()["limit"], 40)

    async def test_workflow_client_uses_same_contract(self) -> None:
        with patch.dict(os.environ, {"KNOWLEDGE_SERVICE_TOKEN": "secret"}, clear=True):
            client = KnowledgeClient(
                url="http://knowledge.test",
                token="secret",
                transport=httpx.ASGITransport(app=knowledge_api.app),
            )
            result = await client.search(
                KnowledgeSearchRequest(question="绿色金融政策与绿色创新", top_k=1)
            )
            catalog = await client.catalog(query="绿色金融", limit=10)
            text_slice = await client.document_text("paper-green", limit=40)

        self.assertEqual(result.evidence_hits[0].document_id, "paper-green")
        self.assertEqual(catalog.matched_documents, 1)
        self.assertEqual(catalog.items[0].document_id, "paper-green")
        self.assertEqual(text_slice.document_id, "paper-green")


if __name__ == "__main__":
    unittest.main()
