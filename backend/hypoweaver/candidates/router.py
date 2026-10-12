from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from ..db import session
from ..llm.service import get_llm
from . import service

router = APIRouter(prefix='/api')


@router.post('/projects/{project_id}/candidate-sets')
async def generate(project_id: str, request: Request, llm=Depends(get_llm)):
    return {'job_id': service.start(request.app, project_id, llm)}


@router.get('/projects/{project_id}/candidate-sets')
def list_sets(project_id: str, db: Session = Depends(session)):
    return service.list_(db, project_id)


from .models import CandidateDraft


@router.patch('/candidates/{candidate_id}')
def edit(candidate_id: str, payload: CandidateDraft, db: Session = Depends(session)):
    return service.edit(db, candidate_id, payload)


@router.post('/candidates/{candidate_id}:select')
def select(candidate_id: str, db: Session = Depends(session)):
    return service.select_(db, candidate_id)
