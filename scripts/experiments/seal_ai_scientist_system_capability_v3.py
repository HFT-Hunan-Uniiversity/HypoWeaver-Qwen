from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_DIR = Path("output/experiments/ai_scientist_system_capability_v3")
DEFAULT_PROTOCOL = Path("experiments/ai_scientist_system_capability_v3_protocol.json")
SECRET_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{20,}")
TEXT_SUFFIXES = {".json", ".md", ".txt", ".csv", ".py"}


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def relative(path: Path, workspace: Path) -> str:
    return path.resolve().relative_to(workspace.resolve()).as_posix()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workspace = args.workspace.resolve(strict=True)
    output_dir = (workspace / args.output_dir).resolve(strict=True)
    protocol_path = (workspace / args.protocol).resolve(strict=True)
    if workspace not in output_dir.parents:
        raise ValueError("output directory must stay inside the workspace")

    binding_path = output_dir / "protocol_binding.json"
    run_manifest_path = output_dir / "run_manifest.json"
    evaluation_path = output_dir / "evaluation.json"
    recheck_path = output_dir / "evaluation_recheck.json"
    comparison_path = output_dir / "comparison_v2_v3.json"

    protocol = load_json(protocol_path)
    binding = load_json(binding_path)
    run_manifest = load_json(run_manifest_path)
    evaluation = load_json(evaluation_path)
    recheck = load_json(recheck_path)
    comparison = load_json(comparison_path)

    raw_protocol_hash = file_sha256(protocol_path)
    canonical_protocol_hash = canonical_json_sha256(protocol)
    bound_hashes = {
        str(binding["protocol_sha256"]),
        str(run_manifest["protocol_sha256"]),
        str(evaluation["protocol_sha256"]),
        str(recheck["protocol_sha256"]),
    }
    if bound_hashes != {canonical_protocol_hash}:
        raise ValueError("canonical protocol binding mismatch")

    cells = run_manifest.get("cells")
    if not isinstance(cells, list) or len(cells) != 30:
        raise ValueError("run manifest must contain all 30 frozen cells")
    completed = sum(cell.get("status") == "completed" for cell in cells)
    failed = sum(cell.get("status") == "failed" for cell in cells)
    if (completed, failed) != (29, 1):
        raise ValueError(f"unexpected run status counts: completed={completed}, failed={failed}")

    if (
        evaluation.get("evaluated_cells") != 30
        or evaluation.get("completed_cells") != 29
        or evaluation.get("failed_cells") != 1
    ):
        raise ValueError("evaluation cell counts do not match the frozen run")
    if comparison.get("matched_cells") != 30:
        raise ValueError("comparison does not contain all 30 paired cells")

    evaluation_recomputed = dict(evaluation)
    recheck_recomputed = dict(recheck)
    evaluation_recomputed.pop("evaluated_at", None)
    recheck_recomputed.pop("evaluated_at", None)
    if evaluation_recomputed != recheck_recomputed:
        raise ValueError("independent evaluator recheck differs from the primary evaluation")

    metrics = evaluation["metrics_wilson_95"]
    if metrics["qwen_receipts_valid"]["successes"] != 30:
        raise ValueError("not every cell has valid anonymized Qwen receipts")
    if metrics["safe_stop"]["successes"] != 30:
        raise ValueError("safe stopping is not verified for every frozen cell")

    scanned_files = 0
    secret_match_files: list[str] = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        scanned_files += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        if SECRET_PATTERN.search(text):
            secret_match_files.append(relative(path, workspace))
    if secret_match_files:
        raise ValueError(
            "potential API key text detected in: " + ", ".join(secret_match_files)
        )

    evidence_paths = [
        protocol_path,
        binding_path,
        run_manifest_path,
        output_dir / "retrieval_ablation.json",
        evaluation_path,
        output_dir / "evaluation.md",
        recheck_path,
        output_dir / "evaluation_recheck.md",
        comparison_path,
        output_dir / "comparison_v2_v3.md",
        output_dir / "figures/system_capability_v2_v3.png",
        output_dir / "figures/system_capability_v2_v3.pdf",
        output_dir / "figures/system_capability_v2_v3.svg",
        output_dir / "figures/system_capability_v2_v3_metadata.json",
        workspace / "output/experiments/execution_readiness_contract_control_v1/result.json",
        workspace / "output/experiments/qwen_vl_scientific_table/qwen_runs/batch_summary.json",
        workspace / "docs/AI_Scientist系统能力实验_v3_误差审计.md",
        workspace / "docs/真实案例_问题集Case009_十项中文结果_v1.md",
        workspace / "docs/竞赛提交前系统验收与补全_v3.md",
        workspace / "scripts/experiments/run_ai_scientist_system_capability_v2.py",
        workspace / "scripts/experiments/evaluate_ai_scientist_system_capability_v2.py",
        workspace / "scripts/experiments/compare_ai_scientist_system_capability_v2_v3.py",
        workspace / "scripts/experiments/plot_ai_scientist_system_capability_v2_v3.py",
    ]
    missing = [relative(path, workspace) for path in evidence_paths if not path.is_file()]
    if missing:
        raise ValueError("required evidence files are missing: " + ", ".join(missing))

    for path in evidence_paths:
        if output_dir in path.parents or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        scanned_files += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        if SECRET_PATTERN.search(text):
            secret_match_files.append(relative(path, workspace))
    if secret_match_files:
        raise ValueError(
            "potential API key text detected in: " + ", ".join(secret_match_files)
        )

    artifacts = {
        relative(path, workspace): {
            "sha256": file_sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for path in sorted(evidence_paths, key=lambda item: relative(item, workspace))
    }
    manifest = {
        "schema_version": "ai-scientist-system-capability-evidence-seal/1.0.0",
        "sealed_run_completed_at": run_manifest["completed_at"],
        "protocol": {
            "path": relative(protocol_path, workspace),
            "raw_file_sha256": raw_protocol_hash,
            "canonical_json_sha256": canonical_protocol_hash,
            "schema_version": protocol["schema_version"],
            "cases": len(protocol["cases"]),
            "seeds": len(protocol["generation"]["seeds"]),
            "cells": len(protocol["cases"]) * len(protocol["generation"]["seeds"]),
        },
        "assertions": {
            "all_frozen_cells_included": True,
            "completed_cells": completed,
            "failed_cells_retained": failed,
            "evaluation_recheck_equal_except_timestamp": True,
            "valid_anonymized_receipt_cells": 30,
            "provider_attempts": evaluation["usage_totals"]["provider_attempts"],
            "safe_stop_cells": 30,
            "potential_api_key_matches": 0,
            "secret_scan_text_files": scanned_files,
        },
        "headline_metrics": {
            key: {
                "successes": metrics[key]["successes"],
                "total": metrics[key]["total"],
                "rate": metrics[key]["rate"],
                "wilson_95": [metrics[key]["lower"], metrics[key]["upper"]],
            }
            for key in (
                "cell_completed",
                "h0_compilable",
                "topic_fidelity",
                "diversity_gate_passed",
                "readiness_blocked_correctly",
                "safe_stop",
            )
        },
        "artifacts": artifacts,
        "release_boundary": (
            "This seal indexes internal evidence. Build a separately sanitized submission "
            "package; do not publish raw cell outputs, internal evidence snippets, databases, "
            "credentials, or private receipts."
        ),
    }

    manifest_path = output_dir / "evidence_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    manifest_hash = file_sha256(manifest_path)
    hash_path = output_dir / "evidence_manifest.sha256"
    hash_path.write_text(f"{manifest_hash}  evidence_manifest.json\n", encoding="ascii")
    print(
        json.dumps(
            {
                "manifest": relative(manifest_path, workspace),
                "sha256": manifest_hash,
                "artifacts": len(artifacts),
                "secret_scan_text_files": scanned_files,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
