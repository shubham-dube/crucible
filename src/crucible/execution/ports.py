"""Ports for executing scenarios against a target network."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from crucible.domain.scenario import Scenario
from crucible.domain.trace import RunResult, SensitiveValue


class RunRequest(BaseModel):
    """One scenario repetition to execute."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    target: str
    scenario: Scenario
    repetition: int = 0
    sensitive: tuple[SensitiveValue, ...] = ()
    timeout_s: float = Field(default=120.0, gt=0)
    chaos: tuple[str, ...] = ()


class TargetAdapter(Protocol):
    """Executes scenarios against some kind of target (in-process Neuro-SAN, HTTP server, ...)."""

    name: str

    def run(self, request: RunRequest) -> RunResult:
        """Execute one scenario repetition; must not raise for target-side failures (report them in the result)."""
        ...
