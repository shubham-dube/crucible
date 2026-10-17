"""Scenario expectation judges: routes and answers."""

from __future__ import annotations

from collections.abc import Iterable

from crucible.domain.findings import Evidence, Finding, Severity
from crucible.domain.trace import RunResult, SpanKind
from crucible.judges.base import JudgeContext, judge, run_finding


def _invoked(run: RunResult) -> list[str]:
    return [str(s.target) for s in run.spans if s.kind is SpanKind.DELEGATION and s.target]


def _is_subsequence(needle: Iterable[str], haystack: list[str]) -> bool:
    iterator = iter(haystack)
    return all(any(item == other for other in iterator) for item in needle)


@judge
class RoutingJudge:
    """Expected routes taken, forbidden routes avoided."""

    id = "routing"
    rule_ids = ("routing/expected-route-missed", "routing/forbidden-route")

    def judge(self, run: RunResult, ctx: JudgeContext) -> Iterable[Finding]:
        if ctx.scenario is None:
            return
        expect = ctx.scenario.expect
        invoked = _invoked(run)
        if expect.route and not _is_subsequence(expect.route, invoked):
            missing = next((a for a in expect.route if a not in invoked), expect.route[0])
            yield run_finding(
                "routing/expected-route-missed",
                Severity.ERROR,
                f"Expected route {list(expect.route)} but the network invoked {invoked[:12]}.",
                run,
                ctx,
                agent=missing,
                evidence=[Evidence(kind="answer", ref=run.run_id, excerpt=" -> ".join(invoked[:12]))],
                remediation="Clarify the parent's routing instructions and the child's description.",
            )
        for forbidden in expect.must_not_route:
            if forbidden in invoked:
                yield run_finding(
                    "routing/forbidden-route",
                    Severity.ERROR,
                    f"'{forbidden}' was invoked although this scenario must not use it.",
                    run,
                    ctx,
                    agent=forbidden,
                    evidence=[Evidence(kind="answer", ref=run.run_id, excerpt=" -> ".join(invoked[:12]))],
                    remediation=f"Tighten when '{forbidden}' may be used (description + caller instructions).",
                )


@judge
class AnswerJudge:
    """Required / forbidden answer content."""

    id = "answer"
    rule_ids = ("answer/missing-content", "answer/forbidden-content")

    def judge(self, run: RunResult, ctx: JudgeContext) -> Iterable[Finding]:
        if ctx.scenario is None or not run.answer:
            return
        answer = run.answer.lower()
        expect = ctx.scenario.expect
        missing = [t for t in expect.answer_contains if t.lower() not in answer]
        if missing:
            yield run_finding(
                "answer/missing-content",
                Severity.WARNING,
                f"Answer lacks expected content {missing}.",
                run,
                ctx,
                agent=ctx.graph.front_man,
                evidence=[Evidence(kind="answer", ref=run.run_id, excerpt=run.answer[:200])],
            )
        present = [t for t in expect.answer_not_contains if t.lower() in answer]
        if present:
            yield run_finding(
                "answer/forbidden-content",
                Severity.ERROR,
                f"Answer contains forbidden content {present}.",
                run,
                ctx,
                agent=ctx.graph.front_man,
                evidence=[Evidence(kind="answer", ref=run.run_id, excerpt=run.answer[:200])],
            )
