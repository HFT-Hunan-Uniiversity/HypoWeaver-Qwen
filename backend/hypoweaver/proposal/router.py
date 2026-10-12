from fastapi import APIRouter,Depends,Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from ..db import session
from ..llm.service import get_llm
from . import service
from .models import SectionEdit
from .rendering import render_markdown
router=APIRouter(prefix='/api')

@router.post('/projects/{project_id}/proposals')
async def start(project_id:str,request:Request,llm=Depends(get_llm)):
    return {'job_id':service.start(request.app,project_id,llm)}

@router.get('/projects/{project_id}/proposals')
def list_(project_id:str,db:Session=Depends(session)):
    return service.list_(db,project_id)

@router.get('/proposals/{identifier}.md')
def download(identifier:str,db:Session=Depends(session)):
    return Response(render_markdown(service.get(db,identifier)),media_type='text/markdown; charset=utf-8',headers={'Content-Disposition':'attachment; filename="research-proposal.md"'})

@router.get('/proposals/{identifier}')
def get(identifier:str,db:Session=Depends(session)):
    return service.public(service.get(db,identifier))

@router.patch('/proposals/{identifier}/sections/{key}')
def edit(identifier:str,key:str,payload:SectionEdit,db:Session=Depends(session)):
    return service.edit(db,identifier,key,payload)
