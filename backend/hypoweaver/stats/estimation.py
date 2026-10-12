import warnings
import numpy as np
import pandas as pd
from scipy.stats import f as f_dist, t as t_dist
from linearmodels.panel import PanelOLS
from ..errors import AppError
from .preparation import prepare, monotone_units


def fit(clean, regressors, fe, drop_absorbed=False):
    data = clean.set_index(["unit", "time"])
    x = data[regressors].copy()
    x.insert(0, "constant", 1.0)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            model = PanelOLS(
                data["y"], x, entity_effects="unit" in fe, time_effects="time" in fe, drop_absorbed=drop_absorbed
            )
            result = model.fit(
                cov_type="clustered",
                clusters=data[["cluster"]],
                debiased=True,
                auto_df=False,
                count_effects=True,
                group_debias=True,
                low_memory=True,
            )
        except Exception as exc:
            raise AppError(
                "estimation_failed", "模型无法估计：字段共线、被固定效应吸收或样本自由度不足，请检查设定"
            ) from exc
    notes = [str(w.message).strip()[:500] for w in caught]
    if clean["cluster"].nunique() < 30:
        notes.append("聚类组少于30，虽作小样本校正，常规聚类推断仍需谨慎。")
    return result, notes


def summary(result, target, clean):
    if target not in result.params:
        raise AppError("target_absorbed", "核心解释变量被固定效应吸收，无法报告系数")
    clusters = int(clean["cluster"].nunique())
    degrees = clusters - 1
    coefficient, se = float(result.params[target]), float(result.std_errors[target])
    critical = float(t_dist.ppf(0.975, degrees))
    ci = [coefficient - critical * se, coefficient + critical * se]
    values = {
        "coef": float(result.params[target]),
        "se": float(result.std_errors[target]),
        "t": float(result.tstats[target]),
        "p": float(2 * t_dist.sf(abs(result.tstats[target]), degrees)),
        "ci": ci,
        "inference_df": degrees,
        "n_clusters": clusters,
        "n_obs": int(result.nobs),
        "n_units": int(clean["unit"].nunique()),
        "r2_within": float(result.rsquared_within),
        "df_resid": int(result.df_resid),
        "df_model": int(result.df_model),
        "target": target,
    }
    if not all(np.isfinite(values[k]) for k in ["coef", "se", "t", "p"]) or values["se"] <= 0:
        raise AppError("invalid_inference", "模型推断结果无效，可能是变异或聚类数不足")
    return values


def estimate(spec, frame):
    clean, regressors, target, report, _ = prepare(spec, frame)
    result, notes = fit(clean, regressors, spec.fe)
    return summary(result, target, clean), report, notes


def event_study(spec, raw):
    clean, regressors, _, _, paths = prepare(spec, raw)
    eligible = monotone_units(spec, raw)
    clean = clean.loc[clean["unit"].isin(eligible)].copy()
    first = paths.loc[paths["treatment"] == 1].groupby("unit")["time"].min()
    relative = clean["time"] - clean["unit"].map(first)
    clipped = relative.clip(spec.event.bins[0], spec.event.bins[-1])
    terms, omitted = {}, []
    for k in spec.event.bins:
        name = f"event_m{abs(k)}" if k < 0 else f"event_p{k}"
        clean[name] = (clipped == k).astype(float)
        if clean[name].nunique() < 2:
            omitted.append(k)
        else:
            terms[k] = name
    if not terms or clean.empty:
        raise AppError("event_empty", "单调路径样本没有可估计的事件期")
    controls = [r for r in regressors if r.startswith("control_")]
    result, warnings_ = fit(clean, list(terms.values()) + controls, spec.fe, drop_absorbed=True)
    output = []
    for k, name in terms.items():
        if name not in result.params:
            omitted.append(k)
            continue
        output.append(
            {
                "k": k,
                **{
                    key: value
                    for key, value in summary(result, name, clean).items()
                    if key in ["coef", "se", "p", "ci"]
                },
            }
        )
    pre = [name for k, name in terms.items() if k < -1 and name in result.params]
    wald = {"stat": None, "p": None, "df": len(pre)}
    if pre:
        b = result.params[pre].to_numpy()
        cov = result.cov.loc[pre, pre].to_numpy()
        if np.linalg.matrix_rank(cov) == len(pre):
            stat = float(b @ np.linalg.solve(cov, b) / len(pre))
            degrees = int(clean["cluster"].nunique()) - 1
            wald = {
                "stat": stat,
                "p": float(f_dist.sf(stat, len(pre), degrees)),
                "df": len(pre),
                "df_denom": degrees,
                "distribution": "F",
            }
    return {
        "terms": output,
        "reference": -1,
        "pretrend_wald": wald,
        "omitted_bins": sorted(omitted),
        "n_obs": len(clean),
        "n_units": int(clean["unit"].nunique()),
        "excluded_nonmonotone_units": int(paths["unit"].nunique() - len(eligible)),
        "warnings": warnings_,
    }
