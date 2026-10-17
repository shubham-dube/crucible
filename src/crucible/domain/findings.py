"""Findings: the unit of output for every analysis Crucible performs."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Severity(StrEnum):
    """How bad a finding is. Ordered: error > warning > info."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    @property
    def rank(self) -> int:
        """Higher is more severe."""
        return {"error": 3, "warning": 2, "info": 1}[self.value]


class Location(BaseModel):
    """Where a finding points in the target's source."""

    model_config = ConfigDict(frozen=True)

    file: str | None = None
    agent: str | None = None
    json_path: str | None = None


class Evidence(BaseModel):
    """A pointer into run/trace data (or static config) that supports a finding."""

    model_config = ConfigDict(frozen=True)

    kind: str = Field(description="e.g. 'config', 'span', 'prompt', 'message'")
    ref: str = Field(description="id or path of the referenced item")
    excerpt: str | None = None


class Finding(BaseModel):
    """One defect or risk detected by a lint rule or judge."""

    model_config = ConfigDict(frozen=True)

    rule_id: str
    severity: Severity
    message: str
    agent: str | None = None
    location: Location = Field(default_factory=Location)
    remediation: str | None = None
    evidence: tuple[Evidence, ...] = ()
    run_id: str | None = None
    scenario_id: str | None = None

    @property
    def fingerprint(self) -> str:
        """Stable identity used for dedupe and regression diffing (ignores run-specific data)."""
        return f"{self.rule_id}|{self.agent or ''}|{self.location.json_path or ''}|{self.scenario_id or ''}"


def sort_findings(findings: list[Finding]) -> list[Finding]:
    """Most severe first, then by rule and agent for stable output."""
    return sorted(findings, key=lambda f: (-f.severity.rank, f.rule_id, f.agent or "", f.message))


def dedupe_findings(findings: list[Finding]) -> list[Finding]:
    """Drop findings with identical fingerprint and message, keeping the first."""
    seen: set[tuple[str, str]] = set()
    out: list[Finding] = []
    for finding in findings:
        key = (finding.fingerprint, finding.message)
        if key not in seen:
            seen.add(key)
            out.append(finding)
    return out
