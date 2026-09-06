from __future__ import annotations

import hashlib
import json
import unittest
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from scripts.research.build_group1_handoff import (
    _handoff_status_errors,
    _normalize_doi,
    _returned_dois,
    _review_status_errors,
)


ROOT = Path(__file__).resolve().parents[2]
BASE = (
    ROOT
    / "output"
    / "real_pilot"
    / "2026-08-09_green_finance_decarbonization"
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Group1HandoffTest(unittest.TestCase):
    def setUp(self) -> None:
        self.review_path = BASE / "F_discovery" / "nearest_work_review.json"
        self.novelty_path = BASE / "F_discovery" / "novelty_search.json"
        self.gap_path = BASE / "H_discovery_release" / "gap_cards" / "gap_001.json"
        self.handoff_dir = BASE / "I_group1_handoff"
        self.review = _load(self.review_path)
        self.novelty = _load(self.novelty_path)
        self.gap = _load(self.gap_path)
        self.handoff = _load(self.handoff_dir / "handoff.json")

    def test_review_and_handoff_match_schemas(self) -> None:
        pairs = [
            (
                self.review,
                ROOT / "schemas" / "group1_literature_review.schema.json",
            ),
            (self.handoff, ROOT / "schemas" / "group1_handoff.schema.json"),
        ]
        for instance, schema_path in pairs:
            with self.subTest(schema=schema_path.name):
                validator = Draft202012Validator(
                    _load(schema_path), format_checker=FormatChecker()
                )
                errors = sorted(validator.iter_errors(instance), key=str)
                self.assertEqual([], errors)

    def test_five_formal_nearest_works_are_returned_and_bound_to_gap(self) -> None:
        review_dois = {
            _normalize_doi(work["doi"])
            for work in self.review["works"]
            if work["formal_nearest"]
        }
        gap_dois = {
            _normalize_doi(work["paper_id"])
            for work in self.gap["novelty_check"]["nearest_works"]
        }
        self.assertEqual(5, len(review_dois))
        self.assertEqual(review_dois, gap_dois)
        self.assertTrue(review_dois.issubset(_returned_dois(self.novelty)))
        self.assertTrue(
            all(
                work["verification_status"] == "verified"
                for work in self.gap["novelty_check"]["nearest_works"]
            )
        )

    def test_sign_conflict_and_group_boundary_are_explicit(self) -> None:
        directions = self.review["conflict_summary"][
            "policy_greenwashing_directions"
        ]
        self.assertTrue(directions["increase"])
        self.assertTrue(directions["decrease"])
        self.assertEqual("ready_for_group2_with_conditions", self.handoff["status"])
        excluded = " ".join(self.handoff["group1_scope"]["excluded"]).casefold()
        self.assertIn("method-library selection", excluded)
        self.assertIn("scientific-ten-item", excluded)

    def test_handoff_and_manifest_hashes_are_current(self) -> None:
        for item in self.handoff["source_artifacts"]:
            path = BASE / item["path"]
            self.assertTrue(path.is_file(), path)
            self.assertEqual(item["sha256"], _sha(path), path)
        manifest = _load(self.handoff_dir / "manifest.json")
        for item in manifest["artifacts"]:
            path = self.handoff_dir / item["path"]
            self.assertEqual(item["sha256"], _sha(path), path)

    def test_formal_nearest_rejects_unverified_or_retracted_work(self) -> None:
        mutated = deepcopy(self.review)
        formal_work = next(
            work for work in mutated["works"] if work["formal_nearest"]
        )
        formal_work["identity_status"] = "rejected"
        formal_work["publication_status_check"]["status"] = "retracted"

        schema = _load(
            ROOT / "schemas" / "group1_literature_review.schema.json"
        )
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        self.assertTrue(list(validator.iter_errors(mutated)))
        self.assertTrue(_review_status_errors(mutated))

    def test_ready_handoff_rejects_failed_gate(self) -> None:
        mutated = deepcopy(self.handoff)
        mutated["completed_gates"][0]["status"] = "failed"

        schema = _load(ROOT / "schemas" / "group1_handoff.schema.json")
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        self.assertTrue(list(validator.iter_errors(mutated)))
        self.assertTrue(_handoff_status_errors(mutated))


if __name__ == "__main__":
    unittest.main()
