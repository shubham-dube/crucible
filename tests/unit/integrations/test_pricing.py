"""Per-call usage capture and pricing (Neuro-SAN's price table)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from crucible.domain.trace import LlmMessage, TokenUsage
from crucible.integrations.neurosan.direct_adapter import best_usage
from crucible.integrations.neurosan.pricing import cost_usd
from crucible.integrations.neurosan.prompt_capture import PromptCapture


def test_cost_uses_neurosan_prices_and_is_zero_for_unpriced_models() -> None:
    # gemini-3.5-flash-lite: $0.0003 / 1k input, $0.0025 / 1k output
    assert cost_usd("models/gemini-3.5-flash-lite", 1000, 1000) == pytest.approx(0.0028)
    assert cost_usd("scripted", 1000, 1000) == 0.0
    assert cost_usd(None, 10, 10) == 0.0


def test_capture_attaches_usage_by_run_id() -> None:
    capture = PromptCapture()
    first, second = uuid4(), uuid4()
    capture.record([LlmMessage(role="human", content="hi")], model="gemini-3.5-flash-lite", run_id=first)
    capture.record([LlmMessage(role="human", content="again")], model="gemini-3.5-flash-lite", run_id=second)
    capture.add_usage(second, 1000, 0)
    capture.add_usage(first, 0, 1000, "gemini-3.5-flash-lite")
    capture.add_usage(uuid4(), 5, 5)  # unknown run id: ignored
    usage = capture.usage()
    assert (usage.prompt, usage.completion, usage.total) == (1000, 1000, 2000)
    assert usage.cost_usd == pytest.approx(0.0028)


def test_best_usage_prefers_captured_when_the_run_never_reported() -> None:
    reported = TokenUsage(total=186, prompt=162, completion=24, cost_usd=0.0001)
    captured = TokenUsage(total=50_000, prompt=45_000, completion=5_000, cost_usd=0.03)
    assert best_usage(reported, captured) == captured
    assert best_usage(captured, reported) == captured
