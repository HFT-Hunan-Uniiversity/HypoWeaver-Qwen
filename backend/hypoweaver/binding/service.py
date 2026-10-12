import numpy as np
import pandas as pd
from ..db import now
from ..errors import AppError
from ..plans import service as plans
from ..datasets import service as datasets
from ..literature.service import serialize
from ..staleness import invalidate
from .models import VariableBinding, BindingOutput
from .expressions import resolve


def get(db, plan_id):
    plans.get(db, plan_id)
    binding = db.get(VariableBinding, plan_id)
    return serialize(binding) if binding else None


def save(db, plan_id, payload):
    plan = plans.get(db, plan_id)
    if plan.stale or plan.status != "confirmed":
        raise AppError("plan_unconfirmed", "请先确认当前未过期方案，再保存变量绑定")
    from ..projects import service as projects

    datasets.get(db, payload.dataset_id)
    plans.schema_for(db, projects.get(db, plan.project_id), payload.dataset_id).model_validate(serialize(plan))
    data = datasets.frame(db, payload.dataset_id)
    variables = {v["name"]: v for v in plan.variables}
    for name, value in payload.bindings.items():
        if name not in variables:
            raise AppError("unknown_variable", f"方案中没有变量：{name}")
        if variables[name]["role"] in {"unit", "time"} and value.formula:
            raise AppError("invalid_key", "个体和时间标识请直接绑定字段")
        resolve(value.model_dump(), data)
    binding = db.get(VariableBinding, plan_id)
    if binding is None:
        binding = VariableBinding(plan_id=plan_id)
        db.add(binding)
    values = payload.model_dump()
    changed = any(getattr(binding, k) != v for k, v in values.items())
    for key, value in values.items():
        setattr(binding, key, value)
    binding.updated_at = now()
    if changed:
        invalidate(db, plan.project_id, "data")
    db.commit()
    return serialize(binding)


def materialize(plan, frame, bindings):
    """Produce role-name columns from the saved specification, with readable missing errors."""
    output = pd.DataFrame(index=frame.index)
    missing = []
    for variable in plan.variables:
        name = variable["name"]
        value = bindings.get(name)
        if not value:
            missing.append(name)
            continue
        output[name] = resolve(value, frame)
    return output, missing


def sample_report(plan, frame):
    variables = plan.variables
    roles = {v["role"]: v["name"] for v in variables if v["role"] != "control"}
    unit, time, treatment = (roles[x] for x in ["unit", "time", "treatment"])
    clean = frame.copy()
    invalid = {}
    for v in variables:
        name = v["name"]
        if v["role"] != "unit":
            clean[name] = pd.to_numeric(clean[name], errors="coerce").replace([np.inf, -np.inf], np.nan)
        invalid[name] = int(clean[name].isna().sum())
    valid = clean.dropna()
    errors = []
    if len(valid) < 10:
        errors.append("有效样本少于 10 行")
    duplicates = int(valid.duplicated([unit, time]).sum())
    if duplicates:
        errors.append(f"个体—时间键重复 {duplicates} 行，请先修正数据")
    n_units, n_periods = int(valid[unit].nunique()), int(valid[time].nunique())
    if n_units < 2 or n_periods < 2:
        errors.append("至少需要两个个体和两个时期")
    ordered = valid.sort_values([unit, time])
    binary = bool(set(ordered[treatment].unique()) <= {0, 1})
    treated, control, monotone, reversals, cohorts = None, None, None, None, []
    if binary:
        ever = ordered.groupby(unit)[treatment].max()
        treated, control = int((ever == 1).sum()), int((ever == 0).sum())
        backward = ordered.groupby(unit)[treatment].diff().lt(0)
        reversed_units = set(ordered.loc[backward, unit])
        monotone = n_units - len(reversed_units)
        reversals = int(backward.sum())
        first = ordered.loc[ordered[treatment] == 1].groupby(unit)[time].min()
        cohorts = [{"year": float(y), "count": int(n)} for y, n in first.value_counts().sort_index().items()]
        if plan.method_family == "policy_causal" and (treated == 0 or control == 0):
            errors.append("政策检验需要曾暴露个体和从未暴露的对照个体")
    elif plan.method_family == "policy_causal":
        errors.append("政策 DID 的处理变量必须为 0/1")
    if valid[treatment].nunique() < 2:
        errors.append("处理 / 核心解释变量没有变化")
    outcome = roles["outcome"]
    if valid[outcome].nunique() < 2:
        errors.append("结果变量没有变化")
    return {
        "n_total": len(frame),
        "n_valid": len(valid),
        "dropped": len(frame) - len(valid),
        "invalid_by_variable": invalid,
        "n_units": n_units,
        "n_periods": n_periods,
        "duplicates": duplicates,
        "binary_treatment": binary,
        "treated_units": treated,
        "control_units": control,
        "monotone_units": monotone,
        "reversal_transitions": reversals,
        "first_exposure": cohorts,
        "errors": errors,
    }, valid


def readiness(db, plan_id):
    plan = plans.get(db, plan_id)
    binding = db.get(VariableBinding, plan_id)
    issues = []
    from pydantic import ValidationError
    from ..projects import service as projects

    try:
        plans.schema_for(db, projects.get(db, plan.project_id)).model_validate(serialize(plan))
    except ValidationError:
        issues.append("方案不满足当前案例的数据约束，请新建版本补充稳健性设定")
    if plan.status != "confirmed" or plan.stale:
        issues.append("确认当前未过期的研究方案")
    if not binding:
        missing = [v["name"] for v in plan.variables]
        return {
            "status": "not_ready",
            "missing": missing,
            "bound": [],
            "data_plan": issues + ["选择数据资产并绑定变量：" + ", ".join(missing)],
            "sample": None,
        }
    if not binding.confirmed:
        issues.append("审阅并确认变量绑定")
    raw = datasets.frame(db, binding.dataset_id)
    try:
        materialized, missing = materialize(plan, raw, binding.bindings)
        issues += [f"补充变量 {name} 的字段或派生公式" for name in missing]
        sample = None
        if not missing:
            sample, _ = sample_report(plan, materialized)
            issues += sample["errors"]
    except AppError as exc:
        missing = []
        sample = None
        issues.append(exc.message)
    return {
        "status": "not_ready" if issues else "ready",
        "missing": missing,
        "bound": list(binding.bindings),
        "data_plan": issues,
        "sample": sample,
        "dataset_id": binding.dataset_id,
    }


async def suggest(db, plan_id, dataset_id, llm):
    plan = plans.get(db, plan_id)
    dataset = datasets.get(db, dataset_id)
    output = await llm.generate(
        "suggest_bindings",
        {
            "variables": plan.variables,
            "fields": [{"name": f["name"], "label": f["label"], "type": f["type"]} for f in dataset.profile],
        },
        BindingOutput,
        plan.project_id,
    )
    # Suggestions are not saved or confirmed on behalf of the user.
    names = {v["name"] for v in plan.variables}
    return {
        "bindings": [b.model_dump() for b in output.bindings if b.role_name in names],
        "note": "建议尚未保存，请核对字段含义及公式后确认",
    }
