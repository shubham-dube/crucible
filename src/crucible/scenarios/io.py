"""Scenario interchange: Crucible YAML suites and Neuro-SAN data-driven test-case HOCON/JSON."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from crucible.domain.scenario import Expectation, Interaction, Scenario, ScenarioSource, ScenarioSuite


def write_suite(suite: ScenarioSuite, path: str | Path) -> Path:
    """Write a suite as YAML (stable key order, no Python tags)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = suite.model_dump(mode="json", exclude_defaults=True)
    target.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return target


def merge_suites(base: ScenarioSuite, extra: list[Scenario]) -> ScenarioSuite:
    """Append scenarios whose ids are new."""
    known = {s.id for s in base.scenarios}
    return ScenarioSuite(scenarios=(*base.scenarios, *(s for s in extra if s.id not in known)))


def to_neurosan_test(
    scenario: Scenario, agent: str, success_ratio: str = "1/1", timeout_s: int = 120, connection: str = "direct"
) -> dict[str, Any]:
    """Neuro-SAN data-driven test case (``neuro_san.test``); Crucible-only fields live under ``crucible``."""
    interactions: list[dict[str, Any]] = []
    for index, turn in enumerate(scenario.interactions):
        item: dict[str, Any] = {"text": turn.text}
        if turn.sly_data:
            item["sly_data"] = dict(turn.sly_data)
        if index > 0:
            item["continue_conversation"] = True
        if index == len(scenario.interactions) - 1:
            text_checks: dict[str, Any] = {}
            if scenario.expect.answer_contains:
                text_checks["keywords"] = list(scenario.expect.answer_contains)
            if scenario.expect.answer_not_contains:
                text_checks["not_keywords"] = list(scenario.expect.answer_not_contains)
            if text_checks:
                item["response"] = {"text": text_checks}
        interactions.append(item)
    return {
        "agent": agent,
        "connections": connection,
        "success_ratio": success_ratio,
        "timeout_in_seconds": timeout_s,
        "interactions": interactions,
        "crucible": {
            "id": scenario.id,
            "description": scenario.description,
            "route": list(scenario.expect.route),
            "must_not_route": list(scenario.expect.must_not_route),
            "tags": list(scenario.tags),
            "source": scenario.source.value,
        },
    }


def from_neurosan_test(data: dict[str, Any], fallback_id: str = "imported") -> Scenario:
    """Read a Neuro-SAN test case back into a Scenario (keywords become answer expectations)."""
    meta = data.get("crucible") or {}
    turns = data.get("interactions") or []
    contains: list[str] = []
    not_contains: list[str] = []
    for turn in turns:
        text_checks = ((turn.get("response") or {}).get("text")) or {}
        contains.extend(text_checks.get("keywords") or [])
        not_contains.extend(text_checks.get("not_keywords") or [])
    return Scenario(
        id=str(meta.get("id") or fallback_id),
        description=str(meta.get("description") or ""),
        interactions=tuple(Interaction(text=str(t.get("text", "")), sly_data=t.get("sly_data") or {}) for t in turns),
        expect=Expectation(
            route=tuple(meta.get("route") or ()),
            must_not_route=tuple(meta.get("must_not_route") or ()),
            answer_contains=tuple(contains),
            answer_not_contains=tuple(not_contains),
        ),
        tags=tuple(meta.get("tags") or ()),
        source=ScenarioSource(meta.get("source", "hand")),
    )
