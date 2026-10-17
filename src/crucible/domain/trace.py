"""Execution traces: what happened inside the target network during one scenario run."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SpanKind(StrEnum):
    """Kinds of observable events in a run."""

    SYSTEM_PROMPT = "system_prompt"
    USER_INPUT = "user_input"
    DELEGATION = "delegation"  # agent decided to call a tool/agent (with LLM-chosen params)
    TOOL_ARGS = "tool_args"  # callee received its arguments
    TOOL_RESULT = "tool_result"  # callee finished successfully
    TOOL_ERROR = "tool_error"  # callee failed
    TOOL_RETURN = "tool_return"  # callee output delivered back into the caller's LLM context
    LLM_OUTPUT = "llm_output"
    TOKENS = "tokens"
    FRAMEWORK = "framework"  # other framework notices
    FINAL_ANSWER = "final_answer"


class Span(BaseModel):
    """One event. ``origin`` is the delegation path, e.g. ('helpdesk#1', 'billing_expert#2')."""

    model_config = ConfigDict(frozen=True)

    id: str
    seq: int
    kind: SpanKind
    agent: str | None = None
    origin: tuple[str, ...] = ()
    target: str | None = Field(default=None, description="callee for DELEGATION, source tool for TOOL_RETURN")
    text: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    turn: int = 0
    t: float = Field(default=0.0, description="seconds since run start")


class LlmMessage(BaseModel):
    """One message of an LLM input."""

    model_config = ConfigDict(frozen=True)

    role: str
    content: str


class LlmCall(BaseModel):
    """The exact input of one model call, attributed to an agent when possible."""

    model_config = ConfigDict(frozen=True)

    id: str
    agent: str | None = None
    model: str | None = None
    messages: tuple[LlmMessage, ...] = ()
    t: float = 0.0

    @property
    def text(self) -> str:
        """All message contents concatenated (for scanning)."""
        return "\n".join(m.content for m in self.messages)


class TokenUsage(BaseModel):
    """Token accounting for a run."""

    model_config = ConfigDict(frozen=True)

    total: int = 0
    prompt: int = 0
    completion: int = 0
    cost_usd: float = 0.0


class RunStatus(StrEnum):
    """Outcome of executing a scenario (not whether it passed judging)."""

    OK = "ok"
    TIMEOUT = "timeout"
    ERROR = "error"


class SensitiveValue(BaseModel):
    """A value that must never leave sly_data (a planted canary or a scenario-provided secret)."""

    model_config = ConfigDict(frozen=True)

    key: str
    value: str
    planted: bool = False


class RunResult(BaseModel):
    """Everything observed while running one scenario repetition."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    target: str
    scenario_id: str
    repetition: int = 0
    status: RunStatus = RunStatus.OK
    answer: str = ""
    returned_sly_data: dict[str, Any] = Field(default_factory=dict)
    spans: tuple[Span, ...] = ()
    llm_calls: tuple[LlmCall, ...] = ()
    tokens: TokenUsage = Field(default_factory=TokenUsage)
    duration_s: float = 0.0
    error: str | None = None
    sensitive: tuple[SensitiveValue, ...] = ()
    chaos: tuple[str, ...] = Field(default=(), description="fault ids active during this run")

    def spans_of(self, *kinds: SpanKind) -> list[Span]:
        """Spans of the given kinds in order."""
        return [s for s in self.spans if s.kind in kinds]

    def delegations(self) -> list[tuple[str | None, str | None]]:
        """(caller, callee) pairs in order."""
        return [(s.agent, s.target) for s in self.spans if s.kind is SpanKind.DELEGATION]


class RunBatch(BaseModel):
    """Results of running a set of scenarios against one target."""

    model_config = ConfigDict(frozen=True)

    batch_id: str
    target: str
    network_path: str | None = None
    config_hash: str | None = None
    started_at: str
    runs: tuple[RunResult, ...] = ()
    meta: dict[str, Any] = Field(default_factory=dict)
