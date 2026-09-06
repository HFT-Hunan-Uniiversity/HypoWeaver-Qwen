#!/usr/bin/env python3
"""Execute the Track 1B two-round social-science experiment.

Round 1 must be run from its frozen protocol. Round 2 refuses to run unless
its protocol cryptographically binds the completed Round-1 result. The script
never edits the source workbook.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
from typing import Any, Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from linearmodels.iv import AbsorbingLS
import linearmodels
import scipy
from scipy.stats import chi2


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA = ROOT / "experiments/fixtures/case009_harvard_dataverse_data_v1.xlsx"
DEFAULT_ROUND1_PROTOCOL = ROOT / "experiments/track1b_case009_pm25_round1_protocol.json"
DEFAULT_ROUND2_PROTOCOL = ROOT / "experiments/track1b_case009_pm25_round2_protocol.json"
DEFAULT_OUTPUT = ROOT / "output/experiments/track1b_case009_two_round_v1"
CONTROL_COLUMNS = ["Temp", "lnGDP", "lngdp2", "greenration_pct", "fdi", "pop"]


def file_hash(path: Path, algorithm: str = "sha256") -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json_hash(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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


def round_float(value: Any, digits: int = 10) -> float | None:
    if value is None:
        return None
    number = float(np.asarray(value).squeeze())
    if not np.isfinite(number):
        return None
    return round(number, digits)


def load_data(path: Path, protocol: dict[str, Any]) -> tuple[pd.DataFrame, str]:
    contract = protocol["data_contract"]
    md5 = file_hash(path, "md5")
    sha256 = file_hash(path, "sha256")
    if md5.lower() != str(contract["official_md5"]).lower():
        raise ValueError(f"official MD5 mismatch: {md5}")
    if sha256.lower() != str(contract["local_sha256"]).lower():
        raise ValueError(f"local SHA-256 mismatch: {sha256}")

    data = pd.read_excel(path, sheet_name=contract["sheet"])
    green_columns = [name for name in data.columns if str(name).startswith("greenration")]
    if len(green_columns) != 1:
        raise ValueError(f"expected one greenration column, found {green_columns}")
    green_source = str(green_columns[0])
    data = data.rename(columns={green_source: "greenration_pct"}).copy()
    data["id"] = pd.to_numeric(data["id"], errors="raise").astype(int)
    data["month"] = pd.to_numeric(data["month"], errors="raise").astype(int)
    data["treat"] = pd.to_numeric(data["treat"], errors="raise").astype(int)
    data["time"] = pd.to_numeric(data["time"], errors="raise").astype(int)
    data["dudt"] = pd.to_numeric(data["dudt"], errors="raise").astype(int)
    for column in ["PM2.5", *CONTROL_COLUMNS]:
        data[column] = pd.to_numeric(data[column], errors="coerce")

    if not data["time"].eq(data["month"].ge(31).astype(int)).all():
        raise ValueError("time is not identical to month>=31")
    if not data["dudt"].eq(data["treat"] * data["time"]).all():
        raise ValueError("dudt is not identical to treat*time")
    if data.duplicated(["id", "month"]).any():
        raise ValueError("duplicate id-month rows detected")
    if set(data["month"].unique()) != set(range(1, 61)):
        raise ValueError("expected month index 1..60")
    return data, green_source


def prepare_sample(
    data: pd.DataFrame,
    outcome: str,
    controls: Iterable[str],
    *,
    lower_month: int | None = None,
    upper_month: int | None = None,
) -> pd.DataFrame:
    sample = data
    if lower_month is not None:
        sample = sample.loc[sample["month"] >= lower_month]
    if upper_month is not None:
        sample = sample.loc[sample["month"] <= upper_month]
    required = [outcome, "dudt", "id", "month", *controls]
    return sample.dropna(subset=required).copy()


def fit_clustered(
    sample: pd.DataFrame,
    outcome: str,
    regressors: list[str],
) -> Any:
    absorb = pd.DataFrame(
        {
            "city": pd.Categorical(sample["id"]),
            "month": pd.Categorical(sample["month"]),
        },
        index=sample.index,
    )
    model = AbsorbingLS(
        sample[outcome].astype(float),
        sample[regressors].astype(float),
        absorb=absorb,
        drop_absorbed=True,
    )
    return model.fit(
        cov_type="clustered",
        clusters=pd.Series(sample["id"].to_numpy(), index=sample.index),
        debiased=True,
        method="hdfe",
        absorb_options={"compute_degrees": False},
        use_cache=True,
    )


def term_result(model: Any, term: str) -> dict[str, Any]:
    interval = model.conf_int(level=0.95).loc[term]
    return {
        "term": term,
        "coefficient": round_float(model.params[term]),
        "clustered_standard_error": round_float(model.std_errors[term]),
        "p_value_two_sided": round_float(model.pvalues[term]),
        "confidence_interval_95": [round_float(interval.iloc[0]), round_float(interval.iloc[1])],
        "nobs": int(model.nobs),
        "entity_clusters": None,
        "r_squared": round_float(model.rsquared),
    }


def model_summary(model: Any, sample: pd.DataFrame, term: str) -> dict[str, Any]:
    result = term_result(model, term)
    result["entity_clusters"] = int(sample["id"].nunique())
    result["treated_entities"] = int(sample.loc[sample["treat"].eq(1), "id"].nunique())
    result["control_entities"] = int(sample.loc[sample["treat"].eq(0), "id"].nunique())
    return result


def fit_event_study(sample: pd.DataFrame) -> tuple[Any, list[str], list[dict[str, Any]], float]:
    event = sample.copy()
    relative = event["month"] - 31
    event["event_remote_pre"] = (
        event["treat"].eq(1) & relative.le(-12)
    ).astype(float)
    pre_terms = ["event_remote_pre"]
    for k in range(-11, -1):
        name = f"event_m{abs(k)}"
        event[name] = (event["treat"].eq(1) & relative.eq(k)).astype(float)
        pre_terms.append(name)
    post_terms: list[str] = []
    for k in range(0, 12):
        name = f"event_p{k}"
        event[name] = (event["treat"].eq(1) & relative.eq(k)).astype(float)
        post_terms.append(name)
    event["event_remote_post"] = (
        event["treat"].eq(1) & relative.ge(12)
    ).astype(float)
    post_terms.append("event_remote_post")

    regressors = [*pre_terms, *post_terms, *CONTROL_COLUMNS]
    model = fit_clustered(event, "PM2.5", regressors)
    pre_coefficients = model.params.loc[pre_terms].to_numpy(dtype=float)
    pre_covariance = model.cov.loc[pre_terms, pre_terms].to_numpy(dtype=float)
    wald_statistic = float(
        pre_coefficients @ np.linalg.pinv(pre_covariance) @ pre_coefficients
    )
    joint_p = float(chi2.sf(wald_statistic, df=len(pre_terms)))

    ordering = [
        ("event_remote_pre", -12, "<=-12"),
        *[(f"event_m{abs(k)}", k, str(k)) for k in range(-11, -1)],
        *[(f"event_p{k}", k, str(k)) for k in range(0, 12)],
        ("event_remote_post", 12, ">=12"),
    ]
    rows: list[dict[str, Any]] = []
    confidence = model.conf_int(level=0.95)
    for name, relative_month, label in ordering:
        rows.append(
            {
                "term": name,
                "relative_month_plot": relative_month,
                "relative_month_label": label,
                "coefficient": round_float(model.params[name]),
                "standard_error": round_float(model.std_errors[name]),
                "p_value": round_float(model.pvalues[name]),
                "ci_lower": round_float(confidence.loc[name].iloc[0]),
                "ci_upper": round_float(confidence.loc[name].iloc[1]),
                "period_role": "pre" if name in pre_terms else "post",
            }
        )
    return model, pre_terms, rows, joint_p


def data_profile(data: pd.DataFrame, complete: pd.DataFrame, green_source: str) -> dict[str, Any]:
    raw_treated = int(data.loc[data["treat"].eq(1), "id"].nunique())
    complete_treated = int(complete.loc[complete["treat"].eq(1), "id"].nunique())
    complete_loss = 1.0 - len(complete) / len(data)
    return {
        "rows": int(len(data)),
        "columns": int(data.shape[1]),
        "cities": int(data["id"].nunique()),
        "months": int(data["month"].nunique()),
        "duplicate_id_month_rows": int(data.duplicated(["id", "month"]).sum()),
        "raw_treated_cities": raw_treated,
        "raw_control_cities": int(data.loc[data["treat"].eq(0), "id"].nunique()),
        "complete_case_rows": int(len(complete)),
        "complete_case_loss_rate": round(complete_loss, 6),
        "complete_case_treated_cities": complete_treated,
        "complete_case_control_cities": int(
            complete.loc[complete["treat"].eq(0), "id"].nunique()
        ),
        "source_greenration_column": green_source,
        "encoding_checks": {
            "time_equals_month_ge_31": True,
            "dudt_equals_treat_times_time": True,
        },
        "missing_by_analysis_field": {
            column: int(data[column].isna().sum())
            for column in ["PM2.5", "dudt", *CONTROL_COLUMNS]
        },
    }


def plot_event_study(rows: list[dict[str, Any]], output: Path) -> None:
    frame = pd.DataFrame(rows)
    figure, axis = plt.subplots(figsize=(10, 5.5), constrained_layout=True)
    axis.errorbar(
        frame["relative_month_plot"],
        frame["coefficient"],
        yerr=[
            frame["coefficient"] - frame["ci_lower"],
            frame["ci_upper"] - frame["coefficient"],
        ],
        fmt="o",
        color="#16697A",
        ecolor="#82C0CC",
        capsize=2.5,
        markersize=4,
    )
    axis.axhline(0, color="#333333", linewidth=1)
    axis.axvline(-0.5, color="#D1495B", linestyle="--", linewidth=1)
    axis.set_xlabel("Months relative to policy start (binned at tails)")
    axis.set_ylabel("PM2.5 coefficient in source-data units")
    axis.set_title("Round 1 event-study diagnostic")
    axis.grid(axis="y", alpha=0.2)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=220)
    plt.close(figure)


def execute_round1(protocol_path: Path, data_path: Path, output_dir: Path) -> dict[str, Any]:
    protocol = load_json(protocol_path)
    if protocol.get("phase") != "round1":
        raise ValueError("round1 command requires a round1 protocol")
    data, green_source = load_data(data_path, protocol)
    complete = prepare_sample(data, "PM2.5", CONTROL_COLUMNS)
    baseline = fit_clustered(complete, "PM2.5", ["dudt", *CONTROL_COLUMNS])
    _, pre_terms, event_rows, joint_pretrend_p = fit_event_study(complete)

    profile = data_profile(data, complete, green_source)
    primary = model_summary(baseline, complete, "dudt")
    alpha = float(protocol["hypothesis"]["alpha"])
    triggers = {
        "R1_PRETREND": joint_pretrend_p < alpha,
        "R1_MISSINGNESS": (
            profile["complete_case_loss_rate"] > 0.10
            or profile["complete_case_treated_cities"] < profile["raw_treated_cities"]
        ),
        "R1_SMALL_TREATED_CLUSTER": profile["complete_case_treated_cities"] < 10,
        "R1_SUPPORTIVE": (
            primary["coefficient"] < 0
            and primary["p_value_two_sided"] < alpha
            and joint_pretrend_p >= alpha
            and profile["complete_case_loss_rate"] <= 0.10
            and profile["complete_case_treated_cities"] >= 10
        ),
    }
    feedback = {
        "triggered_rules": [name for name, triggered in triggers.items() if triggered],
        "required_round2_tasks": [
            rule["round2_requirement"]
            for rule in protocol["adaptive_decision_rules"]
            if triggers.get(rule["rule_id"], False)
        ],
        "causal_claim_authorized_after_round1": bool(triggers["R1_SUPPORTIVE"]),
        "reason": (
            "第一轮识别或数据完整性门未全部通过；第二轮必须执行冻结规则指定的诊断任务。"
            if not triggers["R1_SUPPORTIVE"]
            else "第一轮通过支持性分支，可进入预先限定的稳健性任务。"
        ),
    }
    result = {
        "schema_version": "track1b-adaptive-social-science-result/1.0.0",
        "experiment_id": protocol["experiment_id"],
        "phase": "round1",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "path": protocol_path.resolve().relative_to(ROOT.resolve()).as_posix(),
            "raw_sha256": file_hash(protocol_path),
            "canonical_sha256": canonical_json_hash(protocol),
            "frozen_at": protocol["frozen_at"],
        },
        "data": {
            "path": data_path.resolve().relative_to(ROOT.resolve()).as_posix(),
            "md5": file_hash(data_path, "md5"),
            "sha256": file_hash(data_path, "sha256"),
            "license": protocol["data_contract"]["license"],
            "persistent_id": protocol["data_contract"]["persistent_id"],
        },
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "linearmodels": linearmodels.__version__,
            "scipy": scipy.__version__,
        },
        "protocol_deviations": [
            {
                "field": "reproducibility.software",
                "planned": "statsmodels",
                "executed": "linearmodels.iv.AbsorbingLS",
                "reason": (
                    "冻结后首次启动在导入 statsmodels 时因其与本机 SciPy 版本不兼容而停止，"
                    "尚未读取或产生任何 PM2.5 模型结果；随后改用项目既有的 AbsorbingLS 实现。"
                ),
                "estimand_change": False,
                "covariance_change": False,
            }
        ],
        "data_profile": profile,
        "primary_model": {
            "specification": protocol["estimator"]["formula"],
            "covariance": protocol["estimator"]["covariance"],
            "result": primary,
        },
        "event_study": {
            "reference_month": 30,
            "reference_relative_month": -1,
            "pretrend_terms": pre_terms,
            "joint_pretrend_p_value": round(joint_pretrend_p, 10),
            "joint_pretrend_rejected_at_alpha_0_05": joint_pretrend_p < alpha,
            "rows": event_rows,
        },
        "decision_triggers": triggers,
        "feedback": feedback,
        "claim_boundary": (
            "这是关联性与识别诊断。只有冻结门全部通过才可进入支持性表述；当前结果不得自动写成因果效应。"
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    event_path = output_dir / "round1_event_study.csv"
    pd.DataFrame(event_rows).to_csv(event_path, index=False, encoding="utf-8-sig")
    plot_event_study(event_rows, output_dir / "round1_event_study.png")
    result_path = output_dir / "round1_result.json"
    write_json(result_path, result)
    (output_dir / "round1_result.sha256").write_text(
        f"{file_hash(result_path)}  round1_result.json\n", encoding="ascii"
    )
    return result


def double_demean(values: np.ndarray, entity: np.ndarray, period: np.ndarray) -> np.ndarray:
    frame = pd.DataFrame({"value": values, "entity": entity, "period": period})
    entity_mean = frame.groupby("entity")["value"].transform("mean").to_numpy()
    period_mean = frame.groupby("period")["value"].transform("mean").to_numpy()
    return values - entity_mean - period_mean + float(np.mean(values))


def permutation_diagnostic(
    sample: pd.DataFrame, *, treated_count: int, repetitions: int, seed: int
) -> dict[str, Any]:
    entity_ids = np.array(sorted(sample["id"].unique()))
    if len(sample) != len(entity_ids) * sample["month"].nunique():
        raise ValueError("permutation diagnostic requires a balanced panel")
    y = sample["PM2.5"].to_numpy(dtype=float)
    y_residual = double_demean(y, sample["id"].to_numpy(), sample["month"].to_numpy())
    observed_d = sample["dudt"].to_numpy(dtype=float)
    observed_residual = double_demean(
        observed_d, sample["id"].to_numpy(), sample["month"].to_numpy()
    )
    observed = float(observed_residual @ y_residual / (observed_residual @ observed_residual))

    rng = np.random.default_rng(seed)
    coefficients = np.empty(repetitions, dtype=float)
    post = sample["time"].to_numpy(dtype=float)
    row_entity = sample["id"].to_numpy()
    for index in range(repetitions):
        assigned = set(rng.choice(entity_ids, size=treated_count, replace=False).tolist())
        permuted_d = np.fromiter(
            (float(entity in assigned) for entity in row_entity),
            dtype=float,
            count=len(sample),
        ) * post
        residual = double_demean(permuted_d, row_entity, sample["month"].to_numpy())
        coefficients[index] = float(residual @ y_residual / (residual @ residual))
    p_value = (1 + int(np.sum(np.abs(coefficients) >= abs(observed)))) / (
        repetitions + 1
    )
    return {
        "scope": "固定处理城市数的标签置换描述性诊断；政策并非随机分配，p值不能作为随机试验推断",
        "seed": seed,
        "repetitions": repetitions,
        "treated_city_count": treated_count,
        "observed_twfe_no_control_coefficient": round(observed, 10),
        "two_sided_placebo_p_value": round(p_value, 10),
        "placebo_coefficient_quantiles": {
            "q025": round(float(np.quantile(coefficients, 0.025)), 10),
            "q50": round(float(np.quantile(coefficients, 0.5)), 10),
            "q975": round(float(np.quantile(coefficients, 0.975)), 10),
        },
    }


def plot_round_comparison(models: dict[str, dict[str, Any]], output: Path) -> None:
    labels = list(models)
    coefficients = np.array([models[label]["coefficient"] for label in labels])
    lower = np.array([models[label]["confidence_interval_95"][0] for label in labels])
    upper = np.array([models[label]["confidence_interval_95"][1] for label in labels])
    positions = np.arange(len(labels))
    figure, axis = plt.subplots(figsize=(9.5, 5.5), constrained_layout=True)
    axis.errorbar(
        coefficients,
        positions,
        xerr=[coefficients - lower, upper - coefficients],
        fmt="o",
        color="#16697A",
        ecolor="#82C0CC",
        capsize=3,
    )
    axis.axvline(0, color="#333333", linewidth=1)
    axis.set_yticks(positions, labels)
    axis.invert_yaxis()
    axis.set_xlabel("dudt coefficient in source-data units (95% CI)")
    axis.set_title("Round 2 targeted sensitivity models")
    axis.grid(axis="x", alpha=0.2)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=220)
    plt.close(figure)


def execute_round2(
    protocol_path: Path, data_path: Path, output_dir: Path, round1_path: Path
) -> dict[str, Any]:
    protocol = load_json(protocol_path)
    if protocol.get("phase") != "round2":
        raise ValueError("round2 command requires a round2 protocol")
    round1 = load_json(round1_path)
    expected_round1_hash = str(protocol["feedback_binding"]["round1_result_sha256"])
    actual_round1_hash = file_hash(round1_path)
    if actual_round1_hash != expected_round1_hash:
        raise ValueError("round2 protocol does not bind the current round1 result")
    required_rules = set(protocol["feedback_binding"]["triggered_rules"])
    observed_rules = {
        key for key, value in round1["decision_triggers"].items() if bool(value)
    }
    if required_rules != observed_rules:
        raise ValueError(
            f"round2 rule binding mismatch: protocol={sorted(required_rules)}, "
            f"round1={sorted(observed_rules)}"
        )

    data, _ = load_data(data_path, protocol)
    complete = prepare_sample(data, "PM2.5", CONTROL_COLUMNS)
    full = prepare_sample(data, "PM2.5", [])
    baseline_model = fit_clustered(complete, "PM2.5", ["dudt", *CONTROL_COLUMNS])
    baseline = model_summary(baseline_model, complete, "dudt")
    if abs(baseline["coefficient"] - round1["primary_model"]["result"]["coefficient"]) > 1e-9:
        raise ValueError("round1 baseline did not reproduce in round2")

    no_control_model = fit_clustered(full, "PM2.5", ["dudt"])
    no_control = model_summary(no_control_model, full, "dudt")

    trend_sample = complete.copy()
    trend_sample["treated_linear_trend"] = trend_sample["treat"] * (
        trend_sample["month"] - 30
    )
    trend_model = fit_clustered(
        trend_sample,
        "PM2.5",
        ["dudt", "treated_linear_trend", *CONTROL_COLUMNS],
    )
    trend_adjusted = model_summary(trend_model, trend_sample, "dudt")
    trend_term = model_summary(trend_model, trend_sample, "treated_linear_trend")

    short = prepare_sample(
        data, "PM2.5", CONTROL_COLUMNS, lower_month=19, upper_month=42
    )
    short_model = fit_clustered(short, "PM2.5", ["dudt", *CONTROL_COLUMNS])
    short_window = model_summary(short_model, short, "dudt")

    pre = prepare_sample(data, "PM2.5", CONTROL_COLUMNS, upper_month=30)
    pre["treated_pretrend"] = pre["treat"] * (pre["month"] - 30)
    pretrend_model = fit_clustered(
        pre, "PM2.5", ["treated_pretrend", *CONTROL_COLUMNS]
    )
    differential_pretrend = model_summary(pretrend_model, pre, "treated_pretrend")

    permutation = permutation_diagnostic(
        full,
        treated_count=int(full.loc[full["treat"].eq(1), "id"].nunique()),
        repetitions=int(protocol["round2_tasks"]["permutation_repetitions"]),
        seed=int(protocol["round2_tasks"]["random_seed"]),
    )

    estimates = {
        "round1_controlled_complete_case": baseline,
        "round2_no_controls_full_sample": no_control,
        "round2_controlled_with_treated_linear_trend": trend_adjusted,
        "round2_controlled_short_window_month19_42": short_window,
    }
    signs = {name: int(np.sign(item["coefficient"])) for name, item in estimates.items()}
    sign_instability = len(set(signs.values())) > 1
    pretrend_failed = bool(round1["decision_triggers"]["R1_PRETREND"])
    missingness_triggered = bool(round1["decision_triggers"]["R1_MISSINGNESS"])
    causal_authorized = not (pretrend_failed or missingness_triggered or sign_instability)

    result = {
        "schema_version": "track1b-adaptive-social-science-result/1.0.0",
        "experiment_id": protocol["experiment_id"],
        "phase": "round2",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "path": protocol_path.resolve().relative_to(ROOT.resolve()).as_posix(),
            "raw_sha256": file_hash(protocol_path),
            "canonical_sha256": canonical_json_hash(protocol),
            "frozen_at": protocol["frozen_at"],
        },
        "feedback_binding": {
            "round1_result_path": round1_path.resolve().relative_to(ROOT.resolve()).as_posix(),
            "round1_result_sha256": actual_round1_hash,
            "triggered_rules": sorted(observed_rules),
        },
        "data": {
            "path": data_path.resolve().relative_to(ROOT.resolve()).as_posix(),
            "md5": file_hash(data_path, "md5"),
            "sha256": file_hash(data_path, "sha256"),
            "license": protocol["data_contract"]["license"],
            "persistent_id": protocol["data_contract"]["persistent_id"],
        },
        "models": estimates,
        "targeted_diagnostics": {
            "treated_group_linear_trend_in_full_model": trend_term,
            "pre_policy_differential_linear_trend": differential_pretrend,
            "treatment_label_permutation": permutation,
            "coefficient_signs": signs,
            "sign_instability_across_specifications": sign_instability,
        },
        "feedback_effect": {
            "plan_changed": True,
            "change_description": (
                "第一轮触发前趋势、缺失选择和小处理组规则后，第二轮从单一主效应估计转为"
                "全样本缺失敏感性、处理组趋势、短窗口和标签置换诊断。"
            ),
            "not_merely_regenerated": (
                "第二轮执行了第一轮未运行的统计任务；协议绑定第一轮结果哈希，并在执行前冻结。"
            ),
        },
        "final_decision": {
            "causal_claim_authorized": causal_authorized,
            "scientific_status": "limited" if not causal_authorized else "supportive_pending_review",
            "primary_claim_status": "rejected" if not causal_authorized else "candidate",
            "reasons": [
                reason
                for condition, reason in [
                    (pretrend_failed, "第一轮联合前趋势检验拒绝平行趋势。"),
                    (missingness_triggered, "完整样本损失超过冻结阈值或处理城市减少。"),
                    (sign_instability, "预先指定的第二轮规格间核心系数方向不稳定。"),
                    (
                        differential_pretrend["p_value_two_sided"] < 0.05,
                        "政策前处理组差异线性趋势显著。",
                    ),
                ]
                if condition
            ],
            "allowed_wording": (
                "本数据中的模型结果仅构成关联与识别失败证据，不能据此声称试点政策导致 PM2.5 变化。"
                if not causal_authorized
                else "结果与冻结方向性假设一致，但仍需独立数据与外部复核。"
            ),
        },
        "limitations": [
            "政策不是随机分配，标签置换仅为描述性安慰剂诊断。",
            "处理城市数量很少，城市聚类推断可能不稳定。",
            "源工作簿未编码 PM2.5 单位，本报告不补写无法从数据合同核验的单位。",
            "加入处理组线性趋势和短窗口属于第一轮反馈触发的敏感性分析，不替代冻结的第一轮主模型。",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "round2_result.json"
    write_json(result_path, result)
    (output_dir / "round2_result.sha256").write_text(
        f"{file_hash(result_path)}  round2_result.json\n", encoding="ascii"
    )
    pd.DataFrame(
        [
            {
                "model": name,
                **values,
            }
            for name, values in estimates.items()
        ]
    ).to_csv(output_dir / "round2_model_comparison.csv", index=False, encoding="utf-8-sig")
    plot_round_comparison(estimates, output_dir / "round2_model_comparison.png")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    first = subparsers.add_parser("round1")
    first.add_argument("--protocol", type=Path, default=DEFAULT_ROUND1_PROTOCOL)
    first.add_argument("--data", type=Path, default=DEFAULT_DATA)
    first.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    second = subparsers.add_parser("round2")
    second.add_argument("--protocol", type=Path, default=DEFAULT_ROUND2_PROTOCOL)
    second.add_argument("--data", type=Path, default=DEFAULT_DATA)
    second.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    second.add_argument(
        "--round1-result", type=Path, default=DEFAULT_OUTPUT / "round1_result.json"
    )
    args = parser.parse_args()

    if args.command == "round1":
        result = execute_round1(args.protocol, args.data, args.output_dir)
        print(
            json.dumps(
                {
                    "phase": "round1",
                    "output": str((args.output_dir / "round1_result.json").resolve()),
                    "coefficient": result["primary_model"]["result"]["coefficient"],
                    "p_value": result["primary_model"]["result"]["p_value_two_sided"],
                    "joint_pretrend_p": result["event_study"]["joint_pretrend_p_value"],
                    "triggered_rules": result["feedback"]["triggered_rules"],
                },
                ensure_ascii=False,
            )
        )
        return 0

    result = execute_round2(
        args.protocol, args.data, args.output_dir, args.round1_result
    )
    print(
        json.dumps(
            {
                "phase": "round2",
                "output": str((args.output_dir / "round2_result.json").resolve()),
                "causal_claim_authorized": result["final_decision"]["causal_claim_authorized"],
                "reasons": result["final_decision"]["reasons"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
