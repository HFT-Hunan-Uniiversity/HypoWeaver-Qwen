#!/usr/bin/env python3
"""Run the frozen one-component-off AI Scientist ablation campaign."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import run_ai_scientist_system_capability_v2 as base


DEFAULT_CAMPAIGN = (
    base.ROOT / "experiments" / "ai_scientist_component_ablation_20260905_protocol.json"
)
DEFAULT_OUTPUT_ROOT = (
    base.ROOT / "output" / "experiments" / "ai_scientist_component_ablation_20260905"
)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def materialize_arm_protocol(
    campaign: dict[str, Any],
    source: dict[str, Any],
    arm_id: str,
) -> dict[str, Any]:
    arm = campaign["arms"][arm_id]
    protocol = json.loads(json.dumps(source, ensure_ascii=False))
    protocol["schema_version"] = "ai-scientist-system-capability-protocol/4.0.0"
    protocol["frozen_at"] = campaign["frozen_at"]
    protocol["system_under_test"] = arm["public_label"]
    protocol["component_ablation"] = {
        "campaign_schema_version": campaign["schema_version"],
        "campaign_frozen_at": campaign["frozen_at"],
        "arm_id": arm_id,
        "public_label": arm["public_label"],
        "description": arm["description"],
        "one_component_off": arm_id != "complete_loop",
    }
    protocol["fixed_conditions"] = campaign["fixed_conditions"]
    protocol["reporting_rules"] = campaign["reporting_rules"]
    protocol["retrieval"].update(arm.get("retrieval_overrides") or {})
    protocol["generation"].update(arm.get("generation_overrides") or {})
    return protocol


def verify_source(campaign_path: Path, campaign: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    source_path = (
        campaign_path.resolve().parents[1] / campaign["source_protocol"]["path"]
    ).resolve()
    source = load_json(source_path)
    actual = base.canonical_sha256(source)
    expected = campaign["source_protocol"]["canonical_json_sha256"]
    if actual != expected:
        raise ValueError(
            f"source protocol hash mismatch: expected {expected}, observed {actual}"
        )
    return source_path, source


async def build_retrieval_ablation(
    *,
    protocol: dict[str, Any],
    client: base.LocalKnowledgeClient,
) -> dict[str, Any]:
    retrieval = protocol["retrieval"]
    output: dict[str, Any] = {}
    for case in protocol["cases"]:
        base_request = base.KnowledgeSearchRequest(
            question=case["question"],
            top_k=retrieval["top_k"],
            max_graph_edges=retrieval["max_graph_edges"],
            diversity_mode="none",
            max_hits_per_document=retrieval["max_hits_per_document"],
            min_unique_documents=retrieval["min_unique_documents"],
        )
        capped_request = base_request.model_copy(
            update={"diversity_mode": "per_document_cap"}
        )
        uncapped, capped = await asyncio.gather(
            client.search(base_request),
            client.search(capped_request),
        )
        output[case["case_id"]] = {
            "none": base.retrieval_summary(uncapped),
            "per_document_cap": base.retrieval_summary(capped),
        }
    return output


def terminal_result(
    result_path: Path,
    *,
    protocol_sha256: str,
) -> dict[str, Any] | None:
    if not result_path.is_file():
        return None
    existing = load_json(result_path)
    if existing.get("protocol_sha256") != protocol_sha256:
        raise ValueError(f"refusing to overwrite mismatched terminal cell: {result_path}")
    if existing.get("status") not in {"completed", "failed"}:
        raise ValueError(f"unknown terminal status in {result_path}")
    return existing


async def main_async(args: argparse.Namespace) -> int:
    campaign_path = args.campaign.resolve(strict=True)
    campaign = load_json(campaign_path)
    source_path, source = verify_source(campaign_path, campaign)
    requested_arms = args.arms or list(campaign["arms"])
    unknown = sorted(set(requested_arms) - set(campaign["arms"]))
    if unknown:
        raise ValueError("unknown ablation arms: " + ", ".join(unknown))

    output_root = args.output_root.resolve()
    if base.ROOT.resolve() not in output_root.parents:
        raise ValueError("output root must stay inside the workspace")
    output_root.mkdir(parents=True, exist_ok=True)

    protocols: dict[str, dict[str, Any]] = {}
    protocol_hashes: dict[str, str] = {}
    arm_dirs: dict[str, Path] = {}
    for arm_id in requested_arms:
        arm_dir = output_root / arm_id
        arm_dir.mkdir(parents=True, exist_ok=True)
        protocol = materialize_arm_protocol(campaign, source, arm_id)
        protocol_hash = base.canonical_sha256(protocol)
        protocol_path = arm_dir / "frozen_protocol.json"
        if protocol_path.is_file():
            existing = load_json(protocol_path)
            if base.canonical_sha256(existing) != protocol_hash:
                raise ValueError(f"refusing to replace frozen protocol: {protocol_path}")
        else:
            base.atomic_json(protocol_path, protocol)
        protocols[arm_id] = protocol
        protocol_hashes[arm_id] = protocol_hash
        arm_dirs[arm_id] = arm_dir
        base.atomic_json(
            arm_dir / "protocol_binding.json",
            {
                "campaign_path": str(campaign_path),
                "source_protocol_path": str(source_path),
                "arm_protocol_path": str(protocol_path),
                "protocol_sha256": protocol_hash,
                "bound_at": campaign["frozen_at"],
                "public_label": campaign["arms"][arm_id]["public_label"],
            },
        )

    base.atomic_json(
        output_root / "campaign_binding.json",
        {
            "campaign_path": str(campaign_path),
            "campaign_sha256": base.canonical_sha256(campaign),
            "source_protocol_path": str(source_path),
            "source_protocol_sha256": base.canonical_sha256(source),
            "arms": {
                arm_id: {
                    "public_label": campaign["arms"][arm_id]["public_label"],
                    "protocol_sha256": protocol_hashes[arm_id],
                }
                for arm_id in requested_arms
            },
        },
    )
    if args.prepare_only:
        print(
            json.dumps(
                {
                    "status": "prepared",
                    "output_root": str(output_root),
                    "arms": requested_arms,
                },
                ensure_ascii=False,
            )
        )
        return 0

    base.load_private_runtime_environment()
    service = await asyncio.to_thread(base.knowledge_service)
    client = base.LocalKnowledgeClient(service)
    status = service.status().model_dump(mode="json")
    base.atomic_json(output_root / "knowledge_status.json", status)
    retrieval_ablation = await build_retrieval_ablation(
        protocol=protocols[requested_arms[0]],
        client=client,
    )
    for arm_id in requested_arms:
        base.atomic_json(arm_dirs[arm_id] / "knowledge_status.json", status)
        base.atomic_json(
            arm_dirs[arm_id] / "retrieval_ablation.json", retrieval_ablation
        )

    engines = {
        arm_id: base.WorkflowEngine(
            base.RunRepository(arm_dirs[arm_id] / "experiment_runs.db")
        )
        for arm_id in requested_arms
    }
    launch_locks = {arm_id: asyncio.Lock() for arm_id in requested_arms}
    semaphore = asyncio.Semaphore(args.concurrency)

    base_cells = [
        (case, seed)
        for case in source["cases"]
        for seed in source["generation"]["seeds"]
    ]
    if args.limit_per_arm is not None:
        base_cells = base_cells[: args.limit_per_arm]

    work: list[tuple[str, dict[str, Any], int]] = []
    for cell_index, (case, seed) in enumerate(base_cells):
        rotated = requested_arms[cell_index % len(requested_arms) :] + requested_arms[
            : cell_index % len(requested_arms)
        ]
        work.extend((arm_id, case, seed) for arm_id in rotated)

    async def run_one(
        arm_id: str,
        case: dict[str, Any],
        seed: int,
    ) -> dict[str, Any]:
        cell_id = f"{case['case_id']}__seed_{seed}"
        result_path = arm_dirs[arm_id] / "cells" / cell_id / "result.json"
        existing = terminal_result(
            result_path,
            protocol_sha256=protocol_hashes[arm_id],
        )
        if existing is not None:
            return {
                "arm_id": arm_id,
                "cell_id": cell_id,
                "status": existing["status"],
                "retained": True,
                "path": str(result_path),
            }
        result = await base.run_cell(
            case=case,
            seed=seed,
            protocol=protocols[arm_id],
            protocol_sha256=protocol_hashes[arm_id],
            client=client,
            output_dir=arm_dirs[arm_id],
            semaphore=semaphore,
            engine=engines[arm_id],
            launch_lock=launch_locks[arm_id],
        )
        result["arm_id"] = arm_id
        result["retained"] = False
        return result

    tasks = [asyncio.create_task(run_one(*item)) for item in work]
    completed: list[dict[str, Any]] = []
    for future in asyncio.as_completed(tasks):
        item = await future
        completed.append(item)
        print(
            json.dumps(
                {
                    "progress": f"{len(completed)}/{len(tasks)}",
                    "arm": campaign["arms"][item["arm_id"]]["public_label"],
                    "cell_id": item["cell_id"],
                    "status": item["status"],
                    "retained": item["retained"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    arm_summaries: dict[str, Any] = {}
    for arm_id in requested_arms:
        arm_items = [item for item in completed if item["arm_id"] == arm_id]
        manifest = {
            "schema_version": "ai-scientist-component-ablation-arm-run/1.0.0",
            "protocol_sha256": protocol_hashes[arm_id],
            "public_label": campaign["arms"][arm_id]["public_label"],
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "requested_cells": len(arm_items),
            "completed_cells": sum(item["status"] == "completed" for item in arm_items),
            "failed_cells": sum(item["status"] == "failed" for item in arm_items),
            "retained_terminal_cells": sum(bool(item["retained"]) for item in arm_items),
            "cells": sorted(arm_items, key=lambda item: item["cell_id"]),
        }
        base.atomic_json(arm_dirs[arm_id] / "run_manifest.json", manifest)
        arm_summaries[arm_id] = {
            key: manifest[key]
            for key in (
                "public_label",
                "requested_cells",
                "completed_cells",
                "failed_cells",
                "retained_terminal_cells",
            )
        }

    base.atomic_json(
        output_root / "campaign_run_manifest.json",
        {
            "schema_version": "ai-scientist-component-ablation-campaign-run/1.0.0",
            "campaign_sha256": base.canonical_sha256(campaign),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "interleaved": True,
            "concurrency": args.concurrency,
            "arms": arm_summaries,
        },
    )
    return 1 if any(item["failed_cells"] for item in arm_summaries.values()) else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", type=Path, default=DEFAULT_CAMPAIGN)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--arms", nargs="+")
    parser.add_argument("--concurrency", type=int, default=3, choices=(1, 2, 3))
    parser.add_argument("--limit-per-arm", type=int)
    parser.add_argument("--prepare-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    return asyncio.run(main_async(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
