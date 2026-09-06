#!/usr/bin/env python3
"""Run the two-round adaptive carbon-market AI Scientist case.

Round 1 verifies the live-Qwen evidence workflow and the public-data execution
gate without estimating any outcome model. Round 2 is unavailable until a
separately frozen protocol binds the exact Round-1 result hash.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any

import numpy as np
import pandas as pd
from linearmodels.iv import AbsorbingLS
import linearmodels
import scipy
from scipy.stats import chi2


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROUND1_PROTOCOL = ROOT / "experiments/case010_carbon_market_round1_protocol.json"
DEFAULT_ROUND2_PROTOCOL = ROOT / "experiments/case010_carbon_market_round2_protocol.json"
DEFAULT_ROUND1_RESULT = ROOT / "output/experiments/case010_carbon_market_adaptive_v1/round1_result.json"
DEFAULT_OUTPUT = ROOT / "output/experiments/case010_carbon_market_adaptive_v1"
PRIMARY_CONTROLS = ["ln_total_assets", "leverage", "return_on_assets"]
CORE_ROBUSTNESS_IDS = [
    "R_NO_CONTROLS",
    "R_EXCLUDE_2021",
    "R_MONOTONE_PATHS",
    "R_INDEPENDENT_INVENTIONS",
]


def file_hash(path: Path, algorithm: str = "sha256") -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_hash_sidecar(path: Path) -> str:
    digest = file_hash(path)
    sidecar = path.with_suffix(".sha256")
    sidecar.write_text(f"{digest}  {path.name}\n", encoding="ascii")
    return digest


def resolve_root_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def verify_hash(path: Path, expected: str, algorithm: str = "sha256") -> str:
    if not path.is_file():
        raise FileNotFoundError(path)
    observed = file_hash(path, algorithm)
    if observed.lower() != str(expected).lower():
        raise ValueError(
            f"{algorithm.upper()} mismatch for {path}: expected {expected}, observed {observed}"
        )
    return observed


def no_secret_markers(paths: list[Path]) -> dict[str, Any]:
    markers = [b"DASHSCOPE_API_KEY", b'"api_key"', b"Bearer sk-", b"sk-"]
    findings: list[dict[str, str]] = []
    for path in paths:
        raw = path.read_bytes()
        for marker in markers:
            if marker.lower() in raw.lower():
                findings.append({"path": str(path.relative_to(ROOT)), "marker": marker.decode("ascii")})
    return {"passed": not findings, "findings": findings}


def execute_round1(protocol_path: Path, output_dir: Path) -> dict[str, Any]:
    protocol = load_json(protocol_path)
    if protocol.get("phase") != "round1":
        raise ValueError("Round-1 execution requires a phase=round1 protocol")

    qwen_contract = protocol["qwen_contract"]
    generation_path = resolve_root_path(qwen_contract["generation_path"])
    receipt_path = resolve_root_path(qwen_contract["receipt_path"])
    showcase_path = resolve_root_path(qwen_contract["showcase_manifest_path"])
    verify_hash(generation_path, qwen_contract["generation_sha256"])
    verify_hash(receipt_path, qwen_contract["receipt_sha256"])
    verify_hash(showcase_path, qwen_contract["showcase_manifest_sha256"])

    generation = load_json(generation_path)
    receipt = load_json(receipt_path)
    showcase = load_json(showcase_path)
    evidence_bundle = generation["evidence_bundle"]
    hits = evidence_bundle["evidence_hits"]
    document_counts = Counter(str(hit["document_id"]) for hit in hits)
    unique_documents = len(document_counts)
    maximum_hits = max(document_counts.values(), default=0)
    retrieval_rounds = generation.get("retrieval_rounds", [])
    consistency_reviews = generation.get("consistency_reviews", [])
    call_receipts = generation["model_usage"].get("call_receipts", [])

    expected_provider = qwen_contract["required_provider"]
    expected_model = qwen_contract["required_model"]
    call_contract_passed = bool(call_receipts) and all(
        item.get("provider") == expected_provider
        and item.get("model") == expected_model
        and item.get("outcome") == "succeeded"
        for item in call_receipts
    )
    diversity_passed = (
        unique_documents >= int(qwen_contract["minimum_unique_documents"])
        and maximum_hits <= int(qwen_contract["maximum_hits_per_document"])
        and bool(retrieval_rounds)
        and all(bool(item.get("diversity_gate_passed")) for item in retrieval_rounds)
    )
    consistency_passed = (
        bool(generation.get("final_consistency_passed"))
        and bool(consistency_reviews)
        and all(item.get("decision") == "pass" for item in consistency_reviews)
    )
    qwen_receipt = receipt["qwen_generation"]
    receipt_passed = (
        qwen_receipt.get("generation_source") == qwen_contract["required_generation_source"]
        and qwen_receipt.get("external_qwen_used") is True
        and receipt.get("search", {}).get("all_content_hashes_verified") is True
        and showcase.get("source_hashes", {}).get("qwen_generation_sha256")
        == qwen_contract["generation_sha256"]
        and showcase.get("source_hashes", {}).get("qwen_receipt_sha256")
        == qwen_contract["receipt_sha256"]
    )
    qwen_gate_passed = call_contract_passed and diversity_passed and consistency_passed and receipt_passed

    candidate_results: list[dict[str, Any]] = []
    for contract in protocol["candidate_data_contracts"]:
        path = resolve_root_path(contract["local_path"])
        sha256 = verify_hash(path, contract["sha256"])
        result: dict[str, Any] = {
            "candidate_id": contract["candidate_id"],
            "persistent_id": contract["persistent_id"],
            "license": contract["license"],
            "path": str(path.relative_to(ROOT)),
            "bytes": path.stat().st_size,
            "sha256": sha256,
            "hash_verified": True,
        }
        if contract.get("official_md5"):
            result["official_md5"] = verify_hash(path, contract["official_md5"], "md5")
        if contract.get("analysis_extract_path"):
            extract_path = resolve_root_path(contract["analysis_extract_path"])
            result["analysis_extract"] = {
                "path": str(extract_path.relative_to(ROOT)),
                "sha256": verify_hash(extract_path, contract["analysis_extract_sha256"]),
            }
            manifest_path = extract_path.with_suffix(".manifest.json")
            result["analysis_extract_manifest"] = {
                "path": str(manifest_path.relative_to(ROOT)),
                "sha256": verify_hash(
                    manifest_path, contract["analysis_extract_manifest_sha256"]
                ),
            }
        candidate_results.append(result)

    source_audit_contract = protocol["source_audit_contract"]
    source_audit_path = resolve_root_path(source_audit_contract["path"])
    source_audit_hash = verify_hash(source_audit_path, source_audit_contract["sha256"])
    source_audit = load_json(source_audit_path)
    profile = source_audit["data_profile"]
    readiness = source_audit["national_market_readiness"]
    diagnostics = source_audit["policy_field_diagnostics"]
    extract_manifest = load_json(
        resolve_root_path(
            next(
                item["analysis_extract_path"]
                for item in protocol["candidate_data_contracts"]
                if item.get("analysis_extract_path")
            )
        ).with_suffix(".manifest.json")
    )
    extract_output = extract_manifest["output"]

    national_executable = bool(readiness.get("can_support_national_ets_claim"))
    regional_replication_ready = (
        extract_output.get("duplicate_firm_year_rows") == 0
        and int(extract_output.get("year_min", 9999)) <= 2010
        and int(extract_output.get("year_max", 0)) >= 2021
        and int(extract_output.get("rows", 0)) > 0
        and readiness["requirements"].get("high_quality_green_patent_field_present") is True
        and readiness["requirements"].get("financing_constraint_field_present") is True
    )
    source_definition_caveat = (
        readiness["requirements"].get("official_national_ets_firm_list_bound") is not True
        or float(diagnostics.get("public_regional_pilot_encoding_match_rate", 0.0)) < 1.0
        or int(profile.get("policy_reversal_rows", 0)) > 0
    )

    triggered_rules: list[str] = []
    if national_executable:
        triggered_rules.append("R1_NATIONAL_EXECUTABLE")
    elif regional_replication_ready:
        triggered_rules.append("R1_SCOPE_ADAPT_REGIONAL")
    else:
        triggered_rules.append("R1_STOP")
    if source_definition_caveat:
        triggered_rules.append("R1_SOURCE_DEFINITION_CAVEAT")

    secret_scan = no_secret_markers([generation_path, receipt_path, showcase_path])
    all_gates_passed = qwen_gate_passed and secret_scan["passed"] and (
        national_executable or regional_replication_ready
    )
    next_scope = (
        "national_ets_confirmatory"
        if national_executable
        else "regional_source_defined_replication"
        if regional_replication_ready
        else "stopped"
    )

    result: dict[str, Any] = {
        "schema_version": "case010-adaptive-round1-result/1.0.0",
        "experiment_id": protocol["experiment_id"],
        "phase": "round1",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "path": str(protocol_path.relative_to(ROOT)),
            "sha256": file_hash(protocol_path),
            "frozen_at": protocol["frozen_at"],
        },
        "qwen_evidence_gate": {
            "passed": qwen_gate_passed,
            "provider": expected_provider,
            "model": expected_model,
            "generation_source": qwen_receipt.get("generation_source"),
            "external_qwen_used": qwen_receipt.get("external_qwen_used"),
            "call_contract_passed": call_contract_passed,
            "llm_calls": generation["model_usage"].get("llm_calls"),
            "input_tokens": generation["model_usage"].get("input_tokens"),
            "output_tokens": generation["model_usage"].get("output_tokens"),
            "wall_time_seconds": generation["model_usage"].get("wall_time_seconds"),
            "evidence_hit_count": len(hits),
            "unique_document_count": unique_documents,
            "maximum_hits_per_document": maximum_hits,
            "diversity_gate_passed": diversity_passed,
            "question_plan_consistency_passed": consistency_passed,
            "receipt_integrity_passed": receipt_passed,
            "repair_count": generation.get("repair_count"),
            "bundle_id": evidence_bundle.get("bundle_id"),
            "corpus_snapshot_id": evidence_bundle.get("corpus_snapshot_id"),
            "generation_sha256": qwen_contract["generation_sha256"],
            "receipt_sha256": qwen_contract["receipt_sha256"],
        },
        "public_data_gate": {
            "candidates": candidate_results,
            "source_audit": {
                "path": str(source_audit_path.relative_to(ROOT)),
                "sha256": source_audit_hash,
                "rows": profile.get("rows"),
                "unique_firms": profile.get("unique_symbol"),
                "year_min": profile.get("year_min"),
                "year_max": profile.get("year_max"),
                "duplicate_firm_year_rows": profile.get("duplicate_symbol_year_rows"),
                "policy_reversal_rows": profile.get("policy_reversal_rows"),
                "regional_encoding_match_rate": diagnostics.get(
                    "public_regional_pilot_encoding_match_rate"
                ),
            },
            "national_market": {
                "executable": national_executable,
                "blockers": readiness.get("blockers", []),
                "decision": readiness.get("decision"),
            },
            "regional_source_defined_replication": {
                "executable": regional_replication_ready,
                "scope_note": (
                    "Only the publisher-provided firm-year exposure coding may be used; "
                    "it is not an independently reconstructed official treatment list."
                ),
            },
        },
        "adaptive_decision": {
            "passed": all_gates_passed,
            "triggered_rules": triggered_rules,
            "next_scope": next_scope,
            "round2_allowed": all_gates_passed and next_scope != "stopped",
            "national_question_retained_as_future_extension": not national_executable,
            "reasons": [
                "The public panel ends in 2021 and therefore cannot identify a post-launch national ETS effect."
                if not national_executable
                else "The national ETS data gate passed.",
                "The licensed panel supports an outcome-blind, source-defined regional replication."
                if regional_replication_ready
                else "No executable licensed regional replication panel was found.",
                "Exposure provenance and non-monotone paths require restricted wording and diagnostic handling."
                if source_definition_caveat
                else "Exposure provenance is independently bound.",
            ],
        },
        "outcome_blinding": {
            "outcome_models_estimated": False,
            "statement": (
                "Round 1 inspected schema, missingness, keys, treatment trajectories, licenses, "
                "hashes, and workflow receipts only; no green-innovation outcome model was fit."
            ),
        },
        "privacy_and_integrity": {
            "secret_scan": secret_scan,
            "raw_data_modified": False,
            "anonymous_qwen_receipt_only": True,
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
    }
    output_path = output_dir / "round1_result.json"
    write_json(output_path, result)
    result_hash = write_hash_sidecar(output_path)
    print(
        json.dumps(
            {
                "phase": "round1",
                "output": str(output_path.resolve()),
                "sha256": result_hash,
                "round2_allowed": result["adaptive_decision"]["round2_allowed"],
                "next_scope": next_scope,
                "triggered_rules": triggered_rules,
            },
            ensure_ascii=False,
        )
    )
    return result


def round_float(value: Any, digits: int = 10) -> float | None:
    if value is None:
        return None
    number = float(np.asarray(value).squeeze())
    if not np.isfinite(number):
        return None
    return round(number, digits)


def validate_round2_binding(
    protocol: dict[str, Any], round1_result_path: Path
) -> tuple[dict[str, Any], str]:
    if protocol.get("phase") != "round2":
        raise ValueError("Round-2 execution requires a phase=round2 protocol")
    binding = protocol["round1_binding"]
    bound_path = resolve_root_path(binding["path"]).resolve()
    if bound_path != round1_result_path.resolve():
        raise ValueError(
            f"Round-1 path differs from frozen binding: {round1_result_path} != {bound_path}"
        )
    round1_hash = verify_hash(round1_result_path, binding["sha256"])
    round1 = load_json(round1_result_path)
    decision = round1["adaptive_decision"]
    if decision.get("round2_allowed") is not True:
        raise ValueError("Round 1 did not authorize Round 2")
    if decision.get("next_scope") != binding["required_next_scope"]:
        raise ValueError("Round-1 next scope differs from frozen Round-2 binding")
    triggered = set(decision.get("triggered_rules", []))
    required = set(binding.get("required_triggered_rules", []))
    if not required.issubset(triggered):
        raise ValueError(f"Missing required Round-1 triggers: {sorted(required - triggered)}")
    if round1.get("outcome_blinding", {}).get("outcome_models_estimated") is not False:
        raise ValueError("Round 1 does not preserve the required outcome-blinding statement")
    return round1, round1_hash


def load_round2_data(
    protocol: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    contract = protocol["data_contract"]
    source_path = resolve_root_path(contract["source_path"])
    extract_path = resolve_root_path(contract["analysis_extract_path"])
    manifest_path = resolve_root_path(contract["analysis_extract_manifest_path"])
    verify_hash(source_path, contract["source_sha256"])
    verify_hash(extract_path, contract["analysis_extract_sha256"])
    verify_hash(manifest_path, contract["analysis_extract_manifest_sha256"])

    data = pd.read_csv(extract_path)
    expected_years = [int(value) for value in contract["expected_years"]]
    if len(data) != int(contract["expected_rows"]):
        raise ValueError(f"unexpected extract row count: {len(data)}")
    if data["firm_id"].nunique() != int(contract["expected_firms"]):
        raise ValueError("unexpected firm count")
    if sorted(data["year"].astype(int).unique().tolist()) != expected_years:
        raise ValueError("unexpected year coverage")
    if data.duplicated(["firm_id", "year"]).any():
        raise ValueError("duplicate firm-year rows")
    if not set(data["source_policy_post"].dropna().unique()).issubset({0, 1}):
        raise ValueError("source_policy_post must be binary")

    numeric_columns = [
        "year",
        "source_policy_post",
        "leverage",
        "return_on_assets",
        "total_assets",
        "industry_hhi_a",
        "financing_constraint_sa",
        "green_patent_independent_all",
        "green_invention_independent",
        "green_utility_independent",
        "green_patent_joint_all",
        "green_invention_joint",
        "green_utility_joint",
    ]
    for column in numeric_columns:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    if data["total_assets"].le(0).any():
        raise ValueError("total_assets must be strictly positive before log transform")

    data["ln_total_assets"] = np.log(data["total_assets"])
    data["ln_high_quality_green_invention"] = np.log1p(
        data["green_invention_independent"] + data["green_invention_joint"]
    )
    data["ln_independent_green_invention"] = np.log1p(
        data["green_invention_independent"]
    )
    data["ln_total_green_patents"] = np.log1p(
        data["green_patent_independent_all"] + data["green_patent_joint_all"]
    )
    data["ln_green_utility_models"] = np.log1p(
        data["green_utility_independent"] + data["green_utility_joint"]
    )
    data["abs_sa_financing_constraint"] = data["financing_constraint_sa"].abs()
    annual_hhi_median = data.groupby("year")["industry_hhi_a"].transform("median")
    data["high_competition"] = np.where(
        data["industry_hhi_a"].notna(),
        (data["industry_hhi_a"] <= annual_hhi_median).astype(float),
        np.nan,
    )
    data["source_policy_post_x_high_competition"] = (
        data["source_policy_post"] * data["high_competition"]
    )
    data = data.sort_values(["firm_id", "year"]).reset_index(drop=True)
    reversal_rows = data.groupby("firm_id", sort=False)["source_policy_post"].diff().lt(0)
    reversal_firms = set(data.loc[reversal_rows, "firm_id"].tolist())
    data["monotone_policy_path"] = ~data["firm_id"].isin(reversal_firms)

    primary_required = [
        "ln_high_quality_green_invention",
        "source_policy_post",
        *PRIMARY_CONTROLS,
    ]
    expected_year_set = set(expected_years)
    complete_firms: list[Any] = []
    for firm_id, group in data.groupby("firm_id", sort=False):
        if (
            len(group) == len(expected_years)
            and set(group["year"].astype(int)) == expected_year_set
            and not group[primary_required].isna().any().any()
        ):
            complete_firms.append(firm_id)
    primary = data.loc[data["firm_id"].isin(complete_firms)].copy()
    if len(primary) != len(complete_firms) * len(expected_years):
        raise ValueError("primary sample is not balanced")

    sample_audit = {
        "source_rows": int(len(data)),
        "source_firms": int(data["firm_id"].nunique()),
        "primary_rows": int(len(primary)),
        "primary_firms": int(primary["firm_id"].nunique()),
        "primary_years": sorted(primary["year"].astype(int).unique().tolist()),
        "excluded_incomplete_firms": int(data["firm_id"].nunique() - primary["firm_id"].nunique()),
        "policy_reversal_rows": int(reversal_rows.sum()),
        "policy_reversal_firms": int(len(reversal_firms)),
        "primary_monotone_firms": int(
            primary.loc[primary["monotone_policy_path"], "firm_id"].nunique()
        ),
        "primary_ever_exposed_firms": int(
            primary.groupby("firm_id")["source_policy_post"].max().sum()
        ),
        "primary_never_exposed_firms": int(
            primary.groupby("firm_id")["source_policy_post"].max().eq(0).sum()
        ),
        "raw_source_sha256_after_load": file_hash(source_path),
        "analysis_extract_sha256_after_load": file_hash(extract_path),
    }
    return data, primary, sample_audit


def fit_fe_model(sample: pd.DataFrame, outcome: str, regressors: list[str]) -> Any:
    required = [outcome, "firm_id", "year", *regressors]
    estimation = sample.dropna(subset=required).copy()
    if estimation.empty:
        raise ValueError(f"empty estimation sample for {outcome}: {regressors}")
    absorb = pd.DataFrame(
        {
            "firm": pd.Categorical(estimation["firm_id"]),
            "year": pd.Categorical(estimation["year"]),
        },
        index=estimation.index,
    )
    model = AbsorbingLS(
        estimation[outcome].astype(float),
        estimation[regressors].astype(float),
        absorb=absorb,
        drop_absorbed=True,
    )
    fitted = model.fit(
        cov_type="clustered",
        clusters=pd.Series(estimation["firm_id"].to_numpy(), index=estimation.index),
        debiased=True,
        method="hdfe",
        absorb_options={"compute_degrees": False},
        use_cache=True,
    )
    fitted._case010_estimation_index = estimation.index  # type: ignore[attr-defined]
    return fitted


def term_summary(model: Any, term: str, sample: pd.DataFrame) -> dict[str, Any]:
    interval = model.conf_int(level=0.95).loc[term]
    estimation_index = getattr(model, "_case010_estimation_index")
    estimation = sample.loc[estimation_index]
    return {
        "term": term,
        "coefficient": round_float(model.params[term]),
        "clustered_standard_error": round_float(model.std_errors[term]),
        "p_value_two_sided": round_float(model.pvalues[term]),
        "confidence_interval_95": [
            round_float(interval.iloc[0]),
            round_float(interval.iloc[1]),
        ],
        "nobs": int(model.nobs),
        "firm_clusters": int(estimation["firm_id"].nunique()),
        "year_min": int(estimation["year"].min()),
        "year_max": int(estimation["year"].max()),
        "r_squared": round_float(model.rsquared),
        "absorbed_r_squared": round_float(getattr(model, "absorbed_rsquared", None)),
    }


def model_record(
    model_id: str,
    label: str,
    model: Any,
    term: str,
    sample: pd.DataFrame,
    outcome: str,
    regressors: list[str],
) -> dict[str, Any]:
    return {
        "model_id": model_id,
        "label": label,
        "outcome": outcome,
        "regressors": regressors,
        "fixed_effects": ["firm_id", "year"],
        "standard_errors": "clustered_by_firm_id",
        "estimate": term_summary(model, term, sample),
    }


def fit_event_study(
    primary: pd.DataFrame,
) -> tuple[Any, pd.DataFrame, list[dict[str, Any]], dict[str, Any]]:
    event = primary.loc[primary["monotone_policy_path"]].copy()
    first_exposed = (
        event.loc[event["source_policy_post"].eq(1)]
        .groupby("firm_id")["year"]
        .min()
    )
    event["first_exposed_year"] = event["firm_id"].map(first_exposed)
    event["event_time"] = event["year"] - event["first_exposed_year"]
    treated = event["first_exposed_year"].notna()
    definitions = [
        ("event_le_m4", -4, treated & event["event_time"].le(-4), "≤-4"),
        ("event_m3", -3, treated & event["event_time"].eq(-3), "-3"),
        ("event_m2", -2, treated & event["event_time"].eq(-2), "-2"),
        ("event_p0", 0, treated & event["event_time"].eq(0), "0"),
        ("event_p1", 1, treated & event["event_time"].eq(1), "1"),
        ("event_p2", 2, treated & event["event_time"].eq(2), "2"),
        ("event_p3", 3, treated & event["event_time"].eq(3), "3"),
        ("event_ge_p4", 4, treated & event["event_time"].ge(4), "≥4"),
    ]
    event_terms: list[str] = []
    for term, _, mask, _ in definitions:
        event[term] = mask.astype(float)
        event_terms.append(term)
    regressors = [*event_terms, *PRIMARY_CONTROLS]
    model = fit_fe_model(event, "ln_high_quality_green_invention", regressors)
    points: list[dict[str, Any]] = []
    for term, period, _, display in definitions:
        summary = term_summary(model, term, event)
        points.append(
            {
                "term": term,
                "relative_time": period,
                "display_period": display,
                **summary,
            }
        )
    pre_terms = ["event_le_m4", "event_m3", "event_m2"]
    beta = model.params.loc[pre_terms].to_numpy(dtype=float)
    covariance = model.cov.loc[pre_terms, pre_terms].to_numpy(dtype=float)
    statistic = float(beta.T @ np.linalg.pinv(covariance) @ beta)
    p_value = float(chi2.sf(statistic, len(pre_terms)))
    diagnostic = {
        "reference_period": -1,
        "pretrend_terms": pre_terms,
        "joint_pretrend_chi2": round_float(statistic),
        "joint_pretrend_df": len(pre_terms),
        "joint_pretrend_p_value": round_float(p_value),
        "pretrend_pass_at_0_10": p_value >= 0.10,
        "sample_rows": int(model.nobs),
        "sample_firms": int(event["firm_id"].nunique()),
        "treated_firms": int(first_exposed.size),
        "never_exposed_firms": int(event["firm_id"].nunique() - first_exposed.size),
        "interpretation_limit": (
            "Conventional staggered-treatment TWFE event coefficients are used only as "
            "a trend and dynamic-pattern diagnostic."
        ),
    }
    return model, event, points, diagnostic


def two_way_demean(matrix: np.ndarray) -> np.ndarray:
    return matrix - matrix.mean(axis=1, keepdims=True) - matrix.mean(axis=0, keepdims=True) + matrix.mean()


def trajectory_placebo(
    primary: pd.DataFrame, repetitions: int, seed: int, observed_coefficient: float
) -> tuple[dict[str, Any], pd.DataFrame]:
    ordered = primary.sort_values(["firm_id", "year"])
    firms = ordered["firm_id"].drop_duplicates().tolist()
    years = sorted(ordered["year"].astype(int).unique().tolist())
    n_firms, n_years = len(firms), len(years)
    if len(ordered) != n_firms * n_years:
        raise ValueError("trajectory placebo requires a balanced panel")
    y = ordered["ln_high_quality_green_invention"].to_numpy(dtype=float).reshape(n_firms, n_years)
    exposure = ordered["source_policy_post"].to_numpy(dtype=float).reshape(n_firms, n_years)
    y_within = two_way_demean(y)
    observed_within_exposure = two_way_demean(exposure)
    observed_within = float(
        np.sum(observed_within_exposure * y_within)
        / np.sum(observed_within_exposure * observed_within_exposure)
    )
    if not np.isclose(observed_within, observed_coefficient, atol=1e-8, rtol=1e-8):
        raise ValueError(
            f"within estimator and AbsorbingLS disagree: {observed_within} vs {observed_coefficient}"
        )
    rng = np.random.default_rng(seed)
    coefficients = np.empty(repetitions, dtype=float)
    for index in range(repetitions):
        permuted = exposure[rng.permutation(n_firms), :]
        within = two_way_demean(permuted)
        denominator = float(np.sum(within * within))
        coefficients[index] = float(np.sum(within * y_within) / denominator)
    exceedances = int(np.sum(np.abs(coefficients) >= abs(observed_within)))
    p_value = (1 + exceedances) / (1 + repetitions)
    distribution = pd.DataFrame(
        {
            "permutation": np.arange(1, repetitions + 1, dtype=int),
            "coefficient": coefficients,
        }
    )
    summary = {
        "method": "firm-level permutation of complete policy-exposure trajectories",
        "repetitions": repetitions,
        "seed": seed,
        "observed_no_controls_coefficient": round_float(observed_within),
        "exceedances": exceedances,
        "randomization_p_value_two_sided": round_float(p_value),
        "null_distribution": {
            "mean": round_float(coefficients.mean()),
            "standard_deviation": round_float(coefficients.std(ddof=1)),
            "quantiles": {
                "0.025": round_float(np.quantile(coefficients, 0.025)),
                "0.5": round_float(np.quantile(coefficients, 0.5)),
                "0.975": round_float(np.quantile(coefficients, 0.975)),
            },
        },
    }
    return summary, distribution


def write_csv(path: Path, frame: pd.DataFrame) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return file_hash(path)


def render_case_figures(
    output_dir: Path,
    event_points: list[dict[str, Any]],
    model_records: list[dict[str, Any]],
) -> dict[str, Any]:
    spec_dir = output_dir / "figure_specs"
    figure_dir = output_dir / "figures"
    spec_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    renderer = (
        Path.home()
        / ".codex"
        / "skills"
        / "chinese-econ-journal-figures"
        / "scripts"
        / "render_econ_figure.py"
    )
    if not renderer.is_file():
        raise FileNotFoundError(f"figure renderer not found: {renderer}")

    event_spec = {
        "id": "carbon_market_event_study",
        "kind": "event_study",
        "provenance": "estimated",
        "x": [point["relative_time"] for point in event_points],
        "x_labels": [point["display_period"] for point in event_points],
        "estimate": [point["coefficient"] for point in event_points],
        "lower": [point["confidence_interval_95"][0] for point in event_points],
        "upper": [point["confidence_interval_95"][1] for point in event_points],
        "policy_time": 0,
        "reference_period": -1,
        "x_label": "相对首次政策暴露年份",
        "y_label": "绿色发明专利估计系数",
    }
    comparison_ids = [
        "M1_PRIMARY_ASSOCIATION",
        "R_NO_CONTROLS",
        "R_EXCLUDE_2021",
        "R_MONOTONE_PATHS",
        "R_INDEPENDENT_INVENTIONS",
        "R_TOTAL_GREEN_PATENTS",
        "R_UTILITY_MODEL_CONTRAST",
        "R_ADD_INDUSTRY_HHI",
    ]
    selected = {record["model_id"]: record for record in model_records}
    coefficient_spec = {
        "id": "carbon_market_model_comparison",
        "kind": "coefficient",
        "provenance": "estimated",
        "reference": 0,
        "x_label": "政策暴露系数及95%置信区间",
        "rows": [
            {
                "label": selected[model_id]["label"],
                "estimate": selected[model_id]["estimate"]["coefficient"],
                "lower": selected[model_id]["estimate"]["confidence_interval_95"][0],
                "upper": selected[model_id]["estimate"]["confidence_interval_95"][1],
            }
            for model_id in comparison_ids
        ],
    }
    mechanism_spec = {
        "id": "carbon_market_mechanism_framework",
        "kind": "mechanism",
        "provenance": "conceptual",
        "nodes": [
            {
                "id": "exposure",
                "label": "碳市场政策暴露",
                "x": 0.13,
                "y": 0.55,
                "width": 0.2,
                "height": 0.16,
                "fill": "#FFFFFF",
            },
            {
                "id": "finance",
                "label": "融资约束缓解\n绿色融资可得性提高",
                "x": 0.48,
                "y": 0.75,
                "width": 0.25,
                "height": 0.18,
                "fill": "#F2F2F2",
            },
            {
                "id": "incentive",
                "label": "合规压力与碳价信号\n创新收益相对上升",
                "x": 0.48,
                "y": 0.34,
                "width": 0.25,
                "height": 0.18,
                "fill": "#F2F2F2",
            },
            {
                "id": "innovation",
                "label": "高质量绿色技术创新\n绿色发明专利申请",
                "x": 0.84,
                "y": 0.55,
                "width": 0.24,
                "height": 0.18,
                "fill": "#FFFFFF",
            },
            {
                "id": "competition",
                "label": "市场竞争程度\n边界条件",
                "x": 0.66,
                "y": 0.10,
                "width": 0.19,
                "height": 0.14,
                "fill": "#FFFFFF",
            },
        ],
        "edges": [
            {"from": "exposure", "to": "finance", "label": "金融资源配置"},
            {"from": "finance", "to": "innovation", "label": "长期研发投入"},
            {"from": "exposure", "to": "incentive", "label": "规制与价格信号"},
            {"from": "incentive", "to": "innovation", "label": "创新补偿与转型"},
            {
                "from": "competition",
                "to": "innovation",
                "label": "调节",
                "style": "dashed",
                "connection": "arc3,rad=-0.12",
            },
        ],
    }
    specs = {
        "event_study": event_spec,
        "model_comparison": coefficient_spec,
        "mechanism_framework": mechanism_spec,
    }
    entries: list[dict[str, Any]] = []
    captions = {
        "event_study": {
            "title": "图1  政策暴露前后的绿色发明专利动态",
            "note": "点为企业和年份固定效应估计，线段为企业层面聚类的95%置信区间；-1期为基期。仅使用政策路径单调的企业，作为趋势与动态模式诊断。",
            "source": "数据来源：Mendeley Data公开复现样本（CC BY 4.0），作者计算。",
        },
        "model_comparison": {
            "title": "图2  不同模型设定下的政策暴露系数",
            "note": "点为估计系数，线段为企业层面聚类的95%置信区间。不同结果变量的估计用于稳健性和质量区分，不应比较系数绝对大小。",
            "source": "数据来源：Mendeley Data公开复现样本（CC BY 4.0），作者计算。",
        },
        "mechanism_framework": {
            "title": "图3  碳市场影响高质量绿色技术创新的理论机制",
            "note": "该图为理论框架，不是统计估计结果；融资约束和市场竞争仅在本案例中作机制一致性与探索性异质性诊断。",
            "source": "资料来源：HypoWeaver-Qwen基于证据束生成并经研究设计门修订。",
        },
    }
    for name, spec in specs.items():
        spec_path = spec_dir / f"{spec['id']}.json"
        write_json(spec_path, spec)
        completed = subprocess.run(
            [
                sys.executable,
                str(renderer),
                "--spec",
                str(spec_path),
                "--output-dir",
                str(figure_dir),
            ],
            check=True,
            capture_output=True,
        )
        metadata_path = figure_dir / f"{spec['id']}.metadata.json"
        metadata = load_json(metadata_path)
        files: dict[str, dict[str, Any]] = {}
        for extension, filename in metadata["outputs"].items():
            path = figure_dir / filename
            files[extension] = {
                "path": str(path.relative_to(ROOT)),
                "sha256": file_hash(path),
                "bytes": path.stat().st_size,
            }
        entries.append(
            {
                "name": name,
                "figure_id": spec["id"],
                "provenance": spec["provenance"],
                "spec_path": str(spec_path.relative_to(ROOT)),
                "spec_sha256": file_hash(spec_path),
                "renderer_path": str(renderer),
                "renderer_sha256": file_hash(renderer),
                "metadata_path": str(metadata_path.relative_to(ROOT)),
                "metadata_sha256": file_hash(metadata_path),
                "files": files,
                **captions[name],
                "renderer_stdout": completed.stdout.decode("utf-8", errors="replace").strip(),
            }
        )
    manifest = {
        "schema_version": "case010-figure-manifest/1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "style": "Chinese economics journal grayscale manuscript figure",
        "figures": entries,
    }
    manifest_path = output_dir / "figure_manifest.json"
    write_json(manifest_path, manifest)
    return {
        "path": str(manifest_path.relative_to(ROOT)),
        "sha256": file_hash(manifest_path),
        "figures": entries,
    }


def execute_round2(
    protocol_path: Path, output_dir: Path, round1_result_path: Path
) -> dict[str, Any]:
    protocol = load_json(protocol_path)
    round1, round1_hash = validate_round2_binding(protocol, round1_result_path)
    protocol_hash = file_hash(protocol_path)
    source, primary, sample_audit = load_round2_data(protocol)

    baseline_model = fit_fe_model(
        primary,
        "ln_high_quality_green_invention",
        ["source_policy_post", *PRIMARY_CONTROLS],
    )
    model_records: list[dict[str, Any]] = [
        model_record(
            "M1_PRIMARY_ASSOCIATION",
            "基准模型",
            baseline_model,
            "source_policy_post",
            primary,
            "ln_high_quality_green_invention",
            ["source_policy_post", *PRIMARY_CONTROLS],
        )
    ]

    specifications = [
        (
            "R_NO_CONTROLS",
            "不含控制变量",
            primary,
            "ln_high_quality_green_invention",
            ["source_policy_post"],
        ),
        (
            "R_EXCLUDE_2021",
            "剔除2021年",
            primary.loc[primary["year"].lt(2021)].copy(),
            "ln_high_quality_green_invention",
            ["source_policy_post", *PRIMARY_CONTROLS],
        ),
        (
            "R_MONOTONE_PATHS",
            "仅单调暴露路径",
            primary.loc[primary["monotone_policy_path"]].copy(),
            "ln_high_quality_green_invention",
            ["source_policy_post", *PRIMARY_CONTROLS],
        ),
        (
            "R_INDEPENDENT_INVENTIONS",
            "仅独立绿色发明",
            primary,
            "ln_independent_green_invention",
            ["source_policy_post", *PRIMARY_CONTROLS],
        ),
        (
            "R_TOTAL_GREEN_PATENTS",
            "全部绿色专利",
            primary,
            "ln_total_green_patents",
            ["source_policy_post", *PRIMARY_CONTROLS],
        ),
        (
            "R_UTILITY_MODEL_CONTRAST",
            "实用新型对照",
            primary,
            "ln_green_utility_models",
            ["source_policy_post", *PRIMARY_CONTROLS],
        ),
        (
            "R_ADD_INDUSTRY_HHI",
            "加入行业集中度",
            primary.dropna(subset=["industry_hhi_a"]).copy(),
            "ln_high_quality_green_invention",
            ["source_policy_post", *PRIMARY_CONTROLS, "industry_hhi_a"],
        ),
    ]
    for model_id, label, sample, outcome, regressors in specifications:
        fitted = fit_fe_model(sample, outcome, regressors)
        model_records.append(
            model_record(
                model_id,
                label,
                fitted,
                "source_policy_post",
                sample,
                outcome,
                regressors,
            )
        )

    event_model, event_sample, event_points, event_diagnostic = fit_event_study(primary)
    del event_model, event_sample

    mechanism_model = fit_fe_model(
        primary,
        "abs_sa_financing_constraint",
        ["source_policy_post", "leverage", "return_on_assets"],
    )
    mechanism = model_record(
        "M3_FINANCING_CONSTRAINT_DIAGNOSTIC",
        "融资约束代理值",
        mechanism_model,
        "source_policy_post",
        primary,
        "abs_sa_financing_constraint",
        ["source_policy_post", "leverage", "return_on_assets"],
    )
    heterogeneity_sample = primary.dropna(subset=["industry_hhi_a", "high_competition"]).copy()
    heterogeneity_regressors = [
        "source_policy_post",
        "high_competition",
        "source_policy_post_x_high_competition",
        *PRIMARY_CONTROLS,
    ]
    heterogeneity_model = fit_fe_model(
        heterogeneity_sample,
        "ln_high_quality_green_invention",
        heterogeneity_regressors,
    )
    heterogeneity = model_record(
        "M4_COMPETITION_HETEROGENEITY",
        "高竞争行业交互项",
        heterogeneity_model,
        "source_policy_post_x_high_competition",
        heterogeneity_sample,
        "ln_high_quality_green_invention",
        heterogeneity_regressors,
    )

    no_controls_record = next(
        record for record in model_records if record["model_id"] == "R_NO_CONTROLS"
    )
    placebo_contract = protocol["placebo_contract"]
    placebo, placebo_distribution = trajectory_placebo(
        primary,
        int(placebo_contract["repetitions"]),
        int(placebo_contract["seed"]),
        float(no_controls_record["estimate"]["coefficient"]),
    )

    model_rows = []
    for record in model_records:
        estimate = record["estimate"]
        model_rows.append(
            {
                "model_id": record["model_id"],
                "model_label": record["label"],
                "outcome": record["outcome"],
                "coefficient": estimate["coefficient"],
                "clustered_standard_error": estimate["clustered_standard_error"],
                "p_value_two_sided": estimate["p_value_two_sided"],
                "ci95_lower": estimate["confidence_interval_95"][0],
                "ci95_upper": estimate["confidence_interval_95"][1],
                "nobs": estimate["nobs"],
                "firm_clusters": estimate["firm_clusters"],
                "year_min": estimate["year_min"],
                "year_max": estimate["year_max"],
                "firm_fixed_effects": "yes",
                "year_fixed_effects": "yes",
                "firm_clustered_standard_errors": "yes",
            }
        )
    model_table_path = output_dir / "model_comparison.csv"
    model_table_hash = write_csv(model_table_path, pd.DataFrame(model_rows))
    event_table_path = output_dir / "event_study.csv"
    event_table_hash = write_csv(event_table_path, pd.DataFrame(event_points))
    mechanism_table_path = output_dir / "mechanism_and_heterogeneity.csv"
    mechanism_table_hash = write_csv(
        mechanism_table_path,
        pd.DataFrame(
            [
                {
                    "analysis": "financing_constraint_diagnostic",
                    **mechanism["estimate"],
                },
                {
                    "analysis": "competition_heterogeneity_interaction",
                    **heterogeneity["estimate"],
                },
            ]
        ),
    )
    placebo_path = output_dir / "placebo_distribution.csv"
    placebo_hash = write_csv(placebo_path, placebo_distribution)
    figure_manifest = render_case_figures(output_dir, event_points, model_records)

    baseline = model_records[0]["estimate"]
    directional_support = (
        float(baseline["coefficient"]) > 0
        and float(baseline["p_value_two_sided"]) < 0.05
    )
    core_records = [
        record for record in model_records if record["model_id"] in CORE_ROBUSTNESS_IDS
    ]
    positive_core = sum(float(record["estimate"]["coefficient"]) > 0 for record in core_records)
    robustness_support = positive_core >= 3
    pretrend_pass = bool(event_diagnostic["pretrend_pass_at_0_10"])
    decision_flags = [directional_support, pretrend_pass, robustness_support]
    if all(decision_flags):
        replication_evidence = "supportive"
    elif any(decision_flags):
        replication_evidence = "mixed"
    else:
        replication_evidence = "not_supportive"
    mechanism_consistent = (
        float(mechanism["estimate"]["coefficient"]) < 0
        and float(mechanism["estimate"]["p_value_two_sided"]) < 0.05
    )
    competition_consistent = (
        float(heterogeneity["estimate"]["coefficient"]) > 0
        and float(heterogeneity["estimate"]["p_value_two_sided"]) < 0.05
    )

    outputs = {
        "model_table": {
            "path": str(model_table_path.relative_to(ROOT)),
            "sha256": model_table_hash,
        },
        "event_table": {
            "path": str(event_table_path.relative_to(ROOT)),
            "sha256": event_table_hash,
        },
        "mechanism_table": {
            "path": str(mechanism_table_path.relative_to(ROOT)),
            "sha256": mechanism_table_hash,
        },
        "placebo_distribution": {
            "path": str(placebo_path.relative_to(ROOT)),
            "sha256": placebo_hash,
        },
        "figure_manifest": {
            "path": figure_manifest["path"],
            "sha256": figure_manifest["sha256"],
        },
    }
    result: dict[str, Any] = {
        "schema_version": "case010-adaptive-round2-result/1.0.0",
        "experiment_id": protocol["experiment_id"],
        "phase": "round2",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "path": str(protocol_path.relative_to(ROOT)),
            "sha256": protocol_hash,
            "frozen_at": protocol["frozen_at"],
            "round1_result_sha256": round1_hash,
            "round1_binding_verified": True,
        },
        "research_scope": protocol["scope_adaptation"],
        "data_lineage": {
            "persistent_id": protocol["data_contract"]["persistent_id"],
            "license": protocol["data_contract"]["license"],
            "source_sha256": protocol["data_contract"]["source_sha256"],
            "analysis_extract_sha256": protocol["data_contract"][
                "analysis_extract_sha256"
            ],
            "raw_data_modified": False,
        },
        "sample_audit": sample_audit,
        "descriptive_profile": {
            "primary_outcome_mean": round_float(
                primary["ln_high_quality_green_invention"].mean()
            ),
            "primary_outcome_standard_deviation": round_float(
                primary["ln_high_quality_green_invention"].std(ddof=1)
            ),
            "policy_exposure_share": round_float(primary["source_policy_post"].mean()),
            "zero_green_invention_share": round_float(
                primary["ln_high_quality_green_invention"].eq(0).mean()
            ),
        },
        "models": {
            "primary_and_robustness": model_records,
            "event_study": {
                "points": event_points,
                "diagnostic": event_diagnostic,
            },
            "mechanism": mechanism,
            "competition_heterogeneity": heterogeneity,
            "ownership_heterogeneity": {
                "status": "not_executed",
                "reason": protocol["variable_contract"]["ownership_status"],
            },
            "trajectory_placebo": placebo,
        },
        "hypothesis_assessment": {
            "original_national_market_h1": {
                "status": "not_tested",
                "reason": "No post-2021 outcome period is present in the licensed panel.",
            },
            "adapted_regional_replication": {
                "status": replication_evidence,
                "directional_support": directional_support,
                "pretrend_pass": pretrend_pass,
                "robustness_support": robustness_support,
                "positive_core_robustness_count": positive_core,
                "core_robustness_count": len(core_records),
                "placebo_p_value_two_sided": placebo[
                    "randomization_p_value_two_sided"
                ],
            },
            "financing_constraint_mechanism": {
                "status": "consistent" if mechanism_consistent else "not_confirmed",
                "causal_mechanism_identified": False,
            },
            "competition_heterogeneity": {
                "status": "consistent" if competition_consistent else "not_confirmed",
                "exploratory": True,
            },
            "ownership_heterogeneity": "not_tested_due_to_unresolved_value_labels",
        },
        "claim_gate": {
            "causal_claim_authorized": False,
            "causal_blockers": protocol["decision_contract"]["causal_blockers"],
            "allowed_wording": protocol["decision_contract"]["allowed_wording"],
            "forbidden_wording": protocol["decision_contract"]["forbidden_wording"],
            "replication_evidence_assessment": replication_evidence,
        },
        "outputs": outputs,
        "figure_manifest": figure_manifest,
        "qwen_lineage": {
            "generation_sha256": round1["qwen_evidence_gate"]["generation_sha256"],
            "receipt_sha256": round1["qwen_evidence_gate"]["receipt_sha256"],
            "provider": round1["qwen_evidence_gate"]["provider"],
            "model": round1["qwen_evidence_gate"]["model"],
            "external_qwen_used": round1["qwen_evidence_gate"]["external_qwen_used"],
        },
        "environment": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "linearmodels": linearmodels.__version__,
            "runner_sha256": file_hash(Path(__file__)),
        },
    }
    result_path = output_dir / "round2_result.json"
    write_json(result_path, result)
    result_hash = write_hash_sidecar(result_path)
    print(
        json.dumps(
            {
                "phase": "round2",
                "output": str(result_path.resolve()),
                "sha256": result_hash,
                "replication_evidence_assessment": replication_evidence,
                "causal_claim_authorized": False,
                "baseline_coefficient": baseline["coefficient"],
                "baseline_p_value": baseline["p_value_two_sided"],
                "pretrend_p_value": event_diagnostic["joint_pretrend_p_value"],
                "placebo_p_value": placebo["randomization_p_value_two_sided"],
            },
            ensure_ascii=False,
        )
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["round1", "round2"], required=True)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--round1-result", type=Path, default=DEFAULT_ROUND1_RESULT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.phase == "round1":
        protocol = args.protocol or DEFAULT_ROUND1_PROTOCOL
        execute_round1(protocol.resolve(), args.output_dir.resolve())
        return 0
    protocol = args.protocol or DEFAULT_ROUND2_PROTOCOL
    execute_round2(
        protocol.resolve(), args.output_dir.resolve(), args.round1_result.resolve()
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
