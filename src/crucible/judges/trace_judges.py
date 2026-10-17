"""Delegation-pattern and budget judges."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable

from crucible.domain.findings import Evidence, Finding, Severity
from crucible.domain.trace import RunResult, RunStatus, SpanKind
from crucible.judges.base import JudgeContext, judge, run_finding

PING_PONG_MIN = 3
REPEATED_CALL_MIN = 5


@judge
class PingPongJudge:
    """Two agents delegating to each other back and forth."""

    id = "ping-pong"
    rule_ids = ("trace/ping-pong",)

    def judge(self, run: RunResult, ctx: JudgeContext) -> Iterable[Finding]:
        delegations = [s for s in run.spans if s.kind is SpanKind.DELEGATION and s.agent and s.target]
        counts = Counter((s.agent, s.target) for s in delegations)
        reported: set[frozenset[str]] = set()
        for (caller, callee), forward in sorted(counts.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
            if caller is None or callee is None:
                continue
            backward = counts.get((callee, caller), 0)
            pair = frozenset((caller, callee))
            if pair in reported or min(forward, backward) < PING_PONG_MIN:
                continue
            reported.add(pair)
            first, second = sorted(pair)
            spans = [s for s in delegations if {s.agent, s.target} == pair][:6]
            yield run_finding(
                "trace/ping-pong",
                Severity.ERROR,
                f"'{first}' and '{second}' delegated to each other {forward + backward} times "
                f"({counts.get((first, second), 0)} / {counts.get((second, first), 0)}); the task never converged.",
                run,
                ctx,
                agent=first,
                evidence=[Evidence(kind="span", ref=s.id, excerpt=f"{s.agent} -> {s.target}") for s in spans],
                remediation=f"Give '{first}' and '{second}' disjoint responsibilities and tell each when NOT to "
                "delegate back; remove one direction of the edge.",
            )


@judge
class RepeatedCallJudge:
    """The same caller invoking the same callee with identical arguments again and again."""

    id = "repeated-call"
    rule_ids = ("trace/repeated-call",)

    def judge(self, run: RunResult, ctx: JudgeContext) -> Iterable[Finding]:
        keyed = Counter(
            (s.agent, s.target, json.dumps(s.data.get("params", {}), sort_keys=True, default=str))
            for s in run.spans
            if s.kind is SpanKind.DELEGATION
        )
        for (caller, callee, params), count in sorted(keyed.items(), key=lambda kv: -kv[1]):
            if count >= REPEATED_CALL_MIN:
                yield run_finding(
                    "trace/repeated-call",
                    Severity.WARNING,
                    f"'{caller}' called '{callee}' {count} times with identical arguments {params[:120]}.",
                    run,
                    ctx,
                    agent=caller,
                    remediation="Make the caller use the first result, or make the callee's output conclusive.",
                )


@judge
class TimeoutJudge:
    """The run never produced an answer within its time budget."""

    id = "timeout"
    rule_ids = ("trace/timeout",)

    def judge(self, run: RunResult, ctx: JudgeContext) -> Iterable[Finding]:
        if run.status is RunStatus.TIMEOUT:
            yield run_finding(
                "trace/timeout",
                Severity.ERROR,
                f"Run timed out after {run.duration_s:.1f}s ({run.error or run.answer or 'no answer'}).",
                run,
                ctx,
                agent=ctx.graph.front_man,
                evidence=[Evidence(kind="answer", ref=run.run_id, excerpt=(run.answer or run.error or "")[:200])],
                remediation="Find the loop or slow tool in the trace; bound max_steps / max_execution_seconds.",
            )


@judge
class BudgetJudge:
    """Delegation count, tokens and latency against configured budgets."""

    id = "budget"
    rule_ids = ("budget/delegations", "budget/tokens", "budget/latency")

    def judge(self, run: RunResult, ctx: JudgeContext) -> Iterable[Finding]:
        budgets = ctx.budgets
        delegations = len(run.delegations())
        checks = [
            ("budget/delegations", budgets.max_delegations, delegations, "delegations"),
            ("budget/tokens", budgets.max_tokens, run.tokens.total, "tokens"),
            ("budget/latency", budgets.max_seconds, run.duration_s, "seconds"),
        ]
        for rule_id, limit, actual, unit in checks:
            if limit is not None and actual > limit:
                yield run_finding(
                    rule_id,
                    Severity.WARNING,
                    f"Run used {actual:g} {unit} (budget {limit:g}).",
                    run,
                    ctx,
                    agent=ctx.graph.front_man,
                    remediation=f"Reduce {unit} per request or raise the budget deliberately.",
                )
