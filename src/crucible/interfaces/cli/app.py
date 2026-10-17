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


def main() -> None:
    """Console-script entry point."""
    app()
