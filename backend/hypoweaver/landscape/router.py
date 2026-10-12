from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..db import session
from ..literature.service import evidence, serialize
from .service import build_landscape

router = APIRouter(prefix="/api/projects")


@router.get("/{project_id}/landscape")
def landscape(project_id: str, db: Session = Depends(session)):
    return build_landscape([serialize(card) for card in evidence(db, project_id)])
