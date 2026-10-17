"""Scenarios: what Crucible sends to a target network and what it expects back."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ScenarioSource(StrEnum):
    """Who authored a scenario."""

    HAND = "hand"
    GENERATED = "generated"


class Interaction(BaseModel):
    """One user turn."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    sly_data: dict[str, Any] = Field(default_factory=dict)


class Expectation(BaseModel):
    """What a correct run looks like. All fields optional; empty means 'anything goes'."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    route: tuple[str, ...] = Field(default=(), description="agents that must be invoked, in this relative order")
    must_not_route: tuple[str, ...] = ()
    answer_contains: tuple[str, ...] = ()
    answer_not_contains: tuple[str, ...] = ()


class Scenario(BaseModel):
    """A test conversation against a target network."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    description: str = ""
    interactions: tuple[Interaction, ...]
    expect: Expectation = Field(default_factory=Expectation)
    tags: tuple[str, ...] = ()
    target_edge: tuple[str, str] | None = Field(default=None, description="delegation edge this scenario covers")
    source: ScenarioSource = ScenarioSource.HAND


class ScenarioSuite(BaseModel):
    """A file of scenarios for one network."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scenarios: tuple[Scenario, ...] = ()


class ExpectedFinding(BaseModel):
    """A finding Crucible must report for a benchmark target (bug zoo)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: str
    agent: str | None = None
    scenario: str | None = None
    note: str = ""


class ExpectedFindings(BaseModel):
    """Ground truth for a benchmark target."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    findings: tuple[ExpectedFinding, ...] = ()
    must_not: tuple[str, ...] = Field(default=(), description="rule ids that must NOT be reported (false positives)")
