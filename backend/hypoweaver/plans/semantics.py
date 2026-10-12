import ast
import pandas as pd
from ..binding.expressions import formula
from ..binding.models import VariableBinding
from ..datasets.models import Dataset
from ..literature.service import serialize


def treatment_semantics(db, plan):
    binding = db.get(VariableBinding, plan.id)
    dataset = db.get(Dataset, binding.dataset_id) if binding else None
    if not dataset:
        return "unknown"
    fields = {p["name"]: p.get("semantics", "unknown") for p in dataset.profile}
    names = set()
    for variable in plan.variables:
        if variable["role"] != "treatment":
            continue
        value = binding.bindings.get(variable["name"], {})
        if value.get("field"):
            names.add(value["field"])
        elif value.get("formula"):
            expression = value["formula"]
            formula(expression, pd.DataFrame({name: pd.Series(dtype=float) for name in fields}))
            tree = ast.parse(expression, mode="eval")
            functions = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
            names.update(n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and id(n) not in functions)
    semantics = {fields.get(name, "unknown") for name in names}
    if semantics == {"real_assignment"}:
        return "real_assignment"
    return "peer_exposure" if "peer_exposure" in semantics else "unknown"


def public(db, plan):
    return {**serialize(plan), "treatment_semantics": treatment_semantics(db, plan)}
