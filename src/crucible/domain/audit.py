"""An audit of one target: static + runtime findings and the run batch they came from."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from crucible.domain.findings import Finding, sort_findings
from crucible.domain.trace import RunBatch


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
