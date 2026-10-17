"""Regression diff semantics."""

from __future__ import annotations

from crucible.domain.audit import TargetAudit
from crucible.domain.findings import Finding, Severity
from crucible.domain.trace import RunBatch, RunResult, Span, SpanKind, TokenUsage
from crucible.regression.diff import diff


def _finding(rule: str, severity: Severity = Severity.ERROR) -> Finding:
    return Finding(rule_id=rule, severity=severity, message=rule, agent="a", scenario_id="s")


def _run(tokens: int, seconds: float, delegations: int) -> RunResult:
    spans = tuple(Span(id=f"s{i}", seq=i, kind=SpanKind.DELEGATION, agent="f", target="a") for i in range(delegations))
    return RunResult(
        run_id="r", target="t", scenario_id="s", tokens=TokenUsage(total=tokens), duration_s=seconds, spans=spans
    )


def _audit(findings: list[Finding], run: RunResult) -> TargetAudit:
    batch = RunBatch(batch_id="b", target="t", started_at="x", runs=(run,))
    return TargetAudit(target="t", network_path="n", runtime_findings=tuple(findings), batch=batch)


def test_new_fixed_persisting() -> None:
    base = _audit([_finding("x/old"), _finding("x/kept")], _run(100, 1.0, 1))
    cur = _audit([_finding("x/kept"), _finding("x/new", Severity.WARNING)], _run(100, 1.0, 1))
    result = diff(base, cur)
    assert [f.rule_id for f in result.new] == ["x/new"]
    assert [f.rule_id for f in result.fixed] == ["x/old"]
    assert [f.rule_id for f in result.persisting] == ["x/kept"]
    assert not result.fails(Severity.ERROR)
    assert result.fails(Severity.WARNING)
    assert not result.fails(None)
    assert "1 new" in result.to_markdown()


def test_metric_regressions_need_relative_and_absolute_growth() -> None:
    base = _audit([], _run(1000, 1.0, 2))
    small = diff(base, _audit([], _run(1100, 1.5, 3)))
    assert small.metric_regressions == ()
    big = diff(base, _audit([], _run(2000, 5.0, 10)))
    assert {m.metric for m in big.metric_regressions} == {"tokens", "latency_s", "delegations"}
    assert big.fails(Severity.ERROR)
    assert "Metric regressions" in big.to_markdown()
