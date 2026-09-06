from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
from typing import Any


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else key
            result.update(flatten(item, path))
        return result
    return {prefix: value}


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("−", "-")).strip().lower()


def values_match(expected: Any, observed: Any, tolerance: float) -> bool:
    if expected is None or isinstance(expected, bool):
        return expected is observed
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        if not isinstance(observed, (int, float)) or isinstance(observed, bool):
            return False
        return math.isclose(float(expected), float(observed), abs_tol=tolerance, rel_tol=0.0)
    if isinstance(expected, str):
        return isinstance(observed, str) and normalize_text(expected) == normalize_text(observed)
    return expected == observed


def evaluate(expected: dict, observed: dict, tolerance: float) -> dict:
    expected_flat = flatten(expected)
    observed_flat = flatten(observed)
    rows = []
    correct = 0
    numeric_total = 0
    numeric_correct = 0
    significance_total = 0
    significance_correct = 0
    null_total = 0
    null_correct = 0

    for path, expected_value in expected_flat.items():
        observed_value = observed_flat.get(path, "__MISSING__")
        matched = values_match(expected_value, observed_value, tolerance)
        correct += int(matched)
        if isinstance(expected_value, (int, float)) and not isinstance(expected_value, bool):
            numeric_total += 1
            numeric_correct += int(matched)
        if path.endswith(".significance"):
            significance_total += 1
            significance_correct += int(matched)
        if expected_value is None:
            null_total += 1
            null_correct += int(matched)
        rows.append({
            "path": path,
            "expected": expected_value,
            "observed": None if observed_value == "__MISSING__" else observed_value,
            "missing": observed_value == "__MISSING__",
            "correct": matched,
        })

    total = len(expected_flat)
    unexpected_paths = sorted(set(observed_flat) - set(expected_flat))
    missing_fields = sum(1 for row in rows if row["missing"])
    observed_total = len(observed_flat)
    return {
        "summary": {
            "correct_fields": correct,
            "total_fields": total,
            "field_accuracy": round(correct / total, 4) if total else 0.0,
            "field_precision": round(correct / observed_total, 4) if observed_total else 0.0,
            "numeric_accuracy": round(numeric_correct / numeric_total, 4) if numeric_total else 0.0,
            "significance_accuracy": round(significance_correct / significance_total, 4) if significance_total else 0.0,
            "null_handling_accuracy": round(null_correct / null_total, 4) if null_total else 0.0,
            "missing_field_count": missing_fields,
            "unexpected_field_count": len(unexpected_paths),
            "strict_exact_match": correct == total and not unexpected_paths,
            "numeric_tolerance": tolerance,
        },
        "errors": [row for row in rows if not row["correct"]],
        "unexpected_paths": unexpected_paths,
        "fields": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Qwen-VL table extraction")
    parser.add_argument("--ground-truth", required=True, type=Path)
    parser.add_argument("--extraction", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--tolerance", type=float, default=0.0005)
    args = parser.parse_args()

    expected = json.loads(args.ground_truth.read_text(encoding="utf-8"))
    observed = json.loads(args.extraction.read_text(encoding="utf-8"))
    report = evaluate(expected, observed, args.tolerance)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
