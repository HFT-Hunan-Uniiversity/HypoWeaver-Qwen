"""H0 approval and generic Discovery Engine -> H1 workflow handoff."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import Field

from .discovery_pipeline import DiscoveryBuildRequest, DiscoveryReleasePreview
from .models import (
    CaseSubmission,
    CreateRunRequest,
    DatasetRef,
    DesignEnvelope,
    DiscoveryExecutionReadiness,
    Hypothesis,
    IntakeReadiness,
    RunState,
    StrictModel,
    UpstreamProvenance,
    VariableSpec,
)


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


class DiscoveryLaunchRequest(StrictModel):
    build: DiscoveryBuildRequest
    hypothesis_id: str = Field(min_length=1)
    approve_h0: Literal[True]
    approval_reason: str = Field(min_length=10, max_length=4000)
    mode: Literal["research", "fixture"] = "research"
    research_model_provider: Literal["qwen", "code_owned"] = "code_owned"


class DiscoveryRunLaunchResponse(StrictModel):
    discovery_release: DiscoveryReleasePreview
    case_submission: CaseSubmission
    run: RunState


def _selected_card(
    release: DiscoveryReleasePreview,
    hypothesis_id: str,
) -> dict[str, Any]:
    matches = [
        item
        for item in release.hypothesis_cards
        if item.get("hypothesis_id") == hypothesis_id
    ]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one selected hypothesis {hypothesis_id}")
    card = matches[0]
    if card.get("status") == "rejected":
        raise ValueError("a rejected discovery hypothesis cannot enter H1")
    return card


def _direction(card: dict[str, Any]) -> str:
    variables = card.get("variables") if isinstance(card.get("variables"), dict) else {}
    dependent = variables.get("dependent") if isinstance(variables.get("dependent"), list) else []
    candidate = str(dependent[0].get("expected_direction") or "") if dependent else ""
    if candidate in {"positive", "negative", "nonlinear", "heterogeneous"}:
        return candidate
    return "unspecified"


def _variables(
    card: dict[str, Any],
    graph: dict[str, Any],
) -> list[VariableSpec]:
    node_by_id = {item["id"]: item for item in graph.get("nodes", [])}
    groups = {
        "independent": "exposure",
        "dependent": "outcome",
        "mediators": "mediator",
        "moderators": "moderator",
        "controls": "control",
    }
    result: list[VariableSpec] = []
    seen: set[str] = set()
    raw_variables = card.get("variables") if isinstance(card.get("variables"), dict) else {}
    for group, role in groups.items():
        items = raw_variables.get(group)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            node_id = str(item.get("graph_node_id") or "")
            name = node_id.split(":", 1)[-1] if node_id else str(item.get("name") or "")
            if not name or name in seen:
                continue
            seen.add(name)
            node = node_by_id.get(node_id, {})
            evidence_ids = [str(value) for value in node.get("evidence_ids", [])]
            result.append(
                VariableSpec(
                    name=name,
                    label=str(item.get("name") or node.get("label") or name),
                    role=role,  # type: ignore[arg-type]
                    definition=str(
                        item.get("definition")
                        or (node.get("properties") or {}).get("definition")
                        or "Discovery-stage construct requiring H1/H2 operationalization."
                    ),
                    source=", ".join(evidence_ids) or None,
                )
            )
    if not any(item.role == "outcome" for item in result):
        raise ValueError("selected HypothesisCard has no outcome variable")
    return result


def discovery_release_to_case(
    release: DiscoveryReleasePreview,
    *,
    hypothesis_id: str,
    approver: str,
    approval_reason: str,
    execution_readiness: DiscoveryExecutionReadiness | None = None,
) -> CaseSubmission:
    """Create a plan-only CaseSubmission after explicit H0 approval."""

    card = _selected_card(release, hypothesis_id)
    gap_ids = [str(value) for value in card.get("gap_card_ids", [])]
    gap_by_id = {item.get("gap_id"): item for item in release.gap_cards}
    selected_gaps = [gap_by_id[item] for item in gap_ids if item in gap_by_id]
    if not selected_gaps:
        raise ValueError("selected hypothesis has no matching GapCard")
    graph = release.final_research_graph
    node_by_id = {item["id"]: item for item in graph.get("nodes", [])}
    design = card.get("recommended_design") if isinstance(card.get("recommended_design"), dict) else {}
    handoff = card.get("handoff") if isinstance(card.get("handoff"), dict) else {}
    feasibility = card.get("feasibility") if isinstance(card.get("feasibility"), dict) else {}
    evidence_balance = card.get("evidence_balance") if isinstance(card.get("evidence_balance"), dict) else {}
    mechanism_chain = card.get("mechanism_chain") if isinstance(card.get("mechanism_chain"), list) else []
    predictions = card.get("predictions") if isinstance(card.get("predictions"), list) else []
    method_ids = [str(value) for value in design.get("candidate_method_ids", [])]
    identification_ids = [
        str(value)
        for value in design.get("candidate_identification_strategy_ids", [])
    ]
    method_requirements = [
        str(node_by_id.get(item, {}).get("label") or item)
        for item in [*method_ids, *identification_ids]
    ]
    release_blockers = [
        str(value)
        for value in [
            *feasibility.get("blocking_items", []),
            *handoff.get("required_inputs", []),
        ]
        if str(value).strip()
    ]
    blockers = (
        execution_readiness.blockers
        if execution_readiness is not None
        else release_blockers
    )
    warnings = [
        *[str(value) for value in handoff.get("blocking_questions", [])],
        *[str(value) for value in evidence_balance.get("unresolved_conflicts", [])],
        *release.validation_warnings,
    ]
    boundaries = [str(value) for value in card.get("boundary_conditions", [])]
    major_threats = [str(value) for value in design.get("major_threats", [])]
    acceptance = [
        str(value) for value in handoff.get("validation_acceptance_criteria", [])
    ]
    # Evidence IDs in the final graph are the authoritative set; the card refs
    # are retained when they resolve to evidence or novelty identifiers.
    graph_evidence_ids = {item["id"] for item in graph.get("evidence", [])}
    evidence_refs = sorted(
        graph_evidence_ids
        | {
            str(value)
            for value in handoff.get("evidence_bundle_refs", [])
            if str(value).startswith("novelty:")
        }
    )
    release_hash = _canonical_sha256(release.model_dump(mode="json"))
    approval_hash = _canonical_sha256(
        {
            "release_sha256": release_hash,
            "hypothesis_id": hypothesis_id,
            "approver": approver,
            "approval_reason": approval_reason,
        }
    )
    unit = str(design.get("unit_of_analysis") or "").strip() or None
    data_structure = "panel" if unit and "year" in unit.casefold() else "unknown"
    causal = bool(identification_ids)
    source_scope = graph.get("scope") if isinstance(graph.get("scope"), dict) else {}
    years = [source_scope.get("year_start"), source_scope.get("year_end")]
    sample_period = (
        f"Literature coverage {years[0]}-{years[1]}"
        if all(value is not None for value in years)
        else None
    )
    return CaseSubmission(
        case_id=f"discovery:{approval_hash[:24]}",
        title=str(card.get("title") or hypothesis_id),
        research_question=release.evidence_bridge.research_graph["scope"]["themes"][0],
        hypotheses=[
            Hypothesis(
                hypothesis_id=hypothesis_id,
                statement=str(card.get("hypothesis_statement") or ""),
                expected_direction=_direction(card),  # type: ignore[arg-type]
                mechanism=" ".join(
                    str(item.get("statement") or "")
                    for item in mechanism_chain
                    if isinstance(item, dict) and item.get("statement")
                )
                or None,
            )
        ],
        unit_of_analysis=unit,
        sample_period=sample_period,
        data_structure_hint=data_structure,  # type: ignore[arg-type]
        variables=_variables(card, graph),
        dataset_refs=(
            [
                DatasetRef(
                    dataset_id=str(item.resource_id),
                    role="main" if index == 0 else "supplementary",
                    filename=str(item.filename),
                    mime_type=str(item.mime_type or "application/octet-stream"),
                    sha256=str(item.sha256),
                    size_bytes=int(item.size_bytes or 0),
                )
                for index, item in enumerate(execution_readiness.dataset_candidates)
                if item.status == "ready"
                and item.resource_id
                and item.filename
                and item.sha256
                and item.size_bytes
            ]
            if execution_readiness is not None
            else []
        ),
        design_envelope=DesignEnvelope(
            benchmark_track="strict_blind",
            research_goal="causal" if causal else "mixed",
            target_estimands=[
                str(item.get("statement"))
                for item in predictions
                if isinstance(item, dict) and item.get("statement")
            ],
            design_constraints=[*boundaries, *major_threats],
            required_diagnostics=acceptance,
            allowed_claim_strength="causal" if causal else "associational",
        ),
        policy_design=None,
        known_policy_facts=[],
        constraints=[
            *boundaries,
            *major_threats,
            "H0 approval authorizes H1 design review only; it does not authorize scientific claims.",
        ],
        upstream_provenance=UpstreamProvenance(
            source_system="hypoweaver-discovery-engine",
            bridge_version="discovery-to-h1/1.0.0",
            package_id=f"discovery-approved:{approval_hash[:24]}",
            schema_version=release.schema_version,
            generated_at=str(graph.get("as_of") or ""),
            status="h0_approved_for_h1",
            manifest_sha256=release_hash,
            verified_artifact_count=0,
            artifacts=[],
            graph_snapshot_id=str(graph.get("snapshot_id") or "") or None,
            hypothesis_id=hypothesis_id,
            gap_id=gap_ids[0] if gap_ids else None,
            novelty_check_ref=str(card.get("novelty_check_ref") or "") or None,
            evidence_refs=evidence_refs,
            corpus_boundary="corpus_bounded_gap",
        ),
        intake_readiness=IntakeReadiness(
            status=(
                "ready"
                if execution_readiness is not None
                and execution_readiness.can_execute
                else "conditional"
            ),
            can_approve_h1=True,
            can_execute=bool(
                execution_readiness is not None
                and execution_readiness.can_execute
            ),
            blockers=sorted(set(blockers)),
            warnings=sorted(
                set(
                    [
                        *warnings,
                        *(
                            execution_readiness.warnings
                            if execution_readiness is not None
                            else []
                        ),
                    ]
                )
            ),
            required_inputs=sorted(
                {
                    str(value)
                    for value in (
                        execution_readiness.blockers
                        if execution_readiness is not None
                        else handoff.get("required_inputs", [])
                    )
                }
            ),
            method_requirements=method_requirements,
        ),
    )


def create_run_request(
    case: CaseSubmission,
    launch: DiscoveryLaunchRequest,
) -> CreateRunRequest:
    fixture = launch.mode == "fixture"
    return CreateRunRequest(
        mode=launch.mode,
        case=case,
        model_provider="fixture" if fixture else launch.research_model_provider,
        execution_mode="fixture" if fixture else "external",
    )
