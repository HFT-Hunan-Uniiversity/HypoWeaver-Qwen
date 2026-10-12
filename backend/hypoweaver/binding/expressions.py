"""Small expression interpreter. No Python evaluation, attributes, indexing or imports."""

import ast
import operator
import numpy as np
import pandas as pd
from ..errors import AppError

BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
FUNCTIONS = {"log": np.log, "log1p": np.log1p}


def formula(expression, frame):
    if not expression or len(expression) > 500:
        raise AppError("invalid_formula", "公式不能为空且最多 500 个字符")
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, RecursionError) as exc:
        raise AppError("invalid_formula", "公式语法错误，请使用字段、log/log1p 与加减乘除") from exc
    if sum(1 for _ in ast.walk(tree)) > 64:
        raise AppError("invalid_formula", "公式过于复杂，请拆简")
    referenced = set()

    def visit(node):
        if isinstance(node, ast.Name):
            if node.id not in frame:
                raise AppError("missing_field", f"公式引用了不存在的字段：{node.id}")
            referenced.add(node.id)
            return pd.to_numeric(frame[node.id], errors="coerce").astype(float)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float) and np.isfinite(float(node.value)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in BINARY:
            return BINARY[type(node.op)](visit(node.left), visit(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY:
            return UNARY[type(node.op)](visit(node.operand))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in FUNCTIONS
            and len(node.args) == 1
            and not node.keywords
        ):
            return FUNCTIONS[node.func.id](visit(node.args[0]))
        raise AppError("invalid_formula", "公式只允许字段引用、数值、log、log1p 和加减乘除")

    try:
        with np.errstate(all="ignore"):
            result = visit(tree.body)
    except (ZeroDivisionError, OverflowError, TypeError) as exc:
        raise AppError("invalid_formula", "公式包含无效运算，请检查常量与数据类型") from exc
    if not referenced or not isinstance(result, pd.Series):
        raise AppError("invalid_formula", "派生公式必须引用至少一个数据字段")
    return result.replace([np.inf, -np.inf], np.nan)


def resolve(value, frame):
    if value.get("field"):
        if value["field"] not in frame:
            raise AppError("missing_field", f"字段不存在：{value['field']}")
        return frame[value["field"]]
    return formula(value.get("formula"), frame)
