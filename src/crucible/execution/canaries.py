"""Sensitive values: secrets provided in scenario sly_data plus planted canaries."""

from __future__ import annotations

import secrets
from typing import Any

from crucible.domain.scenario import Interaction, Scenario
from crucible.domain.trace import SensitiveValue

CANARY_KEY = "crucible_canary"
MIN_TRACKED_LENGTH = 6


def new_canary() -> str:
    """A unique, unmistakable marker value."""
    return f"CRUCIBLE-CANARY-{secrets.token_hex(6).upper()}"


def _walk(prefix: str, value: Any) -> list[SensitiveValue]:
    if isinstance(value, str):
        return [SensitiveValue(key=prefix, value=value)] if len(value) >= MIN_TRACKED_LENGTH else []
    if isinstance(value, dict):
        return [sv for k, v in value.items() for sv in _walk(f"{prefix}.{k}" if prefix else str(k), v)]
    if isinstance(value, list):
        return [sv for i, v in enumerate(value) for sv in _walk(f"{prefix}[{i}]", v)]
    return []


def plant(scenario: Scenario, canary: str | None = None) -> tuple[Scenario, tuple[SensitiveValue, ...]]:
    """Add a canary key to every turn's sly_data and collect all sensitive values to watch for."""
    marker = canary or new_canary()
    tracked: dict[str, SensitiveValue] = {}
    turns = []
    for turn in scenario.interactions:
        for sv in _walk("", turn.sly_data):
            tracked.setdefault(sv.value, sv)
        turns.append(Interaction(text=turn.text, sly_data={**turn.sly_data, CANARY_KEY: marker}))
    tracked[marker] = SensitiveValue(key=CANARY_KEY, value=marker, planted=True)
    return scenario.model_copy(update={"interactions": tuple(turns)}), tuple(tracked.values())
