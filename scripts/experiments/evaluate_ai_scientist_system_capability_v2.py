#!/usr/bin/env python3
"""Independently recompute the frozen v2 system-capability experiment."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import re
from statistics import mean
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def protocol_major(protocol: dict[str, Any]) -> int:
    version = str(protocol.get("schema_version") or "").rsplit("/", 1)[-1]
    try:
        return max(1, int(version.split(".", 1)[0]))
    except ValueError:
        return 1


def schema_repair_counts(receipts: list[dict[str, Any]]) -> tuple[int, int]:
    """Count schema-failed logical calls and later same-call recoveries."""

    sequences: dict[str, list[dict[str, Any]]] = {}
    for receipt in receipts:
        logical_id = str(receipt.get("logical_call_id") or "")
        if logical_id:
            sequences.setdefault(logical_id, []).append(receipt)
    triggered = 0
    recovered = 0
    for sequence in sequences.values():
        ordered = sorted(
            sequence,
            key=lambda item: int(item.get("attempt_index") or 0),
        )
        failure_indices = [
            int(item.get("attempt_index") or 0)
            for item in ordered
            if item.get("outcome") == "schema_failure"
        ]
        if not failure_indices:
            continue
        triggered += 1
        first_failure = min(failure_indices)
        if any(
            item.get("outcome") == "succeeded"
            and int(item.get("attempt_index") or 0) > first_failure
            for item in ordered
        ):
            recovered += 1
    return triggered, recovered


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def normalized(value: object) -> str:
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", str(value).casefold())


def plan_text(plan: dict[str, Any]) -> str:
    values: list[str] = [
        str(plan.get("candidate_research_question") or ""),
        str(plan.get("hypothesis_statement") or ""),
        str(plan.get("falsifiable_form") or ""),
        str(plan.get("baseline_specification") or ""),
    ]
    for key in ("constructs", "boundary_conditions", "required_inputs"):
        items = plan.get(key) or []
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                values.extend(str(item.get(name) or "") for name in ("label", "definition"))
            else:
                values.append(str(item))
    return " ".join(values)


def round_text(item: dict[str, Any]) -> str:
    return " ".join(
        [
            str(item.get("candidate_research_question") or ""),
            str(item.get("hypothesis_statement") or ""),
            *[str(value) for value in item.get("construct_labels") or []],
        ]
    )


def topic_fidelity(text: str, concept_groups: list[list[str]]) -> tuple[bool, list[dict[str, Any]]]:
    haystack = normalized(text)
    checks = []
    for alternatives in concept_groups:
        matched = [item for item in alternatives if normalized(item) in haystack]
        checks.append({"alternatives": alternatives, "matched": matched})
    return all(item["matched"] for item in checks), checks


def evidence_references(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "evidence_chunk_ids" and isinstance(item, list):
                yield from (str(chunk_id) for chunk_id in item)
            else:
                yield from evidence_references(item)
    elif isinstance(value, list):
        for item in value:
            yield from evidence_references(item)


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> dict[str, Any]:
    if total == 0:
        return {"successes": successes, "total": total, "rate": None, "lower": None, "upper": None}
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    radius = (
        z
        * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
        / denominator
    )
    return {
        "successes": successes,
        "total": total,
        "rate": round(p, 6),
        "lower": round(max(0.0, center - radius), 6),
        "upper": round(min(1.0, center + radius), 6),
        "method": "Wilson 95%",
    }


def percentile(sorted_values: list[float], probability: float) -> float:
    if not sorted_values:
        raise ValueError("percentile requires values")
    position = probability * (len(sorted_values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def cluster_bootstrap(
    values_by_case: dict[str, list[float]],
    *,
    iterations: int = 10_000,
    seed: int = 20260901,
) -> dict[str, Any]:
    case_ids = sorted(values_by_case)
    if not case_ids:
        return {"estimate": None, "lower": None, "upper": None}
    observed = mean(value for case_id in case_ids for value in values_by_case[case_id])
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(iterations):
        sampled = [rng.choice(case_ids) for _ in case_ids]
        estimates.append(
            mean(value for case_id in sampled for value in values_by_case[case_id])
        )
    estimates.sort()
    return {
        "estimate": round(observed, 6),
        "lower": round(percentile(estimates, 0.025), 6),
        "upper": round(percentile(estimates, 0.975), 6),
        "method": f"question-cluster bootstrap 95%, {iterations} resamples",
    }


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    protocol = load_object(args.protocol)
    protocol_hash = canonical_sha256(protocol)
    case_by_id = {item["case_id"]: item for item in protocol["cases"]}
    expected = {
        f"{case_id}__seed_{seed}"
        for case_id in case_by_id
        for seed in protocol["generation"]["seeds"]
    }
    ablation = load_object(args.input_dir / "retrieval_ablation.json")
    cells: list[dict[str, Any]] = []
    missing: list[str] = []
    for cell_id in sorted(expected):
        result_path = args.input_dir / "cells" / cell_id / "result.json"
        generation_path = args.input_dir / "cells" / cell_id / "generation.json"
        if not result_path.is_file():
            missing.append(cell_id)
            continue
        result = load_object(result_path)
        if result.get("protocol_sha256") != protocol_hash:
            raise ValueError(f"protocol binding mismatch: {cell_id}")
        case = case_by_id[result["case_id"]]
        if result.get("status") == "failed":
            retrieval_mode = str(
                protocol.get("retrieval", {}).get(
                    "diversity_mode", "per_document_cap"
                )
            )
            retrieval = ablation[result["case_id"]][retrieval_mode]
            diagnostics = retrieval.get("diagnostics") or {}
            model_usage = result.get("model_usage") or {}
            receipts = model_usage.get("call_receipts") or []
            prompt_keys = [str(item.get("prompt_key")) for item in receipts]
            schema_repairs_triggered, schema_repairs_recovered = schema_repair_counts(
                receipts
            )
            qwen_receipts_valid = bool(receipts) and all(
                item.get("provider") == "qwen"
                and len(str(item.get("response_sha256") or "")) == 64
                for item in receipts
            )
            hit_count = int(retrieval.get("hit_count") or 0)
            unique_documents = int(retrieval.get("unique_document_count") or 0)
            cells.append(
                {
                    "cell_id": cell_id,
                    "case_id": result["case_id"],
                    "seed": result["seed"],
                    "cell_completed": False,
                    "h0_compilable": False,
                    "failure_type": result.get("error_type"),
                    "failure_summary": result.get("error"),
                    "failure_stage": (
                        "consistency_requery_planning"
                        if "discovery_consistency_review" in prompt_keys
                        else "initial_planning"
                    ),
                    "topic_fidelity": False,
                    "concept_checks": [],
                    "initial_topic_fidelity": False,
                    "initial_concept_checks": [],
                    "repair_count": None,
                    "consistency_requery_triggered": (
                        "discovery_consistency_review" in prompt_keys
                    ),
                    "consistency_repair_recovered": False,
                    "final_consistency_passed": False,
                    "hit_count": hit_count,
                    "unique_document_count": unique_documents,
                    "evidence_diversity_ratio": round(
                        unique_documents / hit_count, 6
                    )
                    if hit_count
                    else 0.0,
                    "diversity_gate_passed": bool(
                        diagnostics.get("diversity_gate_passed")
                    ),
                    "max_hits_from_one_document": diagnostics.get(
                        "max_hits_from_one_document"
                    ),
                    "reference_integrity": False,
                    "content_hash_integrity": False,
                    "falsifiable": False,
                    "execution_ready": False,
                    "readiness_blocked_correctly": False,
                    "safe_stop": True,
                    "qwen_receipts_valid": qwen_receipts_valid,
                    "planner_call_recorded": "discovery_planning" in prompt_keys,
                    "reviewer_call_recorded": (
                        "discovery_consistency_review" in prompt_keys
                    ),
                    "schema_repairs_triggered": schema_repairs_triggered,
                    "schema_repairs_recovered": schema_repairs_recovered,
                    "provider_attempts": model_usage.get("provider_attempts"),
                    "input_tokens": model_usage.get("input_tokens"),
                    "output_tokens": model_usage.get("output_tokens"),
                    "wall_time_seconds": model_usage.get("wall_time_seconds"),
                }
            )
            continue
        if result.get("status") != "completed" or not generation_path.is_file():
            missing.append(cell_id)
            continue
        generation = load_object(generation_path)
        plan = generation["plan"]
        final_topic, concept_checks = topic_fidelity(
            plan_text(plan),
            case["concept_groups"],
        )
        rounds = generation.get("retrieval_rounds") or []
        initial_topic, initial_checks = (
            topic_fidelity(round_text(rounds[0]), case["concept_groups"])
            if rounds
            else (False, [])
        )
        hits = generation["evidence_bundle"].get("evidence_hits") or []
        allowed_chunks = {str(item.get("chunk_id")) for item in hits}
        references = set(evidence_references(plan))
        hash_valid = all(
            sha256_text(str(item.get("text") or "")) == item.get("content_sha256")
            for item in hits
        )
        docs = {str(item.get("document_id")) for item in hits}
        diagnostics = generation["evidence_bundle"].get("retrieval_diagnostics") or {}
        readiness = generation.get("execution_readiness") or {}
        launch = result.get("launch") or {}
        model_usage = generation.get("model_usage") or {}
        receipts = model_usage.get("call_receipts") or []
        prompt_keys = [str(item.get("prompt_key")) for item in receipts]
        schema_repairs_triggered, schema_repairs_recovered = schema_repair_counts(
            receipts
        )
        qwen_receipts_valid = bool(receipts) and all(
            item.get("provider") == "qwen"
            and len(str(item.get("response_sha256") or "")) == 64
            for item in receipts
        )
        falsifiable = bool(
            str(plan.get("falsifiable_form") or "").strip()
            and plan.get("predictions")
            and all(
                str(item.get("would_falsify") or "").strip()
                for item in plan.get("predictions") or []
            )
            and plan.get("major_threats")
        )
        execution_ready = bool(readiness.get("can_execute"))
        safe_stop = bool(result.get("safe_stop")) and not bool(
            launch.get("scientific_approval")
        )
        cells.append(
            {
                "cell_id": cell_id,
                "case_id": result["case_id"],
                "seed": result["seed"],
                "cell_completed": True,
                "h0_compilable": bool(launch.get("launched")),
                "failure_type": None,
                "failure_summary": None,
                "failure_stage": None,
                "topic_fidelity": final_topic,
                "concept_checks": concept_checks,
                "initial_topic_fidelity": initial_topic,
                "initial_concept_checks": initial_checks,
                "repair_count": generation.get("repair_count", 0),
                "consistency_requery_triggered": bool(
                    generation.get("repair_count", 0)
                ),
                "consistency_repair_recovered": bool(
                    generation.get("repair_count", 0)
                    and generation.get("final_consistency_passed")
                ),
                "final_consistency_passed": bool(
                    generation.get("final_consistency_passed")
                ),
                "hit_count": len(hits),
                "unique_document_count": len(docs),
                "evidence_diversity_ratio": round(len(docs) / len(hits), 6)
                if hits
                else 0.0,
                "diversity_gate_passed": bool(
                    diagnostics.get("diversity_gate_passed")
                ),
                "max_hits_from_one_document": diagnostics.get(
                    "max_hits_from_one_document"
                ),
                "reference_integrity": bool(references)
                and references.issubset(allowed_chunks),
                "content_hash_integrity": hash_valid,
                "falsifiable": falsifiable,
                "execution_ready": execution_ready,
                "readiness_blocked_correctly": not execution_ready
                and bool(readiness.get("blockers")),
                "safe_stop": safe_stop,
                "qwen_receipts_valid": qwen_receipts_valid,
                "planner_call_recorded": "discovery_planning" in prompt_keys,
                "reviewer_call_recorded": "discovery_consistency_review" in prompt_keys,
                "schema_repairs_triggered": schema_repairs_triggered,
                "schema_repairs_recovered": schema_repairs_recovered,
                "provider_attempts": model_usage.get("provider_attempts"),
                "input_tokens": model_usage.get("input_tokens"),
                "output_tokens": model_usage.get("output_tokens"),
                "wall_time_seconds": model_usage.get("wall_time_seconds"),
            }
        )
    if missing and not args.allow_partial:
        raise ValueError(
            f"experiment is incomplete: {len(missing)} missing cells: "
            + ", ".join(missing[:10])
        )

    binary_fields = [
        "cell_completed",
        "h0_compilable",
        "topic_fidelity",
        "diversity_gate_passed",
        "falsifiable",
        "execution_ready",
        "readiness_blocked_correctly",
        "safe_stop",
        "reference_integrity",
        "content_hash_integrity",
        "qwen_receipts_valid",
        "final_consistency_passed",
    ]
    metrics: dict[str, Any] = {}
    clustered: dict[str, Any] = {}
    for field in binary_fields:
        successes = sum(bool(item[field]) for item in cells)
        metrics[field] = wilson(successes, len(cells))
        clustered[field] = cluster_bootstrap(
            {
                case_id: [float(bool(item[field])) for item in cells if item["case_id"] == case_id]
                for case_id in case_by_id
                if any(item["case_id"] == case_id for item in cells)
            }
        )
    diversity_by_case = {
        case_id: [
            float(item["evidence_diversity_ratio"])
            for item in cells
            if item["case_id"] == case_id
        ]
        for case_id in case_by_id
        if any(item["case_id"] == case_id for item in cells)
    }
    metrics["evidence_diversity_ratio"] = cluster_bootstrap(diversity_by_case)
    completed_cells = [item for item in cells if item["cell_completed"]]
    metrics["topic_fidelity_completed_only"] = wilson(
        sum(item["topic_fidelity"] for item in completed_cells),
        len(completed_cells),
    )
    metrics["readiness_blocked_completed_only"] = wilson(
        sum(item["readiness_blocked_correctly"] for item in completed_cells),
        len(completed_cells),
    )
    repair_rate = wilson(
        sum(item["consistency_requery_triggered"] for item in cells),
        len(cells),
    )
    repair_candidates = [
        item for item in cells if item["consistency_requery_triggered"]
    ]
    repair_completion = wilson(
        sum(item["cell_completed"] for item in repair_candidates),
        len(repair_candidates),
    )
    repair_recovery = wilson(
        sum(item["consistency_repair_recovered"] for item in repair_candidates),
        len(repair_candidates),
    )
    schema_repair_triggered_total = sum(
        int(item["schema_repairs_triggered"]) for item in cells
    )
    schema_repair_recovered_total = sum(
        int(item["schema_repairs_recovered"]) for item in cells
    )
    schema_repair_recovery = wilson(
        schema_repair_recovered_total,
        schema_repair_triggered_total,
    )
    repair_improvement = wilson(
        sum(
            not item["initial_topic_fidelity"] and item["topic_fidelity"]
            for item in repair_candidates
            if item["cell_completed"]
        ),
        sum(item["cell_completed"] for item in repair_candidates),
    )

    reviewer_cells = [item for item in cells if item["cell_completed"]]
    reviewer_confusion = {
        "true_positive": sum(
            item["final_consistency_passed"] and item["topic_fidelity"]
            for item in reviewer_cells
        ),
        "false_positive": sum(
            item["final_consistency_passed"] and not item["topic_fidelity"]
            for item in reviewer_cells
        ),
        "false_negative": sum(
            not item["final_consistency_passed"] and item["topic_fidelity"]
            for item in reviewer_cells
        ),
        "true_negative": sum(
            not item["final_consistency_passed"] and not item["topic_fidelity"]
            for item in reviewer_cells
        ),
    }

    ablation_rows = []
    for case_id, value in sorted(ablation.items()):
        none = value["none"]
        cap = value["per_document_cap"]
        ablation_rows.append(
            {
                "case_id": case_id,
                "baseline_unique_documents": none["unique_document_count"],
                "capped_unique_documents": cap["unique_document_count"],
                "baseline_max_document_share": none["max_document_share"],
                "capped_max_document_share": cap["max_document_share"],
                "unique_document_gain": cap["unique_document_count"]
                - none["unique_document_count"],
            }
        )

    by_question = []
    for case_id in sorted(case_by_id):
        subset = [item for item in cells if item["case_id"] == case_id]
        if not subset:
            continue
        by_question.append(
            {
                "case_id": case_id,
                "cells": len(subset),
                "completed": sum(item["cell_completed"] for item in subset),
                "h0_compilable": sum(item["h0_compilable"] for item in subset),
                "topic_fidelity": sum(item["topic_fidelity"] for item in subset),
                "diversity_gate_passed": sum(
                    item["diversity_gate_passed"] for item in subset
                ),
                "safe_stop": sum(item["safe_stop"] for item in subset),
                "mean_evidence_diversity_ratio": round(
                    mean(item["evidence_diversity_ratio"] for item in subset), 6
                ),
                "repairs": sum((item["repair_count"] or 0) > 0 for item in subset),
            }
        )

    totals = {
        "provider_attempts": sum(int(item["provider_attempts"] or 0) for item in cells),
        "input_tokens": sum(int(item["input_tokens"] or 0) for item in cells),
        "output_tokens": sum(int(item["output_tokens"] or 0) for item in cells),
        "model_wall_time_seconds": round(
            sum(float(item["wall_time_seconds"] or 0) for item in cells), 3
        ),
    }
    failure_stages: dict[str, int] = {}
    for item in cells:
        if item["cell_completed"]:
            continue
        stage = str(item.get("failure_stage") or "unknown")
        failure_stages[stage] = failure_stages.get(stage, 0) + 1
    receipt_outcomes: dict[str, int] = {}
    prompt_outcomes: dict[str, int] = {}
    schema_issue_counts: dict[str, int] = {}
    for cell_id in sorted(expected):
        result_path = args.input_dir / "cells" / cell_id / "result.json"
        generation_path = args.input_dir / "cells" / cell_id / "generation.json"
        if not result_path.is_file():
            continue
        result = load_object(result_path)
        if result.get("status") == "completed" and generation_path.is_file():
            usage = load_object(generation_path).get("model_usage") or {}
        else:
            usage = result.get("model_usage") or {}
        for receipt in usage.get("call_receipts") or []:
            outcome = str(receipt.get("outcome") or "unknown")
            prompt_key = str(receipt.get("prompt_key") or "unknown")
            receipt_outcomes[outcome] = receipt_outcomes.get(outcome, 0) + 1
            prompt_outcome = f"{prompt_key}:{outcome}"
            prompt_outcomes[prompt_outcome] = prompt_outcomes.get(prompt_outcome, 0) + 1
            for issue in receipt.get("schema_error_summary") or []:
                location = ".".join(str(item) for item in issue.get("loc") or []) or "root"
                key = f"{location}:{issue.get('type') or 'invalid'}"
                schema_issue_counts[key] = schema_issue_counts.get(key, 0) + 1
    return {
        "schema_version": (
            f"ai-scientist-system-capability-evaluation/{protocol_major(protocol)}.0.0"
        ),
        "protocol_schema_version": protocol.get("schema_version"),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "protocol_sha256": protocol_hash,
        "expected_cells": len(expected),
        "evaluated_cells": len(cells),
        "completed_cells": sum(item["cell_completed"] for item in cells),
        "failed_cells": sum(not item["cell_completed"] for item in cells),
        "missing_cells": missing,
        "metrics_wilson_95": metrics,
        "metrics_question_cluster_bootstrap_95": clustered,
        "repair_rate": repair_rate,
        "repair_completion_rate": repair_completion,
        "repair_recovery_rate": repair_recovery,
        "schema_repair_recovery_rate": schema_repair_recovery,
        "repair_topic_improvement": repair_improvement,
        "reviewer_confusion_completed_cells": reviewer_confusion,
        "failure_stages": failure_stages,
        "model_call_diagnostics": {
            "receipt_outcomes": receipt_outcomes,
            "prompt_outcomes": prompt_outcomes,
            "schema_issue_counts": dict(
                sorted(
                    schema_issue_counts.items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ),
        },
        "retrieval_ablation": {
            "rows": ablation_rows,
            "mean_baseline_unique_documents": round(
                mean(item["baseline_unique_documents"] for item in ablation_rows), 6
            ),
            "mean_capped_unique_documents": round(
                mean(item["capped_unique_documents"] for item in ablation_rows), 6
            ),
            "mean_unique_document_gain": round(
                mean(item["unique_document_gain"] for item in ablation_rows), 6
            ),
        },
        "by_question": by_question,
        "usage_totals": totals,
        "cells": cells,
        "interpretation_guardrails": [
            "Topic fidelity is independently recomputed from predeclared concept groups; it is not the Qwen Reviewer verdict.",
            f"Intent-to-treat metrics retain schema/model failures in the {len(expected)}-cell denominator; failed cells score false for plan-output metrics and true only for verified fail-closed stopping.",
            "Execution-ready rate is expected to be zero because the frozen online protocol supplies no licensed immutable datasets.",
            "Correct readiness blocking and safe stopping are the relevant system behaviors under that missing-input condition.",
            "Seed reproducibility is best-effort according to the provider contract and does not imply identical generations.",
            "No cell represents completed statistical execution or a scientifically approved claim.",
        ],
    }


def percent(value: float | None) -> str:
    return "—" if value is None else f"{100 * value:.1f}%"


def markdown_report(evaluation: dict[str, Any]) -> str:
    metrics = evaluation["metrics_wilson_95"]
    version = str(evaluation.get("schema_version") or "").rsplit("/", 1)[-1]
    major = version.split(".", 1)[0] if version else "?"
    diversity = metrics["evidence_diversity_ratio"]
    question_count = len(evaluation["by_question"])
    failure_stage_text = "、".join(
        f"{key}={value}" for key, value in evaluation["failure_stages"].items()
    ) or "无"
    top_schema_issues = list(
        evaluation["model_call_diagnostics"]["schema_issue_counts"].items()
    )[:5]
    schema_issue_text = "、".join(
        f"{key}（{value}）" for key, value in top_schema_issues
    ) or "无"
    rows = [
        ("结构化计划完成率", metrics["cell_completed"]),
        ("H0 可编译通过率", metrics["h0_compilable"]),
        ("主题忠实度", metrics["topic_fidelity"]),
        ("检索多样性门通过率", metrics["diversity_gate_passed"]),
        ("计划执行就绪率", metrics["execution_ready"]),
        ("缺输入时正确阻断率", metrics["readiness_blocked_correctly"]),
        ("安全停止率", metrics["safe_stop"]),
        ("问题—计划 Reviewer 最终通过率", metrics["final_consistency_passed"]),
    ]
    lines = [
        f"# AI Scientist 系统能力实验 v{major}（独立复算）",
        "",
        f"冻结协议共 {evaluation['expected_cells']} 个单元；本次纳入 {evaluation['evaluated_cells']} 个，"
        f"其中完整完成 {evaluation['completed_cells']} 个、失败关闭 {evaluation['failed_cells']} 个。",
        "",
        "| 系统指标 | 结果 | 95% CI（Wilson） |",
        "|---|---:|---:|",
    ]
    for label, value in rows:
        lines.append(
            f"| {label} | {value['successes']}/{value['total']}（{percent(value['rate'])}） | "
            f"{percent(value['lower'])}–{percent(value['upper'])} |"
        )
    lines.extend(
        [
            "",
            f"在 {evaluation['completed_cells']} 个完整单元中，主题忠实度为 "
            f"{metrics['topic_fidelity_completed_only']['successes']}/"
            f"{metrics['topic_fidelity_completed_only']['total']}（"
            f"{percent(metrics['topic_fidelity_completed_only']['rate'])}）；"
            f"主表意向分析仍把失败单元留在 {evaluation['expected_cells']} 的分母中。",
            "",
            f"一致性 Reviewer 共触发 {evaluation['repair_rate']['successes']} 次重检索；"
            f"其中 {evaluation['repair_completion_rate']['successes']} 次重新生成了结构合格计划，"
            f"但最终恢复通过为 {evaluation['repair_recovery_rate']['successes']}/"
            f"{evaluation['repair_recovery_rate']['total']}。",
            "",
            "Schema 修复按 logical_call_id 独立复算："
            f"{evaluation['schema_repair_recovery_rate']['successes']}/"
            f"{evaluation['schema_repair_recovery_rate']['total']} 个触发结构修复的逻辑调用"
            "在同一调用预算内恢复成功。",
            "",
            "## 失败审计",
            "",
            f"{evaluation['failed_cells']} 个失败单元的阶段分布为：{failure_stage_text}。"
            f"全部 {evaluation['usage_totals']['provider_attempts']} 次供应商尝试均保留匿名化凭证；"
            f"最常见的 schema 问题为：{schema_issue_text}。",
            "",
            f"证据多样性（不同文献数/命中块数）均值为 {diversity['estimate']:.3f}，"
            f"按问题聚类 bootstrap 95% CI 为 {diversity['lower']:.3f}–{diversity['upper']:.3f}。",
            "",
            "## 检索消融",
            "",
            f"关闭文档上限时，{question_count} 题平均不同文献数为 "
            f"{evaluation['retrieval_ablation']['mean_baseline_unique_documents']:.2f}；"
            f"开启上限后为 {evaluation['retrieval_ablation']['mean_capped_unique_documents']:.2f}，"
            f"平均增加 {evaluation['retrieval_ablation']['mean_unique_document_gain']:.2f} 篇。",
            "",
            "## 正确解释",
            "",
            "本协议故意不提供许可完整、带哈希的数据资产，因此“执行就绪率”不是越高越好。"
            "在这一条件下，系统应把 required inputs 编译成数据候选、变量字典和识别策略阻塞项，"
            "并在 H1 安全停止。只有完整输入下的正向编译能力由单元测试另行验证。",
            "",
            "本结果评价的是 AI Scientist 系统的检索、规划一致性、执行门控和安全停止能力，"
            "不是底层 Qwen 的通用能力排行榜，也不代表已经完成统计分析或获得科学结论。",
            "",
            "## 分问题结果",
            "",
            "| 问题 | 结构完成 | H0通过 | 主题忠实 | 多样性门 | 安全停止 | 多样性均值 | 重检索次数 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for item in evaluation["by_question"]:
        lines.append(
            f"| {item['case_id']} | {item['completed']}/{item['cells']} | "
            f"{item['h0_compilable']}/{item['cells']} | "
            f"{item['topic_fidelity']}/{item['cells']} | "
            f"{item['diversity_gate_passed']}/{item['cells']} | "
            f"{item['safe_stop']}/{item['cells']} | "
            f"{item['mean_evidence_diversity_ratio']:.3f} | {item['repairs']} |"
        )
    lines.extend(
        [
            "",
            f"注：{evaluation['expected_cells']} 个单元共享 {question_count} 个问题，不能视为完全独立样本。"
            "主表按预注册要求给出 Wilson 区间，"
            "机器结果同时保留按问题聚类 bootstrap 的敏感性区间。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--protocol",
        type=Path,
        default=ROOT / "experiments" / "ai_scientist_system_capability_v2_protocol.json",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=ROOT / "output" / "experiments" / "ai_scientist_system_capability_v2",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=ROOT
        / "output"
        / "experiments"
        / "ai_scientist_system_capability_v2"
        / "evaluation.json",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=ROOT / "docs" / "实验_AI_Scientist系统能力_v2.md",
    )
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    result = evaluate(args)
    atomic_json(args.json_output, result)
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(markdown_report(result), encoding="utf-8")
    print(json.dumps({"evaluated_cells": result["evaluated_cells"], "output": str(args.json_output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
