"""Dependency-free semantic validation for coverage certificates.

JSON Schema remains the structural contract.  This module verifies the arithmetic
and cross-field invariants that JSON Schema cannot express.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Callable


OBSERVATION_STATUSES = frozenset(
    {
        "observed_present",
        "observed_absent",
        "not_extracted",
        "source_missing",
        "not_applicable",
    }
)

GAP_TYPES = frozenset(
    {
        "mechanism",
        "data",
        "population",
        "context",
        "method",
        "model",
        "policy",
        "controversy",
        "temporal",
        "cross_stream",
    }
)


def _close(left: float, right: float) -> bool:
    return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-9)


def _ratio(numerator: int | float, denominator: int | float) -> float:
    """Return a coverage ratio; an empty eligible population is vacuously covered."""

    return 1.0 if denominator == 0 else numerator / denominator


def _retrieval_gain(new_count: int, cumulative_count: int) -> float:
    """Return marginal retrieval gain; an empty round over an empty set gains zero."""

    return 0.0 if cumulative_count == 0 else new_count / cumulative_count


def _rate_error(
    errors: list[str], path: str, actual: float | None, expected: float | None
) -> None:
    if expected is None:
        if actual is not None:
            errors.append(f"{path} must be null when its denominator is zero")
    elif actual is None or not _close(actual, expected):
        errors.append(f"{path} is inconsistent: expected {expected:.12g}, got {actual!r}")


def _run_check(errors: list[str], label: str, check: Callable[[], None]) -> None:
    """Keep malformed input diagnosable while treating Schema as a prerequisite."""

    try:
        check()
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        errors.append(
            f"{label}: cannot evaluate semantic constraint ({type(exc).__name__}: {exc}); "
            "run JSON Schema validation first"
        )


def _check_sources(certificate: dict[str, Any], errors: list[str]) -> None:
    sources = certificate["coverage"]["sources"]
    items = sources["items"]
    required_items = [item for item in items if item["required"]]
    covered_required = [
        item
        for item in required_items
        if item["status"] in {"observed_present", "observed_absent"}
    ]
    missing_required = [item for item in required_items if item not in covered_required]

    if sources["registered_source_count"] != len(items):
        errors.append("coverage.sources.registered_source_count does not match items")
    if sources["required_source_count"] != len(required_items):
        errors.append("coverage.sources.required_source_count does not match required items")
    if sources["covered_required_source_count"] != len(covered_required):
        errors.append("coverage.sources.covered_required_source_count is inconsistent")
    if sources["missing_required_source_count"] != len(missing_required):
        errors.append("coverage.sources.missing_required_source_count is inconsistent")
    if (
        sources["covered_required_source_count"]
        + sources["missing_required_source_count"]
        != sources["required_source_count"]
    ):
        errors.append("coverage.sources required-source counts do not close")
    _rate_error(
        errors,
        "coverage.sources.required_coverage_rate",
        sources["required_coverage_rate"],
        _ratio(len(covered_required), len(required_items)),
    )


def _check_languages(certificate: dict[str, Any], errors: list[str]) -> None:
    target = certificate["scope"]["target_document_count"]
    languages = certificate["coverage"]["languages"]
    item_total = sum(item["document_count"] for item in languages["items"])
    if languages["target_document_count"] != target:
        errors.append("coverage.languages.target_document_count does not match scope target")
    if item_total != languages["covered_document_count"]:
        errors.append("coverage.languages item counts do not match covered_document_count")
    if languages["covered_document_count"] + languages["unknown_language_count"] != target:
        errors.append("coverage.languages counts do not close to the scope target")
    _rate_error(
        errors,
        "coverage.languages.coverage_rate",
        languages["coverage_rate"],
        _ratio(languages["covered_document_count"], target),
    )


def _check_years(certificate: dict[str, Any], errors: list[str]) -> None:
    target = certificate["scope"]["target_document_count"]
    years = certificate["coverage"]["years"]
    bin_total = sum(item["document_count"] for item in years["bins"])
    if years["target_document_count"] != target:
        errors.append("coverage.years.target_document_count does not match scope target")
    if bin_total != years["known_year_count"]:
        errors.append("coverage.years bins do not match known_year_count")
    if years["known_year_count"] + years["missing_year_count"] != target:
        errors.append("coverage.years counts do not close to the scope target")
    _rate_error(
        errors,
        "coverage.years.coverage_rate",
        years["coverage_rate"],
        _ratio(years["known_year_count"], target),
    )


def _check_fulltext(certificate: dict[str, Any], errors: list[str]) -> None:
    target = certificate["scope"]["target_document_count"]
    fulltext = certificate["coverage"]["fulltext"]
    if fulltext["target_document_count"] != target:
        errors.append("coverage.fulltext.target_document_count does not match scope target")
    if fulltext["metadata_only_count"] != (
        fulltext["rights_blocked_count"] + fulltext["source_missing_count"]
    ):
        errors.append(
            "coverage.fulltext.metadata_only_count is not explained by rights_blocked_count "
            "plus source_missing_count"
        )
    if (
        fulltext["fulltext_available_count"]
        + fulltext["metadata_only_count"]
        + fulltext["not_applicable_count"]
        != target
    ):
        errors.append("coverage.fulltext counts do not close to the scope target")
    denominator = target - fulltext["not_applicable_count"]
    _rate_error(
        errors,
        "coverage.fulltext.coverage_rate",
        fulltext["coverage_rate"],
        _ratio(fulltext["fulltext_available_count"], denominator),
    )


def _check_parsing_and_indexing(certificate: dict[str, Any], errors: list[str]) -> None:
    target = certificate["scope"]["target_document_count"]
    coverage = certificate["coverage"]
    fulltext = coverage["fulltext"]
    parsing = coverage["parsing"]
    indexing = coverage["indexing"]

    if parsing["target_document_count"] != target:
        errors.append("coverage.parsing.target_document_count does not match scope target")
    if parsing["input_document_count"] != fulltext["fulltext_available_count"]:
        errors.append("coverage.parsing.input_document_count does not match available full text")
    if parsing["success_count"] + parsing["failed_count"] != parsing["input_document_count"]:
        errors.append("coverage.parsing result counts do not close to input_document_count")
    if parsing["input_document_count"] + parsing["not_applicable_count"] != target:
        errors.append("coverage.parsing input and not-applicable counts do not close")
    _rate_error(
        errors,
        "coverage.parsing.success_rate",
        parsing["success_rate"],
        _ratio(parsing["success_count"], parsing["input_document_count"]),
    )

    if indexing["target_document_count"] != target:
        errors.append("coverage.indexing.target_document_count does not match scope target")
    if indexing["input_document_count"] != parsing["success_count"]:
        errors.append("coverage.indexing.input_document_count does not match parsing success_count")
    if indexing["indexed_document_count"] + indexing["failed_count"] != indexing["input_document_count"]:
        errors.append("coverage.indexing result counts do not close to input_document_count")
    if indexing["input_document_count"] + indexing["not_applicable_count"] != target:
        errors.append("coverage.indexing input and not-applicable counts do not close")
    _rate_error(
        errors,
        "coverage.indexing.success_rate",
        indexing["success_rate"],
        _ratio(indexing["indexed_document_count"], indexing["input_document_count"]),
    )


def _check_fields(certificate: dict[str, Any], errors: list[str]) -> None:
    target = certificate["scope"]["target_document_count"]
    section = certificate["coverage"]["field_observability"]
    if section["target_document_count"] != target:
        errors.append("coverage.field_observability.target_document_count does not match scope target")

    critical_rates: list[float] = []
    field_paths: set[str] = set()
    for field in section["fields"]:
        path = field["field_path"]
        if path in field_paths:
            errors.append(f"coverage.field_observability.fields has duplicate field_path: {path}")
        field_paths.add(path)
        counts = field["status_counts"]
        count_total = sum(counts[status] for status in OBSERVATION_STATUSES)
        applicable = target - counts["not_applicable"]
        observable = counts["observed_present"] + counts["observed_absent"]
        if field["target_document_count"] != target or count_total != target:
            errors.append(f"field status counts do not close: {path}")
        if field["applicable_document_count"] != applicable:
            errors.append(f"field applicable_document_count is inconsistent: {path}")
        if field["observable_document_count"] != observable:
            errors.append(f"field observable_document_count is inconsistent: {path}")
        expected_observability = None if applicable == 0 else observable / applicable
        expected_presence = None if observable == 0 else counts["observed_present"] / observable
        _rate_error(
            errors,
            f"field {path} observability_rate",
            field["observability_rate"],
            expected_observability,
        )
        _rate_error(
            errors,
            f"field {path} presence_rate",
            field["presence_rate"],
            expected_presence,
        )
        if field["critical"]:
            if field["observability_rate"] is None:
                errors.append(f"critical field has no applicable observability rate: {path}")
            else:
                critical_rates.append(field["observability_rate"])

    expected_minimum = min(critical_rates) if critical_rates else None
    _rate_error(
        errors,
        "coverage.field_observability.critical_field_min_observability",
        section["critical_field_min_observability"],
        expected_minimum,
    )


def _check_deduplication(certificate: dict[str, Any], errors: list[str]) -> None:
    target = certificate["scope"]["target_document_count"]
    dedup = certificate["coverage"]["deduplication"]
    expected_canonical = (
        dedup["input_record_count"]
        - dedup["exact_duplicate_record_count"]
        - dedup["near_duplicate_record_count"]
    )
    if dedup["canonical_document_count"] != expected_canonical:
        errors.append("coverage.deduplication canonical document count is inconsistent")
    if dedup["canonical_document_count"] != target:
        errors.append("coverage.deduplication.canonical_document_count does not match scope target")
    if dedup["resolved_pair_count"] + dedup["unresolved_pair_count"] != dedup["duplicate_candidate_pair_count"]:
        errors.append("coverage.deduplication candidate-pair counts do not close")
    if dedup["manual_review_pending_count"] > dedup["unresolved_pair_count"]:
        errors.append("coverage.deduplication manual review count exceeds unresolved pairs")
    _rate_error(
        errors,
        "coverage.deduplication.resolution_rate",
        dedup["resolution_rate"],
        _ratio(dedup["resolved_pair_count"], dedup["duplicate_candidate_pair_count"]),
    )


def _check_retrieval(certificate: dict[str, Any], errors: list[str]) -> None:
    retrieval = certificate["coverage"]["retrieval_saturation"]
    rounds = retrieval["rounds"]
    cumulative = 0
    for expected_round, item in enumerate(rounds, start=1):
        cumulative += item["new_unique_document_count"]
        if item["round"] != expected_round:
            errors.append(
                f"coverage.retrieval_saturation.rounds[{expected_round - 1}].round is not contiguous"
            )
        if item["new_unique_document_count"] > item["candidate_count"]:
            errors.append(
                f"retrieval new unique count exceeds candidate count in round {expected_round}"
            )
        if item["cumulative_unique_document_count"] != cumulative:
            errors.append(f"retrieval cumulative count is inconsistent in round {expected_round}")
        _rate_error(
            errors,
            f"retrieval marginal_gain in round {expected_round}",
            item["marginal_gain"],
            _retrieval_gain(item["new_unique_document_count"], cumulative),
        )

    if retrieval["executed_rounds"] != len(rounds):
        errors.append("coverage.retrieval_saturation.executed_rounds does not match rounds")
    if retrieval["unique_retrieved_document_count"] != cumulative:
        errors.append("coverage.retrieval_saturation unique document count is inconsistent")
    expected_last = rounds[-1]["marginal_gain"] if rounds else None
    _rate_error(
        errors,
        "coverage.retrieval_saturation.last_round_marginal_gain",
        retrieval["last_round_marginal_gain"],
        expected_last,
    )

    thresholds = certificate["thresholds"]
    _rate_error(
        errors,
        "coverage.retrieval_saturation.marginal_gain_threshold",
        retrieval["marginal_gain_threshold"],
        thresholds["retrieval_marginal_gain_max"],
    )
    if (
        retrieval["required_consecutive_low_gain_rounds"]
        != thresholds["retrieval_consecutive_low_gain_rounds"]
    ):
        errors.append(
            "coverage.retrieval_saturation.required_consecutive_low_gain_rounds "
            "does not match thresholds"
        )

    if retrieval["saturation_status"] == "saturated":
        needed = retrieval["required_consecutive_low_gain_rounds"]
        if len(rounds) < retrieval["minimum_rounds"]:
            errors.append("saturated retrieval has fewer than minimum_rounds")
        if len(rounds) < needed or any(
            item["marginal_gain"] > retrieval["marginal_gain_threshold"]
            for item in rounds[-needed:]
        ):
            errors.append("saturated retrieval lacks the required consecutive low-gain rounds")


def _values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return _close(float(left), float(right))
    return left == right


def _comparison_result(comparator: str, observed: Any, threshold: Any) -> bool:
    if comparator == ">=":
        return observed >= threshold
    if comparator == "<=":
        return observed <= threshold
    if comparator == "==":
        return _values_equal(observed, threshold)
    if comparator == "in":
        if isinstance(threshold, (list, tuple, set, frozenset)):
            return observed in threshold
        return _values_equal(observed, threshold)
    raise ValueError(f"unsupported comparator {comparator!r}")


def _known_gate_values(certificate: dict[str, Any]) -> dict[tuple[str, str], tuple[Any, Any]]:
    coverage = certificate["coverage"]
    thresholds = certificate["thresholds"]
    return {
        ("sources", "required_coverage_rate"): (
            coverage["sources"]["required_coverage_rate"],
            thresholds["required_source_coverage_rate"],
        ),
        ("languages", "coverage_rate"): (
            coverage["languages"]["coverage_rate"],
            thresholds["language_coverage_rate"],
        ),
        ("years", "coverage_rate"): (
            coverage["years"]["coverage_rate"],
            thresholds["year_coverage_rate"],
        ),
        ("fulltext", "coverage_rate"): (
            coverage["fulltext"]["coverage_rate"],
            thresholds["fulltext_coverage_rate"],
        ),
        ("parsing", "success_rate"): (
            coverage["parsing"]["success_rate"],
            thresholds["parsing_success_rate"],
        ),
        ("indexing", "success_rate"): (
            coverage["indexing"]["success_rate"],
            thresholds["indexing_success_rate"],
        ),
        ("field_observability", "critical_field_min_observability"): (
            coverage["field_observability"]["critical_field_min_observability"],
            thresholds["critical_field_observability_rate"],
        ),
        ("deduplication", "resolution_rate"): (
            coverage["deduplication"]["resolution_rate"],
            thresholds["dedup_resolution_rate"],
        ),
        ("retrieval_saturation", "saturation_status"): (
            coverage["retrieval_saturation"]["saturation_status"],
            "saturated",
        ),
    }


def _check_gates_and_claim_status(certificate: dict[str, Any], errors: list[str]) -> None:
    gates = certificate["gates"]
    gate_ids = [gate["gate_id"] for gate in gates]
    if len(gate_ids) != len(set(gate_ids)):
        errors.append("gates contain duplicate gate_id values")

    known = _known_gate_values(certificate)
    for gate in gates:
        label = gate["gate_id"]
        known_values = known.get((gate["dimension"], gate["metric"]))
        if known_values is not None:
            expected_observed, expected_threshold = known_values
            if not _values_equal(gate["observed"], expected_observed):
                errors.append(f"gate {label} observed value does not match its coverage metric")
            if not _values_equal(gate["threshold"], expected_threshold):
                errors.append(f"gate {label} threshold does not match certificate thresholds")
        if gate["status"] in {"passed", "failed"}:
            expected_pass = _comparison_result(
                gate["comparator"], gate["observed"], gate["threshold"]
            )
            if (gate["status"] == "passed") != expected_pass:
                errors.append(
                    f"gate {label} status {gate['status']!r} contradicts its comparator result"
                )

    blocking_failures = [
        gate for gate in gates if gate["blocking"] and gate["status"] != "passed"
    ]
    status = certificate["coverage_status"]
    blockers = certificate["blockers"]
    claim_gate = certificate["claim_gate"]
    claim_status = claim_gate["status"]
    allowed = claim_gate["allowed_gap_types"]
    conditional = claim_gate["conditional_gap_types"]
    ceiling = claim_gate["claim_ceiling"]

    if status in {"coverage_ready", "coverage_conditional"}:
        if blocking_failures:
            errors.append("ready/conditional certificate has a non-passing blocking gate")
        if blockers:
            errors.append("ready/conditional certificate must not contain blockers")
    if status == "coverage_ready":
        if claim_status != "claim_ready":
            errors.append("coverage_ready requires claim_gate.status=claim_ready")
        if not allowed:
            errors.append("coverage_ready requires at least one allowed gap type")
    elif status == "coverage_conditional":
        if claim_status != "claim_limited":
            errors.append("coverage_conditional requires claim_gate.status=claim_limited")
    elif status == "coverage_blocked":
        if not blocking_failures:
            errors.append("coverage_blocked requires at least one non-passing blocking gate")
        if not blockers:
            errors.append("coverage_blocked requires at least one blocker")
        if claim_status != "coverage_blocked":
            errors.append("coverage_blocked requires claim_gate.status=coverage_blocked")
        if allowed:
            errors.append("coverage_blocked must not allow gap types")
        if ceiling not in {"no_claims", "descriptive_coverage_only"}:
            errors.append("coverage_blocked has an impermissible claim ceiling")
    elif status == "draft":
        if claim_status != "not_evaluated":
            errors.append("draft requires claim_gate.status=not_evaluated")
        if allowed or conditional or ceiling != "no_claims":
            errors.append("draft must not expose gap claims")
    elif status == "invalidated":
        if claim_status != "claim_rejected":
            errors.append("invalidated requires claim_gate.status=claim_rejected")
        if allowed or conditional or ceiling != "no_claims":
            errors.append("invalidated certificate must not expose gap claims")

    if blocking_failures and status not in {"draft", "coverage_blocked", "invalidated"}:
        errors.append("a non-passing blocking gate requires coverage_status=coverage_blocked")


def _check_gap_partitions(certificate: dict[str, Any], errors: list[str]) -> None:
    claim_gate = certificate["claim_gate"]
    raw_partitions = {
        "allowed": claim_gate["allowed_gap_types"],
        "conditional": claim_gate["conditional_gap_types"],
        "blocked": claim_gate["blocked_gap_types"],
    }
    for name, values in raw_partitions.items():
        if len(values) != len(set(values)):
            errors.append(f"claim_gate.{name}_gap_types contains duplicates")
    allowed = set(raw_partitions["allowed"])
    conditional = set(raw_partitions["conditional"])
    blocked = set(raw_partitions["blocked"])
    if allowed & conditional or allowed & blocked or conditional & blocked:
        errors.append("gap-type partitions overlap")
    union = allowed | conditional | blocked
    if union != GAP_TYPES:
        missing = sorted(GAP_TYPES - union)
        unknown = sorted(union - GAP_TYPES)
        errors.append(
            "gap-type partitions do not cover exactly the ten supported types"
            f" (missing={missing}, unknown={unknown})"
        )

    decisions = claim_gate["gap_type_decisions"]
    decision_types = [item["gap_type"] for item in decisions]
    by_type = {item["gap_type"]: item for item in decisions}
    if len(decision_types) != len(set(decision_types)) or set(decision_types) != GAP_TYPES:
        errors.append("gap_type_decisions must contain each supported type exactly once")
    for gap_type, decision in by_type.items():
        expected = (
            "allowed"
            if gap_type in allowed
            else "conditional"
            if gap_type in conditional
            else "blocked"
        )
        if decision["decision"] != expected:
            errors.append(f"gap decision does not match its partition: {gap_type}")
        if decision["decision"] == "allowed" and decision["blocked_by"]:
            errors.append(f"allowed gap type has blocked_by entries: {gap_type}")
        if decision["decision"] != "allowed" and not decision["blocked_by"]:
            errors.append(f"non-allowed gap type lacks blocked_by evidence: {gap_type}")


def validate_certificate(certificate: object) -> list[str]:
    """Return semantic/arithmetic errors; an empty list means the certificate passes.

    This intentionally does not implement JSON Schema.  Run the contract schema first
    for types, required properties, formats, enums, and additional-property checks.
    """

    if not isinstance(certificate, dict):
        return ["certificate root must be a JSON object; run JSON Schema validation first"]

    errors: list[str] = []
    checks: tuple[tuple[str, Callable[[dict[str, Any], list[str]], None]], ...] = (
        ("sources", _check_sources),
        ("languages", _check_languages),
        ("years", _check_years),
        ("fulltext", _check_fulltext),
        ("parsing/indexing", _check_parsing_and_indexing),
        ("field observability", _check_fields),
        ("deduplication", _check_deduplication),
        ("retrieval saturation", _check_retrieval),
        ("gates/claim status", _check_gates_and_claim_status),
        ("gap partitions", _check_gap_partitions),
    )
    for label, check in checks:
        _run_check(errors, label, lambda check=check: check(certificate, errors))
    return errors


def validate_file(path: str | Path) -> tuple[object | None, list[str]]:
    """Load and semantically validate one JSON certificate."""

    certificate_path = Path(path)
    try:
        with certificate_path.open("r", encoding="utf-8") as handle:
            certificate = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, [f"cannot read JSON certificate: {exc}"]
    return certificate, validate_certificate(certificate)
