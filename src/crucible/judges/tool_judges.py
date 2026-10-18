"""Tool-failure handling judges."""

from __future__ import annotations

import re
from collections.abc import Iterable

from crucible.domain.findings import Evidence, Finding, Severity
from crucible.domain.trace import RunResult, Span, SpanKind, agent_of
from crucible.judges.base import JudgeContext, judge, run_finding

ACKNOWLEDGEMENT = re.compile(
    r"\b(sorry|unable|couldn'?t|could not|can'?t|cannot|not able|error|unavailable|failed|failure|"
    r"try again|temporarily|issue|problem|outage|don'?t have|do not have)\b",
    re.IGNORECASE,
)


_FIGURE = re.compile(r"(?<![\w.])\d{2,}(?:[.,]\d+)?")
_GROUNDING = (SpanKind.USER_INPUT, SpanKind.TOOL_RESULT, SpanKind.SYSTEM_PROMPT)


def invented_figures(run: RunResult) -> list[str]:
    """Multi-digit figures in the answer that no tool result, user input or instruction contains."""
    grounded = {m.group(0) for s in run.spans if s.kind in _GROUNDING for m in _FIGURE.finditer(s.text)}
    return sorted({m.group(0) for m in _FIGURE.finditer(run.answer)} - grounded)


def _caller(span: Span) -> str | None:
    return agent_of(span.origin[:-1]) if len(span.origin) > 1 else None


@judge
class ErrorMaskedJudge:
    """A tool failed, was not retried successfully, and the final answer does not admit it."""

    id = "error-masked"
    rule_ids = ("tool/error-masked",)

    def judge(self, run: RunResult, ctx: JudgeContext) -> Iterable[Finding]:
        if not run.answer:
            return
        acknowledged = bool(ACKNOWLEDGEMENT.search(run.answer))
        for error in run.spans_of(SpanKind.TOOL_ERROR):
            recovered = any(
                s.kind is SpanKind.TOOL_RESULT and s.agent == error.agent and s.seq > error.seq for s in run.spans
            )
            invented = invented_figures(run) if acknowledged else []
            if recovered or (acknowledged and not invented):
                continue
            caller = _caller(error) or ctx.graph.front_man
            if invented:
                # Live models often say "the service is down, but expect around 36°C": admitted, still invented.
                severity = Severity.WARNING
                message = (
                    f"Tool '{error.agent}' failed ({error.text[:120]!r}); the answer admits it but still states "
                    f"figures no tool returned ({', '.join(invented[:5])}): {run.answer[:120]!r}."
                )
            else:
                severity = Severity.ERROR
                message = (
                    f"Tool '{error.agent}' failed ({error.text[:120]!r}) but the answer presents a confident result: "
                    f"{run.answer[:120]!r}."
                )
            yield run_finding(
                "tool/error-masked",
                severity,
                message,
                run,
                ctx,
                agent=caller,
                evidence=[
                    Evidence(kind="span", ref=error.id, excerpt=error.text[:200]),
                    Evidence(kind="answer", ref=run.run_id, excerpt=run.answer[:200]),
                ],
                remediation=f"Instruct '{caller}' to tell the user when '{error.agent}' fails (and optionally "
                "retry) instead of inventing an answer.",
            )
