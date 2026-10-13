import operator
import numpy as np
import pandas as pd
from ..binding.expressions import resolve
from ..errors import AppError


def expression(text, frame):
    return resolve({"field": text} if text in frame else {"formula": text}, frame)


def filtered(spec, frame):
    frame = frame.copy()
    operations = {"eq": operator.eq, "ne": operator.ne, "ge": operator.ge, "le": operator.le}
    for rule in spec.sample_filters:
        if rule.field not in frame:
            raise AppError("missing_field", f"样本筛选字段不存在：{rule.field}")
        try:
            mask = (
                frame[rule.field].isin(rule.value)
                if rule.op == "in"
                else operations[rule.op](frame[rule.field], rule.value)
            )
            frame = frame.loc[mask.fillna(False)]
        except (TypeError, ValueError) as exc:
            raise AppError("invalid_filter", f"样本筛选条件无效：{rule.field}") from exc
    return frame


def trajectories(spec, frame):
    for key in [spec.unit, spec.time]:
        if key not in frame:
            raise AppError("missing_field", f"面板键不存在：{key}")
    data = pd.DataFrame(
        {
            "unit": frame[spec.unit],
            "time": pd.to_numeric(frame[spec.time], errors="coerce"),
            "treatment": pd.to_numeric(expression(spec.treatment, frame), errors="coerce"),
        }
    )
    data = data.replace([np.inf, -np.inf], np.nan).dropna(subset=["unit", "time"]).sort_values(["unit", "time"])
    if data.duplicated(["unit", "time"]).any():
        raise AppError("duplicate_panel", "个体—时间键重复，请修正数据后运行")
    return data


def monotone_units(spec, frame):
    data = trajectories(spec, frame)
    bad = set(data.loc[data.groupby("unit")["treatment"].diff().lt(0) | data["treatment"].isna(), "unit"])
    return set(data["unit"]) - bad


def prepare(spec, raw):
    frame = filtered(spec, raw)
    paths = trajectories(spec, frame)
    output = pd.DataFrame(index=frame.index)
    output["unit"] = frame[spec.unit]
    output["time"] = pd.to_numeric(frame[spec.time], errors="coerce")
    outcome = (
        spec.mechanism
        if spec.method_family == "mechanism_boundary" and not spec.moderator and spec.mechanism
        else spec.outcome
    )
    output["y"] = pd.to_numeric(expression(outcome, frame), errors="coerce")
    output["treatment"] = pd.to_numeric(expression(spec.treatment, frame), errors="coerce")
    regressors = ["treatment"]
    for i, text in enumerate(spec.controls):
        name = f"control_{i}"
        output[name] = pd.to_numeric(expression(text, frame), errors="coerce")
        regressors.append(name)
    target = "treatment"
    if spec.method_family == "mechanism_boundary":
        if spec.moderator:
            output["moderator"] = pd.to_numeric(expression(spec.moderator, frame), errors="coerce")
            output["interaction"] = output["treatment"] * output["moderator"]
            regressors += ["moderator", "interaction"]
            target = "interaction"
        elif not spec.mechanism:
            raise AppError("mechanism_missing", "机制与边界分析需要机制变量或调节变量")
    cluster = spec.unit if spec.cluster == "unit" else spec.time if spec.cluster == "time" else spec.cluster
    if cluster not in frame:
        raise AppError("missing_cluster", f"聚类字段不存在：{cluster}")
    output["cluster"] = frame[cluster]
    output = output.replace([np.inf, -np.inf], np.nan)
    invalid = {c: int(output[c].isna().sum()) for c in output}
    clean = output.dropna().sort_values(["unit", "time"])
    if len(clean) < 10 or clean["unit"].nunique() < 2 or clean["time"].nunique() < 2:
        raise AppError("empty_sample", "有效样本不足，至少需要10行、两个个体和两个时期")
    if clean["cluster"].nunique() < 2:
        raise AppError("cluster_insufficient", "聚类标准误至少需要两个聚类组")
    if spec.method_family == "policy_causal" and not set(paths["treatment"].dropna().unique()) <= {0, 1}:
        raise AppError("invalid_treatment", "政策 DID 仅支持 0/1 处理变量")
    report = {
        "input_rows": len(raw),
        "filtered_rows": len(frame),
        "n_valid": len(clean),
        "dropped_by_reason": {"sample_filters": len(raw) - len(frame), "missing_or_nonfinite": len(frame) - len(clean)},
        "invalid_by_column": invalid,
        "n_clusters": int(clean["cluster"].nunique()),
    }
    return clean, regressors, target, report, paths


def robustness_spec(spec, check, frame):
    changed = spec.model_copy(deep=True)
    raw = frame
    if check.kind == "drop_controls":
        from ..plans.robustness import canonical

        requested = check.args.get("controls")
        if requested is None:
            changed.controls = []
        else:
            if not isinstance(requested, list) or not all(isinstance(c, str) for c in requested):
                raise AppError("robustness_args", "移除控制检查需要controls变量列表")
            keys = {canonical(c) for c in requested}
            if not keys <= {canonical(c) for c in changed.controls}:
                raise AppError("robustness_args", "移除的控制变量不在基准模型中")
            changed.controls = [c for c in changed.controls if canonical(c) not in keys]
    elif check.kind == "exclude_years":
        years = check.args.get("years")
        if not isinstance(years, list) or not years:
            raise AppError("robustness_args", "剔除年份检查需要非空 years 列表")
        numeric_years = pd.to_numeric(pd.Series(years), errors="coerce")
        if numeric_years.isna().any():
            raise AppError("robustness_args", "剔除年份必须为有效数值")
        mask = pd.to_numeric(frame[spec.time], errors="coerce").isin(numeric_years)
        if not mask.any():
            raise AppError("robustness_args", "剔除年份未匹配任何观测，请检查年份")
        raw = frame.loc[~mask]
    elif check.kind == "monotone_only":
        raw = frame.loc[frame[spec.unit].isin(monotone_units(spec, frame))]
    elif check.kind == "alt_outcome":
        outcome = check.args.get("outcome")
        if not isinstance(outcome, str) or not outcome:
            raise AppError("robustness_args", "替代结果检查需要 outcome 字段或公式")
        changed.outcome = outcome
        if changed.mechanism and not changed.moderator:
            changed.mechanism = outcome
    elif check.kind == "add_controls":
        controls = check.args.get("controls")
        if not isinstance(controls, list) or not controls or not all(isinstance(c, str) for c in controls):
            raise AppError("robustness_args", "增加控制检查需要非空 controls 列表")
        from ..plans.robustness import canonical

        baseline = {canonical(c) for c in changed.controls}
        if any(canonical(c) in baseline for c in controls):
            raise AppError("robustness_args", "不能加入已在基准模型中的控制变量，这属于空检验")
        changed.controls = list(dict.fromkeys([*changed.controls, *controls]))
    return changed, raw


def demean(values, units, times, effects):
    """Alternating projections support unbalanced panels; also removes the intercept."""
    matrix = np.asarray(values, dtype=float)
    one_dim = matrix.ndim == 1
    output = matrix.reshape(len(matrix), -1).copy()
    output -= output.mean(axis=0)
    groups = []
    for key, vector in [("unit", units), ("time", times)]:
        if key in effects:
            codes, labels = pd.factorize(vector, sort=True)
            groups.append((codes, len(labels), np.bincount(codes)))
    for _ in range(500):
        previous = output.copy()
        for codes, count, sizes in groups:
            totals = np.zeros((count, output.shape[1]))
            np.add.at(totals, codes, output)
            output -= (totals / sizes[:, None])[codes]
        if np.max(np.abs(output - previous)) < 1e-11:
            return output[:, 0] if one_dim else output
    raise AppError("demean_failed", "非平衡面板去均值未收敛，请检查样本结构")
