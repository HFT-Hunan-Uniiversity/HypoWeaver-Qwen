"""Independent within OLS and statsmodels cluster sandwich; no PanelOLS calls."""

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.sandwich_covariance import cov_cluster
from scipy.stats import t as t_dist
from ..errors import AppError
from .models import AnalysisSpec
from .preparation import prepare, robustness_spec


def refit(spec, frame):
    clean, regressors, target, _, _ = prepare(spec, frame)
    values = clean[["y", *regressors]].astype(float).copy()
    values -= values.mean()
    for _ in range(500):
        previous = values.to_numpy().copy()
        for effect in spec.fe:
            values -= values.groupby(clean[effect]).transform("mean")
        if np.max(np.abs(values.to_numpy() - previous)) < 1e-11:
            break
    else:
        raise AppError("reproduction_failed", "独立复算去均值未收敛")
    x = values[regressors].to_numpy()
    if np.linalg.matrix_rank(x) != len(regressors):
        raise AppError("reproduction_failed", "独立复算发现解释变量共线")
    fitted = sm.OLS(values["y"].to_numpy(), x).fit()
    n, groups = len(clean), clean["cluster"].nunique()
    degrees = 1 + len(regressors) + sum(clean[k].nunique() - 1 for k in set(spec.fe))
    if n <= degrees:
        raise AppError("reproduction_failed", "独立复算残差自由度不足")
    cov = cov_cluster(fitted, pd.factorize(clean["cluster"])[0], use_correction=False)
    cov *= groups / (groups - 1) * (n - 1) / (n - degrees)
    i = regressors.index(target)
    coef, se = float(fitted.params[i]), float(np.sqrt(cov[i, i]))
    t = coef / se
    critical = t_dist.ppf(0.975, groups - 1)
    return {
        "coef": coef,
        "se": se,
        "t": t,
        "p": float(2 * t_dist.sf(abs(t), groups - 1)),
        "ci": [float(coef - critical * se), float(coef + critical * se)],
        "n_obs": n,
    }


def reproduce(spec, frame, result=None):
    spec = AnalysisSpec.model_validate(spec) if isinstance(spec, dict) else spec
    rows = []
    for check in [None, *spec.robustness]:
        label = check.change if check else "主模型"
        identifier = check.id if check else "main"
        original = (
            None
            if result is None
            else result["main"]
            if check is None
            else next((r for r in result["robustness"] if r["id"] == identifier), None)
        )
        if check and result is not None and (original is None or original.get("status") != "succeeded"):
            rows.append(
                {
                    "id": identifier,
                    "label": label,
                    "status": "failed",
                    "origin": "analysis",
                    "error": (original or {}).get("error", "原稳健性未运行成功，不纳入复算一致性"),
                    "original": original,
                }
            )
            continue
        try:
            changed, raw = robustness_spec(spec, check, frame) if check else (spec, frame)
            estimate = refit(changed, raw)
            original = (
                None
                if result is None
                else result["main"]
                if check is None
                else next(
                    (r for r in result["robustness"] if r["id"] == identifier and r["status"] == "succeeded"), None
                )
            )
            differences = (
                {}
                if original is None
                else {
                    k: abs(estimate[k] - original[k]) / max(abs(original[k]), 1e-8)
                    for k in ["coef", "se", "t", "p", "n_obs"]
                }
            )
            if original is not None:
                differences.update(
                    {
                        f"ci_{i}": abs(estimate["ci"][i] - original["ci"][i]) / max(abs(original["ci"][i]), 1e-8)
                        for i in range(2)
                    }
                )
            maximum = max(differences.values(), default=0.0)
            rows.append(
                {
                    "id": identifier,
                    "label": label,
                    "estimate": estimate,
                    "original": original,
                    "max_relative_diff": maximum,
                    "status": "consistent"
                    if original is not None and maximum < 1e-6
                    else "uncompared"
                    if original is None
                    else "inconsistent",
                }
            )
        except (AppError, ValueError, np.linalg.LinAlgError) as exc:
            rows.append(
                {
                    "id": identifier,
                    "label": label,
                    "status": "failed",
                    "error": exc.message if isinstance(exc, AppError) else "独立复算数值计算失败",
                }
            )
    return {
        "consistent": all(r["status"] == "consistent" for r in rows if r.get("origin") != "analysis"),
        "main_consistent": rows[0]["status"] == "consistent",
        "max_relative_diff": max((r.get("max_relative_diff", 0.0) for r in rows), default=0.0),
        "rows": rows,
        "tolerance": 1e-6,
        "method": "statsmodels OLS / 独立交替去均值 / 聚类夹心协方差",
    }
