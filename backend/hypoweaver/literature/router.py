from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from ..db import session
from ..llm.service import get_llm
from ..projects import service as projects
from . import service
from .models import EvidencePatch, QuerySuggestion, SearchInput

router = APIRouter(prefix="/api")


@router.post("/projects/{project_id}/queries:suggest")
async def suggest(project_id: str, db: Session = Depends(session), llm=Depends(get_llm)):
    project = projects.get(db, project_id)
    return await llm.generate("suggest_queries", {"direction": project.direction}, QuerySuggestion, project_id)


@router.post("/projects/{project_id}/searches")
async def search(project_id: str, payload: SearchInput, request: Request):
    return {"job_id": service.start_search(request.app, project_id, [q.model_dump() for q in payload.queries])}


@router.get("/projects/{project_id}/searches")
def list_searches(project_id: str, db: Session = Depends(session)):
    return [service.serialize(s) for s in service.searches(db, project_id)]


@router.get("/projects/{project_id}/evidence")
def list_evidence(project_id: str, db: Session = Depends(session)):
    return [service.serialize(card) for card in service.evidence(db, project_id)]


@router.patch("/evidence/{card_id}")
def update_evidence(card_id: str, payload: EvidencePatch, db: Session = Depends(session)):
    return service.serialize(service.patch(db, card_id, payload))
