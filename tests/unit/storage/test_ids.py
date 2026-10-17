"""Path-traversal protection for ids that become file names."""

from __future__ import annotations

from pathlib import Path

import pytest

from crucible.domain.errors import CrucibleError
from crucible.storage.audits import SqliteAuditRepository
from crucible.storage.ids import safe_id
from crucible.storage.run_store import FileRunStore


@pytest.mark.parametrize("bad", ["../etc/passwd", "a/b", "..", "", ".hidden", "x" * 200, "a\\b", "id with space"])
def test_rejects_unsafe_ids(bad: str) -> None:
    with pytest.raises(CrucibleError):
        safe_id(bad)


def test_accepts_generated_ids() -> None:
    assert safe_id("audit-20261017214429-f54199") == "audit-20261017214429-f54199"
    assert safe_id("batch-20261017-ab12.c3_d") == "batch-20261017-ab12.c3_d"


def test_stores_refuse_traversal(tmp_path: Path) -> None:
    (tmp_path / "secret.json").write_text("{}", encoding="utf-8")
    with pytest.raises(CrucibleError):
        SqliteAuditRepository(tmp_path / "home").get("../../secret")
    with pytest.raises(CrucibleError):
        FileRunStore(tmp_path / "home").load("../../x")
