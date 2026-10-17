"""Process-global chaos plan consulted by framework hooks during a run (runs are serialised per process)."""

from __future__ import annotations

import random
import threading
from collections.abc import Sequence
from dataclasses import dataclass, field

from crucible.domain.chaos import FaultSpec


@dataclass
class ActivePlan:
    """Faults active for the current run, with a seeded RNG and a log of what fired."""

    faults: tuple[FaultSpec, ...]
    rng: random.Random
    marker: str | None = None
    fired: list[str] = field(default_factory=list)

    def select(self, agent: str) -> FaultSpec | None:
        """First fault targeting ``agent`` whose probability roll succeeds."""
        for fault in self.faults:
            if fault.applies_to(agent) and self.rng.random() < fault.probability:
                return fault
        return None

    def targets(self, agent: str) -> bool:
        """Whether any fault could apply to ``agent``."""
        return any(f.applies_to(agent) for f in self.faults)


_lock = threading.Lock()
_active: ActivePlan | None = None


def activate(faults: Sequence[FaultSpec], seed: str, marker: str | None = None) -> ActivePlan:
    """Install a plan for the current run."""
    global _active  # noqa: PLW0603 - deliberate process-global, guarded by _lock
    plan = ActivePlan(faults=tuple(faults), rng=random.Random(seed), marker=marker)
    with _lock:
        _active = plan
    return plan


def deactivate() -> None:
    """Remove the active plan."""
    global _active  # noqa: PLW0603
    with _lock:
        _active = None


def current() -> ActivePlan | None:
    """The plan for the run in progress, if any."""
    return _active


def record(plan: ActivePlan, entry: str) -> None:
    """Append to the fired log (thread-safe)."""
    with _lock:
        plan.fired.append(entry)
