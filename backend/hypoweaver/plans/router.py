from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import session
from ..jobs import Job
from ..llm.service import get_llm
from ..literature.service import serialize
from ..projects import service as projects
from . import service
from .models import PlanDraft

router = APIRouter(prefix='/api')


@router.post('/projects/{project_id}/plans')
async def draft(project_id: str, request: Request, llm=Depends(get_llm)):
    return {'job_id': service.draft(request.app, project_id, llm)}


@router.get('/projects/{project_id}/plans')
def list_plans(project_id: str, db: Session = Depends(session)):
    return service.list_(db, project_id)


@router.get('/projects/{project_id}/plan-tasks')
def tasks(project_id: str, db: Session = Depends(session)):
    projects.get(db, project_id)
    return [serialize(j) for j in db.scalars(select(Job).where(Job.project_id == project_id, Job.kind == 'plan').order_by(Job.created_at.desc()).limit(1)).all()]


@router.get('/plans/{plan_id}')
def get(plan_id: str, db: Session = Depends(session)):
    return serialize(service.get(db, plan_id))


@router.patch('/plans/{plan_id}')
def update(plan_id: str, payload: PlanDraft, db: Session = Depends(session)):
    return serialize(service.edit(db, plan_id, payload))


@router.post('/plans/{plan_id}:new-version')
def new_version(plan_id: str, db: Session = Depends(session)):
    return serialize(service.new_version(db, plan_id))


@router.post('/plans/{plan_id}:confirm')
def confirm(plan_id: str, db: Session = Depends(session)):
    return serialize(service.confirm(db, plan_id))
