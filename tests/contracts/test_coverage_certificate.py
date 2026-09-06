from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "coverage_certificate.schema.json"
SAMPLE_PATH = ROOT / "samples" / "coverage_certificate.seed.json"
VALIDATOR_PATH = ROOT / "src" / "coverage" / "validator.py"
CLI_PATH = ROOT / "src" / "coverage" / "validate_coverage_certificate.py"
INVALID_MUTATION_PATH = (
    ROOT / "tests" / "contracts" / "fixtures" / "coverage_certificate.invalid-field-count.json"
)

spec = importlib.util.spec_from_file_location("coverage_certificate_validator", VALIDATOR_PATH)
if spec is None or spec.loader is None:  # pragma: no cover - import machinery guard
    raise RuntimeError(f"Cannot load validator from {VALIDATOR_PATH}")
validator_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator_module)
validate_certificate = validator_module.validate_certificate

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:  # Semantic/CLI checks deliberately do not require jsonschema.
    Draft202012Validator = None
    FormatChecker = None


def apply_mutation(document: dict, mutation: dict) -> None:
    target = document
    for component in mutation["path"][:-1]:
        target = target[component] if isinstance(component, str) else target[component]
    target[mutation["path"][-1]] = mutation["value"]


class CoverageCertificateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.sample = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
        cls.invalid_mutation = json.loads(INVALID_MUTATION_PATH.read_text(encoding="utf-8"))

    def test_schema_and_seed_are_json(self) -> None:
        self.assertEqual("1.0.0", self.schema["properties"]["schema_version"]["const"])
        self.assertEqual("1.0.0", self.sample["schema_version"])

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is not installed")
    def test_seed_matches_json_schema(self) -> None:
        schema_validator = Draft202012Validator(self.schema, format_checker=FormatChecker())
        errors = sorted(
            schema_validator.iter_errors(self.sample), key=lambda item: list(item.path)
        )
        self.assertEqual([], [error.message for error in errors])

    def test_seed_passes_semantic_validator(self) -> None:
        self.assertEqual([], validate_certificate(self.sample))

    def test_invalid_field_count_fixture_is_detected(self) -> None:
        broken = copy.deepcopy(self.sample)
        apply_mutation(broken, self.invalid_mutation)
        errors = validate_certificate(broken)
        self.assertTrue(
            any(self.invalid_mutation["expected_error_substring"] in error for error in errors),
            errors,
        )

    def test_gap_partition_overlap_is_detected(self) -> None:
        broken = copy.deepcopy(self.sample)
        broken["claim_gate"]["allowed_gap_types"].append("data")
        errors = validate_certificate(broken)
        self.assertTrue(any("partitions overlap" in error for error in errors), errors)

    def test_blocking_gate_and_claim_status_mismatch_is_detected(self) -> None:
        broken = copy.deepcopy(self.sample)
        broken["gates"][0]["status"] = "failed"
        errors = validate_certificate(broken)
        self.assertTrue(any("non-passing blocking gate" in error for error in errors), errors)

    def test_retrieval_arithmetic_corruption_is_detected(self) -> None:
        broken = copy.deepcopy(self.sample)
        broken["coverage"]["retrieval_saturation"]["rounds"][2][
            "cumulative_unique_document_count"
        ] += 1
        errors = validate_certificate(broken)
        self.assertTrue(any("cumulative count" in error for error in errors), errors)

    def test_cli_accepts_seed_with_no_third_party_dependency(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(CLI_PATH), "--json", str(SAMPLE_PATH)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(0, completed.returncode, completed.stderr or completed.stdout)
        result = json.loads(completed.stdout)
        self.assertTrue(result[0]["valid"])
        self.assertEqual([], result[0]["errors"])

    def test_cli_rejects_invalid_certificate(self) -> None:
        broken = copy.deepcopy(self.sample)
        apply_mutation(broken, self.invalid_mutation)
        completed = subprocess.run(
            [sys.executable, str(CLI_PATH), "-"],
            cwd=ROOT,
            check=False,
            input=json.dumps(broken, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(1, completed.returncode, completed.stderr or completed.stdout)
        self.assertIn(self.invalid_mutation["expected_error_substring"], completed.stdout)


if __name__ == "__main__":
    unittest.main()
