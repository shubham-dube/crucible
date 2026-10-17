"""Apply judges to runs and aggregate findings across repetitions."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from crucible.domain.findings import Finding, dedupe_findings, sort_findings
from crucible.domain.network import NetworkGraph
from crucible.domain.scenario import Scenario
from crucible.domain.trace import RunBatch
from crucible.judges import Budgets, JudgeContext, JudgeRegistry, judge_registry


def judge_batch(
    batch: RunBatch,
    graph: NetworkGraph,
    scenarios: Sequence[Scenario],
    budgets: Budgets | None = None,
    registry: JudgeRegistry | None = None,
    disabled: frozenset[str] = frozenset(),
) -> list[Finding]:
    """Per-run findings for every run in the batch."""
    by_id = {s.id: s for s in scenarios}
    reg = registry or judge_registry
    findings: list[Finding] = []
    for run in batch.runs:
        ctx = JudgeContext(graph=graph, scenario=by_id.get(run.scenario_id), budgets=budgets or Budgets())
        run_findings: list[Finding] = []
        for j in reg.judges():
            if j.id in disabled:
                continue
            run_findings.extend(f for f in j.judge(run, ctx) if f.rule_id not in disabled)
        findings.extend(fold_symptoms(run_findings))
    return findings


def fold_symptoms(findings: list[Finding]) -> list[Finding]:
    """Drop findings that are mere symptoms of a root cause reported for the same run.

    A ping-pong between A and B necessarily produces repeated identical calls A->B and B->A; reporting both buries
    the root cause, so repeated-call findings on a ping-pong pair are folded into the ping-pong finding.
    """
    pairs = {
        frozenset((e.excerpt or "").split(" -> "))
        for f in findings
        if f.rule_id == "trace/ping-pong"
        for e in f.evidence[:1]
    }
    return [
        f
        for f in findings
        if not (
            f.rule_id == "trace/repeated-call"
            and any(f.agent in pair and any(other in f.message for other in pair - {f.agent}) for pair in pairs)
        )
    ]


def aggregate(findings: Sequence[Finding], runs_per_scenario: dict[str, int]) -> list[Finding]:
    """Collapse repeated findings across repetitions into one per fingerprint, noting the observed frequency."""
    groups: dict[str, list[Finding]] = defaultdict(list)
    for finding in findings:
        groups[finding.fingerprint].append(finding)
    out: list[Finding] = []
    for group in groups.values():
        first = group[0]
        total = runs_per_scenario.get(first.scenario_id or "", len(group))
        observed = len({f.run_id for f in group})
        suffix = f" [observed in {observed}/{total} runs]" if total > 1 else ""
        out.append(first.model_copy(update={"message": first.message + suffix}))
    return sort_findings(dedupe_findings(out))
