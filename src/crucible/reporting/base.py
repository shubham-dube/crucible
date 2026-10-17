"""Reporter port, the report model and the reporter registry."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict

from crucible import __version__
from crucible.domain.findings import Finding


class TargetFindings(BaseModel):
    """Findings for one analysed network."""

    model_config = ConfigDict(frozen=True)

    network: str
    file: str | None = None
    findings: tuple[Finding, ...] = ()


class FindingsReport(BaseModel):
    """What every reporter renders: one or more targets and their findings."""

    model_config = ConfigDict(frozen=True)

    tool: str = "crucible"
    version: str = __version__
    kind: str = "lint"
    targets: tuple[TargetFindings, ...] = ()

    @property
    def all_findings(self) -> list[Finding]:
        """Flattened findings across targets."""
        return [f for t in self.targets for f in t.findings]


class Reporter(Protocol):
    """Renders a ``FindingsReport`` to text."""

    name: str

    def render(self, report: FindingsReport) -> str:
        """Return the rendered report."""
        ...


reporters: dict[str, Reporter] = {}


def register_reporter(reporter: Reporter) -> Reporter:
    """Add a reporter to the registry."""
    reporters[reporter.name] = reporter
    return reporter


def get_reporter(name: str) -> Reporter:
    """Look up a reporter, importing the built-ins on first use."""
    from crucible.reporting import formats  # noqa: F401  (registers built-ins)

    try:
        return reporters[name]
    except KeyError as exc:
        raise ValueError(f"unknown report format '{name}'; choose from {sorted(reporters)}") from exc
