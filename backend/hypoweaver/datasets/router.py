from fastapi import APIRouter, Depends, Request, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy import select
from ..db import session
from . import service
from .models import ImportInput, DatasetPatch, DatasetUpload, FieldPatch

router = APIRouter(prefix="/api")


@router.post("/datasets:inspect")
async def inspect(file: UploadFile, request: Request):
    return await service.inspect_upload(request.app, file)


@router.get("/dataset-uploads")
def uploads(db: Session = Depends(session)):
    return [
        {"upload_id": u.id, "name": u.name, **u.metadata_}
        for u in db.scalars(select(DatasetUpload).order_by(DatasetUpload.created_at.desc()).limit(50)).all()
    ]


@router.get("/dataset-uploads/{upload_id}")
def sheet(upload_id: str, sheet: str, db: Session = Depends(session)):
    return service.inspect_sheet(db, upload_id, sheet)


@router.post("/datasets")
async def import_dataset(payload: ImportInput, request: Request):
    return {"job_id": service.import_(request.app, payload)}


@router.get("/datasets")
def list_datasets(db: Session = Depends(session)):
    return [service.public(d) for d in service.list_(db)]


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: str, db: Session = Depends(session)):
    return service.public(service.get(db, dataset_id))


@router.patch("/datasets/{dataset_id}")
def update(dataset_id: str, payload: DatasetPatch, db: Session = Depends(session)):
    return service.public(service.update(db, dataset_id, payload))


@router.patch("/datasets/{dataset_id}/fields/{field_name}")
def update_field(dataset_id: str, field_name: str, payload: FieldPatch, db: Session = Depends(session)):
    return service.public(service.update_field(db, dataset_id, field_name, payload))
