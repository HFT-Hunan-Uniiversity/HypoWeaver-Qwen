#!/usr/bin/env python3
"""Run deterministic positive and negative controls for H1 input readiness."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT
sys.path.insert(0, str(PROJECT / "backend" / "src"))

from hypoweaver.discovery_planner import (  # noqa: E402
    DiscoveryResearcherContext,
    compile_execution_readiness,
)
from hypoweaver.models import (  # noqa: E402
    DiscoveryDatasetField,
    DiscoveryDatasetResource,
    DiscoveryPlan,
    QuestionPlanConsistencyReview,
)


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def reviewed_plan(generation: dict[str, Any]) -> DiscoveryPlan:
    payload = dict(generation["plan"])
    if not payload.get("identification_strategies"):
        evidence_hits = generation["evidence_bundle"].get("evidence_hits") or []
        if not evidence_hits:
            raise ValueError("generation has no evidence hit for the control strategy")
        payload["identification_strategies"] = [
            {
                "key": "readiness_control_identification",
                "label": "Frozen panel identification contract",
                "description": (
                    "A deterministic H1 contract fixture used only to verify that complete "
                    "data metadata and variable bindings can pass the readiness compiler."
                ),
                "evidence_chunk_ids": [evidence_hits[0]["chunk_id"]],
            }
        ]
    return DiscoveryPlan.model_validate(payload)


def dataset_resource(path: Path, plan: DiscoveryPlan) -> DiscoveryDatasetResource:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        rows = list(reader)
    if not rows:
        raise ValueError("readiness fixture must contain at least one row")
    required_construct_keys = {item.key for item in plan.constructs}
    missing_headers = sorted(required_construct_keys - set(headers))
    if missing_headers:
        raise ValueError("fixture is missing construct fields: " + ", ".join(missing_headers))
    constructs = {item.key: item for item in plan.constructs}
    fields: list[DiscoveryDatasetField] = []
    for header in headers:
        construct = constructs.get(header)
        if construct is not None:
            fields.append(
                DiscoveryDatasetField(
                    name=header,
                    label=construct.label,
                    aliases=[construct.key],
                    role=construct.role,
                )
            )
        else:
            role = "time" if header == "year" else "id" if header.endswith("_id") else "other"
            fields.append(
                DiscoveryDatasetField(name=header, label=header, role=role)
            )
    return DiscoveryDatasetResource(
        resource_id="synthetic-readiness-contract-panel-v1",
        label="Synthetic firm-region-year readiness contract panel",
        filename=path.name,
        mime_type="text/csv",
        sha256=file_sha256(path),
        size_bytes=path.stat().st_size,
        license_status="verified_open",
        license_id="CC0-1.0",
        granularity="firm-region-year",
        time_key="year",
        join_keys=["firm_id", "region_id"],
        fields=fields,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--generation",
        type=Path,
        default=(
            ROOT
            / "output"
            / "experiments"
            / "ai_scientist_system_capability_v2"
            / "cells"
            / "Q01_green_patent_quality__seed_20260901"
            / "generation.json"
        ),
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=ROOT / "experiments" / "fixtures" / "readiness_contract_panel_v1.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            ROOT
            / "output"
            / "experiments"
            / "execution_readiness_contract_control_v1"
            / "result.json"
        ),
    )
    args = parser.parse_args()

    generation = load_object(args.generation)
    plan = reviewed_plan(generation)
    review = QuestionPlanConsistencyReview(
        decision="pass",
        exposure_preserved=True,
        outcome_preserved=True,
        qualifiers_preserved=True,
        rationale=(
            "The frozen source plan already passed the online consistency gate; this control "
            "changes only synthetic input-contract metadata."
        ),
    )
    negative = compile_execution_readiness(
        plan,
        DiscoveryResearcherContext(unit_of_analysis="firm-region-year"),
        consistency_review=review,
    )
    resource = dataset_resource(args.fixture, plan)
    positive = compile_execution_readiness(
        plan,
        DiscoveryResearcherContext(
            unit_of_analysis="firm-region-year",
            dataset_resources=[resource],
        ),
        consistency_review=review,
    )
    if negative.can_execute or negative.status != "blocked":
        raise AssertionError("negative control did not fail closed")
    if not positive.can_execute or positive.status != "ready":
        raise AssertionError("complete positive contract did not become ready")

    output = {
        "schema_version": "execution-readiness-contract-control/1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "deterministic compiler contract test; not scientific execution",
        "source_generation": {
            "path": str(args.generation.resolve()),
            "sha256": file_sha256(args.generation),
            "bundle_id": generation["evidence_bundle"]["bundle_id"],
        },
        "synthetic_fixture": {
            "path": str(args.fixture.resolve()),
            "sha256": resource.sha256,
            "size_bytes": resource.size_bytes,
            "license_id": resource.license_id,
        },
        "negative_control": negative.model_dump(mode="json"),
        "positive_control": positive.model_dump(mode="json"),
        "assertions": {
            "missing_contract_is_blocked": True,
            "complete_contract_is_ready": True,
            "no_statistics_executed": True,
            "no_scientific_claim_authorized": True,
        },
    }
    atomic_json(args.output, output)
    print(
        json.dumps(
            {
                "negative": negative.status,
                "positive": positive.status,
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
