"""Run scenario suites against a target through a ``TargetAdapter``."""

from __future__ import annotations

import secrets
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

import structlog

from crucible.domain.scenario import Scenario
from crucible.domain.trace import RunBatch, RunResult
from crucible.execution.canaries import plant
from crucible.execution.ports import RunRequest, TargetAdapter

log = structlog.get_logger(__name__)


def new_id(prefix: str) -> str:
    """Sortable, unique id: prefix-YYYYmmddHHMMSS-hex."""
    return f"{prefix}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(3)}"


class Runner:
    """Executes scenarios x repetitions sequentially (prompt capture is process-global, see prompt_capture)."""

    def __init__(self, adapter: TargetAdapter, timeout_s: float = 120.0, chaos: Sequence[str] = ()) -> None:
        self.adapter = adapter
        self.timeout_s = timeout_s
        self.chaos = tuple(chaos)

    def run(
        self,
        target: str,
        scenarios: Sequence[Scenario],
        repetitions: int = 1,
        on_result: Callable[[RunResult], None] | None = None,
        meta: dict[str, object] | None = None,
    ) -> RunBatch:
        """Run every scenario ``repetitions`` times; return the batch."""
        batch_id = new_id("batch")
        started = datetime.now(UTC).isoformat()
        results: list[RunResult] = []
        for scenario in scenarios:
            for rep in range(repetitions):
                planted, sensitive = plant(scenario)
                request = RunRequest(
                    run_id=f"{batch_id}-{scenario.id}-{rep}",
                    target=target,
                    scenario=planted,
                    repetition=rep,
                    sensitive=sensitive,
                    timeout_s=self.timeout_s,
                    chaos=self.chaos,
                )
                result = self.adapter.run(request)
                log.info("run finished", scenario=scenario.id, rep=rep, status=result.status.value)
                results.append(result)
                if on_result is not None:
                    on_result(result)
        network_path = getattr(self.adapter, "network_path", None)
        graph = getattr(self.adapter, "graph", None)
        return RunBatch(
            batch_id=batch_id,
            target=target,
            network_path=str(network_path) if network_path else None,
            config_hash=getattr(graph, "config_hash", None),
            started_at=started,
            runs=tuple(results),
            meta=dict(meta or {}),
        )
