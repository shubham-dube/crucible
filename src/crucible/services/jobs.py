"""Background jobs: a queue port, an in-process worker and a SQLite job store.

Jobs run one at a time per process because in-process prompt capture is process-global (ADR 0002); scale out with
more worker processes behind a shared queue implementation of ``JobQueue``.
"""

from __future__ import annotations

import json
import queue
import sqlite3
import threading
import traceback
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

import structlog
from pydantic import BaseModel, ConfigDict, Field

from crucible.execution.runner import new_id

log = structlog.get_logger(__name__)


class JobKind(StrEnum):
    """What a job does."""

    AUDIT = "audit"
    AGENTIC = "agentic"
    FIX = "fix"
    BENCH = "bench"


class JobStatus(StrEnum):
    """Lifecycle."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class JobRecord(BaseModel):
    """A job and its outcome."""

    model_config = ConfigDict(frozen=True)

    id: str
    kind: JobKind
    status: JobStatus = JobStatus.QUEUED
    params: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    started_at: str | None = None
    finished_at: str | None = None


Emit = Callable[[dict[str, Any]], None]
Handler = Callable[[JobRecord, Emit], dict[str, Any]]


class JobStore:
    """SQLite persistence for job records (same database file as audits)."""

    def __init__(self, home: str | Path) -> None:
        self.path = Path(home) / "crucible.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, created_at TEXT, body TEXT NOT NULL)")

    @contextmanager
    def _conn(self) -> Any:
        conn = sqlite3.connect(self.path, timeout=30)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn
            conn.commit()
        finally:
            conn.close()

    def put(self, job: JobRecord) -> None:
        """Insert or update."""
        with self._conn() as conn:
            conn.execute("INSERT OR REPLACE INTO jobs VALUES (?,?,?)", (job.id, job.created_at, job.model_dump_json()))

    def get(self, job_id: str) -> JobRecord | None:
        """Fetch a job."""
        with self._conn() as conn:
            row = conn.execute("SELECT body FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return JobRecord.model_validate_json(row[0]) if row else None

    def list(self, limit: int = 50) -> list[JobRecord]:
        """Newest first."""
        with self._conn() as conn:
            rows = conn.execute("SELECT body FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [JobRecord.model_validate_json(r[0]) for r in rows]


class JobQueue(Protocol):
    """Submit jobs and observe them."""

    def submit(self, kind: JobKind, params: dict[str, Any]) -> JobRecord:
        """Enqueue a job."""
        ...

    def events(self, job_id: str, after: int = 0) -> list[dict[str, Any]]:
        """Progress events emitted so far (index > after)."""
        ...


class InProcessJobQueue:
    """Single worker thread; events kept in memory (bounded), records persisted in the JobStore."""

    MAX_EVENTS = 2000

    def __init__(self, store: JobStore, handlers: dict[JobKind, Handler]) -> None:
        self.store = store
        self.handlers = handlers
        self._queue: queue.Queue[str] = queue.Queue()
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._work, name="crucible-worker", daemon=True)
        self._thread.start()

    def submit(self, kind: JobKind, params: dict[str, Any]) -> JobRecord:
        job = JobRecord(id=new_id("job"), kind=kind, params=params)
        self.store.put(job)
        with self._lock:
            self._events[job.id] = [{"type": "queued", "job": job.id}]
        self._queue.put(job.id)
        return job

    def events(self, job_id: str, after: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events.get(job_id, [])[after:])

    def _emit(self, job_id: str) -> Emit:
        def emit(event: dict[str, Any]) -> None:
            with self._lock:
                bucket = self._events.setdefault(job_id, [])
                if len(bucket) < self.MAX_EVENTS:
                    bucket.append(event)

        return emit

    def _work(self) -> None:
        while True:
            job_id = self._queue.get()
            job = self.store.get(job_id)
            if job is None:
                continue
            emit = self._emit(job_id)
            job = job.model_copy(update={"status": JobStatus.RUNNING, "started_at": datetime.now(UTC).isoformat()})
            self.store.put(job)
            emit({"type": "started", "job": job_id})
            try:
                result = self.handlers[job.kind](job, emit)
                job = job.model_copy(update={"status": JobStatus.SUCCEEDED, "result": json.loads(json.dumps(result))})
            except Exception as exc:  # a failing job must never kill the worker
                log.error("job failed", job=job_id, error=str(exc))
                job = job.model_copy(
                    update={"status": JobStatus.FAILED, "error": f"{type(exc).__name__}: {exc}"[:2000]}
                )
                emit({"type": "error", "message": job.error, "trace": traceback.format_exc()[-1500:]})
            job = job.model_copy(update={"finished_at": datetime.now(UTC).isoformat()})
            self.store.put(job)
            emit({"type": "finished", "job": job_id, "status": job.status.value})
