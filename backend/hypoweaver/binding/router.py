from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..db import session
from ..llm.service import get_llm
from . import service
from .models import BindingInput

router = APIRouter(prefix="/api/plans")


class SuggestInput(BaseModel):
    dataset_id: str


@router.post("/{plan_id}/bindings:suggest")
async def suggest(plan_id: str, payload: SuggestInput, db: Session = Depends(session), llm=Depends(get_llm)):
    return await service.suggest(db, plan_id, payload.dataset_id, llm)


@router.get("/{plan_id}/bindings")
def get(plan_id: str, db: Session = Depends(session)):
    return service.get(db, plan_id)


@router.put("/{plan_id}/bindings")
def update(plan_id: str, payload: BindingInput, db: Session = Depends(session)):
    return service.save(db, plan_id, payload)


@router.get("/{plan_id}/readiness")
def readiness(plan_id: str, db: Session = Depends(session)):
    return service.readiness(db, plan_id)
