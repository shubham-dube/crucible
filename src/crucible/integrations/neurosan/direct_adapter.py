"""Run scenarios against a Neuro-SAN network in-process (DirectAgentSession)."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import structlog

from crucible.chaos import catalog
from crucible.chaos import state as chaos_state
from crucible.domain.chaos import FaultKind, parse_fault
from crucible.domain.network import NetworkGraph
from crucible.domain.trace import LlmCall, RunResult, RunStatus
from crucible.execution.ports import RunRequest
from crucible.integrations.neurosan.loader import load_network
from crucible.integrations.neurosan.normalise import Normaliser
from crucible.integrations.neurosan.prompt_capture import PromptCapture

log = structlog.get_logger(__name__)

TIMEOUT_MARKERS = ("Agent timed out", "max_execution_seconds")
ERROR_MARKERS = ("Agent stopped due to exception", "Error from ")
_GRACE_S = 5.0
_MAX_DRAIN_S = 120.0


def attribute_calls(calls: list[LlmCall], graph: NetworkGraph) -> list[LlmCall]:
    """Name the agent behind each LLM call by matching its system prompt against agent instructions."""
    candidates = [(n.name, n.instructions.strip()[:200]) for n in graph.nodes.values() if n.instructions.strip()]
    out = []
    for call in calls:
        system = "\n".join(m.content for m in call.messages if m.role == "system")
        matches = [(len(snippet), name) for name, snippet in candidates if snippet and snippet in system]
        out.append(call.model_copy(update={"agent": max(matches)[1]}) if matches else call)
    return out


class NeuroSanDirectAdapter:
    """Executes scenarios in this process. Coded-tool paths must already be configured (``Project.activate``)."""

    name = "neurosan-direct"

    def __init__(self, network_path: str | Path, metadata: dict[str, Any] | None = None) -> None:
        self.network_path = Path(network_path).resolve()
        self.graph = load_network(self.network_path).graph
        self.metadata = metadata or {"user_id": "crucible"}
        from crucible.integrations.neurosan import chaos_prepper

        chaos_prepper.register()  # must precede session creation; inert unless a chaos plan is active
        # Creating a DirectAgentSession costs ~3s (manifest + network load); a chat on it costs ~30ms.
        # Reuse one session (reset per turn) and drop it after a timeout or failure.
        self._session: Any = None

    def _get_session(self) -> Any:
        from neuro_san.client.agent_session_factory import AgentSessionFactory

        if self._session is None:
            self._session = AgentSessionFactory().create_session(
                "direct", str(self.network_path), use_direct=True, metadata=self.metadata
            )
        return self._session

    def _drain_seconds(self) -> float:
        """How long to wait for a timed-out request to stop by itself."""
        budget = self.graph.limits.max_execution_seconds or 30.0
        return min(budget + _GRACE_S, _MAX_DRAIN_S)

    def invalidate(self) -> None:
        """Forget the cached session (e.g. after changing process-level chaos configuration)."""
        session, self._session = self._session, None
        if session is not None:
            try:
                session.close()
            except Exception:  # best effort
                log.debug("session close failed")

    def run(self, request: RunRequest) -> RunResult:
        """Run all turns of the scenario (with any requested chaos); never raises for target failures."""
        normaliser = Normaliser()
        state: dict[str, Any] = {"error": None}
        start = time.monotonic()

        def worker() -> None:
            from neuro_san.client.streaming_input_processor import StreamingInputProcessor

            try:
                session = self._get_session()
                chat_context: dict[str, Any] | None = None
                for turn_index, turn in enumerate(request.scenario.interactions):
                    session.reset()
                    sip = StreamingInputProcessor(session=session)
                    chat_request = sip.formulate_chat_request(
                        turn.text, dict(turn.sly_data), chat_context, {"chat_filter_type": "MAXIMAL"}
                    )
                    for response in session.streaming_chat(chat_request):
                        normaliser.feed(response.get("response") or {}, turn_index, time.monotonic() - start)
                    chat_context = normaliser.chat_context
            except Exception as exc:  # target-side failure: report, do not raise
                state["error"] = f"{type(exc).__name__}: {exc}"

        faults = [parse_fault(f) for f in request.chaos]
        marker = catalog.new_marker() if any(f.kind is FaultKind.INJECTED_INSTRUCTION for f in faults) else None
        plan = chaos_state.activate(faults, seed=request.run_id, marker=marker) if faults else None
        try:
            with PromptCapture() as capture:
                timed_out = self._execute(worker, request)
        finally:
            chaos_state.deactivate()
        duration = time.monotonic() - start
        if state["error"]:
            self.invalidate()

        status = RunStatus.OK
        if timed_out or any(m in normaliser.answer for m in TIMEOUT_MARKERS):
            status = RunStatus.TIMEOUT
        elif state["error"] or any(normaliser.answer.startswith(m) for m in ERROR_MARKERS):
            status = RunStatus.ERROR
        return RunResult(
            run_id=request.run_id,
            target=request.target,
            scenario_id=request.scenario.id,
            repetition=request.repetition,
            status=status,
            answer=normaliser.answer,
            returned_sly_data=normaliser.returned_sly_data,
            spans=tuple(normaliser.spans),
            llm_calls=tuple(attribute_calls(capture.calls, self.graph)),
            tokens=normaliser.tokens,
            duration_s=round(duration, 3),
            error=state["error"] or (f"hard timeout after {request.timeout_s}s" if timed_out else None),
            sensitive=request.sensitive,
            chaos=request.chaos,
            chaos_fired=tuple(plan.fired) if plan is not None else (),
        )

    def _execute(self, worker: Any, request: RunRequest) -> bool:
        """Run ``worker`` on a thread under the hard timeout; returns True if it timed out."""
        thread = threading.Thread(target=worker, name=f"crucible-run-{request.run_id}", daemon=True)
        thread.start()
        thread.join(request.timeout_s)
        if not thread.is_alive():
            return False
        # Abandon (do not close) the session: closing a DirectAgentSession shuts down executor queues that Neuro-SAN
        # shares with sessions created afterwards (QueueShutDown in the next run). The runaway request is still
        # bounded by the network's own max_execution_seconds, so wait (bounded) for it to drain; otherwise it
        # interferes with the next run in this process. See ADR 0002.
        self._session = None
        thread.join(self._drain_seconds())
        if thread.is_alive():
            log.warning("runaway request still running; later runs may be affected", run_id=request.run_id)
        return True
