from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any

from evaluate_qwen_vl_table_experiment import evaluate
from run_qwen_vl_table_experiment import (
    DEFAULT_ENDPOINT,
    DEFAULT_MODEL,
    call_qwen_vl,
)


METRIC_KEYS = (
    "field_accuracy",
    "field_precision",
    "numeric_accuracy",
    "significance_accuracy",
    "null_handling_accuracy",
)


def save_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def aggregate(rows: list[dict]) -> dict:
    successful = [row for row in rows if row["status"] == "success"]
    by_condition: dict[str, list[dict]] = {}
    for row in successful:
        by_condition.setdefault(row["condition"], []).append(row)

    def summarize(items: list[dict]) -> dict:
        if not items:
            return {"successful_runs": 0, "model_score_available": False}
        summaries = [item["evaluation_summary"] for item in items]
        result = {
            "successful_runs": len(items),
            "model_score_available": True,
            "strict_exact_match_rate": round(
                mean(float(summary["strict_exact_match"]) for summary in summaries), 4
            ),
        }
        for key in METRIC_KEYS:
            result[f"mean_{key}"] = round(mean(summary[key] for summary in summaries), 4)
        return result

    return {
        "attempted_runs": len(rows),
        "successful_runs": len(successful),
        "failed_runs": len(rows) - len(successful),
        "model_score_available": bool(successful),
        "overall": summarize(successful),
        "conditions": {
            condition: summarize(items) for condition, items in sorted(by_condition.items())
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the paired Qwen-VL table experiment")
    parser.add_argument("--full-page", required=True, type=Path)
    parser.add_argument("--crop", required=True, type=Path)
    parser.add_argument("--ground-truth", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--tolerance", type=float, default=0.0005)
    args = parser.parse_args()

    if args.repeats < 1:
        raise ValueError("--repeats must be positive")
    conditions = {
        "full_page_with_distractor_table": args.full_page.resolve(),
        "cropped_target_table": args.crop.resolve(),
    }
    for image_path in conditions.values():
        if not image_path.is_file():
            raise FileNotFoundError(image_path)
    expected = json.loads(args.ground_truth.read_text(encoding="utf-8"))
    args.out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    for condition, image_path in conditions.items():
        for repeat in range(1, args.repeats + 1):
            case_id = f"{condition}_r{repeat}"
            try:
                response, extraction = call_qwen_vl(
                    image_path,
                    endpoint=args.endpoint,
                    model=args.model,
                    timeout=args.timeout,
                )
                evaluation = evaluate(expected, extraction, args.tolerance)
                save_json(args.out_dir / f"response_{case_id}.json", response)
                save_json(args.out_dir / f"extraction_{case_id}.json", extraction)
                save_json(args.out_dir / f"evaluation_{case_id}.json", evaluation)
                rows.append({
                    "case_id": case_id,
                    "condition": condition,
                    "repeat": repeat,
                    "status": "success",
                    "model_returned": response["metadata"].get("model_returned"),
                    "request_id": response["metadata"].get("request_id"),
                    "elapsed_seconds": response["metadata"].get("elapsed_seconds"),
                    "evaluation_summary": evaluation["summary"],
                })
            except Exception as exc:  # Preserve an auditable failed-run record.
                rows.append({
                    "case_id": case_id,
                    "condition": condition,
                    "repeat": repeat,
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                })

    result = {
        "experiment_id": "qwen-vl-scientific-table-001",
        "model_requested": args.model,
        "endpoint": args.endpoint,
        "temperature": 0.0,
        "repeats_per_condition": args.repeats,
        "aggregate": aggregate(rows),
        "runs": rows,
    }
    save_json(args.out_dir / "batch_summary.json", result)
    print(json.dumps(result["aggregate"], ensure_ascii=False))
    return 0 if result["aggregate"]["model_score_available"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

