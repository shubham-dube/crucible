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
    configure_logging("DEBUG" if verbose else settings.log_level, settings.log_json)
    if not verbose:
        for noisy in ("neuro_san", "leaf_common", "langchain", "httpx", "root"):
            logging.getLogger(noisy).setLevel(logging.ERROR)
        logging.getLogger().setLevel(logging.ERROR)


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


def main() -> None:
    """Console-script entry point."""
    app()
