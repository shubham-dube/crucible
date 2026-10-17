"""Score Crucible against benchmark ground truth (the bug zoo): recall, precision, false positives."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from crucible.domain.findings import Finding, Severity
from crucible.domain.scenario import ExpectedFinding, ExpectedFindings
from crucible.services.audit import AuditOptions, AuditService


def matches(expected: ExpectedFinding, finding: Finding) -> bool:
    """Rule id must match; agent and scenario only when the expectation names them."""
    return (
        expected.rule_id == finding.rule_id
        and (expected.agent is None or expected.agent == finding.agent)
        and (expected.scenario is None or expected.scenario == finding.scenario_id)
    )


class TargetScore(BaseModel):
    """Benchmark result for one target."""

    model_config = ConfigDict(frozen=True)

    target: str
    expected: tuple[ExpectedFinding, ...]
    detected: tuple[ExpectedFinding, ...]
    missed: tuple[ExpectedFinding, ...]
    true_positives: int
    false_positives: tuple[Finding, ...]
    must_not_violations: tuple[Finding, ...]


class BenchmarkReport(BaseModel):
    """Aggregate benchmark result."""

    model_config = ConfigDict(frozen=True)

    targets: tuple[TargetScore, ...]

    @property
    def recall(self) -> float:
        """Detected expected findings / all expected findings."""
        expected = sum(len(t.expected) for t in self.targets)
        return sum(len(t.detected) for t in self.targets) / expected if expected else 1.0

    @property
    def precision(self) -> float:
        """True-positive findings / (true positives + false positives), counting warning+ severities."""
        tp = sum(t.true_positives for t in self.targets)
        fp = sum(len(t.false_positives) for t in self.targets)
        return tp / (tp + fp) if tp + fp else 1.0

    def to_markdown(self) -> str:
        """Human-readable report."""
        lines = [
            "# Crucible benchmark (bug zoo)",
            "",
            f"**Recall {self.recall:.0%} · Precision {self.precision:.0%}**",
            "",
            "| target | expected | detected | missed | false positives | must-not violations |",
            "|---|---|---|---|---|---|",
        ]
        for t in self.targets:
            missed = ", ".join(f"{m.rule_id}@{m.agent or '*'}" for m in t.missed) or "-"
            fps = ", ".join(sorted({f"{f.rule_id}@{f.agent or '*'}" for f in t.false_positives})) or "-"
            violations = ", ".join(sorted({f.rule_id for f in t.must_not_violations})) or "-"
            lines.append(f"| {t.target} | {len(t.expected)} | {len(t.detected)} | {missed} | {fps} | {violations} |")
        return "\n".join(lines) + "\n"


def score(target: str, expected: ExpectedFindings, findings: list[Finding]) -> TargetScore:
    """Compare findings with ground truth."""
    detected = tuple(e for e in expected.findings if any(matches(e, f) for f in findings))
    missed = tuple(e for e in expected.findings if e not in detected)
    significant = [f for f in findings if f.severity.rank >= Severity.WARNING.rank]
    true_pos = [f for f in significant if any(matches(e, f) for e in expected.findings)]
    false_pos = tuple(f for f in significant if f not in true_pos)
    violations = tuple(f for f in findings if f.rule_id in expected.must_not)
    return TargetScore(
        target=target,
        expected=expected.findings,
        detected=detected,
        missed=missed,
        true_positives=len(true_pos),
        false_positives=false_pos,
        must_not_violations=violations,
    )


def run_benchmark(service: AuditService, options: AuditOptions | None = None) -> BenchmarkReport:
    """Audit every project target that has ground truth and score it."""
    scores = []
    for spec in service.project.spec.targets:
        expected = service.project.expected(spec)
        if expected is None:
            continue
        audit = service.audit_target(spec, options)
        scores.append(score(spec.name, expected, audit.findings))
    return BenchmarkReport(targets=tuple(scores))
