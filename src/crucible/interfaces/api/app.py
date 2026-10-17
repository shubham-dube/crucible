"""Crucible HTTP API application factory."""

from __future__ import annotations

import hmac
from typing import Annotated

import structlog
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from crucible import __version__
from crucible.domain.errors import CrucibleError
from crucible.interfaces.api.routes import audits, jobs, projects
from crucible.interfaces.api.settings import ApiSettings
from crucible.interfaces.api.state import AppState
from crucible.services.jobs import InProcessJobQueue, JobQueue, JobStore
from crucible.storage.audits import SqliteAuditRepository

log = structlog.get_logger(__name__)


def create_app(settings: ApiSettings | None = None, queue: JobQueue | None = None) -> FastAPI:
    """Build the app; tests inject settings and/or a job queue."""
    cfg = settings or ApiSettings()
    cfg.home.mkdir(parents=True, exist_ok=True)
    store = JobStore(cfg.home)
    if queue is None:
        from crucible.services.job_handlers import build_handlers

        queue = InProcessJobQueue(store, build_handlers(cfg.home, cfg.project_map))
    keys = cfg.keys()
    if not keys:
        log.warning("CRUCIBLE_API_KEYS is empty: API authentication is DISABLED (development only)")

    def require_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
        if keys and not any(hmac.compare_digest(x_api_key or "", k) for k in keys):
            raise HTTPException(status_code=401, detail="missing or invalid X-API-Key")

    app = FastAPI(
        title="Crucible API", version=__version__, description="Chaos, fuzz and regression QA for agent networks."
    )
    app.state.crucible = AppState(settings=cfg, repo=SqliteAuditRepository(cfg.home), store=store, jobs=queue)
    app.add_middleware(CORSMiddleware, allow_origins=cfg.origins(), allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(CrucibleError)
    async def crucible_error(_: Request, exc: CrucibleError) -> JSONResponse:
        return JSONResponse(status_code=404 if "unknown" in str(exc) else 400, content={"detail": str(exc)})

    @app.get("/v1/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    for router in (projects, audits, jobs):
        app.include_router(router, prefix="/v1", dependencies=[Depends(require_key)])
    return app
