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

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.tracers.context import register_configure_hook

from crucible.domain.trace import LlmCall, LlmMessage


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
            )


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

    def record(self, messages: list[LlmMessage], model: str | None = None) -> None:
        """Store one captured call."""
        with self._lock:
            self.calls.append(
                LlmCall(
                    id=f"llm{len(self.calls) + 1}",
                    model=model,
                    messages=tuple(messages),
                    t=round(time.monotonic() - self._start, 4),
                )
            )
