"""SQLite audit repository."""

from __future__ import annotations

from pathlib import Path

import pytest

from crucible.domain.audit import TargetAudit
from crucible.domain.errors import CrucibleError
from crucible.domain.findings import Finding, Severity
from crucible.storage.audits import SqliteAuditRepository


def _audit(target: str, *rules: str) -> TargetAudit:
    findings = tuple(Finding(rule_id=r, severity=Severity.ERROR, message=r, agent="a") for r in rules)
    return TargetAudit(target=target, network_path="n.hocon", runtime_findings=findings)


def test_save_get_list_and_baselines(tmp_path: Path) -> None:
    repo = SqliteAuditRepository(tmp_path)
    repo.save("audit-1", _audit("t", "x/one"))
    repo.save("audit-2", _audit("t", "x/one", "x/two"))
    repo.save("audit-3", _audit("other"))
    assert repo.get("audit-2").findings[1].rule_id in {"x/one", "x/two"}
    assert [r.id for r in repo.list("t")] == ["audit-2", "audit-1"]
    assert repo.list("t")[0].errors == 2
    assert len(repo.list()) == 3
    assert repo.baseline("t", "main") is None
    repo.set_baseline("t", "main", "audit-1")
    repo.set_baseline("t", "main", "audit-2")
    assert repo.baseline("t", "main") == "audit-2"
    with pytest.raises(CrucibleError):
        repo.set_baseline("t", "main", "audit-missing")
    with pytest.raises(CrucibleError):
        repo.get("nope")


def test_resave_replaces_findings(tmp_path: Path) -> None:
    repo = SqliteAuditRepository(tmp_path)
    repo.save("a", _audit("t", "x/one", "x/two"))
    repo.save("a", _audit("t"))
    assert repo.list("t")[0].errors == 0
