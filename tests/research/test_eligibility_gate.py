from __future__ import annotations

import json
from pathlib import Path
import unittest

from scripts.research.build_eligible_fulltext_manifest import build_eligible_manifest


ROOT = Path(__file__).resolve().parents[2]
TEST_TMP = ROOT / "tmp"
TEST_TMP.mkdir(parents=True, exist_ok=True)


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class EligibilityGateTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[Path, Path]:
        source = {
            "schema_version": "open-fulltext-collection/1.0.0",
            "source": "fixture",
            "retrieved_at": "2026-08-09T00:00:00+00:00",
            "record_count": 2,
            "items": [
                {
                    "pmcid": "PMC1",
                    "doi": "10.1/included",
                    "title": "Included",
                    "raw_file": "PMC1.xml",
                    "raw_sha256": "a" * 64,
                    "is_retracted": None,
                },
                {
                    "pmcid": "PMC2",
                    "doi": "10.1/retracted",
                    "title": "Retracted",
                    "raw_file": "PMC2.xml",
                    "raw_sha256": "b" * 64,
                    "is_retracted": "Y",
                },
            ],
        }
        decisions = {
            "schema_version": "document-eligibility/1.0.0",
            "as_of": "2026-08-09T12:00:00+08:00",
            "decisions": [
                {
                    "pmcid": "PMC1",
                    "doi": "10.1/included",
                    "decision": "include",
                    "reason": "eligible fixture",
                },
                {
                    "pmcid": "PMC2",
                    "doi": "10.1/retracted",
                    "decision": "exclude_retracted",
                    "reason": "publisher retraction",
                    "status_source": "publisher",
                    "status_uri": "https://example.org/retraction",
                    "retraction_notice_doi": "10.1/notice",
                },
            ],
        }
        source_path = root / "source.json"
        decisions_path = root / "decisions.json"
        _write(source_path, source)
        _write(decisions_path, decisions)
        return source_path, decisions_path

    def test_retracted_document_is_excluded_and_source_is_retained(self) -> None:
        root = TEST_TMP / "eligibility_gate_test_release"
        root.mkdir(parents=True, exist_ok=True)
        source, decisions = self._fixture(root)
        source_before = source.read_bytes()
        output = root / "eligible.json"
        audit_path = root / "audit.json"
        manifest, audit = build_eligible_manifest(source, decisions, output, audit_path)
        self.assertEqual(1, manifest["record_count"])
        self.assertEqual("PMC1", manifest["items"][0]["pmcid"])
        self.assertEqual(1, audit["excluded_document_count"])
        self.assertEqual("exclude_retracted", audit["excluded"][0]["decision"])
        self.assertFalse(audit["raw_assets_deleted"])
        self.assertEqual(source_before, source.read_bytes())

        first_output = output.read_bytes()
        first_audit = audit_path.read_bytes()
        build_eligible_manifest(source, decisions, output, audit_path)
        self.assertEqual(first_output, output.read_bytes())
        self.assertEqual(first_audit, audit_path.read_bytes())

    def test_registry_must_cover_source_exactly(self) -> None:
        root = TEST_TMP / "eligibility_gate_test_coverage"
        root.mkdir(parents=True, exist_ok=True)
        source, decisions = self._fixture(root)
        registry = json.loads(decisions.read_text(encoding="utf-8"))
        registry["decisions"].pop()
        _write(decisions, registry)
        with self.assertRaisesRegex(ValueError, "cover the source manifest exactly"):
            build_eligible_manifest(source, decisions, root / "out.json", root / "audit.json")

    def test_source_retraction_signal_cannot_be_overridden_by_include(self) -> None:
        root = TEST_TMP / "eligibility_gate_test_retracted_override"
        root.mkdir(parents=True, exist_ok=True)
        source, decisions = self._fixture(root)
        registry = json.loads(decisions.read_text(encoding="utf-8"))
        registry["decisions"][1] = {
            "pmcid": "PMC2",
            "doi": "10.1/retracted",
            "decision": "include",
            "reason": "incorrect override",
        }
        _write(decisions, registry)
        with self.assertRaisesRegex(ValueError, "marks the work retracted"):
            build_eligible_manifest(source, decisions, root / "out.json", root / "audit.json")


if __name__ == "__main__":
    unittest.main()
