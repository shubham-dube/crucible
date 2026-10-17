"""Judges analyse run traces. Importing this package registers the built-in judges."""

from crucible.judges import injection, leak, routing, tool_judges, trace_judges
from crucible.judges.base import Budgets, Judge, JudgeContext, JudgeRegistry, judge_registry

__all__ = [
    "Budgets",
    "Judge",
    "JudgeContext",
    "JudgeRegistry",
    "injection",
    "judge_registry",
    "leak",
    "routing",
    "tool_judges",
    "trace_judges",
]
