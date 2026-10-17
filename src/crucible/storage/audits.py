"""Audit persistence: SQLite index + JSON blobs, behind a repository port."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from crucible.domain.audit import TargetAudit
from crucible.domain.errors import CrucibleError
from crucible.storage.ids import safe_id

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audits (
    id TEXT PRIMARY KEY,
    target TEXT NOT NULL,
    network_path TEXT,
    config_hash TEXT,
    created_at TEXT NOT NULL,
    errors INTEGER NOT NULL,
    warnings INTEGER NOT NULL,
    runs INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS audits_target ON audits(target, created_at);
CREATE TABLE IF NOT EXISTS findings (
    audit_id TEXT NOT NULL REFERENCES audits(id) ON DELETE CASCADE,
    fingerprint TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    agent TEXT,
    scenario_id TEXT,
    message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS findings_audit ON findings(audit_id);
CREATE TABLE IF NOT EXISTS baselines (
    target TEXT NOT NULL,
    label TEXT NOT NULL,
    audit_id TEXT NOT NULL REFERENCES audits(id),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (target, label)
);
"""


class AuditRecord(BaseModel):
    """Index row for an audit."""

    model_config = ConfigDict(frozen=True)

    id: str
    target: str
    created_at: str
    errors: int
    warnings: int
    runs: int
    config_hash: str | None = None


class AuditRepository(Protocol):
    """Stores audits and baselines."""

    def save(self, audit_id: str, audit: TargetAudit) -> None:
        """Persist an audit under ``audit_id``."""
        ...

    def get(self, audit_id: str) -> TargetAudit:
        """Load an audit."""
        ...

    def list(self, target: str | None = None, limit: int = 50) -> list[AuditRecord]:
        """Newest first."""
        ...

    def set_baseline(self, target: str, label: str, audit_id: str) -> None:
        """Point ``label`` for ``target`` at an audit."""
        ...

    def baseline(self, target: str, label: str) -> str | None:
        """Audit id of a baseline, if set."""
        ...


class SqliteAuditRepository:
    """SQLite index at ``<home>/crucible.db`` with audit JSON blobs in ``<home>/audits``."""

    def __init__(self, home: str | Path) -> None:
        self.home = Path(home)
        self.blobs = self.home / "audits"
        self.blobs.mkdir(parents=True, exist_ok=True)
        self.db_path = self.home / "crucible.db"
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=30)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
            conn.commit()
        finally:
            conn.close()

    def save(self, audit_id: str, audit: TargetAudit) -> None:
        safe_id(audit_id, "audit")
        tmp = self.blobs / f"{audit_id}.json.tmp"
        tmp.write_text(audit.model_dump_json(), encoding="utf-8")
        tmp.replace(self.blobs / f"{audit_id}.json")
        findings = audit.findings
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO audits VALUES (?,?,?,?,?,?,?,?)",
                (
                    audit_id,
                    audit.target,
                    audit.network_path,
                    audit.batch.config_hash if audit.batch else None,
                    datetime.now(UTC).isoformat(),
                    sum(f.severity.value == "error" for f in findings),
                    sum(f.severity.value == "warning" for f in findings),
                    len(audit.batch.runs) if audit.batch else 0,
                ),
            )
            conn.execute("DELETE FROM findings WHERE audit_id = ?", (audit_id,))
            conn.executemany(
                "INSERT INTO findings VALUES (?,?,?,?,?,?,?)",
                [
                    (audit_id, f.fingerprint, f.rule_id, f.severity.value, f.agent, f.scenario_id, f.message)
                    for f in findings
                ],
            )

    def get(self, audit_id: str) -> TargetAudit:
        safe_id(audit_id, "audit")
        path = self.blobs / f"{audit_id}.json"
        if not path.is_file():
            raise CrucibleError(f"unknown audit '{audit_id}' in {self.home}")
        return TargetAudit.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self, target: str | None = None, limit: int = 50) -> list[AuditRecord]:
        query = "SELECT id, target, created_at, errors, warnings, runs, config_hash FROM audits"
        params: tuple[object, ...] = ()
        if target:
            query += " WHERE target = ?"
            params = (target,)
        query += " ORDER BY created_at DESC LIMIT ?"
        with self._conn() as conn:
            rows = conn.execute(query, (*params, limit)).fetchall()
        keys = ("id", "target", "created_at", "errors", "warnings", "runs", "config_hash")
        return [AuditRecord.model_validate(dict(zip(keys, row, strict=True))) for row in rows]

    def set_baseline(self, target: str, label: str, audit_id: str) -> None:
        self.get(audit_id)  # must exist
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO baselines VALUES (?,?,?,?)",
                (target, label, audit_id, datetime.now(UTC).isoformat()),
            )

    def baseline(self, target: str, label: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT audit_id FROM baselines WHERE target = ? AND label = ?", (target, label)
            ).fetchone()
        return str(row[0]) if row else None
