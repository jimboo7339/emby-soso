from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.dashboard import router as dashboard_router
from app.api.health import router as health_router
from app.api.router import router as resource_router
from app.api.settings import router as settings_router
from app.core.config import get_settings
from app.core.scheduler import shutdown_scheduler, start_scheduler
from app.services.task_runner import recover_stale_task_runs

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logging.basicConfig(level=settings.log_level.upper())
    recovered = recover_stale_task_runs()
    if recovered:
        logger.warning("Recovered %d stale task run(s) stuck in running", recovered)
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

api = FastAPI()
api.include_router(health_router)
api.include_router(dashboard_router)
api.include_router(settings_router)
api.include_router(resource_router)

app.mount("/api/v1", api)


static_dir = Path(settings.static_dir)
if static_dir.exists():
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/")
    async def spa_index():
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Frontend not built")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")

        candidate = static_dir / full_path
        if candidate.is_file():
            return FileResponse(candidate)

        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Frontend not built")
else:
    @app.get("/")
    async def root():
        return {
            "app": settings.app_name,
            "message": "API is running. Build frontend to enable SPA.",
            "docs": "/docs",
        }
