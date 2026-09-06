from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hypoweaver.visualization import (
    ChineseEconJournalFigureRenderer,
    FigureRequest,
    FigureSource,
)


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source(
    spec_path: Path,
    generation_path: Path,
) -> tuple[FigureSource, list[FigureSource]]:
    return (
        FigureSource(
            artifact_id="carbon-market-showcase:research_run",
            artifact_key=spec_path.name,
            sha256=_sha256(spec_path),
        ),
        [
            FigureSource(
                artifact_id="carbon-market-qwen:discovery_generation",
                artifact_key=generation_path.name,
                sha256=_sha256(generation_path),
            )
        ],
    )


def _mechanism_request(
    spec: dict[str, Any],
    spec_path: Path,
    generation_path: Path,
) -> FigureRequest:
    source, data_sources = _source(spec_path, generation_path)
    return FigureRequest(
        request_id="carbon-showcase-mechanism",
        stage="evidence",
        case_id="carbon-market-showcase",
        research_run_id="carbon-market-showcase-demo",
        contract_hash=_sha256(generation_path),
        recipe_id="mechanism_evidence_graph",
        provenance="conceptual",
        source=source,
        data_sources=data_sources,
        execution_ids=["showcase-mechanism-plan"],
        bindings={
            "data": {
                "nodes": [
                    {
                        "node_id": item["id"],
                        "label": item["label"],
                        "x": item.get("x"),
                        "y": item.get("y"),
                        "width": item.get("width"),
                        "height": item.get("height"),
                        "fill": item.get("fill"),
                    }
                    for item in spec["nodes"]
                ],
                "edges": [
                    {
                        "edge_id": f"path-{index:02d}",
                        "source": item["from"],
                        "target": item["to"],
                        "edge_kind": "hypothesized",
                        "label": item.get("label"),
                        "style": item.get("style", "solid"),
                        "curvature": _connection_curvature(item.get("connection")),
                        "label_dx": item.get("label_dx", 0),
                        "label_dy": item.get("label_dy", 0.035),
                    }
                    for index, item in enumerate(spec["edges"], 1)
                ],
            }
        },
    )


def _connection_curvature(value: Any) -> float:
    if not isinstance(value, str):
        return 0.0
    match = re.fullmatch(r"arc3,rad=(-?(?:0(?:\.\d+)?|\.\d+))", value.strip())
    return float(match.group(1)) if match else 0.0


def _event_study_request(
    spec: dict[str, Any],
    spec_path: Path,
    generation_path: Path,
) -> FigureRequest:
    source, data_sources = _source(spec_path, generation_path)
    reference_period = spec.get("reference_period")
    points = [
        {
            "relative_time": period,
            "coefficient": estimate,
            "ci_lower": lower,
            "ci_upper": upper,
            "execution_id": "showcase-event-study",
        }
        for period, estimate, lower, upper in zip(
            spec["x"],
            spec["estimate"],
            spec["lower"],
            spec["upper"],
            strict=True,
        )
        if period != reference_period
    ]
    return FigureRequest(
        request_id="carbon-showcase-event-study",
        stage="evidence",
        case_id="carbon-market-showcase",
        research_run_id="carbon-market-showcase-demo",
        contract_hash=_sha256(generation_path),
        recipe_id="event_study",
        provenance="demo",
        source=source,
        data_sources=data_sources,
        execution_ids=["showcase-event-study"],
        bindings={
            "data": {
                "points": points,
                "reference_period": reference_period,
            }
        },
    )


def _coefficient_request(
    spec: dict[str, Any],
    spec_path: Path,
    generation_path: Path,
) -> FigureRequest:
    source, data_sources = _source(spec_path, generation_path)
    records = [
        {
            "specification": item["label"],
            "run_type": "baseline" if index == 1 else "robustness",
            "coefficient": item["estimate"],
            "ci_lower": item["lower"],
            "ci_upper": item["upper"],
            "execution_id": f"showcase-specification-{index:02d}",
        }
        for index, item in enumerate(spec["rows"], 1)
    ]
    return FigureRequest(
        request_id="carbon-showcase-robustness",
        stage="evidence",
        case_id="carbon-market-showcase",
        research_run_id="carbon-market-showcase-demo",
        contract_hash=_sha256(generation_path),
        recipe_id="specification_curve",
        provenance="demo",
        source=source,
        data_sources=data_sources,
        execution_ids=[item["execution_id"] for item in records],
        bindings={"data": {"term": "全国碳市场处理项", "points": records}},
    )


def _sanitized_qwen_summary(
    generation: dict[str, Any],
    receipt: dict[str, Any],
) -> dict[str, Any]:
    usage = generation.get("model_usage") or {}
    raw_calls = usage.get("call_receipts") or []
    calls = [
        {
            key: call.get(key)
            for key in (
                "attempt_index",
                "attempt_type",
                "prompt_key",
                "prompt_version",
                "provider",
                "model",
                "outcome",
                "input_tokens",
                "output_tokens",
                "input_sha256",
                "output_schema_sha256",
                "response_sha256",
                "provider_response_id_sha256",
            )
        }
        for call in raw_calls
        if isinstance(call, dict)
    ]
    plan = generation.get("plan") or {}
    evidence = generation.get("evidence_bundle") or {}
    document_ids = {
        str(item.get("document_id"))
        for item in evidence.get("evidence_hits") or []
        if isinstance(item, dict) and item.get("document_id")
    }
    return {
        "provider": calls[0].get("provider") if calls else None,
        "model": calls[0].get("model") if calls else None,
        "live_qwen_used": bool(
            receipt.get("qwen_generation", {}).get("external_qwen_used")
        ),
        "prompt_versions": sorted(
            {
                f"{item.get('prompt_key')}@{item.get('prompt_version')}"
                for item in calls
            }
        ),
        "provider_attempts": usage.get("provider_attempts"),
        "logical_calls": usage.get("logical_calls"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "wall_time_seconds": usage.get("wall_time_seconds"),
        "calls": calls,
        "evidence": {
            "corpus_snapshot_id": evidence.get("corpus_snapshot_id"),
            "bundle_id": evidence.get("bundle_id"),
            "hit_count": len(evidence.get("evidence_hits") or []),
            "unique_document_count": len(document_ids),
            "all_plan_references_inside_bundle": receipt.get("search", {}).get(
                "all_plan_references_inside_bundle"
            ),
        },
        "plan": {
            key: plan.get(key)
            for key in (
                "field_label",
                "stream_label",
                "gap_title",
                "gap_statement",
                "candidate_research_question",
                "hypothesis_title",
                "hypothesis_statement",
                "falsifiable_form",
                "required_inputs",
                "blocking_questions",
                "scores",
            )
        },
        "consistency_review": (
            (generation.get("consistency_reviews") or [None])[-1]
        ),
        "execution_readiness": generation.get("execution_readiness"),
    }


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    generation = _load_object(args.generation)
    receipt = _load_object(args.receipt)
    specs = {
        "mechanism": args.spec_dir / "figure_1_mechanism.json",
        "event_study": args.spec_dir / "figure_2_event_study.json",
        "robustness": args.spec_dir / "figure_3_robustness.json",
    }
    raw_specs = {name: _load_object(path) for name, path in specs.items()}
    requests = [
        _mechanism_request(raw_specs["mechanism"], specs["mechanism"], args.generation),
        _event_study_request(raw_specs["event_study"], specs["event_study"], args.generation),
        _coefficient_request(raw_specs["robustness"], specs["robustness"], args.generation),
    ]
    renderer = ChineseEconJournalFigureRenderer(args.output_dir)
    bundles = [await renderer.render(request) for request in requests]
    manifest = {
        "schema_version": "carbon-market-qwen-showcase/1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "succeeded",
        "scientific_execution_status": "demo_not_executed",
        "disclosure": (
            "研究发现与一致性审阅由百炼 Qwen 实时生成；图形数值来自明确标注的"
            "预置演示规格，不代表授权数据上的正式统计执行。"
        ),
        "qwen": _sanitized_qwen_summary(generation, receipt),
        "figures": [bundle.model_dump(mode="json") for bundle in bundles],
        "source_hashes": {
            "qwen_generation_sha256": _sha256(args.generation),
            "qwen_receipt_sha256": _sha256(args.receipt),
            **{
                f"{name}_spec_sha256": _sha256(path)
                for name, path in specs.items()
            },
        },
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render the carbon-market Qwen showcase through the backend figure Skill."
    )
    parser.add_argument("--generation", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--spec-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    result = asyncio.run(_run(args))
    print(
        json.dumps(
            {
                "status": result["status"],
                "model": result["qwen"]["model"],
                "figure_count": len(result["figures"]),
                "manifest": str(args.manifest),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
