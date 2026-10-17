"""Terminal rendering helpers for CLI commands."""

from __future__ import annotations

import io

from rich.console import Console
from rich.table import Table

from crucible.domain.trace import RunBatch, SpanKind


def render_batch(batch: RunBatch) -> str:
    """One row per run: status, delegations, tool errors, LLM calls, tokens, time, answer."""
    buffer = io.StringIO()
    console = Console(file=buffer, width=150, force_terminal=False, color_system=None)
    table = Table(title=f"{batch.target}  ({batch.batch_id})", expand=True)
    for column in ("scenario", "rep", "status", "deleg.", "tool err", "llm calls", "tokens", "secs", "answer"):
        table.add_column(column, no_wrap=column != "answer")
    for r in batch.runs:
        table.add_row(
            r.scenario_id,
            str(r.repetition),
            r.status.value,
            str(len(r.delegations())),
            str(len(r.spans_of(SpanKind.TOOL_ERROR))),
            str(len(r.llm_calls)),
            str(r.tokens.total),
            f"{r.duration_s:.1f}",
            (r.answer or r.error or "")[:90].replace("\n", " "),
        )
    console.print(table)
    return buffer.getvalue()
