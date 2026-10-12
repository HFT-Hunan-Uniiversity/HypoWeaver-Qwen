from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session
from ..db import session
from .models import Decision
from . import service
router=APIRouter(prefix='/api')

@router.get('/runs/{run_id}/claims')
def list_(run_id:str,db:Session=Depends(session)):
    return service.list_(db,run_id)

@router.patch('/claims/{run_id}/{claim_id}')
def patch(run_id:str,claim_id:str,payload:Decision,db:Session=Depends(session)):
    return service.decide(db,run_id,claim_id,payload)
