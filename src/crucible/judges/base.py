"""Judge port, context and registry."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from crucible.domain.findings import Evidence, Finding, Location, Severity
from crucible.domain.network import NetworkGraph
from crucible.domain.scenario import Scenario
from crucible.domain.trace import RunResult


class Budgets(BaseModel):
    """Run-level budgets; None disables a check."""

    model_config = ConfigDict(frozen=True)

    max_delegations: int | None = 50
    max_tokens: int | None = None
    max_seconds: float | None = None


class JudgeContext(BaseModel):
    """What a judge may consult besides the run itself."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    graph: NetworkGraph
    scenario: Scenario | None = None
    budgets: Budgets = Budgets()


class Judge(Protocol):
    """Analyses one run and yields evidence-backed findings."""

    id: str
    rule_ids: tuple[str, ...]

    def judge(self, run: RunResult, ctx: JudgeContext) -> Iterable[Finding]:
        """Yield findings for ``run``."""
        ...


class JudgeRegistry:
    """Judges by id."""

    def __init__(self) -> None:
        self._judges: dict[str, Judge] = {}

    def register(self, judge: Judge) -> Judge:
        """Add a judge; ids must be unique."""
        if judge.id in self._judges:
            raise ValueError(f"duplicate judge id: {judge.id}")
        self._judges[judge.id] = judge
        return judge

    def judges(self) -> list[Judge]:
        """All judges sorted by id."""
        return [self._judges[k] for k in sorted(self._judges)]


judge_registry = JudgeRegistry()


def judge[T](cls: type[T]) -> type[T]:
    """Class decorator: instantiate and register in the default judge registry."""
    instance: Any = cls()
    judge_registry.register(instance)
    return cls


def run_finding(
    rule_id: str,
    severity: Severity,
    message: str,
    run: RunResult,
    ctx: JudgeContext,
    agent: str | None = None,
    evidence: Iterable[Evidence] = (),
    remediation: str | None = None,
) -> Finding:
    """Finding tied to a run and scenario."""
    node = ctx.graph.nodes.get(agent) if agent else None
    return Finding(
        rule_id=rule_id,
        severity=severity,
        message=message,
        agent=agent,
        location=Location(
            file=ctx.graph.source_path,
            agent=agent,
            json_path=f"tools[{node.index}]" if node is not None and node.index >= 0 else None,
        ),
        remediation=remediation,
        evidence=tuple(evidence),
        run_id=run.run_id,
        scenario_id=run.scenario_id,
    )


def excerpt(text: str, needle: str, width: int = 60) -> str:
    """Short context around ``needle`` (needle masked so reports never re-leak secrets)."""
    index = text.find(needle)
    if index < 0:
        return text[: width * 2]
    masked = needle[:3] + "***" if len(needle) > 3 else "***"
    start = max(0, index - width)
    return text[start:index] + masked + text[index + len(needle) : index + len(needle) + width]
