"""File-based store for run batches: ``<home>/runs/<batch_id>/batch.json``."""

from __future__ import annotations

from pathlib import Path

from crucible.domain.errors import CrucibleError
from crucible.domain.trace import RunBatch
from crucible.storage.ids import safe_id


class FileRunStore:
    """Persist and load ``RunBatch`` objects as JSON."""

    def __init__(self, home: str | Path) -> None:
        self.root = Path(home) / "runs"

    def save(self, batch: RunBatch) -> Path:
        """Write a batch; returns its directory."""
        directory = self.root / safe_id(batch.batch_id, "batch")
        directory.mkdir(parents=True, exist_ok=True)
        tmp = directory / "batch.json.tmp"
        tmp.write_text(batch.model_dump_json(indent=1), encoding="utf-8")
        tmp.replace(directory / "batch.json")  # atomic: a crash never leaves a half-written batch
        return directory

    def load(self, batch_id: str) -> RunBatch:
        """Read a batch by id."""
        path = self.root / safe_id(batch_id, "batch") / "batch.json"
        if not path.is_file():
            raise CrucibleError(f"unknown batch '{batch_id}' in {self.root}")
        return RunBatch.model_validate_json(path.read_text(encoding="utf-8"))

    def list_ids(self) -> list[str]:
        """Batch ids, newest first."""
        if not self.root.is_dir():
            return []
        return sorted((p.name for p in self.root.iterdir() if (p / "batch.json").is_file()), reverse=True)
