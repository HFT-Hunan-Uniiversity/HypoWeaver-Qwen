import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .config import ROOT, Settings
from .db import Base, create_database
from .errors import AppError, install
from . import jobs
from .llm.router import router as llm_router
from .llm.service import LLM
from .projects.router import router as projects_router


def create_app(settings=None):
    settings = settings or Settings()
    engine, sessions = create_database(settings.storage_dir() / "hypoweaver.sqlite")

    @asynccontextmanager
    async def lifespan(app):
        Base.metadata.create_all(engine)
        jobs.recover(sessions)
        yield
        tasks = list(app.state.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        engine.dispose()

    app = FastAPI(title="HypoWeaver v2", lifespan=lifespan)
    app.state.settings = settings
    app.state.sessions = sessions
    app.state.tasks = set()
    app.state.llm = LLM(settings, sessions)
    install(app)
    app.include_router(projects_router)
    app.include_router(jobs.router)
    app.include_router(llm_router)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    dist = ROOT / "frontend" / "dist"
    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/") or not (dist / "index.html").exists():
            raise AppError("not_found", "页面不存在", 404)
        return FileResponse(dist / "index.html")

    return app


app = create_app()
