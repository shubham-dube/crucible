"""Reporter output shape."""

from __future__ import annotations

import json

import pytest

from crucible.domain.findings import Finding, Location, Severity
from crucible.reporting import FindingsReport, get_reporter
from crucible.reporting.base import TargetFindings

FINDING = Finding(
    rule_id="topology/cycle-risk",
    severity=Severity.WARNING,
    message="cycle",
    agent="a",
    location=Location(file="n.hocon", agent="a", json_path="tools[1]"),
    remediation="break it",
)
REPORT = FindingsReport(targets=(TargetFindings(network="n", file="n.hocon", findings=(FINDING,)),))


def test_sarif_shape() -> None:
    sarif = json.loads(get_reporter("sarif").render(REPORT))
    assert sarif["version"] == "2.1.0"
    result = sarif["runs"][0]["results"][0]
    assert result["ruleId"] == "topology/cycle-risk"
    assert result["level"] == "warning"
    assert result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "n.hocon"
    assert sarif["runs"][0]["tool"]["driver"]["rules"][0]["id"] == "topology/cycle-risk"


def test_json_roundtrip() -> None:
    parsed = FindingsReport.model_validate_json(get_reporter("json").render(REPORT))
    assert parsed.all_findings == [FINDING]


def test_table_mentions_rule() -> None:
    assert "topology/cycle-risk" in get_reporter("table").render(REPORT)


def test_unknown_reporter() -> None:
    with pytest.raises(ValueError, match="unknown report format"):
        get_reporter("xml")


def test_junit_and_markdown() -> None:
    from xml.etree import ElementTree as ET

    error = FINDING.model_copy(update={"severity": Severity.ERROR, "scenario_id": "s1"})
    report = FindingsReport(targets=(TargetFindings(network="n", findings=(error, FINDING)),))
    root = ET.fromstring(get_reporter("junit").render(report))
    suite = root.find("testsuite")
    assert suite is not None
    assert suite.get("failures") == "1"
    assert len(suite.findall("testcase")) == 3
    markdown = get_reporter("markdown").render(report)
    assert "**1 error(s), 1 warning(s)**" in markdown
    assert "Remediation" in markdown
