from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from ..db import session
from . import service
from .models import ProjectCreate, ProjectOut, ProjectPatch

router = APIRouter(prefix="/api/projects")


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(session)):
    return service.list_(db)


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(payload: ProjectCreate, db: Session = Depends(session)):
    return service.create(db, payload)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, db: Session = Depends(session)):
    return service.get(db, project_id)


@router.patch("/{project_id}")
def update_project(project_id: str, payload: ProjectPatch, db: Session = Depends(session)):
    project = service.update(db, project_id, payload)
    return {"project": ProjectOut.model_validate(project), "affected": []}


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(session)):
    service.delete(db, project_id)
    return Response(status_code=204)


@router.get("/{project_id}/overview")
def overview(project_id: str, db: Session = Depends(session)):
    project = service.get(db, project_id)
    return {"project": ProjectOut.model_validate(project), "stages": service.stage_status(project)}
