#!/usr/bin/env python3
"""Independently recompute and verify the adaptive carbon-market case.

This verifier does not import the execution script. It residualizes firm and
year effects by alternating projections, solves OLS directly with NumPy, and
reconstructs the firm-clustered sandwich covariance and trajectory placebo.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import chi2, t


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "output/experiments/case010_carbon_market_adaptive_v1"
ROUND1_PROTOCOL = ROOT / "experiments/case010_carbon_market_round1_protocol.json"
ROUND2_PROTOCOL = ROOT / "experiments/case010_carbon_market_round2_protocol.json"
ROUND1_RESULT = OUTPUT_DIR / "round1_result.json"
ROUND2_RESULT = OUTPUT_DIR / "round2_result.json"
PRIMARY_CONTROLS = ["ln_total_assets", "leverage", "return_on_assets"]


def file_hash(path: Path, algorithm: str = "sha256") -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def resolve_root(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def transform_data(protocol: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    contract = protocol["data_contract"]
    source = resolve_root(contract["source_path"])
    extract = resolve_root(contract["analysis_extract_path"])
    manifest = resolve_root(contract["analysis_extract_manifest_path"])
    if file_hash(source) != contract["source_sha256"]:
        raise ValueError("source data hash mismatch")
    if file_hash(extract) != contract["analysis_extract_sha256"]:
        raise ValueError("analysis extract hash mismatch")
    if file_hash(manifest) != contract["analysis_extract_manifest_sha256"]:
        raise ValueError("analysis extract manifest hash mismatch")

    data = pd.read_csv(extract).sort_values(["firm_id", "year"]).reset_index(drop=True)
    if len(data) != contract["expected_rows"]:
        raise ValueError("unexpected row count")
    if data.duplicated(["firm_id", "year"]).any():
        raise ValueError("duplicate firm-year keys")
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
    annual_median = data.groupby("year")["industry_hhi_a"].transform("median")
    data["high_competition"] = np.where(
        data["industry_hhi_a"].notna(),
        (data["industry_hhi_a"] <= annual_median).astype(float),
        np.nan,
    )
    data["source_policy_post_x_high_competition"] = (
        data["source_policy_post"] * data["high_competition"]
    )
    reversal = data.groupby("firm_id", sort=False)["source_policy_post"].diff().lt(0)
    reversal_firms = set(data.loc[reversal, "firm_id"])
    data["monotone_policy_path"] = ~data["firm_id"].isin(reversal_firms)

    required = [
        "ln_high_quality_green_invention",
        "source_policy_post",
        *PRIMARY_CONTROLS,
    ]
    expected_years = set(int(value) for value in contract["expected_years"])
    firm_ok = data.groupby("firm_id", sort=False).apply(
        lambda group: len(group) == len(expected_years)
        and set(group["year"].astype(int)) == expected_years
        and not group[required].isna().any().any(),
        include_groups=False,
    )
    primary = data.loc[data["firm_id"].isin(firm_ok[firm_ok].index)].copy()
    return data, primary


def residualize_two_way(
    sample: pd.DataFrame, columns: list[str], tolerance: float = 1e-12
) -> np.ndarray:
    work = sample[["firm_id", "year", *columns]].copy()
    values = work[columns].to_numpy(dtype=float)
    firm_codes, _ = pd.factorize(work["firm_id"], sort=False)
    year_codes, _ = pd.factorize(work["year"], sort=False)

    def subtract_group_means(matrix: np.ndarray, codes: np.ndarray) -> np.ndarray:
        groups = int(codes.max()) + 1
        counts = np.bincount(codes, minlength=groups).astype(float)
        totals = np.vstack(
            [np.bincount(codes, weights=matrix[:, index], minlength=groups) for index in range(matrix.shape[1])]
        ).T
        return matrix - (totals / counts[:, None])[codes]

    for _ in range(10000):
        previous = values.copy()
        values = subtract_group_means(values, firm_codes)
        values = subtract_group_means(values, year_codes)
        if np.max(np.abs(values - previous)) < tolerance:
            break
    else:
        raise RuntimeError("two-way fixed-effect residualization did not converge")
    if np.max(np.abs(np.vstack([
        np.bincount(firm_codes, weights=values[:, i]) / np.bincount(firm_codes)
        for i in range(values.shape[1])
    ]))) > 1e-9:
        raise ValueError("firm means remain after residualization")
    return values


def independent_fit(
    sample: pd.DataFrame, outcome: str, regressors: list[str]
) -> dict[str, Any]:
    estimation = sample.dropna(subset=[outcome, "firm_id", "year", *regressors]).copy()
    residualized = residualize_two_way(estimation, [outcome, *regressors])
    y = residualized[:, 0]
    x = residualized[:, 1:]
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    errors = y - x @ beta
    clusters = estimation["firm_id"].to_numpy()
    unique_clusters = np.unique(clusters)
    scores = np.vstack(
        [(x[clusters == cluster] * errors[clusters == cluster, None]).sum(axis=0) for cluster in unique_clusters]
    )
    bread = np.linalg.pinv(x.T @ x)
    covariance = bread @ (scores.T @ scores) @ bread
    nobs, parameters, cluster_count = len(estimation), x.shape[1], len(unique_clusters)
    covariance *= (cluster_count / (cluster_count - 1)) * ((nobs - 1) / (nobs - parameters))
    standard_errors = np.sqrt(np.diag(covariance))
    t_values = beta / standard_errors
    year_count = estimation["year"].nunique()
    absorbed_rank = cluster_count + year_count - 1
    residual_degrees_of_freedom = nobs - absorbed_rank - parameters
    p_values = 2 * t.sf(np.abs(t_values), residual_degrees_of_freedom)
    critical_value = t.ppf(0.975, residual_degrees_of_freedom)
    return {
        "terms": {
            term: {
                "coefficient": float(beta[index]),
                "clustered_standard_error": float(standard_errors[index]),
                "p_value_two_sided": float(p_values[index]),
                "confidence_interval_95": [
                    float(beta[index] - critical_value * standard_errors[index]),
                    float(beta[index] + critical_value * standard_errors[index]),
                ],
            }
            for index, term in enumerate(regressors)
        },
        "covariance": covariance,
        "term_order": regressors,
        "nobs": nobs,
        "firm_clusters": cluster_count,
        "residual_degrees_of_freedom": residual_degrees_of_freedom,
    }


def compare_term(
    observed: dict[str, Any], recomputed: dict[str, Any]
) -> dict[str, float | bool]:
    coefficient_difference = abs(
        float(observed["coefficient"]) - float(recomputed["coefficient"])
    )
    standard_error_difference = abs(
        float(observed["clustered_standard_error"])
        - float(recomputed["clustered_standard_error"])
    )
    p_value_difference = abs(
        float(observed["p_value_two_sided"]) - float(recomputed["p_value_two_sided"])
    )
    return {
        "coefficient_abs_difference": coefficient_difference,
        "standard_error_abs_difference": standard_error_difference,
        "p_value_abs_difference": p_value_difference,
        "passed": coefficient_difference < 5e-9
        and standard_error_difference < 5e-9
        and p_value_difference < 5e-9,
    }


def event_design(primary: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    event = primary.loc[primary["monotone_policy_path"]].copy()
    first = event.loc[event["source_policy_post"].eq(1)].groupby("firm_id")["year"].min()
    event["first_exposed_year"] = event["firm_id"].map(first)
    event["event_time"] = event["year"] - event["first_exposed_year"]
    treated = event["first_exposed_year"].notna()
    conditions = {
        "event_le_m4": treated & event["event_time"].le(-4),
        "event_m3": treated & event["event_time"].eq(-3),
        "event_m2": treated & event["event_time"].eq(-2),
        "event_p0": treated & event["event_time"].eq(0),
        "event_p1": treated & event["event_time"].eq(1),
        "event_p2": treated & event["event_time"].eq(2),
        "event_p3": treated & event["event_time"].eq(3),
        "event_ge_p4": treated & event["event_time"].ge(4),
    }
    for name, condition in conditions.items():
        event[name] = condition.astype(float)
    return event, list(conditions)


def recompute_placebo(
    primary: pd.DataFrame, repetitions: int, seed: int
) -> np.ndarray:
    ordered = primary.sort_values(["firm_id", "year"])
    n_firms = ordered["firm_id"].nunique()
    n_years = ordered["year"].nunique()
    y = ordered["ln_high_quality_green_invention"].to_numpy().reshape(n_firms, n_years)
    exposure = ordered["source_policy_post"].to_numpy().reshape(n_firms, n_years)

    def demean(matrix: np.ndarray) -> np.ndarray:
        return matrix - matrix.mean(1, keepdims=True) - matrix.mean(0, keepdims=True) + matrix.mean()

    y = demean(y)
    rng = np.random.default_rng(seed)
    values = np.empty(repetitions)
    for index in range(repetitions):
        x = demean(exposure[rng.permutation(n_firms), :])
        values[index] = np.sum(x * y) / np.sum(x * x)
    return values


def verify_output_hashes(result: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    for item in result["outputs"].values():
        path = resolve_root(item["path"])
        observed = file_hash(path)
        records.append(
            {
                "path": str(path.relative_to(ROOT)),
                "expected_sha256": item["sha256"],
                "observed_sha256": observed,
                "passed": observed == item["sha256"],
            }
        )
    figure_manifest = load_json(resolve_root(result["outputs"]["figure_manifest"]["path"]))
    for figure in figure_manifest["figures"]:
        for file_info in figure["files"].values():
            path = resolve_root(file_info["path"])
            observed = file_hash(path)
            records.append(
                {
                    "path": str(path.relative_to(ROOT)),
                    "expected_sha256": file_info["sha256"],
                    "observed_sha256": observed,
                    "passed": observed == file_info["sha256"],
                }
            )
    return all(record["passed"] for record in records), records


def main() -> int:
    round1_protocol = load_json(ROUND1_PROTOCOL)
    round2_protocol = load_json(ROUND2_PROTOCOL)
    round1 = load_json(ROUND1_RESULT)
    result = load_json(ROUND2_RESULT)
    binding = round2_protocol["round1_binding"]
    _, primary = transform_data(round2_protocol)

    records = {record["model_id"]: record for record in result["models"]["primary_and_robustness"]}
    specifications = {
        "M1_PRIMARY_ASSOCIATION": (
            primary,
            "ln_high_quality_green_invention",
            ["source_policy_post", *PRIMARY_CONTROLS],
        ),
        "R_NO_CONTROLS": (primary, "ln_high_quality_green_invention", ["source_policy_post"]),
        "R_EXCLUDE_2021": (
            primary.loc[primary["year"].lt(2021)],
            "ln_high_quality_green_invention",
            ["source_policy_post", *PRIMARY_CONTROLS],
        ),
        "R_MONOTONE_PATHS": (
            primary.loc[primary["monotone_policy_path"]],
            "ln_high_quality_green_invention",
            ["source_policy_post", *PRIMARY_CONTROLS],
        ),
        "R_INDEPENDENT_INVENTIONS": (
            primary,
            "ln_independent_green_invention",
            ["source_policy_post", *PRIMARY_CONTROLS],
        ),
        "R_TOTAL_GREEN_PATENTS": (
            primary,
            "ln_total_green_patents",
            ["source_policy_post", *PRIMARY_CONTROLS],
        ),
        "R_UTILITY_MODEL_CONTRAST": (
            primary,
            "ln_green_utility_models",
            ["source_policy_post", *PRIMARY_CONTROLS],
        ),
        "R_ADD_INDUSTRY_HHI": (
            primary.dropna(subset=["industry_hhi_a"]),
            "ln_high_quality_green_invention",
            ["source_policy_post", *PRIMARY_CONTROLS, "industry_hhi_a"],
        ),
    }
    comparisons: dict[str, Any] = {}
    for model_id, (sample, outcome, regressors) in specifications.items():
        recomputed = independent_fit(sample, outcome, regressors)
        comparisons[model_id] = compare_term(
            records[model_id]["estimate"], recomputed["terms"]["source_policy_post"]
        )

    event, event_terms = event_design(primary)
    event_fit = independent_fit(
        event,
        "ln_high_quality_green_invention",
        [*event_terms, *PRIMARY_CONTROLS],
    )
    observed_event = {point["term"]: point for point in result["models"]["event_study"]["points"]}
    event_comparisons = {
        term: compare_term(observed_event[term], event_fit["terms"][term])
        for term in event_terms
    }
    pre_terms = ["event_le_m4", "event_m3", "event_m2"]
    indices = [event_fit["term_order"].index(term) for term in pre_terms]
    beta = np.array([event_fit["terms"][term]["coefficient"] for term in pre_terms])
    covariance = event_fit["covariance"][np.ix_(indices, indices)]
    pretrend_statistic = float(beta.T @ np.linalg.pinv(covariance) @ beta)
    pretrend_p_value = float(chi2.sf(pretrend_statistic, len(pre_terms)))
    observed_pretrend = result["models"]["event_study"]["diagnostic"]

    mechanism_observed = result["models"]["mechanism"]
    mechanism_fit = independent_fit(
        primary,
        "abs_sa_financing_constraint",
        ["source_policy_post", "leverage", "return_on_assets"],
    )
    mechanism_comparison = compare_term(
        mechanism_observed["estimate"], mechanism_fit["terms"]["source_policy_post"]
    )
    heterogeneity_observed = result["models"]["competition_heterogeneity"]
    heterogeneity_sample = primary.dropna(subset=["industry_hhi_a", "high_competition"])
    heterogeneity_fit = independent_fit(
        heterogeneity_sample,
        "ln_high_quality_green_invention",
        [
            "source_policy_post",
            "high_competition",
            "source_policy_post_x_high_competition",
            *PRIMARY_CONTROLS,
        ],
    )
    heterogeneity_comparison = compare_term(
        heterogeneity_observed["estimate"],
        heterogeneity_fit["terms"]["source_policy_post_x_high_competition"],
    )

    placebo_contract = round2_protocol["placebo_contract"]
    placebo_values = recompute_placebo(
        primary,
        int(placebo_contract["repetitions"]),
        int(placebo_contract["seed"]),
    )
    saved_placebo = pd.read_csv(OUTPUT_DIR / "placebo_distribution.csv")["coefficient"].to_numpy()
    placebo_max_difference = float(np.max(np.abs(placebo_values - saved_placebo)))
    no_controls = independent_fit(
        primary, "ln_high_quality_green_invention", ["source_policy_post"]
    )["terms"]["source_policy_post"]["coefficient"]
    exceedances = int(np.sum(np.abs(placebo_values) >= abs(no_controls)))
    placebo_p_value = (1 + exceedances) / (1 + len(placebo_values))
    observed_placebo = result["models"]["trajectory_placebo"]

    output_hashes_passed, output_hash_records = verify_output_hashes(result)
    text_paths = [
        ROUND1_RESULT,
        ROUND2_RESULT,
        OUTPUT_DIR / "model_comparison.csv",
        OUTPUT_DIR / "event_study.csv",
        OUTPUT_DIR / "mechanism_and_heterogeneity.csv",
        OUTPUT_DIR / "figure_manifest.json",
    ]
    secret_markers = [b"DASHSCOPE_API_KEY", b'"api_key"', b"Bearer sk-", b"sk-"]
    secret_findings = []
    for path in text_paths:
        raw = path.read_bytes().lower()
        for marker in secret_markers:
            if marker.lower() in raw:
                secret_findings.append({"path": str(path.relative_to(ROOT)), "marker": marker.decode("ascii")})

    checks = {
        "round1_protocol_hash_matches_record": file_hash(ROUND1_PROTOCOL)
        == round1["protocol"]["sha256"],
        "round1_binding_matches": file_hash(ROUND1_RESULT) == binding["sha256"],
        "round2_protocol_hash_matches_result": file_hash(ROUND2_PROTOCOL)
        == result["protocol"]["sha256"],
        "round2_binding_verified_in_result": result["protocol"]["round1_binding_verified"] is True,
        "all_primary_and_robustness_models_match": all(
            item["passed"] for item in comparisons.values()
        ),
        "all_event_coefficients_match": all(
            item["passed"] for item in event_comparisons.values()
        ),
        "event_pretrend_statistic_matches": abs(
            pretrend_statistic - float(observed_pretrend["joint_pretrend_chi2"])
        )
        < 5e-8,
        "event_pretrend_p_value_matches": abs(
            pretrend_p_value - float(observed_pretrend["joint_pretrend_p_value"])
        )
        < 5e-8,
        "mechanism_model_matches": mechanism_comparison["passed"],
        "heterogeneity_model_matches": heterogeneity_comparison["passed"],
        "placebo_distribution_matches": placebo_max_difference < 5e-12,
        "placebo_p_value_matches": abs(
            placebo_p_value - float(observed_placebo["randomization_p_value_two_sided"])
        )
        < 5e-12,
        "output_hashes_match": output_hashes_passed,
        "claim_gate_remains_closed": result["claim_gate"]["causal_claim_authorized"] is False,
        "no_secret_markers_in_text_outputs": not secret_findings,
        "raw_source_hash_unchanged": file_hash(
            resolve_root(round2_protocol["data_contract"]["source_path"])
        )
        == round2_protocol["data_contract"]["source_sha256"],
    }
    verification_passed = all(checks.values())
    verification = {
        "schema_version": "case010-independent-recompute/1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verification_passed": verification_passed,
        "method": (
            "Independent NumPy OLS after two-way alternating-projection residualization, "
            "with a separately reconstructed firm-clustered sandwich covariance."
        ),
        "checks": checks,
        "model_comparisons": comparisons,
        "event_comparisons": event_comparisons,
        "event_pretrend_recompute": {
            "chi2": pretrend_statistic,
            "p_value": pretrend_p_value,
        },
        "mechanism_comparison": mechanism_comparison,
        "heterogeneity_comparison": heterogeneity_comparison,
        "placebo_recompute": {
            "maximum_coefficient_difference": placebo_max_difference,
            "exceedances": exceedances,
            "p_value": placebo_p_value,
        },
        "output_hash_records": output_hash_records,
        "secret_findings": secret_findings,
        "environment": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "scipy": __import__("scipy").__version__,
            "verifier_sha256": file_hash(Path(__file__)),
        },
    }
    output_path = OUTPUT_DIR / "independent_recompute.json"
    write_json(output_path, verification)
    digest = file_hash(output_path)
    output_path.with_suffix(".sha256").write_text(
        f"{digest}  {output_path.name}\n", encoding="ascii"
    )
    print(
        json.dumps(
            {
                "output": str(output_path.resolve()),
                "sha256": digest,
                "verification_passed": verification_passed,
                "checks_passed": sum(checks.values()),
                "checks_total": len(checks),
                "maximum_model_coefficient_difference": max(
                    item["coefficient_abs_difference"] for item in comparisons.values()
                ),
            },
            ensure_ascii=False,
        )
    )
    if not verification_passed:
        failed = [name for name, passed in checks.items() if not passed]
        raise SystemExit(f"verification failed: {failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
