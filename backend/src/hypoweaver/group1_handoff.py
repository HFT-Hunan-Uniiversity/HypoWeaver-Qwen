from __future__ import annotations

import hashlib
import csv
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from .models import (
    CaseSubmission,
    DatasetRef,
    DesignEnvelope,
    Group2DataFeasibilityItem,
    Group2FeasibilityPackage,
    Group2MethodFeasibilityItem,
    Hypothesis,
    IntakeReadiness,
    RunState,
    ScientificTenItem,
    StrictModel,
    UpstreamArtifactRef,
    UpstreamProvenance,
    VariableSpec,
)


BRIDGE_VERSION = "group1-to-group2-v2"
MAX_JSON_BYTES = 32 * 1024 * 1024
PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _default_workspace_root(project_root: Path) -> Path:
    """Keep legacy workspace discovery without failing in shallow containers."""

    return project_root.parents[2] if len(project_root.parents) > 2 else project_root


WORKSPACE_ROOT = _default_workspace_root(PROJECT_ROOT)


class Group1HandoffError(ValueError):
    pass


class Group1LocalHandoffRequest(StrictModel):
    path: str
    mode: Literal["research", "fixture"] = "research"
    research_model_provider: Literal["qwen", "code_owned"] = "code_owned"
    execution_panel_path: str | None = None
    execution_manifest_path: str | None = None
    source_config_path: str | None = None


class Group1IntegrityReport(StrictModel):
    status: Literal["passed"] = "passed"
    handoff_id: str
    manifest_sha256: str
    verified_artifact_count: int
    verified_artifacts: list[UpstreamArtifactRef]


class Group1EvidenceBundle(StrictModel):
    handoff_id: str
    hypothesis_id: str
    gap_id: str
    graph_snapshot_id: str | None = None
    novelty_check_ref: str | None = None
    evidence_refs: list[str]
    corpus_boundary: str
    artifact_refs: list[UpstreamArtifactRef]


class Group1BridgeResult(StrictModel):
    bridge_version: str = BRIDGE_VERSION
    case_submission: CaseSubmission
    evidence_bundle: Group1EvidenceBundle
    integrity: Group1IntegrityReport
    feasibility: IntakeReadiness
    group2_feasibility_package: Group2FeasibilityPackage


class Group1RunLaunchResponse(StrictModel):
    bridge: Group1BridgeResult
    run: RunState


class Group1VerifiedBundleStatus(StrictModel):
    status: Literal["ready", "unavailable", "invalid"]
    message: str
    bundle_id: str | None = None
    label: str | None = None
    handoff_id: str | None = None
    handoff_manifest_sha256: str | None = None
    verified_artifact_count: int = 0
    dataset_filename: str | None = None
    dataset_sha256: str | None = None
    dataset_size_bytes: int | None = None
    panel_rows: int | None = None
    panel_columns: int | None = None
    source_config_sha256: str | None = None
    acceptance_run_id: str | None = None
    acceptance_seal_sha256: str | None = None
    verified_at: str | None = None
    execution_status: str | None = None
    scientific_status: str | None = None
    reproduction_status: str | None = None
    reproduction_scope: str | None = None
    model_provider: Literal["code_owned"] = "code_owned"
    execution_mode: Literal["external"] = "external"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        size = path.stat().st_size
    except OSError as error:
        raise Group1HandoffError(f"cannot inspect Group 1 artifact: {path.name}") from error
    if size > MAX_JSON_BYTES:
        raise Group1HandoffError(
            f"Group 1 JSON artifact exceeds the {MAX_JSON_BYTES}-byte bridge limit: {path.name}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Group1HandoffError(f"invalid Group 1 JSON artifact: {path.name}") from error
    if not isinstance(payload, dict):
        raise Group1HandoffError(f"Group 1 artifact must contain a JSON object: {path.name}")
    return payload


def _configured_path(environment_name: str, default: Path) -> Path:
    configured = os.getenv(environment_name, "").strip()
    return Path(configured).expanduser() if configured else default


def _verified_bundle_request_from_paths() -> Group1LocalHandoffRequest:
    handoff = _configured_path(
        "HYPOWEAVER_GROUP1_HANDOFF_PATH",
        WORKSPACE_ROOT
        / "output"
        / "real_pilot"
        / "2026-08-09_green_finance_decarbonization"
        / "I_group1_handoff",
    )
    panel = _configured_path(
        "HYPOWEAVER_GROUP1_EXECUTION_PANEL_PATH",
        PROJECT_ROOT
        / "backend"
        / "var"
        / "group1_execution"
        / "group1_paired_stacked_panel.csv",
    )
    manifest = _configured_path(
        "HYPOWEAVER_GROUP1_EXECUTION_MANIFEST_PATH",
        panel.with_suffix(".manifest.json"),
    )
    source_config = _configured_path(
        "HYPOWEAVER_GROUP1_SOURCE_CONFIG_PATH",
        PROJECT_ROOT / "backend" / "config" / "group1_execution_sources.json",
    )
    return Group1LocalHandoffRequest(
        path=str(handoff),
        mode="research",
        research_model_provider="code_owned",
        execution_panel_path=str(panel),
        execution_manifest_path=str(manifest),
        source_config_path=str(source_config),
    )


def _verified_acceptance_receipt_path() -> Path:
    return _configured_path(
        "HYPOWEAVER_GROUP1_ACCEPTANCE_RECEIPT_PATH",
        PROJECT_ROOT
        / "backend"
        / "var"
        / "group1_execution"
        / "acceptance-latest.json",
    )


def inspect_verified_group1_bundle() -> Group1VerifiedBundleStatus:
    request = _verified_bundle_request_from_paths()
    receipt_path = _verified_acceptance_receipt_path()
    required_paths = {
        "Group1 handoff": Path(request.path),
        "execution panel": Path(request.execution_panel_path or ""),
        "execution manifest": Path(request.execution_manifest_path or ""),
        "source config": Path(request.source_config_path or ""),
        "acceptance receipt": receipt_path,
    }
    missing = [label for label, path in required_paths.items() if not path.exists()]
    if missing:
        return Group1VerifiedBundleStatus(
            status="unavailable",
            message="Missing local verified-bundle assets: " + ", ".join(missing),
        )

    try:
        bridge = bind_group1_execution_panel(
            import_group1_handoff(request.path),
            request.execution_panel_path or "",
            request.execution_manifest_path or "",
            request.source_config_path or "",
        )
        panel_path = Path(request.execution_panel_path or "").resolve(strict=True)
        manifest_path = Path(request.execution_manifest_path or "").resolve(strict=True)
        source_config_path = Path(request.source_config_path or "").resolve(strict=True)
        manifest = _load_json(manifest_path)
        receipt = _load_json(receipt_path.resolve(strict=True))
        output = manifest.get("output")
        if not isinstance(output, dict):
            raise Group1HandoffError("execution-panel manifest has no output binding")
        panel_sha256 = _sha256(panel_path)
        if receipt.get("schema_version") != "group1-group2-acceptance-receipt-v1":
            raise Group1HandoffError("unsupported Group1→Group2 acceptance receipt")
        if receipt.get("status") != "completed" or receipt.get("execution_status") != "succeeded":
            raise Group1HandoffError("the latest Group1→Group2 acceptance run did not complete successfully")
        if panel_sha256 not in [str(value) for value in receipt.get("data_hashes", [])]:
            raise Group1HandoffError("acceptance receipt is not bound to the current execution panel")
        reproduction = receipt.get("reproduction")
        if not isinstance(reproduction, dict) or reproduction.get("status") != "matched":
            raise Group1HandoffError("the latest acceptance receipt has no matched reproduction")
        sealed_output = receipt.get("sealed_output")
        if not isinstance(sealed_output, dict) or not sealed_output.get("seal_sha256"):
            raise Group1HandoffError("the latest acceptance receipt has no H4 seal")
        source_config_sha256 = _sha256(source_config_path)
        identity = ":".join(
            [
                bridge.integrity.manifest_sha256,
                panel_sha256,
                source_config_sha256,
                str(receipt.get("workflow_run_id", "")),
            ]
        )
        return Group1VerifiedBundleStatus(
            status="ready",
            message="The hash-bound Group1 execution bundle passed the recorded H1–H4 acceptance run.",
            bundle_id=f"group1-verified:{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}",
            label=bridge.case_submission.title,
            handoff_id=bridge.integrity.handoff_id,
            handoff_manifest_sha256=bridge.integrity.manifest_sha256,
            verified_artifact_count=bridge.integrity.verified_artifact_count,
            dataset_filename=panel_path.name,
            dataset_sha256=panel_sha256,
            dataset_size_bytes=panel_path.stat().st_size,
            panel_rows=int(output.get("rows", 0)),
            panel_columns=int(output.get("columns", 0)),
            source_config_sha256=source_config_sha256,
            acceptance_run_id=str(receipt.get("workflow_run_id", "")) or None,
            acceptance_seal_sha256=str(sealed_output.get("seal_sha256", "")) or None,
            verified_at=datetime.fromtimestamp(
                receipt_path.stat().st_mtime,
                tz=timezone.utc,
            ).isoformat(),
            execution_status=str(receipt.get("execution_status", "")) or None,
            scientific_status=str(receipt.get("scientific_status", "")) or None,
            reproduction_status=str(reproduction.get("status", "")) or None,
            reproduction_scope=str(reproduction.get("independence_scope", "")) or None,
        )
    except (OSError, TypeError, ValueError) as error:
        return Group1VerifiedBundleStatus(
            status="invalid",
            message=str(error),
        )


def verified_group1_bundle_request() -> Group1LocalHandoffRequest:
    status = inspect_verified_group1_bundle()
    if status.status != "ready":
        raise Group1HandoffError(status.message)
    return _verified_bundle_request_from_paths()


def _package_roots(path: str | Path) -> tuple[Path, Path]:
    requested = Path(path).expanduser()
    try:
        resolved = requested.resolve(strict=True)
    except OSError as error:
        raise Group1HandoffError("Group 1 handoff path does not exist") from error
    if not resolved.is_dir():
        raise Group1HandoffError("Group 1 handoff path must be a directory")
    direct_manifest = resolved / "manifest.json"
    direct_handoff = resolved / "handoff.json"
    if direct_manifest.is_file() and direct_handoff.is_file():
        return resolved.parent, resolved
    handoff_dir = resolved / "I_group1_handoff"
    if (handoff_dir / "manifest.json").is_file() and (handoff_dir / "handoff.json").is_file():
        return resolved, handoff_dir
    raise Group1HandoffError(
        "expected either a Group 1 pilot root or its I_group1_handoff directory"
    )


def _safe_artifact_path(base: Path, relative: str) -> Path:
    posix = PurePosixPath(relative.replace("\\", "/"))
    if (
        not relative.strip()
        or posix.is_absolute()
        or ".." in posix.parts
        or re.match(r"^[A-Za-z]:", relative)
    ):
        raise Group1HandoffError(f"unsafe Group 1 artifact path: {relative!r}")
    try:
        candidate = base.joinpath(*posix.parts).resolve(strict=True)
    except OSError as error:
        raise Group1HandoffError(f"missing Group 1 artifact: {relative}") from error
    resolved_base = base.resolve(strict=True)
    if candidate != resolved_base and resolved_base not in candidate.parents:
        raise Group1HandoffError(f"Group 1 artifact escapes package root: {relative}")
    if not candidate.is_file():
        raise Group1HandoffError(f"Group 1 artifact is not a file: {relative}")
    return candidate


def _verify_manifest(
    pilot_root: Path,
    handoff_dir: Path,
) -> tuple[dict[str, Any], Group1IntegrityReport, dict[str, Path]]:
    manifest_path = handoff_dir / "manifest.json"
    manifest = _load_json(manifest_path)
    handoff = _load_json(handoff_dir / "handoff.json")
    if manifest.get("handoff_id") != handoff.get("handoff_id"):
        raise Group1HandoffError("manifest handoff_id does not match handoff.json")

    verified: list[UpstreamArtifactRef] = []
    resolved_by_name: dict[str, Path] = {}
    groups = (
        (manifest.get("artifacts"), handoff_dir, "I_group1_handoff"),
        (manifest.get("source_artifacts"), pilot_root, ""),
    )
    for entries, base, prefix in groups:
        if not isinstance(entries, list):
            raise Group1HandoffError("manifest artifact lists are missing or invalid")
        for raw in entries:
            if not isinstance(raw, dict):
                raise Group1HandoffError("manifest artifact entry must be an object")
            name = str(raw.get("name", "")).strip()
            relative = str(raw.get("path", "")).strip()
            expected = str(raw.get("sha256", "")).strip().lower()
            if not name or not re.fullmatch(r"[a-f0-9]{64}", expected):
                raise Group1HandoffError("manifest artifact name or sha256 is invalid")
            if name in resolved_by_name:
                raise Group1HandoffError(f"duplicate Group 1 artifact name: {name}")
            artifact_path = _safe_artifact_path(base, relative)
            actual = _sha256(artifact_path)
            if actual != expected:
                raise Group1HandoffError(f"Group 1 artifact hash mismatch: {name}")
            public_path = str(PurePosixPath(prefix) / PurePosixPath(relative)) if prefix else str(PurePosixPath(relative))
            reference = UpstreamArtifactRef(name=name, path=public_path, sha256=actual)
            verified.append(reference)
            resolved_by_name[name] = artifact_path

    report = Group1IntegrityReport(
        handoff_id=str(handoff["handoff_id"]),
        manifest_sha256=_sha256(manifest_path),
        verified_artifact_count=len(verified),
        verified_artifacts=verified,
    )
    return handoff, report, resolved_by_name


def _unique_strings(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _variable_name(label: str) -> str:
    aliases = {
        "ESG greenwashing gap": "greenwashing_gap",
        "Firm emission intensity": "firm_emission_intensity",
        "GFRIPZ exposure": "gfripz_exposure",
        "R&D expenditure": "rd_expenditure",
        "Granted patent count": "green_patent_count",
        "Environmental-investment efficiency (EPIE)": "epie",
        "Pre-policy regional digital/fintech capacity": "prepolicy_digital_fintech_capacity",
    }
    if label in aliases:
        return aliases[label]
    normalized = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return normalized or "unmapped_variable"


def _variables(card: dict[str, Any]) -> list[VariableSpec]:
    raw_variables = card.get("variables")
    if not isinstance(raw_variables, dict):
        raise Group1HandoffError("HypothesisCard variables are missing")
    role_map = {
        "dependent": "outcome",
        "independent": "treatment",
        "mediators": "mediator",
        "moderators": "moderator",
        "controls": "control",
    }
    result: list[VariableSpec] = [
        VariableSpec(
            name="firm_id",
            label="Firm identifier",
            role="id",
            definition="Stable listed-firm identifier used for the firm-year panel.",
            source="Required Group 2 join key; not supplied by Group 1.",
        ),
        VariableSpec(
            name="year",
            label="Year",
            role="time",
            definition="Firm-year observation year.",
            source="Required Group 2 time key; not supplied by Group 1.",
        ),
        VariableSpec(
            name="region_id",
            label="Pilot-region identifier",
            role="spatial_id",
            definition="Region used to bind firms to GFRIPZ designation and spillover exposure.",
            source="Required Group 2 policy crosswalk; not supplied by Group 1.",
        ),
        VariableSpec(
            name="treatment_cohort_year",
            label="GFRIPZ treatment cohort year",
            role="event_date",
            definition="First policy-treatment year for the firm's linked pilot region.",
            source="Required Group 2 policy-timing crosswalk; not supplied by Group 1.",
        ),
    ]
    for group, role in role_map.items():
        entries = raw_variables.get(group, [])
        if not isinstance(entries, list):
            raise Group1HandoffError(f"HypothesisCard variable group is invalid: {group}")
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            label = str(entry.get("name", "")).strip()
            if not label:
                continue
            graph_id = str(entry.get("graph_node_id", "")).strip()
            result.append(
                VariableSpec(
                    name=_variable_name(label),
                    label=label,
                    role=role,  # type: ignore[arg-type]
                    definition=str(entry.get("definition", "")).strip() or None,
                    source=f"Group 1 HypothesisCard {graph_id}".strip(),
                )
            )
    if not any(variable.role == "outcome" for variable in result):
        raise Group1HandoffError("HypothesisCard does not define an outcome")
    return result


def _hypotheses(card: dict[str, Any]) -> list[Hypothesis]:
    main_id = str(card.get("hypothesis_id", "")).strip()
    statement = str(card.get("hypothesis_statement", "")).strip()
    if not main_id or not statement:
        raise Group1HandoffError("HypothesisCard main hypothesis is incomplete")
    result = [
        Hypothesis(
            hypothesis_id=main_id,
            statement=statement,
            expected_direction="heterogeneous",
            mechanism=str(card.get("falsifiable_form", "")).strip() or None,
        )
    ]
    predictions = card.get("predictions", [])
    if not isinstance(predictions, list):
        raise Group1HandoffError("HypothesisCard predictions are invalid")
    for prediction in predictions:
        if not isinstance(prediction, dict):
            continue
        prediction_id = str(prediction.get("prediction_id", "")).strip()
        prediction_statement = str(prediction.get("statement", "")).strip()
        if not prediction_id or not prediction_statement:
            continue
        observable = str(prediction.get("observable_pattern", "")).strip()
        falsifier = str(prediction.get("would_falsify", "")).strip()
        result.append(
            Hypothesis(
                hypothesis_id=prediction_id,
                statement=prediction_statement,
                expected_direction=(
                    "positive"
                    if prediction_id == "prediction:capacity_separates_innovation_epie"
                    else "heterogeneous"
                ),
                mechanism=" ".join(
                    part
                    for part in (
                        f"Observable: {observable}" if observable else "",
                        f"Falsified by: {falsifier}" if falsifier else "",
                    )
                    if part
                )
                or None,
            )
        )
    return result


def _group2_data_matrix(card: dict[str, Any]) -> list[Group2DataFeasibilityItem]:
    raw_variables = card.get("variables")
    if not isinstance(raw_variables, dict):
        raise Group1HandoffError("HypothesisCard variables are missing")
    role_labels = {
        "independent": "treatment",
        "moderators": "moderator",
        "dependent": "outcome",
        "mediators": "mechanism",
        "controls": "control",
    }
    next_actions = {
        "GFRIPZ exposure": "Validate the open policy source and build a firm-to-region-to-cohort crosswalk.",
        "Pre-policy regional digital/fintech capacity": "Select and freeze a baseline window that strictly predates each treatment cohort.",
        "ESG greenwashing gap": "Confirm licensing, disclosure coverage and one preregistered gap construction.",
        "Firm emission intensity": "Acquire a licensed firm-year emissions panel and preregister defensible scale denominators.",
        "R&D expenditure": "Confirm firm-year coverage and accounting comparability across treatment cohorts.",
        "Granted patent count": "Freeze green-patent taxonomy, grant/application choice and lag structure.",
        "Environmental-investment efficiency (EPIE)": "Verify that EPIE is separable from investment scale, overinvestment and general efficiency.",
    }
    matrix: list[Group2DataFeasibilityItem] = []
    for group in ("independent", "moderators", "dependent", "mediators", "controls"):
        entries = raw_variables.get(group, [])
        if not isinstance(entries, list):
            raise Group1HandoffError(f"HypothesisCard variable group is invalid: {group}")
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            construct = str(entry.get("name", "")).strip()
            if not construct:
                continue
            candidates = entry.get("measurement_candidates", [])
            if not isinstance(candidates, list):
                candidates = []
            candidate_records = [item for item in candidates if isinstance(item, dict)]
            source_ids = _unique_strings(
                [item.get("data_source_id", "") for item in candidate_records]
            )
            access_values = {
                str(item.get("availability", "")).strip().lower()
                for item in candidate_records
                if str(item.get("availability", "")).strip()
            }
            if not source_ids:
                source_access = "missing"
            elif "open" in access_values and len(access_values) == 1:
                source_access = "open_candidate"
            elif "commercial" in access_values and len(access_values) == 1:
                source_access = "commercial_candidate"
            else:
                source_access = "mixed_candidate"
            if role_labels[group] in {"treatment", "moderator"}:
                join_keys = ["region_id", "year", "treatment_cohort_year"]
            else:
                join_keys = ["firm_id", "year"]
            evidence_refs = _unique_strings(
                [
                    evidence_id
                    for item in candidate_records
                    for evidence_id in (
                        item.get("evidence_ids", [])
                        if isinstance(item.get("evidence_ids"), list)
                        else []
                    )
                ]
            )
            matrix.append(
                Group2DataFeasibilityItem(
                    item_id=str(entry.get("graph_node_id", "")).strip()
                    or f"construct:{_variable_name(construct)}",
                    construct_name=construct,
                    role=role_labels[group],
                    definition=str(entry.get("definition", "")).strip(),
                    candidate_source_ids=source_ids,
                    source_access=source_access,  # type: ignore[arg-type]
                    executable_asset_supplied=False,
                    readiness=(
                        "candidate_requires_validation"
                        if source_ids
                        else "missing_blocks_execution"
                    ),
                    required_join_keys=join_keys,
                    evidence_refs=evidence_refs,
                    next_action=next_actions.get(
                        construct,
                        "Validate coverage, rights, measurement and join keys before execution.",
                    ),
                )
            )
    matrix.append(
        Group2DataFeasibilityItem(
            item_id="join:firm_policy_cohort_crosswalk",
            construct_name="Firm-to-pilot-region and policy-cohort crosswalk",
            role="join_key",
            definition="Auditable mapping from listed firms to pilot regions and staggered policy timing.",
            candidate_source_ids=[],
            source_access="missing",
            executable_asset_supplied=False,
            readiness="missing_blocks_execution",
            required_join_keys=["firm_id", "region_id", "treatment_cohort_year"],
            evidence_refs=[],
            next_action="Build, license and hash-freeze the firm-region-cohort crosswalk.",
        )
    )
    return matrix


def _group2_method_matrix(card: dict[str, Any]) -> list[Group2MethodFeasibilityItem]:
    recommended = card.get("recommended_design")
    handoff = card.get("handoff")
    if not isinstance(recommended, dict) or not isinstance(handoff, dict):
        raise Group1HandoffError("HypothesisCard method or handoff section is missing")
    criteria = _unique_strings(list(handoff.get("validation_acceptance_criteria", [])))
    method_ids = _unique_strings(list(recommended.get("candidate_method_ids", [])))
    primary_id = method_ids[0] if method_ids else "method:staggered_did_event_study_ddd"
    return [
        Group2MethodFeasibilityItem(
            method_id=primary_id,
            name="Cohort-robust staggered DID with pre-policy continuous-capacity DDD",
            purpose="Estimate cohort/event-time policy effects and the preregistered sign switch over baseline capacity.",
            implementation_status="adapter_required",
            acceptance_criteria=criteria[:3],
            next_action="Implement or bind an executor that preserves cohort-robust ATT semantics and the continuous moderator.",
        ),
        Group2MethodFeasibilityItem(
            method_id="diagnostic:pretrend_common_support_spillover",
            name="Pre-trend, common-support and spillover diagnostics",
            purpose="Keep anticipation, support failure and neighboring-region contamination from masquerading as a sign switch.",
            implementation_status="design_required",
            acceptance_criteria=criteria[:2],
            next_action="Freeze diagnostic windows, equivalence thresholds and spillover exposure maps before H2 execution freeze.",
        ),
        Group2MethodFeasibilityItem(
            method_id="diagnostic:disclosure_emissions_missingness",
            name="Disclosure and emissions selection sensitivity",
            purpose="Report paired greenwashing and real-emissions outcomes under auditable missingness assumptions.",
            implementation_status="design_required",
            acceptance_criteria=[item for item in criteria if "missing" in item.lower()][:2],
            next_action="Preregister complete-case, selection-weighted and denominator-sensitivity analyses.",
        ),
        Group2MethodFeasibilityItem(
            method_id="mechanism:temporally_ordered_competing_pathways",
            name="Temporally ordered competing-pathway contrasts",
            purpose="Separate innovation/EPIE from overinvestment, misallocation and disclosure opportunism without post-treatment conditioning.",
            implementation_status="design_required",
            acceptance_criteria=[item for item in criteria if "mechanism" in item.lower() or "Efficient" in item][:2],
            next_action="Keep mechanism claims associative unless sequential-mediation assumptions and timing are defensible.",
        ),
    ]


def _scientific_ten(
    card: dict[str, Any],
    gap_card: dict[str, Any],
    handoff: dict[str, Any],
    data_matrix: list[Group2DataFeasibilityItem],
    method_matrix: list[Group2MethodFeasibilityItem],
) -> list[ScientificTenItem]:
    handoff_section = card.get("handoff") if isinstance(card.get("handoff"), dict) else {}
    recommended = card.get("recommended_design") if isinstance(card.get("recommended_design"), dict) else {}
    evidence_balance = card.get("evidence_balance") if isinstance(card.get("evidence_balance"), dict) else {}
    questions = gap_card.get("candidate_research_questions", [])
    if not isinstance(questions, list) or not questions:
        questions = [gap_card.get("statement", "")]
    boundary_conditions = _unique_strings(list(card.get("boundary_conditions", [])))
    criteria = _unique_strings(list(handoff_section.get("validation_acceptance_criteria", [])))
    blocking_questions = _unique_strings(list(handoff_section.get("blocking_questions", [])))
    unresolved = _unique_strings(list(handoff.get("unresolved_conditions", [])))
    evidence_refs = _unique_strings(
        list(handoff_section.get("evidence_bundle_refs", []))
        + list(evidence_balance.get("supporting_finding_ids", []))
    )
    mechanism_chain = card.get("mechanism_chain", [])
    mechanism_statements = _unique_strings(
        [
            item.get("statement", "")
            for item in mechanism_chain
            if isinstance(item, dict)
        ]
    )
    data_summary = "; ".join(
        f"{item.construct_name}: {item.source_access}/{item.readiness}"
        for item in data_matrix
    )
    method_summary = "; ".join(
        f"{item.name}: {item.implementation_status}" for item in method_matrix
    )
    hypothesis_id = str(card.get("hypothesis_id", "")).strip()
    gap_id = str(gap_card.get("gap_id", "")).strip()
    novelty_ref = str(card.get("novelty_check_ref", "")).strip()
    graph_ref = str(card.get("graph_snapshot_id", "")).strip()
    return [
        ScientificTenItem(
            item_no=1,
            title="研究问题与项目定位",
            content=" ".join(_unique_strings(questions)),
            status="evidence_bound",
            evidence_refs=[ref for ref in (gap_id, hypothesis_id) if ref],
        ),
        ScientificTenItem(
            item_no=2,
            title="研究空白与贡献边界",
            content=(
                f"{str(gap_card.get('statement', '')).strip()} "
                "贡献仅表述为 corpus-bounded gap，不主张全球首次或领域级空白。"
            ).strip(),
            status="evidence_bound",
            evidence_refs=[ref for ref in (gap_id, novelty_ref, graph_ref) if ref],
            unresolved_actions=[
                "依法补齐受限最近邻全文后，再复核细粒度构念等价与优先权表述。"
            ],
        ),
        ScientificTenItem(
            item_no=3,
            title="核心假设与可证伪预测",
            content=(
                f"{str(card.get('hypothesis_statement', '')).strip()} "
                f"Falsification: {str(card.get('falsifiable_form', '')).strip()}"
            ).strip(),
            status="evidence_bound",
            evidence_refs=[hypothesis_id] if hypothesis_id else [],
        ),
        ScientificTenItem(
            item_no=4,
            title="竞争机制与理论路径",
            content=" ".join(mechanism_statements),
            status="evidence_bound",
            evidence_refs=evidence_refs[:8],
            unresolved_actions=["机制结论在时序与中介识别条件未满足前保持关联性表述。"],
        ),
        ScientificTenItem(
            item_no=5,
            title="研究对象、处理与边界条件",
            content=(
                f"分析单位：{str(recommended.get('unit_of_analysis', '')).strip()}。"
                f"边界条件：{' '.join(boundary_conditions)}"
            ),
            status="conditional",
            evidence_refs=[hypothesis_id] if hypothesis_id else [],
            unresolved_actions=["确认企业—试点地区—政策批次映射与可用样本期。"],
        ),
        ScientificTenItem(
            item_no=6,
            title="变量操作化与测量口径",
            content=data_summary,
            status="conditional",
            evidence_refs=_unique_strings(
                [ref for item in data_matrix for ref in item.evidence_refs]
            )[:12],
            unresolved_actions=[item.next_action for item in data_matrix],
        ),
        ScientificTenItem(
            item_no=7,
            title="数据、授权与连接可行性",
            content=(
                "Group 1 只提供候选数据节点和测量证据，没有提供可执行数据文件；"
                "开放、商业和缺失资产必须分别完成授权、覆盖、哈希与 join-key 审计。"
            ),
            status="pending",
            evidence_refs=evidence_refs[:6],
            unresolved_actions=unresolved[:4],
        ),
        ScientificTenItem(
            item_no=8,
            title="识别策略与方法实现",
            content=(
                f"建议基线：{str(recommended.get('baseline_specification', '')).strip()} "
                f"Group 2 实现审计：{method_summary}"
            ).strip(),
            status="conditional",
            evidence_refs=[hypothesis_id] if hypothesis_id else [],
            unresolved_actions=[item.next_action for item in method_matrix],
        ),
        ScientificTenItem(
            item_no=9,
            title="诊断、稳健性与停止规则",
            content=" ".join(criteria),
            status="conditional",
            evidence_refs=[hypothesis_id] if hypothesis_id else [],
            unresolved_actions=blocking_questions,
        ),
        ScientificTenItem(
            item_no=10,
            title="阶段产物、Go/No-Go 与主张边界",
            content=(
                "当前允许产出变量—数据矩阵、方法候选比较、风险与替代方案以及 Proposal 草案；"
                "在企业碳排、交叉映射和执行器未闭合前，不产生实证效应、显著性或因果结论。"
            ),
            status="conditional",
            evidence_refs=[ref for ref in (gap_id, hypothesis_id, novelty_ref) if ref],
            unresolved_actions=[
                "数据和方法通过后转为 go_for_execution；若核心构念无法操作化，再返回 Group 1。"
            ],
        ),
    ]


def _group2_feasibility_package(
    card: dict[str, Any],
    gap_card: dict[str, Any],
    handoff: dict[str, Any],
) -> Group2FeasibilityPackage:
    data_matrix = _group2_data_matrix(card)
    method_matrix = _group2_method_matrix(card)
    handoff_id = str(handoff.get("handoff_id", "")).strip()
    package_suffix = hashlib.sha256(
        f"{handoff_id}:{BRIDGE_VERSION}".encode("utf-8")
    ).hexdigest()[:24]
    return Group2FeasibilityPackage(
        package_id=f"group2-feasibility:{package_suffix}",
        upstream_handoff_id=handoff_id,
        handoff_status="accepted_for_group2_design",
        execution_status="not_ready",
        go_no_go_decision="conditional_go_for_design",
        decision_rationale=(
            "Group 1 evidence, novelty boundary and falsifiable hypothesis are complete enough for "
            "Group 2 feasibility/design work. Executable data, join keys and the required staggered-DID/DDD "
            "executor are not yet closed, so statistical execution remains fail-closed."
        ),
        return_to_group1_required=False,
        data_matrix=data_matrix,
        method_matrix=method_matrix,
        scientific_ten=_scientific_ten(
            card,
            gap_card,
            handoff,
            data_matrix,
            method_matrix,
        ),
    )


def import_group1_handoff(path: str | Path) -> Group1BridgeResult:
    pilot_root, handoff_dir = _package_roots(path)
    handoff, integrity, resolved = _verify_manifest(pilot_root, handoff_dir)
    try:
        hypothesis_card = _load_json(resolved["hypothesis_card"])
        gap_card = _load_json(resolved["gap_card"])
    except KeyError as error:
        raise Group1HandoffError(f"manifest is missing required artifact: {error.args[0]}") from error

    final_hypothesis = handoff.get("final_hypothesis")
    if not isinstance(final_hypothesis, dict):
        raise Group1HandoffError("handoff final_hypothesis is missing")
    if final_hypothesis.get("hypothesis_id") != hypothesis_card.get("hypothesis_id"):
        raise Group1HandoffError("handoff and HypothesisCard hypothesis IDs do not match")
    if final_hypothesis.get("gap_id") != gap_card.get("gap_id"):
        raise Group1HandoffError("handoff and GapCard IDs do not match")

    handoff_section = hypothesis_card.get("handoff")
    feasibility_section = hypothesis_card.get("feasibility")
    recommended_design = hypothesis_card.get("recommended_design")
    if not isinstance(handoff_section, dict) or not isinstance(feasibility_section, dict):
        raise Group1HandoffError("HypothesisCard handoff or feasibility section is missing")
    if not isinstance(recommended_design, dict):
        raise Group1HandoffError("HypothesisCard recommended_design is missing")

    group2_scope = handoff.get("group2_scope") if isinstance(handoff.get("group2_scope"), dict) else {}
    scientific_constraints = _unique_strings(
        list(handoff.get("scientific_constraints", []))
        + list(group2_scope.get("must_not_change_without_return_to_group1", []))
        + list(hypothesis_card.get("boundary_conditions", []))
    )
    validation_criteria = _unique_strings(list(handoff_section.get("validation_acceptance_criteria", [])))
    required_inputs = _unique_strings(list(handoff_section.get("required_inputs", [])))
    blockers = _unique_strings(
        [
            "No executable dataset_refs were supplied by the Group 1 discovery package.",
            "Group 2 policy-did-v2 does not implement cohort-robust staggered DID with a pre-treatment continuous-capacity DDD sign-switch estimand.",
        ]
        + list(feasibility_section.get("blocking_items", []))
    )
    warnings = _unique_strings(list(handoff.get("unresolved_conditions", [])))
    method_requirements = _unique_strings(
        [str(recommended_design.get("baseline_specification", "")).strip()]
        + validation_criteria
    )
    readiness = IntakeReadiness(
        status="conditional",
        can_approve_h1=True,
        can_execute=False,
        blockers=blockers,
        warnings=warnings,
        required_inputs=required_inputs,
        method_requirements=method_requirements,
    )
    feasibility_package = _group2_feasibility_package(
        hypothesis_card,
        gap_card,
        handoff,
    )
    evidence_balance = hypothesis_card.get("evidence_balance")
    if not isinstance(evidence_balance, dict):
        evidence_balance = {}
    evidence_refs = _unique_strings(
        list(handoff_section.get("evidence_bundle_refs", []))
        + list(evidence_balance.get("supporting_finding_ids", []))
    )

    questions = gap_card.get("candidate_research_questions", [])
    if not isinstance(questions, list) or not questions:
        questions = [str(gap_card.get("statement", "")).strip()]
    research_question = " ".join(_unique_strings(questions))
    target_estimands = [
        "Cohort-robust GFRIPZ effects by treatment cohort and event time.",
        "Marginal GFRIPZ effects over pre-policy digital/fintech capacity, including a preregistered zero crossing.",
        "Joint high- versus low-capacity effects on greenwashing and direct firm carbon intensity under one cohort definition.",
        "Capacity-specific innovation, EPIE, overinvestment and disclosure-opportunism mechanism contrasts.",
    ]
    case = CaseSubmission(
        case_id=str(handoff["handoff_id"]),
        title=str(final_hypothesis.get("title", hypothesis_card.get("title", "Group 1 hypothesis"))),
        research_question=research_question,
        hypotheses=_hypotheses(hypothesis_card),
        unit_of_analysis=str(recommended_design.get("unit_of_analysis", "firm-year")),
        sample_period=None,
        data_structure_hint="panel",
        variables=_variables(hypothesis_card),
        dataset_refs=[],
        design_envelope=DesignEnvelope(
            benchmark_track="reproduction_aligned",
            research_goal="causal",
            target_estimands=target_estimands,
            design_constraints=scientific_constraints,
            required_diagnostics=validation_criteria,
            allowed_claim_strength="causal",
        ),
        policy_design=None,
        known_policy_facts=[
            "Treatment is firm exposure induced by GFRIPZ pilot-region designation and cohort timing.",
            "Required method family is cohort-robust staggered DID with a strictly pre-treatment continuous-capacity DDD sign-switch estimand.",
            "The exact firm-to-region and cohort-timing crosswalk remains unresolved and must be verified before H2 execution-contract freeze.",
        ],
        constraints=scientific_constraints,
        upstream_provenance=UpstreamProvenance(
            source_system="group1-discovery",
            bridge_version=BRIDGE_VERSION,
            package_id=str(handoff["handoff_id"]),
            schema_version=str(handoff.get("schema_version", "unknown")),
            generated_at=str(handoff.get("generated_at", "")),
            status=str(handoff.get("status", "unknown")),
            manifest_sha256=integrity.manifest_sha256,
            verified_artifact_count=integrity.verified_artifact_count,
            artifacts=integrity.verified_artifacts,
            graph_snapshot_id=str(hypothesis_card.get("graph_snapshot_id", "")) or None,
            hypothesis_id=str(hypothesis_card.get("hypothesis_id", "")) or None,
            gap_id=str(gap_card.get("gap_id", "")) or None,
            novelty_check_ref=str(hypothesis_card.get("novelty_check_ref", "")) or None,
            evidence_refs=evidence_refs,
            corpus_boundary="corpus_bounded_gap",
        ),
        intake_readiness=readiness,
        group2_feasibility_package=feasibility_package,
    )

    evidence_bundle = Group1EvidenceBundle(
        handoff_id=str(handoff["handoff_id"]),
        hypothesis_id=str(hypothesis_card["hypothesis_id"]),
        gap_id=str(gap_card["gap_id"]),
        graph_snapshot_id=str(hypothesis_card.get("graph_snapshot_id", "")) or None,
        novelty_check_ref=str(hypothesis_card.get("novelty_check_ref", "")) or None,
        evidence_refs=evidence_refs,
        corpus_boundary="corpus_bounded_gap",
        artifact_refs=integrity.verified_artifacts,
    )
    return Group1BridgeResult(
        case_submission=case,
        evidence_bundle=evidence_bundle,
        integrity=integrity,
        feasibility=readiness,
        group2_feasibility_package=feasibility_package,
    )


def bind_group1_execution_panel(
    bridge: Group1BridgeResult,
    panel_path: str | Path,
    manifest_path: str | Path,
    source_config_path: str | Path,
) -> Group1BridgeResult:
    """Bind an audited Group 2 execution panel without mutating Group 1 evidence."""

    panel = Path(panel_path).expanduser().resolve(strict=True)
    manifest_file = Path(manifest_path).expanduser().resolve(strict=True)
    source_config = Path(source_config_path).expanduser().resolve(strict=True)
    if not panel.is_file() or panel.suffix.casefold() != ".csv":
        raise Group1HandoffError("Group 1 execution panel must be an existing CSV file")
    if not manifest_file.is_file() or not source_config.is_file():
        raise Group1HandoffError("Group 1 execution manifest or source config is missing")
    manifest = _load_json(manifest_file)
    if manifest.get("schema_version") != "group1-stacked-panel-manifest-v1":
        raise Group1HandoffError("unsupported Group 1 execution-panel manifest")
    output = manifest.get("output")
    if not isinstance(output, dict):
        raise Group1HandoffError("execution-panel manifest has no output binding")
    actual_sha256 = _sha256(panel)
    actual_size = panel.stat().st_size
    if output.get("filename") != panel.name:
        raise Group1HandoffError("execution-panel filename disagrees with its manifest")
    if output.get("sha256") != actual_sha256:
        raise Group1HandoffError("execution-panel SHA256 disagrees with its manifest")
    if int(output.get("size_bytes", -1)) != actual_size:
        raise Group1HandoffError("execution-panel size disagrees with its manifest")
    if manifest.get("source_config_sha256") != _sha256(source_config):
        raise Group1HandoffError("source-config SHA256 disagrees with the panel manifest")
    if output.get("stack_firm_year_key_unique") is not True:
        raise Group1HandoffError("execution-panel stacked primary key is not unique")
    if output.get("paired_outcome_complete") is not True:
        raise Group1HandoffError("execution-panel paired outcomes are not complete")

    required_fields = {
        "stack_cohort_year",
        "stack_entity_id",
        "stack_time_id",
        "firm_id",
        "year",
        "treated",
        "gfripz_exposure",
        "treatment_cohort_year",
        "region_id",
        "assignment_boundary_precision",
        "prepolicy_digital_fintech_capacity",
        "capacity_year_count",
        "capacity_source_end_year",
        "greenwashing_gap",
        "firm_emission_intensity",
        "firm_size",
        "leverage",
        "return_on_assets",
        "sales_growth",
        "cash_ratio",
        "state_owned",
    }
    try:
        with panel.open("r", encoding="utf-8-sig", newline="") as handle:
            header = next(csv.reader(handle))
    except (OSError, UnicodeError, StopIteration) as error:
        raise Group1HandoffError("cannot read the execution-panel CSV header") from error
    missing = sorted(required_fields - set(header))
    if missing:
        raise Group1HandoffError(
            "execution panel is missing frozen fields: " + ", ".join(missing)
        )

    dataset_ref = DatasetRef(
        dataset_id=f"group1-paired-{actual_sha256[:16]}",
        role="main",
        filename=panel.name,
        mime_type="text/csv",
        sha256=actual_sha256,
        size_bytes=actual_size,
    )
    existing = {variable.name: variable for variable in bridge.case_submission.variables}
    additions = {
        "stack_cohort_year": ("Stack cohort year", "event_date"),
        "stack_entity_id": ("Stack-by-firm fixed-effect key", "fixed_effect"),
        "stack_time_id": ("Stack-by-year fixed-effect key", "fixed_effect"),
        "treated": ("Treated entity in cohort stack", "treatment"),
        "assignment_boundary_precision": ("Pilot boundary precision", "control"),
        "capacity_year_count": ("Pre-policy capacity source-year count", "control"),
        "capacity_source_end_year": ("Last capacity source year", "control"),
        "firm_size": ("Firm size", "control"),
        "leverage": ("Leverage", "control"),
        "return_on_assets": ("Return on assets", "control"),
        "sales_growth": ("Sales growth", "control"),
        "cash_ratio": ("Cash ratio", "control"),
        "state_owned": ("State-owned indicator", "control"),
    }
    variables = list(bridge.case_submission.variables)
    for name, (label, role) in additions.items():
        if name in existing:
            continue
        variables.append(
            VariableSpec(
                name=name,
                label=label,
                role=role,  # type: ignore[arg-type]
                definition=(
                    "Code-owned field in the hash-frozen Group 2 paired stacked panel."
                ),
                source=f"Group 2 execution manifest {_sha256(manifest_file)}",
            )
        )

    scientific_blockers = [
        str(value)
        for value in manifest.get("scientific_release_blockers", [])
        if str(value).strip()
    ]
    readiness = IntakeReadiness(
        status="conditional",
        can_approve_h1=True,
        can_execute=True,
        blockers=[],
        warnings=scientific_blockers,
        required_inputs=[],
        method_requirements=[
            "Execute group1-staggered-ddd-v1 on the paired stacked panel.",
            "Run an independent NumPy within-estimator reproduction.",
            "Hold causal release whenever the manifest or paired sign-switch gate fails.",
        ],
    )
    method_matrix = [
        item.model_copy(
            update={
                "implementation_status": (
                    "available"
                    if item.method_id
                    in {
                        "method:staggered_did_event_study_ddd",
                        "diagnostic:pretrend_common_support_spillover",
                    }
                    or "staggered" in item.method_id
                    else item.implementation_status
                ),
                "next_action": (
                    "Execute the frozen adapter and preserve the scientific-release hold."
                    if "staggered" in item.method_id
                    else item.next_action
                ),
            }
        )
        for item in bridge.group2_feasibility_package.method_matrix
    ]
    feasibility_package = bridge.group2_feasibility_package.model_copy(
        update={
            "method_matrix": method_matrix,
            "decision_rationale": (
                "The hash-bound paired stacked panel and code-owned staggered DDD adapter are ready "
                "for the frozen core sign-switch execution. Scientific release and broader mechanism "
                "extensions remain conditional on the recorded rights, boundary, denominator and "
                "additional-variable blockers."
            ),
        }
    )
    case = bridge.case_submission.model_copy(
        update={
            "sample_period": "2012-2021 paired stacked execution window",
            "variables": variables,
            "dataset_refs": [dataset_ref],
            "known_policy_facts": list(
                dict.fromkeys(
                    [
                        *bridge.case_submission.known_policy_facts,
                        "The Group 2 paired stacked panel and source manifest are SHA256-bound.",
                        "Adoption years are excluded and post-treatment starts in the following calendar year.",
                        "Engineering execution is authorized; scientific release remains conditional on the manifest blockers and empirical claim gate.",
                    ]
                )
            ),
            "constraints": list(
                dict.fromkeys(
                    [
                        *bridge.case_submission.constraints,
                        *scientific_blockers,
                    ]
                )
            ),
            "intake_readiness": readiness,
            "group2_feasibility_package": feasibility_package,
        }
    )
    return bridge.model_copy(
        update={
            "case_submission": case,
            "feasibility": readiness,
            "group2_feasibility_package": feasibility_package,
        }
    )
