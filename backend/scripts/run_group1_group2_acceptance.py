from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from hypoweaver.case_import import DatasetRegistry
from hypoweaver.engine import WorkflowEngine
from hypoweaver.group1_handoff import (
    bind_group1_execution_panel,
    import_group1_handoff,
)
from hypoweaver.models import (
    CreateRunRequest,
    GateDecisionRequest,
    ResearchRun,
    ReproductionAudit,
    RunState,
)
from hypoweaver.repository import RunRepository
from hypoweaver.runtime_config import RuntimeConfigStore


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = PROJECT_ROOT.parents[2]
DEFAULT_HANDOFF = (
    WORKSPACE_ROOT
    / "output"
    / "real_pilot"
    / "2026-08-09_green_finance_decarbonization"
    / "I_group1_handoff"
)
DEFAULT_PANEL = (
    PROJECT_ROOT
    / "backend"
    / "var"
    / "group1_execution"
    / "group1_paired_stacked_panel.csv"
)
DEFAULT_MANIFEST = DEFAULT_PANEL.with_suffix(".manifest.json")
DEFAULT_SOURCE_CONFIG = (
    PROJECT_ROOT / "backend" / "config" / "group1_execution_sources.json"
)
DEFAULT_RECEIPT_ROOT = PROJECT_ROOT / "backend" / "var" / "group1_execution"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the bound Group 1 -> Group 2 workflow through H4 sealing."
    )
    parser.add_argument("--handoff", type=Path, default=DEFAULT_HANDOFF)
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--source-config", type=Path, default=DEFAULT_SOURCE_CONFIG)
    parser.add_argument("--run-id")
    parser.add_argument(
        "--research-engine-url",
        default=os.getenv("RESEARCH_ENGINE_URL", "http://127.0.0.1:8001"),
    )
    return parser.parse_args()


def _gate_hashes(engine: WorkflowEngine, state: RunState, gate: str) -> dict[str, str]:
    return engine._gate_artifact_hashes(state, gate)  # noqa: SLF001


def _candidate_id(state: RunState) -> str:
    arena = state.artifacts.get("design_arena", {}).get("payload", {})
    recommended = arena.get("recommended_candidate_ids", [])
    if not recommended:
        diagnostics = {
            candidate.get("candidate_id"): {
                "probe": candidate.get("probe_report", {}).get("verdict"),
                "executor_ready": candidate.get("probe_report", {}).get(
                    "executor_ready"
                ),
            }
            for candidate in arena.get("candidates", [])
        }
        raise RuntimeError(
            "H2 has no recommended executable candidate: "
            + json.dumps(diagnostics, ensure_ascii=False, sort_keys=True)
        )
    return str(recommended[0])


def _receipt(state: RunState) -> dict[str, Any]:
    primary_payload = state.artifacts.get("research_run", {}).get("payload")
    reproduction_payload = state.artifacts.get("reproduction_audit", {}).get(
        "payload"
    )
    contract_payload = state.artifacts.get("formal_research_contract", {}).get(
        "payload", {}
    )
    primary = (
        ResearchRun.model_validate(primary_payload)
        if isinstance(primary_payload, dict)
        else None
    )
    reproduction = (
        ReproductionAudit.model_validate(reproduction_payload)
        if isinstance(reproduction_payload, dict)
        else None
    )
    sign_switch: dict[str, Any] | None = None
    support: dict[str, Any] | None = None
    if primary is not None:
        for execution in primary.executions:
            if execution.plan_step_id == "check-group1-sign-switch":
                sign_switch = {
                    "status": execution.diagnostic_results.get(
                        "paired_sign_switch_status"
                    ),
                    "reason": execution.diagnostic_results.get(
                        "paired_sign_switch_reason"
                    ),
                    "outcomes": execution.diagnostic_results.get(
                        "paired_outcome_assessments"
                    ),
                }
            if execution.plan_step_id == "check-group1-support":
                support = {
                    "scientific_release_ready": execution.diagnostic_results.get(
                        "scientific_release_ready"
                    ),
                    "treated_entities_by_cohort": execution.diagnostic_results.get(
                        "treated_entities_by_cohort"
                    ),
                    "cohorts_below_scientific_minimum": execution.diagnostic_results.get(
                        "cohorts_below_scientific_treated_entity_minimum"
                    ),
                    "prefecture_proxy_treated_entities": execution.diagnostic_results.get(
                        "prefecture_proxy_treated_entities"
                    ),
                }
    return {
        "schema_version": "group1-group2-acceptance-receipt-v1",
        "workflow_run_id": state.id,
        "case_id": state.case_id,
        "status": state.status,
        "current_gate": state.current_gate,
        "model_provider": state.model_provider,
        "execution_mode": state.execution_mode,
        "execution_status": state.execution_status,
        "scientific_status": state.scientific_status,
        "plan_only": state.plan_only,
        "version": state.version,
        "selected_candidate_id": (
            state.decisions[-1].selected_candidate_id
            if state.decisions and state.decisions[-1].selected_candidate_id
            else next(
                (
                    decision.selected_candidate_id
                    for decision in state.decisions
                    if decision.selected_candidate_id
                ),
                None,
            )
        ),
        "gate_decisions": [
            {
                "gate": decision.gate,
                "action": decision.action,
                "actor": decision.actor,
                "created_at": decision.created_at,
                "claim_decisions": decision.claim_decisions,
            }
            for decision in state.decisions
        ],
        "data_hashes": (
            list(contract_payload.get("data_hashes", []))
            if isinstance(contract_payload, dict)
            else []
        ),
        "artifact_hashes": {
            key: str(envelope.get("sha256"))
            for key, envelope in state.artifacts.items()
            if isinstance(envelope, dict) and envelope.get("sha256")
        },
        "primary_research_run_id": (
            primary.research_run_id if primary is not None else None
        ),
        "primary_execution_steps": (
            [
                {
                    "plan_step_id": execution.plan_step_id,
                    "status": execution.execution_status,
                    "estimate_count": len(execution.estimates),
                    "implementation_id": (
                        execution.provenance.implementation_id
                        if execution.provenance is not None
                        else None
                    ),
                }
                for execution in primary.executions
            ]
            if primary is not None
            else []
        ),
        "reproduction": (
            {
                "audit_id": reproduction.audit_id,
                "replication_run_id": reproduction.replication_run_id,
                "status": reproduction.status,
                "independence_scope": reproduction.independence_scope,
                "primary_implementation_id": reproduction.primary_implementation_id,
                "replication_implementation_id": reproduction.replication_implementation_id,
                "covered_plan_step_ids": reproduction.covered_plan_step_ids,
                "differences": reproduction.differences,
            }
            if reproduction is not None
            else None
        ),
        "support_gate": support,
        "sign_switch_gate": sign_switch,
        "claim_admission": [
            {
                "claim_id": claim.claim_id,
                "admission_status": claim.admission_status,
                "allowed_strength": claim.allowed_strength,
                "evidence_status": claim.evidence_status,
                "approval_status": claim.approval_status,
                "human_decision_reason": claim.human_decision_reason,
            }
            for claim in state.claims
        ],
        "sealed_output": state.artifacts.get("sealed_output", {}).get("payload"),
        "last_error": state.last_error,
    }


def _write_receipt(state: RunState) -> Path:
    DEFAULT_RECEIPT_ROOT.mkdir(parents=True, exist_ok=True)
    payload = _receipt(state)
    run_path = DEFAULT_RECEIPT_ROOT / f"acceptance-{state.id}.json"
    latest_path = DEFAULT_RECEIPT_ROOT / "acceptance-latest.json"
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    run_path.write_text(rendered, encoding="utf-8")
    latest_path.write_text(rendered, encoding="utf-8")
    return run_path


async def _run(args: argparse.Namespace) -> RunState:
    os.environ["RESEARCH_ENGINE_URL"] = str(args.research_engine_url).rstrip("/")
    bridge = bind_group1_execution_panel(
        import_group1_handoff(args.handoff),
        args.panel,
        args.manifest,
        args.source_config,
    )
    registry = DatasetRegistry()
    main_ref = bridge.case_submission.dataset_refs[0]
    registry.register(main_ref, args.panel.resolve(strict=True))
    repository = RunRepository()
    engine = WorkflowEngine(
        repository,
        dataset_registry=registry,
        runtime_config_store=RuntimeConfigStore(),
    )
    if args.run_id:
        state = engine.get_run(args.run_id)
    else:
        state = await engine.create_run(
            CreateRunRequest(
                mode="research",
                case=bridge.case_submission,
                model_provider="code_owned",
                execution_mode="external",
            )
        )
        _write_receipt(state)

    if state.status == "waiting_human" and state.current_gate == "H1":
        state = await engine.decide_gate(
            state.id,
            "H1",
            GateDecisionRequest(
                action="approve",
                actor="codex_backend_acceptance",
                comment="Approve the verified Group 1 evidence and bound execution panel for H2 design freeze.",
                expected_run_version=state.version,
                idempotency_key=f"{state.id}-accept-h1-v1",
                reviewed_artifact_hashes=_gate_hashes(engine, state, "H1"),
            ),
        )
        _write_receipt(state)

    if state.status == "waiting_human" and state.current_gate == "H2":
        selected = _candidate_id(state)
        state = await engine.decide_gate(
            state.id,
            "H2",
            GateDecisionRequest(
                action="approve",
                actor="codex_backend_acceptance",
                comment="Freeze the code-owned paired stacked-DDD candidate and execute it through the external Research Engine.",
                expected_run_version=state.version,
                idempotency_key=f"{state.id}-accept-h2-v1",
                reviewed_artifact_hashes=_gate_hashes(engine, state, "H2"),
                selected_candidate_id=selected,
            ),
        )
        _write_receipt(state)

    if state.status == "waiting_human" and state.current_gate == "H3":
        state = await engine.decide_gate(
            state.id,
            "H3",
            GateDecisionRequest(
                action="generate_identification_failure_report",
                actor="codex_backend_acceptance",
                comment=(
                    "The engineering execution and independent reproduction completed, "
                    "but the scientific-support and paired sign-switch gates do not admit a causal claim."
                ),
                expected_run_version=state.version,
                idempotency_key=f"{state.id}-accept-h3-v1",
                reviewed_artifact_hashes=_gate_hashes(engine, state, "H3"),
                claims=[
                    {
                        "claim_id": claim.claim_id,
                        "decision": "reject",
                        "reason": "Rejected by the code-owned evidence and scientific-release gates.",
                    }
                    for claim in state.claims
                ],
            ),
        )
        _write_receipt(state)

    if state.status == "waiting_human" and state.current_gate == "H4":
        state = await engine.decide_gate(
            state.id,
            "H4",
            GateDecisionRequest(
                action="approve",
                actor="codex_backend_acceptance",
                comment="Approve and seal the executed-but-not-admissible identification-failure delivery.",
                expected_run_version=state.version,
                idempotency_key=f"{state.id}-accept-h4-v1",
                reviewed_artifact_hashes=_gate_hashes(engine, state, "H4"),
            ),
        )
        _write_receipt(state)

    if state.status != "completed":
        _write_receipt(state)
        raise RuntimeError(
            f"workflow did not complete: status={state.status}, gate={state.current_gate}, error={state.last_error}"
        )
    return state


def main() -> None:
    args = _arguments()
    state = asyncio.run(_run(args))
    receipt_path = _write_receipt(state)
    print(
        json.dumps(
            {
                "workflow_run_id": state.id,
                "status": state.status,
                "execution_status": state.execution_status,
                "scientific_status": state.scientific_status,
                "receipt": str(receipt_path),
                "seal_sha256": state.artifacts["sealed_output"]["payload"][
                    "seal_sha256"
                ],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
