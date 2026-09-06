from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import unittest

from jsonschema import Draft202012Validator

from src.parse.jats import build_parsed_batch
from src.retrieve.vector_index import read_chunks_jsonl


ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "output" / "real_pilot" / "2026-08-09_green_finance_decarbonization"
SOURCE_MANIFEST = RUN / "B_fulltext" / "manifest.json"
PARSED = RUN / "C_parsed"
CHUNK_SCHEMA = ROOT / "schemas" / "chunk.schema.json"
TEST_TEMP = ROOT / "tmp" / "jats_parser_tests"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class JatsParserPilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((PARSED / "manifest.json").read_text(encoding="utf-8"))
        cls.chunks = read_jsonl(PARSED / "chunks.jsonl")
        cls.exclusions = read_jsonl(PARSED / "excluded_blocks.jsonl")
        cls.documents = {
            document["document_id"]: document
            for path in PARSED.glob("PMC*.parsed.json")
            for document in [json.loads(path.read_text(encoding="utf-8"))]
        }

    def test_formal_pilot_deliverables_are_complete(self) -> None:
        self.assertEqual(7, self.manifest["document_count"])
        self.assertEqual(7, len(self.manifest["documents"]))
        self.assertEqual(7, len(self.documents))
        self.assertEqual(494, self.manifest["block_count"])
        self.assertEqual(572, self.manifest["chunk_count"])
        self.assertEqual(52, self.manifest["excluded_block_count"])
        self.assertEqual(self.manifest["chunk_count"], len(self.chunks))
        self.assertEqual(self.manifest["excluded_block_count"], len(self.exclusions))
        self.assertTrue(all(item["status"] == "ok" for item in self.manifest["documents"]))

    def test_source_asset_hashes_and_output_hashes_close(self) -> None:
        source = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
        source_by_pmcid = {item["pmcid"]: item for item in source["items"]}
        for entry in self.manifest["documents"]:
            source_item = source_by_pmcid[entry["pmcid"]]
            raw_path = SOURCE_MANIFEST.parent / source_item["raw_file"]
            self.assertEqual(source_item["raw_sha256"], sha256_bytes(raw_path.read_bytes()))
            self.assertEqual(source_item["raw_sha256"], entry["raw_sha256"])
            self.assertEqual(source_item["bytes"], raw_path.stat().st_size)
            parsed_path = PARSED / entry["parsed_file"]
            self.assertEqual(entry["parsed_sha256"], sha256_bytes(parsed_path.read_bytes()))
        self.assertEqual(
            self.manifest["source_manifest_sha256"],
            sha256_bytes(SOURCE_MANIFEST.read_bytes()),
        )
        self.assertEqual(self.manifest["chunks_sha256"], sha256_bytes((PARSED / "chunks.jsonl").read_bytes()))
        self.assertEqual(
            self.manifest["excluded_blocks_sha256"],
            sha256_bytes((PARSED / "excluded_blocks.jsonl").read_bytes()),
        )

    def test_every_chunk_passes_schema_and_id_lineage(self) -> None:
        schema = json.loads(CHUNK_SCHEMA.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        chunk_ids: set[str] = set()
        evidence_ids: set[str] = set()
        releases: set[str] = set()
        for line_number, chunk in enumerate(self.chunks, start=1):
            errors = sorted(validator.iter_errors(chunk), key=lambda error: list(error.path))
            self.assertFalse(errors, f"chunk line {line_number}: {[error.message for error in errors]}")
            self.assertNotIn(chunk["chunk_id"], chunk_ids)
            self.assertNotIn(chunk["evidence_id"], evidence_ids)
            chunk_ids.add(chunk["chunk_id"])
            evidence_ids.add(chunk["evidence_id"])
            releases.add(chunk["release_id"])
            self.assertEqual(f"doi:{chunk['doi']}", chunk["document_id"])
            self.assertIn(chunk["pmcid"].casefold(), chunk["asset_id"])
            self.assertEqual(chunk["raw_sha256"], chunk["content_sha256"])
            self.assertEqual(sha256_bytes(chunk["text"].encode("utf-8")), chunk["text_sha256"])
            self.assertEqual(chunk["text_sha256"], chunk["content_hash"])
        self.assertEqual({self.manifest["release_id"]}, releases)

    def test_locators_reproduce_exact_chunk_text(self) -> None:
        for chunk in self.chunks:
            document = self.documents[chunk["document_id"]]
            block = next(item for item in document["blocks"] if item["block_id"] == chunk["block_id"])
            locator = chunk["locator"]
            self.assertEqual(block["section"], locator["section"])
            self.assertEqual(block["xml_id"], locator["xml_id"])
            self.assertEqual(block["xml_path"], locator["xml_path"])
            self.assertTrue(locator["xml_path"].startswith("/article[1]/"))
            self.assertEqual(chunk["text"], block["text"][locator["start_char"]:locator["end_char"]])
            self.assertEqual(
                locator["document_start_char"],
                block["document_char_start"] + locator["start_char"],
            )
            self.assertEqual(
                locator["document_end_char"],
                block["document_char_start"] + locator["end_char"],
            )

    def test_abstract_is_not_fulltext_and_administrative_sections_are_excluded(self) -> None:
        source_types = Counter(chunk["source_type"] for chunk in self.chunks)
        self.assertEqual({"paper_abstract": 16, "paper_fulltext": 556}, dict(source_types))
        for chunk in self.chunks:
            is_abstract = chunk["section_path"][0].casefold().startswith("abstract")
            self.assertEqual("paper_abstract" if is_abstract else "paper_fulltext", chunk["source_type"])
            lowered_section = chunk["section"].casefold()
            for forbidden in (
                "funding statement",
                "credit authorship contribution statement",
                "data availability statement",
                "declaration of competing interest",
                "acknowledgements",
            ):
                self.assertNotIn(forbidden, lowered_section)
        excluded_categories = Counter(item["category"] for item in self.exclusions)
        for expected in (
            "acknowledgements",
            "funding",
            "author_contributions",
            "declarations",
            "data_availability",
        ):
            self.assertGreater(excluded_categories[expected], 0)
        self.assertIn("retained in the audit log", self.manifest["exclusion_policy"]["data_availability"])

    def test_tex_formula_preamble_is_removed_but_formula_core_is_retained(self) -> None:
        raw_formula_xml = (SOURCE_MANIFEST.parent / "PMC12228155.xml").read_text(encoding="utf-8")
        self.assertIn("\\documentclass", raw_formula_xml)
        pilot_chunks = [chunk for chunk in self.chunks if chunk["pmcid"] == "PMC12228155"]
        joined = "\n".join(chunk["text"] for chunk in pilot_chunks)
        lowered = joined.casefold()
        for forbidden in ("documentclass", "usepackage", "begin{document}", "end{document}"):
            self.assertNotIn(forbidden, lowered)
        for formula_core in ("lnCE", "CTFP", "DEGF"):
            self.assertIn(formula_core, joined)

    def test_chunks_are_accepted_by_vector_baseline(self) -> None:
        records, input_sha256 = read_chunks_jsonl(PARSED / "chunks.jsonl")
        self.assertEqual(572, len(records))
        self.assertEqual(self.manifest["chunks_sha256"], input_sha256)
        self.assertEqual(
            {"paper_abstract": 16, "paper_fulltext": 556},
            dict(Counter(record.source_type for record in records)),
        )

    def test_same_input_and_configuration_are_byte_deterministic(self) -> None:
        first = TEST_TEMP / "first"
        second = TEST_TEMP / "second"
        if TEST_TEMP.exists():
            shutil.rmtree(TEST_TEMP)
        first_manifest = build_parsed_batch(SOURCE_MANIFEST, first)
        second_manifest = build_parsed_batch(SOURCE_MANIFEST, second)
        self.assertEqual(first_manifest, second_manifest)
        first_files = sorted(path.relative_to(first) for path in first.iterdir())
        second_files = sorted(path.relative_to(second) for path in second.iterdir())
        self.assertEqual(first_files, second_files)
        for relative in first_files:
            self.assertEqual((first / relative).read_bytes(), (second / relative).read_bytes(), str(relative))
        shutil.rmtree(TEST_TEMP)


if __name__ == "__main__":
    unittest.main()
