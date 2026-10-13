"""Bound data context shared by candidate, plan and binding suggestions."""

from sqlalchemy import select
from .models import Dataset


def for_project(db, project):
    from ..binding.models import VariableBinding
    from ..plans.models import StudyPlan

    dataset = db.scalar(
        select(Dataset)
        .join(VariableBinding, VariableBinding.dataset_id == Dataset.id)
        .join(StudyPlan, StudyPlan.id == VariableBinding.plan_id)
        .where(StudyPlan.project_id == project.id)
        .order_by(StudyPlan.version.desc())
        .limit(1)
    )
    if dataset is None and project.case == "carbon":
        dataset = db.scalar(
            select(Dataset)
            .where(Dataset.name == "碳市场企业面板 · Mendeley V1")
            .order_by(Dataset.created_at.desc())
            .limit(1)
        )
    return dataset


def fields(dataset):
    return [
        {
            key: field.get(key, "unknown" if key in {"semantics", "level"} else None)
            for key in ("name", "label", "type", "semantics", "level", "missing_rate")
        }
        for field in dataset.profile
    ]


def payload(db, project):
    dataset = for_project(db, project)
    return {"dataset_fields": fields(dataset)} if dataset else {}
