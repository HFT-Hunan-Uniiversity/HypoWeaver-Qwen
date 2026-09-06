#!/usr/bin/env python3
"""Run the focused tests that prove the component switches are real."""

from __future__ import annotations

from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
OUTPUT = (
    ROOT
    / "output"
    / "experiments"
    / "ai_scientist_component_ablation_20260905"
    / "implementation_verification.json"
)

TESTS = {
    "审阅反馈回写默认开启": (
        "test_discovery_planner.DiscoveryPlannerTests."
        "test_failed_consistency_review_triggers_one_retrieval_repair"
    ),
    "审阅反馈回写可以单独关闭": (
        "test_discovery_planner.DiscoveryPlannerTests."
        "test_consistency_repair_can_be_disabled_for_component_ablation"
    ),
    "结构纠错默认保持原行为": (
        "test_model_call_batching.QwenGatewayReceiptTests."
        "test_schema_repair_uses_one_logical_call_and_detailed_receipts"
    ),
    "结构纠错可以单独关闭": (
        "test_model_call_batching.QwenGatewayReceiptTests."
        "test_schema_repair_can_be_disabled_without_changing_default"
    ),
}


def main() -> int:
    sys.path.insert(0, str(BACKEND / "src"))
    sys.path.insert(0, str(BACKEND / "tests"))
    suite = unittest.defaultTestLoader.loadTestsFromNames(list(TESTS.values()))
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    failed_ids = {
        test.id() for test, _ in [*result.failures, *result.errors]
    }
    rows = []
    for public_label, test_id in TESTS.items():
        rows.append(
            {
                "verification": public_label,
                "passed": test_id not in failed_ids,
                "internal_test_id": test_id,
            }
        )
    payload = {
        "schema_version": "component-ablation-implementation-verification/1.0.0",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "passed": result.wasSuccessful(),
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "checks": rows,
        "runner_output": stream.getvalue(),
        "scope": (
            "Focused unit verification for the schema-repair and reviewer-feedback switches; "
            "the source-diversification switch was pre-existing and is audited in the frozen protocol diff."
        ),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": payload["passed"], "tests_run": payload["tests_run"], "output": str(OUTPUT)}, ensure_ascii=False))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
