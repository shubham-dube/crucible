"""Per-application state shared by routers (set by the app factory)."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request

from crucible.config.project import Project
from crucible.interfaces.api.settings import ApiSettings
from crucible.services.jobs import JobQueue, JobStore
from crucible.storage.audits import SqliteAuditRepository


@dataclass
class AppState:
    """Everything a request handler needs."""

    settings: ApiSettings
    repo: SqliteAuditRepository
    store: JobStore
    jobs: JobQueue

    def project(self, name: str) -> Project:
        """Registered project by name (404 if unknown)."""
        registry = self.settings.project_map()
        if name not in registry:
            raise HTTPException(status_code=404, detail=f"unknown project '{name}'")
        return Project.load(registry[name])


def get_state(request: Request) -> AppState:
    """FastAPI dependency."""
    state: AppState = request.app.state.crucible
    return state
