"""AuditService: lint -> run -> judge for project targets (used by CLI, benchmark and the agent network)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence

from pydantic import BaseModel, ConfigDict, Field

from crucible.config.project import Project, TargetSpec
from crucible.domain.findings import Finding, sort_findings
from crucible.domain.scenario import Scenario
from crucible.domain.trace import RunBatch, RunResult
from crucible.execution.ports import TargetAdapter
from crucible.execution.runner import Runner
from crucible.integrations.neurosan.loader import load_network
from crucible.judges import Budgets
from crucible.judges.engine import aggregate, judge_batch
from crucible.topology.linter import lint
from crucible.topology.rules import LintConfig


class AuditOptions(BaseModel):
    """Knobs for one audit."""

    model_config = ConfigDict(frozen=True)

    repetitions: int = Field(default=1, ge=1)
    timeout_s: float = 120.0
    budgets: Budgets = Budgets()
    lint: LintConfig = LintConfig()
    disabled_judges: frozenset[str] = frozenset()
    scenario_ids: frozenset[str] | None = None
    chaos: tuple[str, ...] = ()


class TargetAudit(BaseModel):
    """Everything Crucible learned about one target."""

    model_config = ConfigDict(frozen=True)

    target: str
    network_path: str
    static_findings: tuple[Finding, ...] = ()
    runtime_findings: tuple[Finding, ...] = ()
    batch: RunBatch | None = None

    @property
    def findings(self) -> list[Finding]:
        """Static + runtime findings, most severe first."""
        return sort_findings([*self.static_findings, *self.runtime_findings])


AdapterFactory = Callable[[Project, TargetSpec], TargetAdapter]


def default_adapter(project: Project, spec: TargetSpec) -> TargetAdapter:
    """In-process Neuro-SAN adapter."""
    from crucible.integrations.neurosan.direct_adapter import NeuroSanDirectAdapter

    return NeuroSanDirectAdapter(project.network_path(spec))


class AuditService:
    """Runs the deterministic audit pipeline for project targets."""

    def __init__(self, project: Project, adapter_factory: AdapterFactory = default_adapter) -> None:
        self.project = project
        self.adapter_factory = adapter_factory
        project.activate()

    def audit_target(
        self,
        spec: TargetSpec,
        options: AuditOptions | None = None,
        scenarios: Sequence[Scenario] | None = None,
        on_result: Callable[[RunResult], None] | None = None,
    ) -> TargetAudit:
        """Lint, execute scenarios and judge the traces for one target."""
        opts = options or AuditOptions()
        loaded = load_network(self.project.network_path(spec))
        static = lint(loaded, opts.lint).findings
        suite = list(scenarios) if scenarios is not None else list(self.project.scenarios(spec).scenarios)
        if opts.scenario_ids is not None:
            suite = [s for s in suite if s.id in opts.scenario_ids]
        if not suite:
            return TargetAudit(target=spec.name, network_path=str(loaded.path), static_findings=static)
        runner = Runner(self.adapter_factory(self.project, spec), timeout_s=opts.timeout_s, chaos=opts.chaos)
        batch = runner.run(spec.name, suite, opts.repetitions, on_result=on_result)
        raw = judge_batch(batch, loaded.graph, suite, opts.budgets, disabled=opts.disabled_judges)
        per_scenario = Counter(r.scenario_id for r in batch.runs)
        return TargetAudit(
            target=spec.name,
            network_path=str(loaded.path),
            static_findings=static,
            runtime_findings=tuple(aggregate(raw, dict(per_scenario))),
            batch=batch,
        )
