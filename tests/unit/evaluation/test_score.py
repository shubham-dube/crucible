"""Benchmark scoring against ground truth."""

from __future__ import annotations

from crucible.domain.findings import Finding, Severity
from crucible.domain.scenario import ExpectedFindings
from crucible.evaluation.benchmark import score


def finding(rule_id: str, agent: str | None = None, scenario: str | None = None) -> Finding:
    return Finding(rule_id=rule_id, severity=Severity.WARNING, message="m", agent=agent, scenario_id=scenario)


def test_allowed_findings_are_neither_required_nor_false_positives() -> None:
    expected = ExpectedFindings.model_validate(
        {
            "findings": [{"rule_id": "a/required", "agent": "x"}],
            "allowed": [{"rule_id": "b/maybe", "agent": "y"}],
            "must_not": ["c/never"],
        }
    )
    result = score("t", expected, [finding("a/required", "x"), finding("b/maybe", "y"), finding("d/other")])
    assert result.missed == ()
    assert result.true_positives == 1
    assert [f.rule_id for f in result.false_positives] == ["d/other"]
    assert score("t", expected, [finding("a/required", "x")]).false_positives == ()
