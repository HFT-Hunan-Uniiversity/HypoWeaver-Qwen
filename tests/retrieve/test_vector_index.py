from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
from io import StringIO
import json
from pathlib import Path
import re
import shutil
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from retrieve.vector_index import (  # noqa: E402
    HashingEmbeddingBackend,
    LocalVectorIndex,
    RESULT_SCHEMA_VERSION,
    build_index,
    main,
    read_chunks_jsonl,
)


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ToyEmbeddingBackend:
    backend_id = "toy-qwen-compatible"
    model_id = "toy-embedding-v1"
    algorithm = "test-keyword-vector"
    dimensions = 2

    @staticmethod
    def _embed(text: str) -> list[float]:
        lowered = text.lower()
        return [float("green" in lowered), float("bank" in lowered or "risk" in lowered)]

    def embed_documents(self, texts):
        return [self._embed(text) for text in texts]

    def embed_query(self, text):
        return self._embed(text)


class VectorIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = ROOT / "tmp" / "vector_index_tests" / self._testMethodName
        if self.base.exists():
            shutil.rmtree(self.base)
        self.base.mkdir(parents=True)
        self.chunks_path = self.base / "chunks.jsonl"
        green_text = "Green finance supports renewable energy investment."
        bank_text = "Bank credit risk models estimate default probability."
        carbon_text = "绿色债券能够支持清洁能源并降低碳排放。"
        self.rows = [
            {
                "chunk_id": "chk_green",
                "document_id": "doc:green",
                "evidence_id": "evd_green",
                "text": green_text,
                "content_hash": _text_hash(green_text),
                "text_sha256": _text_hash(green_text),
                "content_sha256": "a" * 64,
                "release_id": "release:2026-08-09",
                "asset_id": "asset:green",
                "document_version": "v2",
                "access_level": "open",
                "license": "CC-BY-4.0",
                "source_type": "paper_fulltext",
                "source_locator": "Results / paragraph 2",
                "section": "Results",
                "block_char_start": 12,
                "block_char_end": 64,
            },
            {
                "chunk_id": "chk_bank",
                "document_id": "doc:bank",
                "evidence_id": "evd_bank",
                "text": bank_text,
                "content_hash": _text_hash(bank_text),
                "access_level": "restricted",
                "license": "licensed-internal-use",
                "source_type": "paper_fulltext",
                "source_locator": "Methods / paragraph 4",
            },
            {
                "document_id": "doc:carbon",
                "text": carbon_text,
                "source_type": "abstract",
                "source_locator": "结论 / 第三段",
            },
        ]
        self._write_rows(self.chunks_path, self.rows)

    @staticmethod
    def _write_rows(path: Path, rows: list[dict]) -> None:
        path.write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        if self.base.exists():
            shutil.rmtree(self.base)

    def test_reads_chunks_derives_stable_ids_and_preserves_metadata(self) -> None:
        first, first_hash = read_chunks_jsonl(self.chunks_path)
        second, second_hash = read_chunks_jsonl(self.chunks_path)
        self.assertEqual("chk_green", first[0].chunk_id)
        self.assertTrue(first[2].chunk_id.startswith("chk_"))
        self.assertTrue(first[2].evidence_id.startswith("evd_"))
        self.assertEqual(first[2].chunk_id, second[2].chunk_id)
        self.assertEqual(first_hash, second_hash)
        self.assertEqual("结论 / 第三段", first[2].locator["source_locator"])
        self.assertEqual(first[0].content_hash, first[0].text_sha256)
        self.assertEqual("a" * 64, first[0].content_sha256)
        self.assertEqual("release:2026-08-09", first[0].release_id)
        self.assertEqual("asset:green", first[0].asset_id)
        self.assertEqual("v2", first[0].document_version)
        self.assertEqual("CC-BY-4.0", first[0].license)

    def test_hash_aliases_are_compatible_and_validated(self) -> None:
        legacy_only = [dict(self.rows[0])]
        legacy_only[0].pop("text_sha256")
        source = self.base / "legacy.jsonl"
        self._write_rows(source, legacy_only)
        records, _ = read_chunks_jsonl(source)
        self.assertEqual(records[0].content_hash, records[0].text_sha256)

        for field, bad_value, expected in (
            ("content_hash", "0" * 64, "content_hash does not match text"),
            ("text_sha256", "0" * 64, "text_sha256 does not match text"),
            ("content_sha256", "not-a-sha", "content_sha256 must be a 64-character"),
        ):
            bad_rows = [dict(self.rows[0])]
            bad_rows[0][field] = bad_value
            invalid = self.base / f"bad-{field}.jsonl"
            self._write_rows(invalid, bad_rows)
            with self.assertRaisesRegex(ValueError, expected):
                read_chunks_jsonl(invalid)

    def test_manifest_and_snapshot_are_content_and_model_bound(self) -> None:
        first = build_index(self.chunks_path, backend=HashingEmbeddingBackend(dimensions=128))
        second = build_index(self.chunks_path, backend=HashingEmbeddingBackend(dimensions=128))
        different_model = build_index(self.chunks_path, backend=HashingEmbeddingBackend(dimensions=256))
        self.assertEqual(first.snapshot_id, second.snapshot_id)
        self.assertNotEqual(first.snapshot_id, different_model.snapshot_id)
        self.assertEqual(3, first.manifest["chunk_count"])
        self.assertEqual("greenfin-lexical-hashing-v1", first.manifest["model_id"])
        self.assertEqual("signed-feature-hashing-logtf-v1", first.manifest["algorithm"])
        self.assertEqual(64, len(first.manifest["input_sha256"]))
        self.assertEqual({"open": 1, "restricted": 1, "unknown": 1}, first.manifest["access_level_counts"])
        self.assertTrue(first.manifest["contains_non_open_content"])
        self.assertEqual("open-only", first.manifest["text_persistence_policy"])

    def test_search_returns_traceable_envelope_and_metadata(self) -> None:
        index = build_index(self.chunks_path, backend=HashingEmbeddingBackend(dimensions=512))
        response = index.search("renewable green finance", top_k=2)
        results = response.results
        self.assertEqual(index.snapshot_id, response.index_snapshot_id)
        self.assertRegex(response.query_hash, r"^[0-9a-f]{64}$")
        self.assertEqual({}, response.filters)
        self.assertEqual("chk_green", results[0].chunk_id)
        self.assertEqual("doc:green", results[0].document_id)
        self.assertEqual("evd_green", results[0].evidence_id)
        self.assertEqual(1, results[0].rank)
        self.assertGreater(results[0].score, results[1].score)
        self.assertEqual("Results / paragraph 2", results[0].locator["source_locator"])
        self.assertEqual("asset:green", results[0].asset_id)
        self.assertEqual("paper_fulltext", results[0].source_type)
        self.assertEqual(results[0].content_hash, results[0].text_sha256)
        self.assertEqual(
            response.query_hash,
            index.search("  RENEWABLE   GREEN FINANCE  ", top_k=1).query_hash,
        )
        required = {"chunk_id", "document_id", "evidence_id", "score", "rank", "locator"}
        self.assertTrue(required.issubset(results[0].to_dict()))

    def test_search_filters_document_source_and_access(self) -> None:
        index = build_index(self.chunks_path, backend=HashingEmbeddingBackend(dimensions=256))
        response = index.search(
            "bank risk",
            filters={
                "document_id": ["doc:green", "doc:bank", "doc:bank"],
                "source_type": "paper_fulltext",
                "access_level": "restricted",
            },
        )
        self.assertEqual(["chk_bank"], [item.chunk_id for item in response.results])
        self.assertEqual(
            {
                "document_id": ["doc:bank", "doc:green"],
                "source_type": ["paper_fulltext"],
                "access_level": ["restricted"],
            },
            response.filters,
        )
        unknown = index.search("clean energy", filters={"access_level": "unknown"})
        self.assertEqual(["doc:carbon"], [item.document_id for item in unknown.results])
        with self.assertRaisesRegex(ValueError, "unsupported search filter"):
            index.search("green", filters={"license": "CC-BY-4.0"})

    def test_non_open_text_is_not_persisted_or_returned(self) -> None:
        index = build_index(self.chunks_path, backend=HashingEmbeddingBackend(dimensions=128))
        target = self.base / "secure-index.json"
        index.save(target)
        payload = json.loads(target.read_text(encoding="utf-8"))
        persisted = {item["chunk_id"]: item for item in payload["records"]}
        self.assertIn("text", persisted["chk_green"])
        self.assertNotIn("text", persisted["chk_bank"])
        derived_chunk_id = next(item.chunk_id for item in index.records if item.document_id == "doc:carbon")
        self.assertNotIn("text", persisted[derived_chunk_id])

        loaded = LocalVectorIndex.load(target)
        response = loaded.search("bank risk", filters={"document_id": "doc:bank"})
        serialized = response.to_dict(include_text=True)["results"][0]
        self.assertNotIn("text", serialized)
        self.assertTrue(serialized["text_redacted"])

    def test_custom_backend_can_build_save_load_and_search(self) -> None:
        backend = ToyEmbeddingBackend()
        index = build_index(self.chunks_path, backend=backend)
        target = self.base / "toy-index.json"
        index.save(target)
        with self.assertRaisesRegex(ValueError, "matching embedding backend"):
            LocalVectorIndex.load(target)
        loaded = LocalVectorIndex.load(target, backend=backend)
        self.assertEqual("chk_bank", loaded.search("bank risk", top_k=1).results[0].chunk_id)

    def test_cli_build_search_filters_and_result_contract(self) -> None:
        target = self.base / "offline-index.json"
        build_stdout = StringIO()
        with redirect_stdout(build_stdout):
            self.assertEqual(
                0,
                main(["build", "--chunks", str(self.chunks_path), "--index", str(target), "--dimensions", "128"]),
            )
        build_payload = json.loads(build_stdout.getvalue())
        self.assertEqual(3, build_payload["chunk_count"])
        self.assertTrue(target.exists())

        search_stdout = StringIO()
        with redirect_stdout(search_stdout):
            self.assertEqual(
                0,
                main(
                    [
                        "search",
                        "--index",
                        str(target),
                        "--query",
                        "green renewable",
                        "--top-k",
                        "1",
                        "--access-level",
                        "open",
                        "--include-text",
                    ]
                ),
            )
        search_payload = json.loads(search_stdout.getvalue())
        self.assertEqual(RESULT_SCHEMA_VERSION, search_payload["schema_version"])
        self.assertEqual(build_payload["snapshot_id"], search_payload["index_snapshot_id"])
        self.assertRegex(search_payload["query_hash"], r"^[0-9a-f]{64}$")
        self.assertEqual({"access_level": ["open"]}, search_payload["filter"])
        self.assertEqual("chk_green", search_payload["results"][0]["chunk_id"])
        self.assertIn("text", search_payload["results"][0])

    def test_schema_and_sample_expose_machine_readable_contract(self) -> None:
        schema = json.loads((ROOT / "schemas" / "retrieval_result.schema.json").read_text(encoding="utf-8"))
        sample = json.loads((ROOT / "samples" / "retrieval_result.seed.json").read_text(encoding="utf-8"))
        self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
        self.assertEqual(RESULT_SCHEMA_VERSION, sample["schema_version"])
        self.assertTrue(set(schema["required"]).issubset(sample))
        self.assertTrue(re.fullmatch(r"[0-9a-f]{64}", sample["query_hash"]))
        result_required = set(schema["$defs"]["result"]["required"])
        self.assertTrue(result_required.issubset(sample["results"][0]))

    def test_duplicate_chunk_ids_are_rejected(self) -> None:
        duplicate = self.base / "duplicates.jsonl"
        self._write_rows(duplicate, [self.rows[0], self.rows[0]])
        with self.assertRaisesRegex(ValueError, "duplicate chunk_id"):
            read_chunks_jsonl(duplicate)


if __name__ == "__main__":
    unittest.main()
