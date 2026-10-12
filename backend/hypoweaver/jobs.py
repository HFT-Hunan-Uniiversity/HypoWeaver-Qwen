import asyncio
import logging
import traceback
from fastapi import APIRouter, Depends, Request
from sqlalchemy import ForeignKey, JSON, select, update
from sqlalchemy.orm import Mapped, Session, mapped_column
from .db import Base, now, session, uid
from .errors import AppError


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: uid("job"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    kind: Mapped[str]
    status: Mapped[str] = mapped_column(default="queued")
    progress_text: Mapped[str] = mapped_column(default="等待执行")
    error: Mapped[str | None]
    result: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(default=now)
    started_at: Mapped[str | None]
    finished_at: Mapped[str | None]


def get(db, job_id):
    job = db.get(Job, job_id)
    if not job:
        raise AppError("job_not_found", "后台任务不存在", 404)
    return {column.name: getattr(job, column.name) for column in Job.__table__.columns}


def recover(sessions):
    with sessions() as db:
        db.execute(update(Job).where(Job.status.in_(["queued", "running"])).values(
            status="failed", error="服务重启中断了执行，请重新发起此步骤", finished_at=now()))
        db.commit()


def submit(app, kind, project_id, fn):
    """fn(progress) is async; expensive synchronous work must use asyncio.to_thread."""
    with app.state.sessions() as db:
        job = Job(project_id=project_id, kind=kind)
        db.add(job)
        db.commit()
        job_id = job.id

    def write(**fields):
        with app.state.sessions() as db:
            db.execute(update(Job).where(Job.id == job_id).values(**fields))
            db.commit()

    def progress(message):
        write(progress_text=message)

    async def execute():
        write(status="running", started_at=now())
        try:
            result = await fn(progress)
            write(status="succeeded", progress_text="已完成", result=result or {}, finished_at=now())
        except asyncio.CancelledError:
            write(status="failed", error="服务停止中断了执行，请重试", finished_at=now())
            raise
        except Exception as exc:
            detail = str(exc)
            secret = app.state.settings.dashscope_api_key
            if secret:
                detail = detail.replace(secret, "[redacted]")
            logging.getLogger(__name__).error("Task %s (%s): %s: %s\n%s", job_id, kind,
                                             type(exc).__name__, detail[:500], "".join(traceback.format_tb(exc.__traceback__)))
            message = exc.message if isinstance(exc, AppError) else f"执行失败（{type(exc).__name__}），请检查输入后重试"
            write(status="failed", error=message, finished_at=now())

    task = asyncio.create_task(execute())
    app.state.tasks.add(task)
    task.add_done_callback(app.state.tasks.discard)
    return job_id


router = APIRouter(prefix="/api/jobs")


@router.get("/{job_id}")
def get_job(job_id: str, db: Session = Depends(session)):
    return get(db, job_id)
