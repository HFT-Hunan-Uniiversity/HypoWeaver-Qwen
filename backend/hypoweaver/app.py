import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .config import ROOT, Settings
from .db import Base, create_database
from .errors import AppError, install
from .landscape.router import router as landscape_router
from .literature.router import router as literature_router
from .literature import service as literature_service
from .literature.sources import LiteratureClient
from .claims.router import router as claims_router
from .stats.router import router as stats_router
from .stats import service as stats_service
from .binding.router import router as binding_router
from .datasets.router import router as datasets_router
from .plans.router import router as plans_router
from . import jobs
from .candidates import service as candidates_service
from .candidates.router import router as candidates_router
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
        literature_service.recover(sessions)
        candidates_service.recover(sessions)
        stats_service.recover(sessions)
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
    app.state.literature_client = LiteratureClient(settings)
    app.state.llm = LLM(settings, sessions)
    install(app)
    app.include_router(projects_router)
    app.include_router(jobs.router)
    app.include_router(jobs.project_router)
    app.include_router(llm_router)
    app.include_router(literature_router)
    app.include_router(landscape_router)
    app.include_router(candidates_router)
    app.include_router(plans_router)
    app.include_router(datasets_router)
    app.include_router(binding_router)
    app.include_router(stats_router)
    app.include_router(claims_router)

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
