"""Live-LLM spend accounting and a hard budget stop.

Costs come from Neuro-SAN's token accounting (its per-model price table), so only *priced* runs are recorded:
scripted (keyless) runs cost nothing and never touch the ledger. The ledger is cumulative across processes so a
budget spans a whole testing session, not one command; delete the file to start over.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from crucible.domain.errors import BudgetExceededError
from crucible.domain.trace import TokenUsage

LEDGER_FILE = "llm_spend.jsonl"


class SpendEntry(BaseModel):
    """One priced unit of work (a scenario run or an agentic session)."""

    model_config = ConfigDict(frozen=True)

    at: str
    source: str
    ref: str
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0


class SpendTotals(BaseModel):
    """Aggregated spend."""

    model_config = ConfigDict(frozen=True)

    entries: int = 0
    calls: int = 0
    tokens: int = 0
    cost_usd: float = 0.0


class SpendLedger:
    """Append-only JSONL ledger; also tracks what this process spent."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.process = SpendTotals()

    def record(self, source: str, ref: str, tokens: TokenUsage, calls: int = 0) -> SpendEntry | None:
        """Append an entry for a priced run; unpriced (keyless) runs are ignored."""
        if tokens.cost_usd <= 0:
            return None
        entry = SpendEntry(
            at=datetime.now(UTC).isoformat(),
            source=source,
            ref=ref,
            calls=calls,
            prompt_tokens=tokens.prompt,
            completion_tokens=tokens.completion,
            cost_usd=tokens.cost_usd,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(entry.model_dump_json() + "\n")
        self.process = _add(self.process, entry)
        return entry

    def totals(self) -> SpendTotals:
        """Everything recorded in the ledger file."""
        total = SpendTotals()
        if not self.path.is_file():
            return total
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                total = _add(total, SpendEntry.model_validate(json.loads(line)))
        return total


def _add(total: SpendTotals, entry: SpendEntry) -> SpendTotals:
    return SpendTotals(
        entries=total.entries + 1,
        calls=total.calls + entry.calls,
        tokens=total.tokens + entry.prompt_tokens + entry.completion_tokens,
        cost_usd=total.cost_usd + entry.cost_usd,
    )


class BudgetGuard:
    """Refuses to start more live work once the ledger reaches the configured limits."""

    def __init__(self, ledger: SpendLedger, max_usd: float | None = None, max_calls: int | None = None) -> None:
        self.ledger = ledger
        self.max_usd = max_usd
        self.max_calls = max_calls

    def ensure(self) -> None:
        """Raise ``BudgetExceededError`` if a limit is reached."""
        if self.max_usd is None and self.max_calls is None:
            return
        total = self.ledger.totals()
        if self.max_usd is not None and total.cost_usd >= self.max_usd:
            raise BudgetExceededError(
                f"LLM budget reached: ${total.cost_usd:.4f} of ${self.max_usd:.4f} ({self.ledger.path})"
            )
        if self.max_calls is not None and total.calls >= self.max_calls:
            raise BudgetExceededError(f"LLM call budget reached: {total.calls} of {self.max_calls}")

    def charge(self, source: str, ref: str, tokens: TokenUsage, calls: int = 0) -> None:
        """Record spend for finished work."""
        self.ledger.record(source, ref, tokens, calls)


_guards: dict[Path, BudgetGuard] = {}


def default_guard() -> BudgetGuard:
    """The process guard for ``$CRUCIBLE_HOME`` with limits from settings."""
    from crucible.config import get_settings

    settings = get_settings()
    path = (Path(settings.home) / LEDGER_FILE).resolve()
    guard = _guards.get(path)
    if guard is None:
        guard = _guards[path] = BudgetGuard(SpendLedger(path))
    guard.max_usd = settings.llm_budget_usd
    guard.max_calls = settings.llm_budget_calls
    return guard


def describe_spend(usd: float, usd_inr: float) -> str:
    """``$0.0123 (₹1.08)``."""
    return f"${usd:.4f} (₹{usd * usd_inr:.2f})"
