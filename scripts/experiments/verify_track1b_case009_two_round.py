#!/usr/bin/env python3
"""Independent explicit-dummy recomputation for the Track 1B experiment."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import chi2, t


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA = ROOT / "experiments/fixtures/case009_harvard_dataverse_data_v1.xlsx"
DEFAULT_OUTPUT_DIR = ROOT / "output/experiments/track1b_case009_two_round_v1"
CONTROLS = ["Temp", "lnGDP", "lngdp2", "greenration_pct", "fdi", "pop"]


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


def load_data(path: Path) -> pd.DataFrame:
    frame = pd.read_excel(path, sheet_name="Sheet1")
    green = [name for name in frame.columns if str(name).startswith("greenration")]
    if len(green) != 1:
        raise ValueError(f"unexpected greenration columns: {green}")
    frame = frame.rename(columns={green[0]: "greenration_pct"}).copy()
    for name in ["id", "month", "treat", "time", "dudt", "PM2.5", *CONTROLS]:
        frame[name] = pd.to_numeric(frame[name], errors="coerce")
    return frame


def explicit_design(sample: pd.DataFrame, regressors: list[str]) -> tuple[np.ndarray, list[str]]:
    regressor_block = sample[regressors].to_numpy(dtype=float)
    city = pd.get_dummies(sample["id"].astype(int), prefix="city", drop_first=True, dtype=float)
    month = pd.get_dummies(
        sample["month"].astype(int), prefix="month", drop_first=True, dtype=float
    )
    matrix = np.column_stack(
        [np.ones(len(sample), dtype=float), regressor_block, city.to_numpy(), month.to_numpy()]
    )
    names = ["const", *regressors, *city.columns.astype(str), *month.columns.astype(str)]
    return matrix, names


def fit_explicit(sample: pd.DataFrame, regressors: list[str], term: str) -> dict[str, Any]:
    matrix, names = explicit_design(sample, regressors)
    outcome = sample["PM2.5"].to_numpy(dtype=float)
    coefficients, _, rank, _ = np.linalg.lstsq(matrix, outcome, rcond=None)
    residuals = outcome - matrix @ coefficients
    bread = np.linalg.pinv(matrix.T @ matrix)
    clusters = sample["id"].astype(int).to_numpy()
    unique_clusters = np.unique(clusters)
    meat = np.zeros((matrix.shape[1], matrix.shape[1]), dtype=float)
    for cluster in unique_clusters:
        mask = clusters == cluster
        score = matrix[mask].T @ residuals[mask]
        meat += np.outer(score, score)
    correction = (len(unique_clusters) / (len(unique_clusters) - 1)) * (
        (len(sample) - 1) / (len(sample) - rank)
    )
    covariance = correction * bread @ meat @ bread
    index = names.index(term)
    standard_error = float(np.sqrt(max(covariance[index, index], 0.0)))
    coefficient = float(coefficients[index])
    p_value = float(2 * t.sf(abs(coefficient / standard_error), df=len(unique_clusters) - 1))
    return {
        "coefficient": coefficient,
        "clustered_standard_error_cr1": standard_error,
        "p_value_t_cluster_df": p_value,
        "nobs": int(len(sample)),
        "rank": int(rank),
        "columns": int(matrix.shape[1]),
        "clusters": int(len(unique_clusters)),
    }


def event_terms(sample: pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[str]]:
    frame = sample.copy()
    relative = frame["month"] - 31
    frame["event_remote_pre"] = (frame["treat"].eq(1) & relative.le(-12)).astype(float)
    pre = ["event_remote_pre"]
    for k in range(-11, -1):
        name = f"event_m{abs(k)}"
        frame[name] = (frame["treat"].eq(1) & relative.eq(k)).astype(float)
        pre.append(name)
    post: list[str] = []
    for k in range(0, 12):
        name = f"event_p{k}"
        frame[name] = (frame["treat"].eq(1) & relative.eq(k)).astype(float)
        post.append(name)
    frame["event_remote_post"] = (frame["treat"].eq(1) & relative.ge(12)).astype(float)
    post.append("event_remote_post")
    return frame, pre, post


def event_wald(sample: pd.DataFrame) -> dict[str, Any]:
    frame, pre, post = event_terms(sample)
    regressors = [*pre, *post, *CONTROLS]
    matrix, names = explicit_design(frame, regressors)
    outcome = frame["PM2.5"].to_numpy(dtype=float)
    coefficients, _, rank, _ = np.linalg.lstsq(matrix, outcome, rcond=None)
    residuals = outcome - matrix @ coefficients
    bread = np.linalg.pinv(matrix.T @ matrix)
    clusters = frame["id"].astype(int).to_numpy()
    unique_clusters = np.unique(clusters)
    meat = np.zeros((matrix.shape[1], matrix.shape[1]), dtype=float)
    for cluster in unique_clusters:
        mask = clusters == cluster
        score = matrix[mask].T @ residuals[mask]
        meat += np.outer(score, score)
    correction = (len(unique_clusters) / (len(unique_clusters) - 1)) * (
        (len(frame) - 1) / (len(frame) - rank)
    )
    covariance = correction * bread @ meat @ bread
    indices = [names.index(term) for term in pre]
    values = coefficients[indices]
    block = covariance[np.ix_(indices, indices)]
    statistic = float(values @ np.linalg.pinv(block) @ values)
    return {
        "statistic": statistic,
        "df": len(pre),
        "p_value_chi_square": float(chi2.sf(statistic, df=len(pre))),
        "pretrend_terms": pre,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    round1_path = args.output_dir / "round1_result.json"
    round2_path = args.output_dir / "round2_result.json"
    round1 = load_json(round1_path)
    round2 = load_json(round2_path)
    data = load_data(args.data)
    complete = data.dropna(subset=["PM2.5", "dudt", "id", "month", *CONTROLS]).copy()
    full = data.dropna(subset=["PM2.5", "dudt", "id", "month"]).copy()
    trend = complete.copy()
    trend["treated_linear_trend"] = trend["treat"] * (trend["month"] - 30)
    short = complete.loc[complete["month"].between(19, 42)].copy()

    recomputed = {
        "round1_controlled_complete_case": fit_explicit(
            complete, ["dudt", *CONTROLS], "dudt"
        ),
        "round2_no_controls_full_sample": fit_explicit(full, ["dudt"], "dudt"),
        "round2_controlled_with_treated_linear_trend": fit_explicit(
            trend, ["dudt", "treated_linear_trend", *CONTROLS], "dudt"
        ),
        "round2_controlled_short_window_month19_42": fit_explicit(
            short, ["dudt", *CONTROLS], "dudt"
        ),
    }
    expected = round2["models"]
    differences = {
        name: abs(recomputed[name]["coefficient"] - expected[name]["coefficient"])
        for name in recomputed
    }
    max_difference = max(differences.values())
    event = event_wald(complete)
    event_p_difference = abs(
        event["p_value_chi_square"] - round1["event_study"]["joint_pretrend_p_value"]
    )

    result = {
        "schema_version": "track1b-independent-recompute/1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "implementation": (
            "NumPy explicit city/month dummy OLS with independently implemented CR1 city-cluster sandwich covariance"
        ),
        "independence_scope": (
            "Does not import the primary AbsorbingLS executor; shares only the frozen data and model specification."
        ),
        "source_hashes": {
            "data_sha256": file_hash(args.data),
            "round1_result_sha256": file_hash(round1_path),
            "round2_result_sha256": file_hash(round2_path),
        },
        "models": recomputed,
        "coefficient_absolute_differences": differences,
        "event_pretrend": event,
        "event_pretrend_p_absolute_difference": event_p_difference,
        "assertions": {
            "all_four_coefficients_match_within_1e_8": max_difference <= 1e-8,
            "event_pretrend_decision_matches": (
                event["p_value_chi_square"] < 0.05
            )
            == bool(round1["event_study"]["joint_pretrend_rejected_at_alpha_0_05"]),
            "round2_binds_round1_hash": (
                round2["feedback_binding"]["round1_result_sha256"] == file_hash(round1_path)
            ),
            "source_md5_matches_official": file_hash(args.data, "md5")
            == "51a94dfef15bc522a950908a510cc025",
        },
        "maximum_coefficient_absolute_difference": max_difference,
        "note": (
            "CR1 standard errors are reported for audit but need not exactly equal AbsorbingLS because absorbed-degree corrections differ; coefficient equality and the pretrend decision are the hard checks."
        ),
    }
    if not all(result["assertions"].values()):
        raise AssertionError(json.dumps(result["assertions"], ensure_ascii=False))
    output = args.output_dir / "independent_recompute.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "independent_recompute.sha256").write_text(
        f"{file_hash(output)}  independent_recompute.json\n", encoding="ascii"
    )
    print(
        json.dumps(
            {
                "output": str(output.resolve()),
                "maximum_coefficient_absolute_difference": max_difference,
                "event_pretrend_p_value": event["p_value_chi_square"],
                "assertions": result["assertions"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
