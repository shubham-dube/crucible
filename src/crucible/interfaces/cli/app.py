"""``crucible`` command-line interface."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from crucible import __version__
from crucible.domain.errors import CrucibleError
from crucible.domain.findings import Severity
from crucible.reporting import FindingsReport, get_reporter
from crucible.reporting.base import TargetFindings

app = typer.Typer(
    name="crucible",
    help="Chaos, fuzz and regression QA for multi-agent networks.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def _main(
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Show framework (Neuro-SAN) logs.")] = False,
) -> None:
    """Configure logging before any command runs."""
    import logging

    from crucible.config import get_settings
    from crucible.observability.logging import configure_logging

    settings = get_settings()
    configure_logging("DEBUG" if verbose else "WARNING", settings.log_json)
    if not verbose:
        # Target networks' own failures are findings, not log noise (Neuro-SAN logs coded-tool tracebacks at ERROR).
        for noisy in ("neuro_san", "leaf_common", "langchain", "httpx"):
            logging.getLogger(noisy).setLevel(logging.CRITICAL)
        logging.getLogger().setLevel(logging.CRITICAL)


class FailOn(StrEnum):
    """Severity threshold that makes the command exit non-zero."""

    ERROR = "error"
    WARNING = "warning"
    NEVER = "never"

    def threshold(self) -> Severity | None:
        """Map to a Severity (None = never fail)."""
        return None if self is FailOn.NEVER else Severity(self.value)


def emit(text: str, output: Path | None) -> None:
    """Write to a file or stdout."""
    if output is None:
        typer.echo(text, nl=not text.endswith("\n"))
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        typer.echo(f"wrote {output}", err=True)


@app.command()
def version() -> None:
    """Print the Crucible version."""
    typer.echo(__version__)


@app.command()
def lint(
    paths: Annotated[list[Path], typer.Argument(help="Network .hocon files to lint.", exists=True)],
    fmt: Annotated[str, typer.Option("--format", "-f", help="table | json | sarif")] = "table",
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Write report to this file.")] = None,
    fail_on: Annotated[FailOn, typer.Option(help="Exit 1 if findings at/above this severity.")] = FailOn.ERROR,
    disable: Annotated[list[str] | None, typer.Option(help="Rule id to disable (repeatable).")] = None,
    no_neurosan: Annotated[bool, typer.Option(help="Skip Neuro-SAN's built-in validators.")] = False,
) -> None:
    """Statically analyse agent network topology."""
    from crucible.integrations.neurosan.loader import load_network
    from crucible.topology.linter import lint as run_lint
    from crucible.topology.rules import LintConfig

    config = LintConfig(disabled=frozenset(disable or []), run_neurosan_validators=not no_neurosan)
    targets: list[TargetFindings] = []
    failed = False
    for path in paths:
        try:
            result = run_lint(load_network(path), config)
        except CrucibleError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(2) from exc
        targets.append(TargetFindings(network=result.network, file=result.file, findings=result.findings))
        failed = failed or result.fails(fail_on.threshold())
    try:
        reporter = get_reporter(fmt)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="--format") from exc
    emit(reporter.render(FindingsReport(kind="lint", targets=tuple(targets))), output)
    if failed:
        raise typer.Exit(1)


@app.command()
def run(
    project_dir: Annotated[Path, typer.Argument(help="Directory containing crucible.yaml.", exists=True)],
    target: Annotated[list[str] | None, typer.Option("--target", "-t", help="Target name (repeatable).")] = None,
    scenario: Annotated[str | None, typer.Option(help="Only run this scenario id.")] = None,
    repetitions: Annotated[int, typer.Option("--repetitions", "-n", min=1, help="Runs per scenario.")] = 1,
    timeout: Annotated[float, typer.Option(help="Hard timeout per run, seconds.")] = 120.0,
    save: Annotated[bool, typer.Option(help="Persist traces under $CRUCIBLE_HOME/runs.")] = True,
) -> None:
    """Execute hand-written scenarios against target networks and record full traces."""
    from crucible.config import get_settings
    from crucible.config.project import Project
    from crucible.execution.runner import Runner
    from crucible.integrations.neurosan.direct_adapter import NeuroSanDirectAdapter
    from crucible.interfaces.cli.render import render_batch
    from crucible.storage.run_store import FileRunStore

    try:
        project = Project.load(project_dir)
        project.activate()
        specs = [project.target(name) for name in target] if target else list(project.spec.targets)
        store = FileRunStore(get_settings().home)
        for spec in specs:
            scenarios = [s for s in project.scenarios(spec).scenarios if scenario is None or s.id == scenario]
            if not scenarios:
                typer.echo(f"{spec.name}: no scenarios", err=True)
                continue
            adapter = NeuroSanDirectAdapter(project.network_path(spec))
            batch = Runner(adapter, timeout_s=timeout).run(spec.name, scenarios, repetitions)
            typer.echo(render_batch(batch))
            if save:
                typer.echo(f"saved {store.save(batch)}", err=True)
    except CrucibleError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc


@app.command()
def audit(
    project_dir: Annotated[Path, typer.Argument(help="Directory containing crucible.yaml.", exists=True)],
    target: Annotated[list[str] | None, typer.Option("--target", "-t", help="Target name (repeatable).")] = None,
    repetitions: Annotated[int, typer.Option("--repetitions", "-n", min=1)] = 1,
    timeout: Annotated[float, typer.Option(help="Hard timeout per run, seconds.")] = 120.0,
    fmt: Annotated[str, typer.Option("--format", "-f", help="table | json | sarif")] = "table",
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    fail_on: Annotated[FailOn, typer.Option(help="Exit 1 if findings at/above this severity.")] = FailOn.ERROR,
    max_delegations: Annotated[int, typer.Option(help="Delegation budget per run (0 = off).")] = 50,
    save: Annotated[bool, typer.Option(help="Persist traces under $CRUCIBLE_HOME/runs.")] = True,
    agentic: Annotated[
        bool, typer.Option(help="Let Crucible's Neuro-SAN agent network plan and run the audit.")
    ] = False,
    scripted: Annotated[bool, typer.Option(help="With --agentic: deterministic keyless agents (CI/demo).")] = False,
    request: Annotated[str | None, typer.Option(help="With --agentic: what to ask the conductor.")] = None,
) -> None:
    """Lint, run and judge targets: static + runtime findings with trace evidence."""
    from crucible.config import get_settings
    from crucible.config.project import Project
    from crucible.judges import Budgets
    from crucible.services.audit import AuditOptions, AuditService
    from crucible.storage.run_store import FileRunStore

    if agentic:
        _agentic_audit(project_dir, target, scripted, request, fail_on)
        return
    try:
        project = Project.load(project_dir)
        service = AuditService(project)
        specs = [project.target(name) for name in target] if target else list(project.spec.targets)
        options = AuditOptions(
            repetitions=repetitions,
            timeout_s=timeout,
            budgets=Budgets(max_delegations=max_delegations or None),
        )
        store = FileRunStore(get_settings().home)
        targets: list[TargetFindings] = []
        failed = False
        for spec in specs:
            result = service.audit_target(spec, options)
            if save and result.batch is not None:
                store.save(result.batch)
            targets.append(
                TargetFindings(network=result.target, file=result.network_path, findings=tuple(result.findings))
            )
            threshold = fail_on.threshold()
            failed = failed or (
                threshold is not None and any(f.severity.rank >= threshold.rank for f in result.findings)
            )
        emit(get_reporter(fmt).render(FindingsReport(kind="audit", targets=tuple(targets))), output)
    except CrucibleError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc
    if failed:
        raise typer.Exit(1)


def _agentic_audit(
    project_dir: Path, targets: list[str] | None, scripted: bool, request: str | None, fail_on: FailOn
) -> None:
    from crucible.config.project import Project
    from crucible.services import toolkit
    from crucible.services.agentic import DEFAULT_REQUEST, run_agentic_audit

    try:
        project = Project.load(project_dir)
        names = targets or [t.name for t in project.spec.targets]
        failed = False
        for name in names:
            result = run_agentic_audit(project_dir, name, request or DEFAULT_REQUEST, scripted=scripted)
            typer.echo(f"== {name}  ({result.duration_s:.1f}s, {len(result.delegations)} hand-offs)")
            typer.echo(result.answer)
            if result.report_path:
                typer.echo(f"report: {result.report_path}")
            threshold = fail_on.threshold()
            findings = [f for a in result.audit_ids for f in toolkit.get_audit(a).findings]
            failed = failed or (threshold is not None and any(f.severity.rank >= threshold.rank for f in findings))
    except CrucibleError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc
    if failed:
        raise typer.Exit(1)


@app.command()
def bench(
    project_dir: Annotated[Path, typer.Argument(help="Benchmark project (targets with expected findings).")] = Path(
        "examples/targets"
    ),
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Write the markdown report here.")] = None,
    min_recall: Annotated[float, typer.Option(help="Exit 1 below this recall.")] = 0.9,
    min_precision: Annotated[float, typer.Option(help="Exit 1 below this precision.")] = 0.9,
    timeout: Annotated[float, typer.Option(help="Hard timeout per run, seconds.")] = 60.0,
) -> None:
    """Score Crucible against ground truth (the bug zoo)."""
    from crucible.config.project import Project
    from crucible.evaluation.benchmark import run_benchmark
    from crucible.services.audit import AuditOptions, AuditService

    try:
        report = run_benchmark(AuditService(Project.load(project_dir)), AuditOptions(timeout_s=timeout))
    except CrucibleError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc
    emit(report.to_markdown(), output)
    if report.recall < min_recall or report.precision < min_precision:
        raise typer.Exit(1)


@app.command()
def chaos(
    project_dir: Annotated[Path, typer.Argument(help="Directory containing crucible.yaml.", exists=True)],
    target: Annotated[str, typer.Option("--target", "-t", help="Target name.")],
    fault: Annotated[
        list[str] | None,
        typer.Option("--fault", help="Fault profile, e.g. exception:order_status (repeatable). Default: matrix."),
    ] = None,
    timeout: Annotated[float, typer.Option(help="Hard timeout per run, seconds.")] = 60.0,
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Write markdown here.")] = None,
    min_resilience: Annotated[float, typer.Option(help="Exit 1 below this resilience.")] = 0.0,
) -> None:
    """Chaos matrix: which tool failures break the network (new findings vs. baseline)."""
    from crucible.config.project import Project
    from crucible.domain.chaos import parse_fault
    from crucible.services.audit import AuditOptions, AuditService
    from crucible.services.chaos_matrix import run_matrix

    try:
        for spec_text in fault or []:
            parse_fault(spec_text)  # validate early
        service = AuditService(Project.load(project_dir))
        matrix = run_matrix(service, service.project.target(target), fault, AuditOptions(timeout_s=timeout))
    except CrucibleError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc
    emit(matrix.to_markdown(), output)
    if matrix.resilience < min_resilience:
        raise typer.Exit(1)


@app.command()
def plan(
    project_dir: Annotated[Path, typer.Argument(help="Directory containing crucible.yaml.", exists=True)],
    target: Annotated[str, typer.Option("--target", "-t", help="Target name.")],
    measure: Annotated[bool, typer.Option(help="Run existing scenarios to measure achieved coverage.")] = True,
    write: Annotated[Path | None, typer.Option(help="Write existing + generated scenarios to this YAML.")] = None,
    probes: Annotated[bool, typer.Option(help="Add adversarial probe scenarios.")] = True,
    timeout: Annotated[float, typer.Option(help="Hard timeout per run, seconds.")] = 60.0,
) -> None:
    """Delegation-edge coverage of the scenario set, plus generated scenarios for the gaps."""
    from crucible.config.project import Project
    from crucible.execution.runner import Runner
    from crucible.integrations.neurosan.direct_adapter import NeuroSanDirectAdapter
    from crucible.integrations.neurosan.loader import load_network
    from crucible.scenarios.coverage import CoverageReport, coverage, edges
    from crucible.scenarios.generator import TemplateGenerator
    from crucible.scenarios.io import merge_suites, write_suite

    try:
        project = Project.load(project_dir)
        project.activate()
        spec = project.target(target)
        graph = load_network(project.network_path(spec)).graph
        suite = project.scenarios(spec)
        if measure and suite.scenarios:
            adapter = NeuroSanDirectAdapter(project.network_path(spec))
            report = coverage(graph, [Runner(adapter, timeout_s=timeout).run(spec.name, suite.scenarios)])
        else:
            report = CoverageReport(edges=tuple(edges(graph)), covered=())
        generated = TemplateGenerator(include_probes=probes).generate(graph, report.uncovered)
    except CrucibleError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc
    typer.echo(f"{spec.name}: edge coverage {report.ratio:.0%} ({len(report.covered)}/{len(report.edges)})")
    for edge in report.edges:
        mark = "x" if edge in report.covered else " "
        typer.echo(f"  [{mark}] {edge.src} -> {edge.dst}")
    typer.echo(f"generated {len(generated)} scenario(s): {', '.join(s.id for s in generated)}")
    if write is not None:
        typer.echo(f"wrote {write_suite(merge_suites(suite, generated), write)}", err=True)


@app.command("export-tests")
def export_tests(
    project_dir: Annotated[Path, typer.Argument(help="Directory containing crucible.yaml.", exists=True)],
    target: Annotated[str, typer.Option("--target", "-t", help="Target name.")],
    out_dir: Annotated[Path, typer.Option("--out", "-o", help="Directory for Neuro-SAN test-case files.")],
    agent_name: Annotated[str | None, typer.Option(help="Agent name to test (default: network file path).")] = None,
) -> None:
    """Export scenarios as Neuro-SAN data-driven test cases (neuro_san.test compatible)."""
    import json

    from crucible.config.project import Project
    from crucible.scenarios.io import to_neurosan_test

    try:
        project = Project.load(project_dir)
        spec = project.target(target)
        agent = agent_name or str(project.network_path(spec))
        out_dir.mkdir(parents=True, exist_ok=True)
        for scenario in project.scenarios(spec).scenarios:
            path = out_dir / f"{scenario.id}.hocon"
            path.write_text(json.dumps(to_neurosan_test(scenario, agent), indent=2) + "\n", encoding="utf-8")
            typer.echo(f"wrote {path}")
    except CrucibleError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from exc


def main() -> None:
    """Console-script entry point."""
    app()
