#!/usr/bin/env python3
"""Recompute the AI Scientist system-capability experiment from sealed artifacts.

The evaluator intentionally separates structural workflow reliability, semantic
task fidelity, scientific execution, evidence governance, and the Qwen-VL
component ablation. It does not emit a single blended score.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def evaluate_online_discovery(root: Path) -> dict[str, Any]:
    exp = root / "output" / "experiments" / "ai_scientist_system_capability_v1"
    case_specs = [
        ("case01_innovation", exp / "case01_innovation"),
        ("case02_greenwashing_conflict", exp / "case02_greenwashing_conflict"),
    ]
    semantic = load_json(exp / "semantic_adjudication.json")
    pre_fix = load_json(exp / "pre_fix_observations.json")
    pre_by_id = {item["case_id"]: item for item in pre_fix["cases"]}

    cases: list[dict[str, Any]] = []
    total_referenced = 0
    total_hits = 0
    total_input_tokens = 0
    total_output_tokens = 0
    total_wall_time = 0.0
    global_referenced_chunks: set[str] = set()

    for case_id, case_dir in case_specs:
        generation_path = case_dir / "qwen_generation.json"
        receipt_path = case_dir / "postfix_e2e_receipt.json"
        full_output_path = case_dir / "postfix_full_output.json"
        generation = load_json(generation_path)
        receipt = load_json(receipt_path)
        require(full_output_path.is_file(), f"missing post-fix output for {case_id}")

        generation_hash = sha256_file(generation_path)
        pre = pre_by_id[case_id]
        require(
            generation_hash == pre["qwen_generation_sha256"],
            f"pre/post generation binding mismatch for {case_id}",
        )
        adjudication = semantic["cases"][case_id]
        require(
            generation_hash == adjudication["qwen_generation_sha256"],
            f"semantic adjudication binding mismatch for {case_id}",
        )

        search = receipt["search"]
        health = receipt["knowledge_health"]
        launch = receipt["technical_launch"]
        usage = receipt["qwen_generation"]["model_usage"]
        plan = generation["plan"]
        call_receipts = usage["call_receipts"]
        unique_retrieved_documents = len(
            {item["document_id"] for item in search.get("top_hits", [])}
        )
        plan_referenced_chunks: set[str] = set()
        for collection_name in (
            "findings",
            "constructs",
            "mechanisms",
            "datasets",
            "methods",
            "models",
            "identification_strategies",
            "mechanism_chain",
        ):
            for item in plan.get(collection_name, []):
                plan_referenced_chunks.update(item.get("evidence_chunk_ids", []))
        require(
            len(plan_referenced_chunks) == search["referenced_chunk_count"],
            f"receipt reference count mismatch for {case_id}",
        )
        global_referenced_chunks.update(plan_referenced_chunks)

        checks = {
            "workflow_health_ok": receipt["workflow_health"]["status"] == "ok",
            "corpus_snapshot_bound": health["corpus_snapshot_id"]
            == search["corpus_snapshot_id"],
            "evidence_available": search["evidence_hit_count"] > 0,
            "all_hits_fulltext": search["all_hits_fulltext"] is True,
            "content_hashes_verified": search["all_content_hashes_verified"] is True,
            "all_plan_references_inside_bundle": search[
                "all_plan_references_inside_bundle"
            ]
            is True,
            "qwen_provider_call_succeeded": usage["provider_attempts"] >= 1
            and all(item["outcome"] == "succeeded" for item in call_receipts),
            "structured_plan_generated": generation["plan"]["schema_version"]
            == "discovery-plan/1.0.0",
            "postfix_compiler_succeeded": launch["gap_cards"] == 1
            and launch["hypothesis_cards"] == 1,
            "stopped_at_h1": launch["current_gate"] == "H1"
            and launch["run_status"] == "waiting_human",
            "missing_inputs_block_execution": launch["intake_can_execute"] is False
            and len(launch["intake_blockers"]) > 0,
            "no_unauthorized_scientific_approval": launch["scientific_approval"]
            is False,
        }
        require(all(checks.values()), f"post-fix structural check failed: {case_id}")

        predictions = plan.get("predictions", [])
        falsifiable = bool(plan.get("falsifiable_form")) and bool(predictions) and all(
            item.get("observable_pattern") and item.get("would_falsify")
            for item in predictions
        )
        dataset_count = len(plan.get("datasets", []))
        method_count = len(plan.get("methods", []))
        identification_count = len(plan.get("identification_strategies", []))
        execution_ready = (
            dataset_count > 0
            and (method_count > 0 or identification_count > 0)
            and launch["intake_can_execute"] is True
        )

        total_referenced += int(search["referenced_chunk_count"])
        total_hits += int(search["evidence_hit_count"])
        total_input_tokens += int(usage["input_tokens"])
        total_output_tokens += int(usage["output_tokens"])
        total_wall_time += float(usage["wall_time_seconds"])
        cases.append(
            {
                "case_id": case_id,
                "question": search["question"],
                "candidate_research_question": plan["candidate_research_question"],
                "artifact_hashes": {
                    "qwen_generation_sha256": generation_hash,
                    "postfix_receipt_sha256": sha256_file(receipt_path),
                    "postfix_full_output_sha256": sha256_file(full_output_path),
                },
                "retrieval": {
                    "evidence_hit_count": search["evidence_hit_count"],
                    "unique_retrieved_document_count": unique_retrieved_documents,
                    "referenced_chunk_count": search["referenced_chunk_count"],
                    "graph_candidate_count": search["graph_candidate_count"],
                    "corpus_snapshot_id": search["corpus_snapshot_id"],
                },
                "qwen": {
                    "model": call_receipts[0]["model"],
                    "provider_attempts": usage["provider_attempts"],
                    "input_tokens": usage["input_tokens"],
                    "output_tokens": usage["output_tokens"],
                    "wall_time_seconds": usage["wall_time_seconds"],
                },
                "plan_structure": {
                    "finding_count": len(plan.get("findings", [])),
                    "construct_count": len(plan.get("constructs", [])),
                    "mechanism_count": len(plan.get("mechanisms", [])),
                    "dataset_count": dataset_count,
                    "method_count": method_count,
                    "identification_strategy_count": identification_count,
                    "prediction_count": len(predictions),
                    "required_input_count": len(plan.get("required_inputs", [])),
                },
                "semantic_and_readiness": {
                    "topic_fidelity": adjudication["topic_fidelity"],
                    "topic_fidelity_rationale": adjudication["rationale"],
                    "falsifiable": falsifiable,
                    "execution_ready": execution_ready,
                },
                "postfix_structural_checks": checks,
                "technical_launch": {
                    "current_gate": launch["current_gate"],
                    "run_status": launch["run_status"],
                    "intake_can_execute": launch["intake_can_execute"],
                    "scientific_approval": launch["scientific_approval"],
                },
            }
        )

    structural_passes = sum(
        all(item["postfix_structural_checks"].values()) for item in cases
    )
    topic_passes = sum(item["semantic_and_readiness"]["topic_fidelity"] for item in cases)
    falsifiable_passes = sum(item["semantic_and_readiness"]["falsifiable"] for item in cases)
    ready_passes = sum(item["semantic_and_readiness"]["execution_ready"] for item in cases)
    pre_compile_passes = sum(bool(item["compile_succeeded"]) for item in pre_fix["cases"])

    return {
        "experiment_type": "two-case live Qwen generation plus deterministic same-output post-fix replay",
        "case_count": len(cases),
        "cases": cases,
        "aggregate": {
            "structural_e2e_passes": structural_passes,
            "structural_e2e_pass_rate": ratio(structural_passes, len(cases)),
            "pre_fix_compile_passes": pre_compile_passes,
            "pre_fix_compile_pass_rate": ratio(pre_compile_passes, len(cases)),
            "post_fix_compile_passes": structural_passes,
            "post_fix_compile_pass_rate": ratio(structural_passes, len(cases)),
            "verified_in_bundle_reference_instances": total_referenced,
            "globally_unique_referenced_chunks": len(global_referenced_chunks),
            "retrieved_evidence_hits": total_hits,
            "topic_fidelity_passes": topic_passes,
            "topic_fidelity_rate": ratio(topic_passes, len(cases)),
            "falsifiable_plan_passes": falsifiable_passes,
            "falsifiable_plan_rate": ratio(falsifiable_passes, len(cases)),
            "execution_ready_plan_passes": ready_passes,
            "execution_ready_plan_rate": ratio(ready_passes, len(cases)),
            "qwen_provider_attempts": sum(
                item["qwen"]["provider_attempts"] for item in cases
            ),
            "qwen_input_tokens": total_input_tokens,
            "qwen_output_tokens": total_output_tokens,
            "qwen_wall_time_seconds": round(total_wall_time, 3),
        },
        "interpretation": {
            "supported": "The workflow can bind retrieved evidence to a structured plan, compile it, and stop safely at H1 when data/method prerequisites are missing.",
            "limitation": "This two-case pilot does not establish broad reliability: one case drifted from the requested outcome, and neither plan was execution-ready.",
        },
    }


def evaluate_evidence_governance(root: Path) -> dict[str, Any]:
    pilot = (
        root
        / "output"
        / "real_pilot"
        / "2026-08-09_green_finance_decarbonization"
    )
    green_manifest = load_json(pilot / "A_metadata" / "green" / "manifest.json")
    eligibility = load_json(pilot / "A_selection" / "eligibility_audit.json")
    parsed = load_json(pilot / "C_parsed_eligible" / "manifest.json")
    graph = load_json(pilot / "H_discovery_release" / "final_research_graph.json")
    coverage = load_json(pilot / "F_discovery" / "coverage_certificate.json")
    release = load_json(
        pilot / "H_discovery_release" / "discovery_release_manifest.json"
    )

    evidence = graph["evidence"]
    required_evidence_fields = (
        "id",
        "source_document_id",
        "source_ref",
        "content_hash",
        "content_sha256",
        "verification_status",
    )
    traceable = 0
    fulltext_evidence = 0
    fulltext_chunk_linked = 0
    for item in evidence:
        locator = item.get("locator") or {}
        if all(item.get(field) for field in required_evidence_fields) and locator.get(
            "section"
        ):
            traceable += 1
        if item.get("source_type") in {"paper_fulltext", "paper_abstract"}:
            fulltext_evidence += 1
            if item.get("chunk_id"):
                fulltext_chunk_linked += 1

    downstream_dirs = [
        pilot / "C_parsed_eligible",
        pilot / "D_profiles" / "release_eligible",
        pilot / "E_vector",
        pilot / "G_graph",
        pilot / "H_discovery_release",
    ]
    forbidden_tokens = [b"PMC11101729", b"10.1016/j.heliyon.2024.e30141"]
    leakage_occurrences = 0
    scanned_files = 0
    for directory in downstream_dirs:
        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            scanned_files += 1
            data = path.read_bytes()
            leakage_occurrences += sum(data.count(token) for token in forbidden_tokens)

    blocking_gates = [item for item in coverage["gates"] if item["blocking"]]
    blocking_passes = sum(item["status"] == "passed" for item in blocking_gates)
    require(leakage_occurrences == 0, "retracted record leaked downstream")
    require(traceable == len(evidence), "not all evidence records are source traceable")
    require(
        fulltext_chunk_linked == fulltext_evidence,
        "not all fulltext evidence records are linked to source chunks",
    )
    require(blocking_passes == len(blocking_gates), "a blocking coverage gate failed")
    require(release["verification"]["errors"] == [], "release verification has errors")

    excluded = eligibility["excluded"]
    retracted = [item for item in excluded if item["decision"] == "exclude_retracted"]
    return {
        "metadata_records_in_scope": green_manifest["record_count"],
        "fulltext_candidates": eligibility["source_document_count"],
        "eligible_fulltext_documents": eligibility["included_document_count"],
        "excluded_fulltext_documents": eligibility["excluded_document_count"],
        "retracted_documents_excluded": len(retracted),
        "parsed_documents": parsed["document_count"],
        "parsed_chunks": parsed["chunk_count"],
        "formal_evidence_records": len(evidence),
        "traceable_evidence_records": traceable,
        "evidence_traceability_rate": ratio(traceable, len(evidence)),
        "fulltext_evidence_records": fulltext_evidence,
        "fulltext_evidence_with_chunk_id": fulltext_chunk_linked,
        "fulltext_chunk_link_rate": ratio(fulltext_chunk_linked, fulltext_evidence),
        "metadata_evidence_without_chunk_id": len(evidence) - fulltext_evidence,
        "graph_nodes": graph["statistics"]["node_count"],
        "graph_edges": graph["statistics"]["edge_count"],
        "downstream_files_scanned_for_retracted_record": scanned_files,
        "retracted_record_downstream_occurrences": leakage_occurrences,
        "blocking_coverage_gates_passed": blocking_passes,
        "blocking_coverage_gate_count": len(blocking_gates),
        "nonblocking_retrieval_saturation_status": next(
            item["status"]
            for item in coverage["gates"]
            if item["gate_id"] == "gate:retrieval-saturation"
        ),
        "claim_gate_status": coverage["claim_gate"]["status"],
        "claim_ceiling": coverage["claim_gate"]["claim_ceiling"],
        "release_schema_validated": release["verification"]["schema_validated"],
        "release_cross_references_validated": release["verification"][
            "cross_references_validated"
        ],
        "interpretation": "The evidence pipeline excludes a known retraction before indexing and preserves source locators/hashes for every formal evidence record; novelty-search saturation was not reached, so claims remain corpus-bounded.",
    }


def evaluate_case009(root: Path) -> dict[str, Any]:
    path = (
        root
        / "tmp"
        / "group2_intake_2026-08-11"
        / "benchmark-baselines"
        / "sixbench-formal-h9-closure"
        / "tests"
        / "fixtures"
        / "case009_hypoweaver_discovery_v1_gold.json"
    )
    gold = load_json(path)
    provider = gold["provider"]
    verification = gold["verification"]
    baseline = gold["baseline"]
    diagnostics = gold["adverse_identification_diagnostics"]
    reproduction = gold["reproduction"]
    scientific = gold["scientific_outcome"]

    checks = {
        "sealed_snapshot": gold["status"] == "sealed_snapshot",
        "qwen_calls_all_succeeded": provider["successful_calls"] == 7
        and provider["failed_calls"] == 0,
        "all_core_gates_passed": verification["V"] == 1
        and verification["all_core_gates_passed"] is True
        and len(verification["passed_gate_ids"]) == 8,
        "independent_reproduction_matched": reproduction["status"] == "matched"
        and reproduction["max_absolute_difference"] < 1e-8,
        "adverse_pretrend_detected": diagnostics["joint_pretrend_p_value"] < 0.05,
        "causal_claim_rejected": scientific["target_claim_admission_status"]
        == "rejected"
        and scientific["manuscript_mode"] == "identification_failure_report",
    }
    require(all(checks.values()), "Case009 sealed snapshot invariant failed")
    return {
        "source_artifact": str(path.relative_to(root)),
        "source_sha256": sha256_file(path),
        "case_status": "sealed single-case system snapshot; not a formal cross-system ranking",
        "checks": checks,
        "qwen": {
            "model": provider["model"],
            "successful_calls": provider["successful_calls"],
            "failed_calls": provider["failed_calls"],
            "input_tokens": provider["input_tokens"],
            "output_tokens": provider["output_tokens"],
            "provider_wall_time_seconds": provider["provider_wall_time_seconds"],
        },
        "scientific_gates": {
            "passed": len(verification["passed_gate_ids"]),
            "total": 8,
            "gate_ids": verification["passed_gate_ids"],
        },
        "data_and_estimate": {
            "rows_input": baseline["rows_input"],
            "nobs": baseline["nobs"],
            "rows_dropped": baseline["rows_dropped"],
            "treated_entity_count": baseline["treated_entity_count"],
            "coefficient": baseline["coefficient"],
            "standard_error": baseline["standard_error"],
            "p_value": baseline["p_value"],
            "joint_pretrend_p_value": diagnostics["joint_pretrend_p_value"],
            "wild_cluster_bootstrap_p_value": diagnostics[
                "wild_cluster_bootstrap_p_value"
            ],
            "permutation_p_value": diagnostics["permutation_p_value"],
        },
        "reproduction": {
            "metric_count": reproduction["metric_count"],
            "max_absolute_difference": reproduction["max_absolute_difference"],
        },
        "claim_gate": {
            "target_claim_status": scientific["target_claim_admission_status"],
            "maximum_allowed_strength": scientific[
                "target_claim_max_allowed_strength"
            ],
            "manuscript_mode": scientific["manuscript_mode"],
        },
        "interpretation": "The system completed the empirical workflow but rejected the desired causal claim because the pretrend gate failed; this measures scientific self-correction rather than answer fluency.",
    }


def evaluate_multimodal_component(root: Path) -> dict[str, Any]:
    path = (
        root
        / "output"
        / "experiments"
        / "qwen_vl_scientific_table"
        / "qwen_runs"
        / "batch_summary.json"
    )
    batch = load_json(path)
    aggregate = batch["aggregate"]
    crop = aggregate["conditions"]["cropped_target_table"]
    full = aggregate["conditions"]["full_page_with_distractor_table"]
    require(aggregate["successful_runs"] == 6, "Qwen-VL batch is incomplete")
    request_ids = [item.get("request_id") for item in batch["runs"]]
    require(all(request_ids) and len(set(request_ids)) == 6, "request IDs are missing")
    elapsed = sum(float(item["elapsed_seconds"]) for item in batch["runs"])
    return {
        "classification": "component ablation, not an overall AI Scientist score",
        "source_sha256": sha256_file(path),
        "model": batch["model_requested"],
        "successful_calls": aggregate["successful_runs"],
        "attempted_calls": aggregate["attempted_runs"],
        "crop_strict_exact_match_rate": crop["strict_exact_match_rate"],
        "full_page_strict_exact_match_rate": full["strict_exact_match_rate"],
        "crop_numeric_accuracy": crop["mean_numeric_accuracy"],
        "full_page_numeric_accuracy": full["mean_numeric_accuracy"],
        "crop_significance_accuracy": crop["mean_significance_accuracy"],
        "full_page_significance_accuracy": full["mean_significance_accuracy"],
        "elapsed_seconds": round(elapsed, 3),
        "request_id_count": len(set(request_ids)),
        "interpretation": "Target-table cropping removes page-level interference and is therefore an upstream system design requirement; crop=1.0 is not evidence that full-page scientific vision is solved.",
    }


def run_gate_stress_tests(root: Path) -> dict[str, Any]:
    repo = (
        root
        / "tmp"
        / "group2_intake_2026-08-11"
        / "hypoweaver-workflow"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo / "backend" / "src")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "backend.tests.test_discovery_planner",
            "-v",
        ],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    discovered_names = re.findall(r"^(test_[^\s]+)", output, flags=re.MULTILINE)
    ran_match = re.search(r"Ran (\d+) tests? in", output)
    ran_count = int(ran_match.group(1)) if ran_match else 0
    require(completed.returncode == 0, f"gate stress tests failed:\n{output}")
    require("\nOK" in output or output.rstrip().endswith("OK"), "unit test suite lacked OK")
    require(ran_count == 6, f"expected 6 passing tests, saw {ran_count}")
    require(len(set(discovered_names)) == 6, "could not bind all six test names")
    return {
        "suite": "backend.tests.test_discovery_planner",
        "passed": ran_count,
        "failed": 0,
        "covered_behaviors": [
            "Qwen plan is evidence-bounded",
            "reviewed plan compiles to release objects",
            "unspecified construct direction remains unknown",
            "missing dataset/method compiles as unknown",
            "out-of-bundle evidence is rejected",
            "generate-review-launch reaches H1 without scientific approval",
        ],
        "test_output": output.strip(),
    }


def build_results(root: Path) -> dict[str, Any]:
    online = evaluate_online_discovery(root)
    governance = evaluate_evidence_governance(root)
    case009 = evaluate_case009(root)
    multimodal = evaluate_multimodal_component(root)
    gate_stress = run_gate_stress_tests(root)
    return {
        "schema_version": "ai-scientist-system-capability-results/1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workspace_root": str(root),
        "evaluation_principle": "Measure the system as a pipeline: evidence governance, context binding, planning, workflow gates, deterministic execution, independent reproduction, and claim control. Qwen-VL is reported only as a component ablation.",
        "online_discovery": online,
        "gate_stress_tests": gate_stress,
        "evidence_governance": governance,
        "scientific_execution_case009": case009,
        "multimodal_component_ablation": multimodal,
        "claim_boundary": {
            "supported": [
                "Two live Qwen discovery generations were evidence-bound and, after the compiler enum fix, both reached H1 with correct safe stopping.",
                "The real evidence pipeline excluded a known retraction and retained complete source traceability for 100 formal evidence records.",
                "The sealed Case009 system snapshot executed a real DID workflow, matched an independent recomputation, and rejected a causal claim when pretrends failed.",
                "The Qwen-VL component experiment demonstrates the value of table cropping before structured extraction.",
            ],
            "not_established": [
                "Population-level reliability of online discovery; only two live discovery cases were run.",
                "Fully autonomous execution readiness for the two online discovery cases; both correctly remained blocked at H1.",
                "Formal superiority over other AI Scientist systems; the existing multi-system formal benchmark is not used as ranking evidence here.",
                "General full-page scientific vision; the full-page table condition failed strict exact match in all three repetitions.",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
    )
    args = parser.parse_args()
    root = args.workspace_root.resolve()
    output = args.output or (
        root
        / "output"
        / "experiments"
        / "ai_scientist_system_capability_v1"
        / "system_capability_results.json"
    )
    results = build_results(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(results, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"output": str(output), "sha256": sha256_file(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
