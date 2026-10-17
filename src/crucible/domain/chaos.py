"""Fault model for chaos testing of coded tools."""

from __future__ import annotations

import fnmatch
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from crucible.domain.errors import ConfigError


class FaultKind(StrEnum):
    """Supported faults."""

    LATENCY = "latency"  # sleep, then behave normally
    EXCEPTION = "exception"  # raise before calling the tool
    TIMEOUT = "timeout"  # sleep far beyond budgets
    EMPTY = "empty"  # tool returns ""
    MALFORMED = "malformed"  # truncated / garbage output
    OVERSIZED = "oversized"  # very large output
    INJECTED_INSTRUCTION = "injected-instruction"  # append an injection payload with a unique marker
    SLY_DROP = "sly-drop"  # remove sly_data keys before the call
    SLY_MUTATE = "sly-mutate"  # replace sly_data values before the call


class FaultSpec(BaseModel):
    """One fault applied to coded tools whose agent name matches ``target`` (glob)."""

    model_config = ConfigDict(frozen=True)

    kind: FaultKind
    target: str = "*"
    probability: float = Field(default=1.0, ge=0.0, le=1.0)
    params: dict[str, Any] = Field(default_factory=dict)

    @property
    def id(self) -> str:
        """Stable textual form, e.g. ``exception:order_status``."""
        extra = "".join(f":{k}={v}" for k, v in sorted(self.params.items()))
        prob = f":p={self.probability:g}" if self.probability < 1.0 else ""
        return f"{self.kind.value}:{self.target}{prob}{extra}"

    def applies_to(self, agent: str) -> bool:
        """True when this fault targets ``agent``."""
        return fnmatch.fnmatchcase(agent, self.target)


def _coerce(value: str) -> Any:
    for cast in (int, float):
        try:
            return cast(value)
        except ValueError:
            continue
    return value


def parse_fault(text: str) -> FaultSpec:
    """Parse ``kind[:target][:key=value]...`` (``p=`` sets probability)."""
    parts = [p for p in text.strip().split(":") if p]
    if not parts:
        raise ConfigError("empty fault spec")
    try:
        kind = FaultKind(parts[0])
    except ValueError as exc:
        raise ConfigError(f"unknown fault '{parts[0]}'; choose from {[k.value for k in FaultKind]}") from exc
    target = "*"
    params: dict[str, Any] = {}
    probability = 1.0
    for part in parts[1:]:
        if "=" in part:
            key, _, value = part.partition("=")
            if key == "p":
                probability = float(value)
            else:
                params[key] = _coerce(value)
        else:
            target = part
    return FaultSpec(kind=kind, target=target, probability=probability, params=params)
