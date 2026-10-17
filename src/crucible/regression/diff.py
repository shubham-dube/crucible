"""Compare two audits of the same target: findings and runtime metrics."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean

from pydantic import BaseModel, ConfigDict

from crucible.domain.audit import TargetAudit
from crucible.domain.findings import Finding, Severity
from crucible.domain.trace import RunBatch


class MetricDelta(BaseModel):
    """Mean of a metric for one scenario in baseline vs. current."""

    model_config = ConfigDict(frozen=True)

    scenario_id: str
    metric: str
    baseline: float
    current: float

    @property
    def change(self) -> float:
        """Relative change (inf when the baseline was 0 and current is not)."""
        if self.baseline == 0:
            return 0.0 if self.current == 0 else float("inf")
        return (self.current - self.baseline) / self.baseline


class RegressionDiff(BaseModel):
    """What changed between a baseline audit and the current one."""

    model_config = ConfigDict(frozen=True)

    target: str
    new: tuple[Finding, ...]
    fixed: tuple[Finding, ...]
    persisting: tuple[Finding, ...]
    metric_regressions: tuple[MetricDelta, ...]

    def fails(self, threshold: Severity | None) -> bool:
        """Gate: any NEW finding at/above threshold, or any metric regression when threshold is set."""
        if threshold is None:
            return False
        return any(f.severity.rank >= threshold.rank for f in self.new) or bool(self.metric_regressions)

    def to_markdown(self) -> str:
        """PR-comment friendly summary."""
        lines = [
            f"## Crucible regression check — `{self.target}`",
            "",
            f"🆕 **{len(self.new)} new** · ✅ {len(self.fixed)} fixed · ↔️ {len(self.persisting)} unchanged",
            "",
        ]
        if self.new:
            lines += [
                "### New findings",
                "",
                "| severity | rule | agent | scenario | finding |",
                "|---|---|---|---|---|",
            ]
            for f in self.new:
                cells = [f.severity.value, f"`{f.rule_id}`", f.agent or "-", f.scenario_id or "-", f.message[:200]]
                lines.append("| " + " | ".join(cells) + " |")
            lines.append("")
        if self.fixed:
            lines += ["### Fixed", ""] + [f"- `{f.rule_id}` ({f.agent or '-'})" for f in self.fixed] + [""]
        if self.metric_regressions:
            lines += ["### Metric regressions", "", "| scenario | metric | baseline | current | change |"]
            lines.append("|---|---|---|---|---|")
            lines += [
                f"| {m.scenario_id} | {m.metric} | {m.baseline:g} | {m.current:g} | {m.change:+.0%} |"
                for m in self.metric_regressions
            ]
            lines.append("")
        return "\n".join(lines)


_MIN_ABSOLUTE = {"tokens": 200.0, "latency_s": 1.0, "delegations": 2.0}


def _metrics(batch: RunBatch | None) -> dict[tuple[str, str], float]:
    if batch is None:
        return {}
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for run in batch.runs:
        grouped[(run.scenario_id, "tokens")].append(run.tokens.total)
        grouped[(run.scenario_id, "latency_s")].append(run.duration_s)
        grouped[(run.scenario_id, "delegations")].append(len(run.delegations()))
    return {key: round(mean(values), 3) for key, values in grouped.items()}


def diff(baseline: TargetAudit, current: TargetAudit, tolerance: float = 0.25) -> RegressionDiff:
    """Findings matched by fingerprint; metrics compared per scenario present in both audits."""
    base_fp = {f.fingerprint: f for f in baseline.findings}
    cur_fp = {f.fingerprint: f for f in current.findings}
    base_metrics, cur_metrics = _metrics(baseline.batch), _metrics(current.batch)
    regressions = []
    for key in sorted(set(base_metrics) & set(cur_metrics)):
        delta = MetricDelta(scenario_id=key[0], metric=key[1], baseline=base_metrics[key], current=cur_metrics[key])
        grew = delta.current - delta.baseline
        if grew > _MIN_ABSOLUTE[key[1]] and delta.change > tolerance:
            regressions.append(delta)
    return RegressionDiff(
        target=current.target,
        new=tuple(f for fp, f in cur_fp.items() if fp not in base_fp),
        fixed=tuple(f for fp, f in base_fp.items() if fp not in cur_fp),
        persisting=tuple(f for fp, f in cur_fp.items() if fp in base_fp),
        metric_regressions=tuple(regressions),
    )
