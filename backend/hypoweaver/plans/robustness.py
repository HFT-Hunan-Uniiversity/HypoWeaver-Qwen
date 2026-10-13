"""Resolve plan aliases structurally, then validate against the data dictionary."""

import ast
from copy import deepcopy
import pandas as pd
from ..errors import AppError
from ..binding.expressions import formula


def canonical(text):
    return ast.dump(ast.parse(text, mode="eval"))


def expression(text, mappings, fields=None):
    if not isinstance(text, str) or not text or len(text) > 500:
        raise AppError("robustness_args", "变量表达式须为非空字符串且不超过500字符")
    try:
        tree = ast.parse(text, mode="eval")

        class Substitute(ast.NodeTransformer):
            def visit_Call(self, node):
                # Function names are not variable aliases.
                node.args = [self.visit(arg) for arg in node.args]
                return node

            def visit_Name(self, node):
                value = mappings.get(node.id)
                if value:
                    return ast.parse(value.get("field") or value.get("formula"), mode="eval").body
                return node

        resolved = ast.unparse(Substitute().visit(tree))
        names = (
            fields if fields is not None else {n.id for n in ast.walk(ast.parse(resolved)) if isinstance(n, ast.Name)}
        )
        formula(resolved, pd.DataFrame({n: pd.Series(dtype=float) for n in names}))
        return resolved
    except (SyntaxError, RecursionError, TypeError, ValueError) as exc:
        raise AppError("robustness_args", "变量或公式无法解析，请使用已有字段、log/log1p与加减乘除") from exc


def compile_checks(plan, mappings, fields=None):
    baseline = [expression(v["name"], mappings, fields) for v in plan.variables if v["role"] == "control"]
    baseline_keys = {canonical(c) for c in baseline}
    checks = deepcopy(plan.robustness)
    for check in checks:
        try:
            args, kind = check["args"], check["kind"]
            if kind in {"add_controls", "drop_controls"}:
                values = args.get("controls")
                if kind == "drop_controls" and values is None:
                    values = baseline
                    # These are already raw expressions: don't resolve aliases twice.
                    resolved = values
                else:
                    if not isinstance(values, list) or not values or not all(isinstance(v, str) for v in values):
                        raise AppError("robustness_args", "controls必须是非空变量/公式列表")
                    resolved = [expression(v, mappings, fields) for v in values]
                keys = {canonical(c) for c in resolved}
                if kind == "add_controls" and keys & baseline_keys:
                    raise AppError("robustness_args", "不能加入已在基准模型中的控制变量，这属于空检验")
                if kind == "drop_controls" and not keys <= baseline_keys:
                    raise AppError("robustness_args", "移除的控制变量不在基准模型中")
                args["controls"] = resolved
            elif kind == "alt_outcome":
                args["outcome"] = expression(args.get("outcome"), mappings, fields)
            elif kind == "exclude_years":
                years = args.get("years")
                if not isinstance(years, list) or not years or any(type(y) not in (int, float) for y in years):
                    raise AppError("robustness_args", "years必须是非空数值年份列表")
                import math

                if not all(math.isfinite(y) for y in years):
                    raise AppError("robustness_args", "年份必须是有限数值")
        except AppError as exc:
            raise AppError("robustness_args", f"稳健性「{check['change']}」：{exc.message}", 422) from exc
    return checks


def validate_plan(db, plan):
    from ..binding.service import get
    from ..datasets.service import get as dataset_get

    binding = get(db, plan.id)
    mappings = binding["bindings"] if binding else plan.suggested_binding or {}
    fields = {f["name"] for f in dataset_get(db, binding["dataset_id"]).profile} if binding else None
    compile_checks(plan, mappings, fields)
