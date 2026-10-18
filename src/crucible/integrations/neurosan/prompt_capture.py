"""Capture the exact input of every LLM call made in-process (LangChain configure hook).

Neuro-SAN's message stream shows LLM *outputs* but not the prompts. A process-wide callback registered with
LangChain's ``register_configure_hook`` sees every chat model invocation. Capture sessions are serialised with a
lock so captured calls can be attributed to the run that made them.
"""

from __future__ import annotations

import threading
import time
from contextvars import ContextVar
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.tracers.context import register_configure_hook

from crucible.domain.trace import LlmCall, LlmMessage, TokenUsage


def _content(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict):
            parts.append(str(block.get("text") or block.get("content") or ""))
    return "".join(parts)


class _CaptureHandler(BaseCallbackHandler):
    """Appends every chat-model input to the active capture, if any."""

    def __init__(self) -> None:
        self.active: PromptCapture | None = None

    def on_chat_model_start(
        self, serialized: dict[str, Any], messages: list[list[BaseMessage]], **kwargs: Any
    ) -> None:
        capture = self.active
        if capture is None:
            return
        metadata = kwargs.get("metadata") or {}
        for batch in messages:
            capture.record(
                [LlmMessage(role=m.type, content=_content(m)) for m in batch],
                model=metadata.get("ls_model_name"),
                run_id=kwargs.get("run_id"),
            )

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        """Per-call usage, so cost is known even when a run never reaches Neuro-SAN's final token report."""
        capture = self.active
        run_id = kwargs.get("run_id")
        if capture is None or run_id is None:
            return
        from crucible.integrations.neurosan.pricing import usage_of

        prompt, completion, model = usage_of(response)
        if prompt or completion:
            capture.add_usage(run_id, prompt, completion, model)


_HANDLER = _CaptureHandler()
_state = {"installed": False}
_install_lock = threading.Lock()
_session_lock = threading.Lock()


def install() -> None:
    """Register the hook once per process."""
    with _install_lock:
        if not _state["installed"]:
            register_configure_hook(ContextVar("crucible_prompt_capture", default=_HANDLER), inheritable=True)
            _state["installed"] = True


class PromptCapture:
    """Context manager collecting LLM inputs for one run. Only one capture is active at a time."""

    def __init__(self) -> None:
        self.calls: list[LlmCall] = []
        self._by_run: dict[UUID, int] = {}
        self._start = 0.0
        self._lock = threading.Lock()

    def __enter__(self) -> PromptCapture:
        install()
        _session_lock.acquire()
        self._start = time.monotonic()
        _HANDLER.active = self
        return self

    def __exit__(self, *exc: object) -> None:
        _HANDLER.active = None
        _session_lock.release()

    def record(self, messages: list[LlmMessage], model: str | None = None, run_id: UUID | None = None) -> None:
        """Store one captured call."""
        with self._lock:
            if run_id is not None:
                self._by_run[run_id] = len(self.calls)
            self.calls.append(
                LlmCall(
                    id=f"llm{len(self.calls) + 1}",
                    model=model,
                    messages=tuple(messages),
                    t=round(time.monotonic() - self._start, 4),
                )
            )

    def add_usage(self, run_id: UUID, prompt_tokens: int, completion_tokens: int, model: str = "") -> None:
        """Attach token usage (and its price) to the call LangChain identified by ``run_id``."""
        from crucible.integrations.neurosan.pricing import cost_usd

        with self._lock:
            index = self._by_run.pop(run_id, None)
            if index is None:
                return
            call = self.calls[index]
            name = model or call.model
            self.calls[index] = call.model_copy(
                update={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "cost_usd": cost_usd(name, prompt_tokens, completion_tokens),
                }
            )

    def usage(self) -> TokenUsage:
        """Sum of per-call usage captured so far."""
        with self._lock:
            prompt = sum(c.prompt_tokens for c in self.calls)
            completion = sum(c.completion_tokens for c in self.calls)
            return TokenUsage(
                total=prompt + completion,
                prompt=prompt,
                completion=completion,
                cost_usd=sum(c.cost_usd for c in self.calls),
            )
