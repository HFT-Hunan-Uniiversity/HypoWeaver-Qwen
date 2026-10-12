import asyncio
from pathlib import Path
from sqlalchemy import select
from .. import jobs
from ..db import uid
from ..errors import AppError
from ..projects import service as projects
from ..literature.service import serialize
from .models import DatasetUpload, Dataset
from . import files


def get(db, dataset_id):
    item = db.get(Dataset, dataset_id)
    if not item:
        raise AppError("dataset_not_found", "数据资产不存在", 404)
    return item


def list_(db):
    return db.scalars(select(Dataset).order_by(Dataset.created_at.desc())).all()


def public(item):
    return {
        **{k: v for k, v in serialize(item).items() if k != "file_path"},
        "profile": [{"semantics": "unknown", "level": "other", **p} for p in item.profile],
    }


async def inspect_upload(app, upload):
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in {".csv", ".xlsx", ".dta"}:
        raise AppError("unsupported_file", "仅支持 .csv、.xlsx 和 .dta")
    files.check_storage(app.state.settings, files.MAX_FILE)
    directory = app.state.settings.storage_dir() / "staging"
    directory.mkdir(parents=True, exist_ok=True)
    upload_id = uid("upload")
    path = directory / (upload_id + suffix)
    size = 0
    with path.open("xb") as stream:
        while chunk := await upload.read(1024**2):
            size += len(chunk)
            if size > files.MAX_FILE:
                raise AppError("file_too_large", "文件超过 500 MB 上限；已读取片段保留，未导入")
            stream.write(chunk)
    metadata = await asyncio.to_thread(files.inspect, path)
    with app.state.sessions() as db:
        item = DatasetUpload(
            id=upload_id, name=Path(upload.filename).name, format=suffix[1:], file_path=str(path), metadata_=metadata
        )
        db.add(item)
        db.commit()
    return {"upload_id": upload_id, "name": item.name, **metadata}


def inspect_sheet(db, upload_id, sheet):
    upload = db.get(DatasetUpload, upload_id)
    if not upload:
        raise AppError("upload_not_found", "暂存文件不存在，请重新上传", 404)
    return {"upload_id": upload_id, "name": upload.name, **files.inspect(upload.file_path, sheet)}


def register(
    settings,
    db,
    frame,
    name,
    source,
    original_format="csv",
    sheet=None,
    labels=None,
    project_id=None,
    unit=None,
    time=None,
):
    files.check_storage(settings, int(frame.memory_usage(deep=True).sum()) * 3)
    if frame.empty or len(frame) > files.MAX_ROWS or len(frame.columns) > files.MAX_COLUMNS:
        raise AppError("dataset_limit", "数据尺寸超出导入范围")
    panel = files.panel_info(frame, unit, time)
    field_profile = files.profile(frame, labels)
    directory = settings.storage_dir() / "datasets"
    directory.mkdir(parents=True, exist_ok=True)
    dataset_id = uid("ds")
    path = directory / (dataset_id + ".csv")
    frame.to_csv(path, index=False)
    if path.stat().st_size > files.MAX_FILE:
        raise AppError("dataset_limit", "转换后的文件超过 500 MB，文件已保留但未登记")
    entity = Dataset(
        id=dataset_id,
        project_id=project_id,
        name=name,
        source=source,
        format=original_format,
        sheet=sheet,
        selected_columns=frame.columns.tolist(),
        file_path=str(path),
        size_bytes=path.stat().st_size,
        sha256=files.sha256(path),
        n_rows=len(frame),
        n_cols=len(frame.columns),
        panel=panel,
        profile=field_profile,
    )
    db.add(entity)
    db.commit()
    return entity


def import_(app, payload):
    with app.state.sessions() as db:
        projects.get(db, payload.project_id)
        upload = db.get(DatasetUpload, payload.upload_id)
        if not upload:
            raise AppError("upload_not_found", "暂存文件不存在，请重新上传", 404)
        path, original_format = upload.file_path, upload.format
    metadata = files.inspect(path, payload.sheet)
    labels = {c["name"]: c["label"] for c in metadata["columns"]}
    if not set(payload.columns) <= set(labels):
        raise AppError("columns_missing", "所选字段不在当前工作表中")

    def work_sync(progress):
        progress("正在读取所选列并建立字段档案")
        frame = files.read_selected(path, payload.columns, payload.sheet)
        with app.state.sessions() as db:
            entity = register(
                app.state.settings,
                db,
                frame,
                payload.name,
                payload.source.model_dump(),
                original_format,
                payload.sheet,
                labels,
                payload.project_id,
                payload.unit,
                payload.time,
            )
            return {"dataset_id": entity.id}

    async def work(progress):
        return await asyncio.to_thread(work_sync, progress)

    return jobs.submit(app, "dataset", payload.project_id, work)


def update(db, dataset_id, payload):
    item = get(db, dataset_id)
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(item, key, value)
    invalidate_dependents(db, item)
    db.commit()
    return item


def invalidate_dependents(db, item):
    dataset_id = item.id
    from ..staleness import invalidate
    from ..binding.models import VariableBinding
    from ..plans.models import StudyPlan
    from ..stats.models import AnalysisRun

    projects = set(
        db.scalars(
            select(StudyPlan.project_id)
            .join(VariableBinding, VariableBinding.plan_id == StudyPlan.id)
            .where(VariableBinding.dataset_id == dataset_id)
        ).all()
    )
    projects.update(db.scalars(select(AnalysisRun.project_id).where(AnalysisRun.dataset_id == dataset_id)).all())
    if item.project_id:
        projects.add(item.project_id)
    for project_id in projects:
        invalidate(db, project_id, "data")


def frame(db, dataset_id):
    import pandas as pd

    item = get(db, dataset_id)
    # Preserve textual identifiers including leading zeroes across CSV persistence.
    types = {p["name"]: "str" for p in item.profile if p["type"] in {"str", "object", "string"}}
    return pd.read_csv(item.file_path, dtype=types)


def update_field(db, dataset_id, field_name, payload):
    item = get(db, dataset_id)
    if field_name not in {p["name"] for p in item.profile}:
        raise AppError("field_not_found", "字段不存在", 404)
    changes = payload.model_dump(exclude_none=True)
    profile = [{**p, **changes} if p["name"] == field_name else p for p in item.profile]
    if profile != item.profile:
        item.profile = profile
        invalidate_dependents(db, item)
        db.commit()
    return item
