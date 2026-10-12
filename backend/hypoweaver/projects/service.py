from sqlalchemy import select
from ..db import now
from ..errors import AppError
from .models import Project

STAGES = [("direction", "研究方向"), ("literature", "文献调研"), ("candidates", "缺口与候选"), ("plan", "研究方案"), ("data", "数据与检验"), ("proposal", "研究提案")]


def get(db, project_id):
    project = db.get(Project, project_id)
    if not project:
        raise AppError("project_not_found", "项目不存在", 404)
    return project


def list_(db):
    return db.scalars(select(Project).order_by(Project.updated_at.desc())).all()


def create(db, payload):
    project = Project(title=payload.title.strip(), direction=payload.direction.model_dump())
    db.add(project)
    db.commit()
    return project


def update(db, project_id, payload):
    project = get(db, project_id)
    if payload.direction is not None and payload.direction.model_dump() != project.direction:
        from ..staleness import invalidate
        invalidate(db, project_id, "direction")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(project, key, value)
    project.updated_at = now()
    db.commit()
    return project


def delete(db, project_id):
    db.delete(get(db, project_id))
    db.commit()


def stage_status(project):
    return [{"key": key, "label": label, "status": "not_started"} for key, label in STAGES]
