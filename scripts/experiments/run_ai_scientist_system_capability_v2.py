#!/usr/bin/env python3
"""Run the frozen 10-question x 3-seed AI Scientist system experiment."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT
BACKEND = PROJECT / "backend"
sys.path.insert(0, str(BACKEND / "src"))

from hypoweaver.discovery_handoff import (  # noqa: E402
    DiscoveryLaunchRequest,
    create_run_request,
    discovery_release_to_case,
)
from hypoweaver.adapters import QwenModelGateway  # noqa: E402
from hypoweaver.discovery_pipeline import build_discovery_release_preview  # noqa: E402
from hypoweaver.discovery_planner import (  # noqa: E402
    DiscoveryPlanGenerationRequest,
    DiscoveryResearcherContext,
    compile_discovery_plan,
    generate_reviewed_discovery_plan,
)
from hypoweaver.engine import WorkflowEngine  # noqa: E402
from hypoweaver.knowledge_models import KnowledgeSearchRequest  # noqa: E402
from hypoweaver.knowledge_service import KnowledgeService, KnowledgeSettings  # noqa: E402
from hypoweaver.repository import RunRepository  # noqa: E402


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


def protocol_major(protocol: dict[str, Any]) -> int:
    version = str(protocol.get("schema_version") or "").rsplit("/", 1)[-1]
    try:
        return max(1, int(version.split(".", 1)[0]))
    except ValueError:
        return 1


def load_private_runtime_environment() -> None:
    """Load only Qwen runtime fields from the project-local, ignored .env file."""

    path = PROJECT / ".env"
    if not path.is_file():
        return
    allowed = {"DASHSCOPE_API_KEY", "QWEN_BASE_URL", "QWEN_MODEL"}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in allowed:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if value:
            os.environ[key] = value


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def knowledge_service() -> KnowledgeService:
    data = Path(os.environ.get("HYPOWEAVER_EXPERIMENT_KNOWLEDGE_DIR", str(ROOT / "knowledge-data-authorized"))).expanduser().resolve()
    if not (data / "all_store.h5").is_file():
        raise FileNotFoundError("Historical online rerun requires the authorized frozen knowledge snapshot. See README_REPRODUCE.md; bundled public sample is not the historical corpus.")
    return KnowledgeService(
        KnowledgeSettings(
            vector_path=data / "all_store.h5",
            cleaned_dir=data / "cleaned",
            metadata_dir=data / "cleaned_meta",
            document_registry_path=data / "manifests" / "doc_registry.csv",
            graph_dir=data / "kg",
            corpus_manifest_path=data / "manifest.json",
            embedding_backend="auto",
            embedding_model=os.environ.get("HYPOWEAVER_KNOWLEDGE_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5"),
            embedding_revision="7999e1d3359715c523056ef9478215996d62a620",
        )
    )


class LocalKnowledgeClient:
    def __init__(self, service: KnowledgeService) -> None:
        self.service = service

    async def search(self, request: KnowledgeSearchRequest):
        return await asyncio.to_thread(self.service.search, request)


def retrieval_summary(bundle: Any) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for hit in bundle.evidence_hits:
        counts[hit.document_id] = counts.get(hit.document_id, 0) + 1
    return {
        "bundle_id": bundle.bundle_id,
        "hit_count": len(bundle.evidence_hits),
        "unique_document_count": len(counts),
        "max_document_share": (
            max(counts.values(), default=0) / len(bundle.evidence_hits)
            if bundle.evidence_hits
            else None
        ),
        "document_counts": counts,
        "diagnostics": bundle.retrieval_diagnostics.model_dump(mode="json"),
        "warnings": bundle.warnings,
    }


async def run_cell(
    *,
    case: dict[str, Any],
    seed: int,
    protocol: dict[str, Any],
    protocol_sha256: str,
    client: LocalKnowledgeClient,
    output_dir: Path,
    semaphore: asyncio.Semaphore,
    engine: WorkflowEngine,
    launch_lock: asyncio.Lock,
) -> dict[str, Any]:
    major = protocol_major(protocol)
    cell_id = f"{case['case_id']}__seed_{seed}"
    cell_dir = output_dir / "cells" / cell_id
    result_path = cell_dir / "result.json"
    if result_path.is_file():
        previous = load_object(result_path)
        if (
            previous.get("protocol_sha256") == protocol_sha256
            and previous.get("status") == "completed"
        ):
            return {"cell_id": cell_id, "status": "resumed", "path": str(result_path)}
    async with semaphore:
        started_at = datetime.now(timezone.utc)
        search_config = protocol["retrieval"]
        request = DiscoveryPlanGenerationRequest(
            search=KnowledgeSearchRequest(
                question=case["question"],
                top_k=search_config["top_k"],
                max_graph_edges=search_config["max_graph_edges"],
                diversity_mode=search_config["diversity_mode"],
                max_hits_per_document=search_config["max_hits_per_document"],
                min_unique_documents=search_config["min_unique_documents"],
            ),
            context=DiscoveryResearcherContext(
                goal=(
                    "在不改变原问题暴露、结果和限定语的前提下，生成一个语料边界内、"
                    "可证伪且可编译的数据与识别方案。"
                ),
                unit_of_analysis="firm-region-year",
                sample_period="由 H1 数据审阅后确定",
                constraints=[
                    "不得把相邻主题替换为原研究问题。",
                    "不得把候选数据源写成已经取得的数据资产。",
                    "未提供许可与哈希数据时必须安全停止。",
                ],
            ),
            experiment_seed=seed,
            temperature=protocol["generation"]["temperature"],
        )
        try:
            gateway = QwenModelGateway(
                seed=seed,
                temperature=protocol["generation"]["temperature"],
                schema_repair_enabled=protocol["generation"].get(
                    "schema_repair_enabled", True
                ),
            )
            try:
                generation = await generate_reviewed_discovery_plan(
                    request,
                    knowledge_client=client,
                    gateway=gateway,
                    max_consistency_repairs=protocol["generation"].get(
                        "max_consistency_repairs", 1
                    ),
                )
            finally:
                await gateway.http_client.aclose()
            generation_payload = generation.model_dump(mode="json")
            atomic_json(cell_dir / "generation.json", generation_payload)
            final_review = (
                generation.consistency_reviews[-1]
                if generation.consistency_reviews
                else None
            )
            launch_payload: dict[str, Any]
            safe_stop = False
            if final_review is not None and final_review.decision == "pass":
                build = compile_discovery_plan(
                    generation.evidence_bundle,
                    generation.plan,
                    reviewer="experiment-h0-reviewer",
                    review_note=(
                        "Frozen experiment review: evidence references and consistency gate were "
                        "checked; no scientific result is approved."
                    ),
                    consistency_review=final_review,
                    execution_readiness=generation.execution_readiness,
                )
                release = build_discovery_release_preview(
                    build,
                    reviewer="experiment-h0-reviewer",
                )
                case_submission = discovery_release_to_case(
                    release,
                    hypothesis_id="hypothesis:online_candidate",
                    approver="experiment-h0-reviewer",
                    approval_reason=(
                        "Frozen system experiment only; H1 must remain human-gated and no "
                        "scientific claim is authorized."
                    ),
                    execution_readiness=generation.execution_readiness,
                )
                launch = DiscoveryLaunchRequest(
                    build=build,
                    hypothesis_id="hypothesis:online_candidate",
                    approve_h0=True,
                    approval_reason=(
                        "Frozen system experiment only; H1 remains human-gated until all inputs "
                        "and diagnostics are independently approved."
                    ),
                    mode="fixture",
                    research_model_provider="code_owned",
                )
                async with launch_lock:
                    run = await engine.create_run(create_run_request(case_submission, launch))
                safe_stop = (
                    not case_submission.intake_readiness.can_execute
                    and run.current_gate == "H1"
                    and run.status == "waiting_human"
                )
                launch_payload = {
                    "launched": True,
                    "run_id": run.id,
                    "run_status": run.status,
                    "current_gate": run.current_gate,
                    "intake_readiness": case_submission.intake_readiness.model_dump(mode="json"),
                    "scientific_approval": False,
                }
            else:
                safe_stop = bool(
                    generation.execution_readiness is not None
                    and not generation.execution_readiness.can_execute
                )
                launch_payload = {
                    "launched": False,
                    "blocked_before_h0": True,
                    "scientific_approval": False,
                    "reason": "bounded consistency repair did not pass",
                }
            result = {
                "schema_version": f"ai-scientist-system-cell/{major}.0.0",
                "protocol_sha256": protocol_sha256,
                "cell_id": cell_id,
                "case_id": case["case_id"],
                "seed": seed,
                "question": case["question"],
                "started_at": started_at.isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "status": "completed",
                "retrieval": retrieval_summary(generation.evidence_bundle),
                "model_usage": generation.model_usage,
                "repair_count": generation.repair_count,
                "final_consistency_passed": generation.final_consistency_passed,
                "consistency_reviews": [
                    item.model_dump(mode="json") for item in generation.consistency_reviews
                ],
                "retrieval_rounds": [
                    item.model_dump(mode="json") for item in generation.retrieval_rounds
                ],
                "execution_readiness": (
                    generation.execution_readiness.model_dump(mode="json")
                    if generation.execution_readiness is not None
                    else None
                ),
                "safe_stop": safe_stop,
                "launch": launch_payload,
                "generation_path": str(cell_dir / "generation.json"),
            }
            atomic_json(result_path, result)
            return {"cell_id": cell_id, "status": "completed", "path": str(result_path)}
        except Exception as error:
            failed_usage = (
                gateway.budget.snapshot()
                if "gateway" in locals() and gateway is not None
                else None
            )
            failure = {
                "schema_version": f"ai-scientist-system-cell/{major}.0.0",
                "protocol_sha256": protocol_sha256,
                "cell_id": cell_id,
                "case_id": case["case_id"],
                "seed": seed,
                "question": case["question"],
                "started_at": started_at.isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "status": "failed",
                "error_type": type(error).__name__,
                "error": str(error)[:2000],
                "model_usage": failed_usage,
                "traceback": traceback.format_exc(limit=12),
            }
            atomic_json(result_path, failure)
            return {"cell_id": cell_id, "status": "failed", "path": str(result_path)}


async def main_async(args: argparse.Namespace) -> int:
    load_private_runtime_environment()
    protocol = load_object(args.protocol)
    protocol_sha256 = canonical_sha256(protocol)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(
        output_dir / "protocol_binding.json",
        {
            "protocol_path": str(args.protocol.resolve()),
            "protocol_sha256": protocol_sha256,
            "bound_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    service = await asyncio.to_thread(knowledge_service)
    client = LocalKnowledgeClient(service)
    status = service.status().model_dump(mode="json")
    atomic_json(output_dir / "knowledge_status.json", status)

    baseline: dict[str, Any] = {}
    retrieval = protocol["retrieval"]
    for case in protocol["cases"]:
        base_request = KnowledgeSearchRequest(
            question=case["question"],
            top_k=retrieval["top_k"],
            max_graph_edges=retrieval["max_graph_edges"],
            diversity_mode="none",
            max_hits_per_document=retrieval["max_hits_per_document"],
            min_unique_documents=retrieval["min_unique_documents"],
        )
        capped_request = base_request.model_copy(
            update={"diversity_mode": retrieval["diversity_mode"]}
        )
        base_bundle = await client.search(base_request)
        capped_bundle = await client.search(capped_request)
        baseline[case["case_id"]] = {
            "none": retrieval_summary(base_bundle),
            "per_document_cap": retrieval_summary(capped_bundle),
        }
    atomic_json(output_dir / "retrieval_ablation.json", baseline)

    repository = RunRepository(output_dir / "experiment_runs.db")
    engine = WorkflowEngine(repository)
    semaphore = asyncio.Semaphore(args.concurrency)
    launch_lock = asyncio.Lock()
    cells = [
        (case, seed)
        for case in protocol["cases"]
        for seed in protocol["generation"]["seeds"]
    ]
    if args.limit is not None:
        cells = cells[: args.limit]
    tasks = [
        asyncio.create_task(
            run_cell(
                case=case,
                seed=seed,
                protocol=protocol,
                protocol_sha256=protocol_sha256,
                client=client,
                output_dir=output_dir,
                semaphore=semaphore,
                engine=engine,
                launch_lock=launch_lock,
            )
        )
        for case, seed in cells
    ]
    completed: list[dict[str, Any]] = []
    for future in asyncio.as_completed(tasks):
        result = await future
        completed.append(result)
        print(
            json.dumps(
                {
                    "progress": f"{len(completed)}/{len(tasks)}",
                    "cell_id": result["cell_id"],
                    "status": result["status"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    manifest = {
        "schema_version": (
            f"ai-scientist-system-run-manifest/{protocol_major(protocol)}.0.0"
        ),
        "protocol_sha256": protocol_sha256,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "requested_cells": len(tasks),
        "completed_cells": sum(item["status"] in {"completed", "resumed"} for item in completed),
        "failed_cells": sum(item["status"] == "failed" for item in completed),
        "cells": sorted(completed, key=lambda item: item["cell_id"]),
    }
    atomic_json(output_dir / "run_manifest.json", manifest)
    return 1 if manifest["failed_cells"] else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--protocol",
        type=Path,
        default=ROOT / "experiments" / "ai_scientist_system_capability_v2_protocol.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "output" / "experiments" / "ai_scientist_system_capability_v2",
    )
    parser.add_argument("--concurrency", type=int, default=3, choices=(1, 2, 3))
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
