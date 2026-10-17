"""Redact tracked sensitive values before traces leave the process (API, dashboard, exports)."""

from __future__ import annotations

from typing import Any

from crucible.domain.trace import LlmCall, LlmMessage, RunResult, Span

MASK = "[REDACTED]"


def _mask_text(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, MASK)
    return text


def _mask_value(value: Any, secrets: list[str]) -> Any:
    if isinstance(value, str):
        return _mask_text(value, secrets)
    if isinstance(value, dict):
        return {k: _mask_value(v, secrets) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_mask_value(v, secrets) for v in value]
    return value


def mask_run(run: RunResult) -> RunResult:
    """Copy of ``run`` with every sensitive value (and planted canary) replaced by [REDACTED]."""
    secrets = sorted({sv.value for sv in run.sensitive}, key=len, reverse=True)
    spans = tuple(
        Span.model_validate(
            {**s.model_dump(), "text": _mask_text(s.text, secrets), "data": _mask_value(s.data, secrets)}
        )
        for s in run.spans
    )
    calls = tuple(
        LlmCall(
            id=c.id,
            agent=c.agent,
            model=c.model,
            t=c.t,
            messages=tuple(LlmMessage(role=m.role, content=_mask_text(m.content, secrets)) for m in c.messages),
        )
        for c in run.llm_calls
    )
    sensitive = tuple(sv.model_copy(update={"value": MASK}) for sv in run.sensitive)
    return run.model_copy(
        update={
            "answer": _mask_text(run.answer, secrets),
            "spans": spans,
            "llm_calls": calls,
            "returned_sly_data": _mask_value(run.returned_sly_data, secrets),
            "sensitive": sensitive,
            "error": _mask_text(run.error, secrets) if run.error else None,
        }
    )
