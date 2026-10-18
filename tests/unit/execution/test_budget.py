"""Spend ledger and budget guard."""

from __future__ import annotations

from pathlib import Path

import pytest

from crucible.domain.errors import BudgetExceededError
from crucible.domain.trace import TokenUsage
from crucible.execution.budget import BudgetGuard, SpendLedger, default_guard, describe_spend

PRICED = TokenUsage(total=150, prompt=100, completion=50, cost_usd=0.01)


def test_unpriced_runs_are_not_recorded(tmp_path: Path) -> None:
    ledger = SpendLedger(tmp_path / "spend.jsonl")
    assert ledger.record("run", "r1", TokenUsage(total=10)) is None
    assert not ledger.path.exists()


def test_ledger_totals_accumulate_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "spend.jsonl"
    SpendLedger(path).record("run", "r1", PRICED, calls=2)
    ledger = SpendLedger(path)
    ledger.record("agentic", "t", PRICED)
    total = ledger.totals()
    assert (total.entries, total.calls, total.tokens) == (2, 2, 300)
    assert total.cost_usd == pytest.approx(0.02)
    assert ledger.process.cost_usd == pytest.approx(0.01)


def test_guard_stops_at_usd_and_call_limits(tmp_path: Path) -> None:
    ledger = SpendLedger(tmp_path / "spend.jsonl")
    BudgetGuard(ledger).ensure()  # no limits
    guard = BudgetGuard(ledger, max_usd=0.015)
    guard.charge("run", "r1", PRICED, calls=3)
    guard.ensure()
    guard.charge("run", "r2", PRICED, calls=3)
    with pytest.raises(BudgetExceededError, match="budget reached"):
        guard.ensure()
    with pytest.raises(BudgetExceededError, match="call budget"):
        BudgetGuard(ledger, max_calls=6).ensure()


def test_default_guard_reads_settings(crucible_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from crucible.config import get_settings

    monkeypatch.setenv("CRUCIBLE_LLM_BUDGET_USD", "2.5")
    get_settings.cache_clear()
    guard = default_guard()
    assert guard.max_usd == 2.5
    assert guard.ledger.path == (crucible_home / "llm_spend.jsonl").resolve()
    assert describe_spend(0.01, 88.0) == "$0.0100 (₹0.88)"
