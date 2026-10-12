from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from ..db import session
from ..literature.service import serialize
from . import service

router = APIRouter(prefix='/api')


@router.post('/plans/{plan_id}/runs')
async def start(plan_id: str, request: Request):
    return {'job_id': service.start(request.app, plan_id)}


@router.get('/plans/{plan_id}/runs')
def plan_runs(plan_id: str, db: Session = Depends(session)):
    return service.list_(db, plan_id=plan_id)


@router.get('/projects/{project_id}/runs')
def project_runs(project_id: str, db: Session = Depends(session)):
    return service.list_(db, project_id=project_id)


@router.get('/runs/{run_id}')
def get(run_id: str, db: Session = Depends(session)):
    return serialize(service.get(db, run_id))
