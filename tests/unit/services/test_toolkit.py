"""Toolkit functions behind Crucible's agent tools (no Neuro-SAN execution)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from crucible.domain.errors import ConfigError
from crucible.domain.findings import Evidence, Finding, Severity
from crucible.services import toolkit
from crucible.services.audit import TargetAudit

FINDING = Finding(
    rule_id="leak/sly-data-exposure",
    severity=Severity.ERROR,
    message="leaked national_id",
    agent="profile_lookup",
    evidence=(Evidence(kind="span", ref="s3", excerpt="id SYN***"),),
    scenario_id="plan-question",
)


def test_finding_id_is_stable() -> None:
    assert toolkit.finding_id(FINDING) == toolkit.finding_id(FINDING.model_copy())
    assert len(toolkit.finding_id(FINDING)) == 8


@pytest.mark.usefixtures("crucible_home")
def test_save_scenarios_validates_and_dedupes() -> None:
    good = {"id": "edge-1", "interactions": [{"text": "hi"}], "expect": {"route": ["a"]}}
    bad = {"id": "broken", "interactions": "not-a-list"}
    first = toolkit.save_scenarios("t", json.dumps([good, bad]))
    assert first["saved"] == ["edge-1"]
    assert first["rejected"][0]["id"] == "broken"
    again = toolkit.save_scenarios("t", [good])
    assert again["rejected"] == [{"id": "edge-1", "reason": "duplicate id"}]
    suite = toolkit.load_generated("t")
    assert [s.id for s in suite.scenarios] == ["edge-1"]
    assert suite.scenarios[0].source.value == "generated"
    assert toolkit.save_scenarios("t", "42")["rejected"]


def test_audit_lookup_evidence_leaks_and_report(crucible_home: Path) -> None:
    audit = TargetAudit(target="account_leak", network_path="n.hocon", runtime_findings=(FINDING,))
    toolkit._AUDITS["audit-x"] = audit
    fid = toolkit.finding_id(FINDING)
    evidence = toolkit.finding_evidence("audit-x", fid)
    assert evidence["finding"]["rule"] == "leak/sly-data-exposure"
    assert evidence["evidence"][0]["excerpt"] == "id SYN***"
    assert "error" in toolkit.finding_evidence("audit-x", "nope")
    assert toolkit.leak_report("audit-x")["leaks"][0]["agent"] == "profile_lookup"
    report = toolkit.render_report(["audit-x"], "markdown", "Top issue: a leak.")
    text = Path(report["path"]).read_text()
    assert text.startswith("# Crucible audit report")
    assert "## Executive summary" in text
    assert report["path"].startswith(str(crucible_home))
    with pytest.raises(ConfigError):
        toolkit.get_audit("audit-missing")


def test_regression_diff_tool(crucible_home: Path) -> None:
    repo = toolkit.repository()
    base = TargetAudit(target="t", network_path="n", runtime_findings=(FINDING,))
    repo.save("audit-base", base)
    current = TargetAudit(target="t", network_path="n")
    repo.save("audit-cur", current)
    assert toolkit.regression_diff("audit-cur")["baseline"] is None
    repo.set_baseline("t", "main", "audit-base")
    result = toolkit.regression_diff("audit-cur")
    assert result["baseline"] == "audit-base"
    assert result["new"] == []
    assert [f["rule"] for f in result["fixed"]] == ["leak/sly-data-exposure"]
