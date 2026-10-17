"""Deterministic, keyless chat model for driving Neuro-SAN networks in tests and the bug zoo.

Neuro-SAN builds each agent with LangChain's ``create_agent``, which calls ``bind_tools`` on the model and then
invokes it with the agent's system prompt plus the conversation so far. ``ScriptedChatModel`` answers from an
ordered list of rules instead of calling a provider, so a whole multi-agent network can be exercised
deterministically. Plug it in through ``llm_config``::

    "llm_config": {
        "class": "crucible.integrations.neurosan.scripted_llm.ScriptedChatModel",
        "script_path": "path/to/script.yaml"
    }

Script format (YAML or JSON)::

    rules:
      - when: {system_contains: "billing specialist", first_turn: true}
        respond: {tool_calls: [{name: "lookup_invoice", args: {invoice_id: "INV-1"}}]}
      - when: {system_contains: "billing specialist", after_tool: "lookup_invoice"}
        respond: {text: "Invoice INV-1 is paid. {last_tool_result}"}
    default: {text: "OK"}

Rules are evaluated top to bottom; the first rule whose conditions all hold wins. Placeholders available in
``text`` and string ``args``: ``{last_input}`` (latest human text), ``{last_tool_result}`` (latest tool output).
"""

from __future__ import annotations

import itertools
import json
import os
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import yaml
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel, ConfigDict, Field, model_validator

_call_ids = itertools.count(1)


class ScriptCondition(BaseModel):
    """Conditions that must all hold for a rule to fire."""

    model_config = ConfigDict(extra="forbid")

    system_contains: str | None = None
    last_message_contains: str | None = None
    after_tool: str | None = None
    first_turn: bool | None = None
    tool_available: str | None = None


class ScriptedToolCall(BaseModel):
    """A tool call the model will emit."""

    model_config = ConfigDict(extra="forbid")

    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class ScriptResponse(BaseModel):
    """What the model answers when a rule fires: plain text or tool calls (or both)."""

    model_config = ConfigDict(extra="forbid")

    text: str = ""
    tool_calls: list[ScriptedToolCall] = Field(default_factory=list)


class ScriptRule(BaseModel):
    """One ``when -> respond`` rule."""

    model_config = ConfigDict(extra="forbid")

    when: ScriptCondition = Field(default_factory=ScriptCondition)
    respond: ScriptResponse


class Script(BaseModel):
    """A full script: ordered rules plus a fallback response."""

    model_config = ConfigDict(extra="forbid")

    rules: list[ScriptRule] = Field(default_factory=list)
    default: ScriptResponse = Field(default_factory=lambda: ScriptResponse(text="OK"))

    @classmethod
    def load(cls, path: str | Path) -> Script:
        """Load a script from a YAML or JSON file."""
        raw = Path(path).read_text(encoding="utf-8")
        data = json.loads(raw) if str(path).endswith(".json") else yaml.safe_load(raw)
        return cls.model_validate(data or {})


class _ConversationView:
    """Read-only helpers over the message list LangChain hands to the model."""

    def __init__(self, messages: Sequence[BaseMessage]) -> None:
        self.messages = list(messages)

    @property
    def system_text(self) -> str:
        return "\n".join(_content_text(m) for m in self.messages if isinstance(m, SystemMessage))

    @property
    def last_message(self) -> BaseMessage | None:
        return self.messages[-1] if self.messages else None

    @property
    def last_human_text(self) -> str:
        for message in reversed(self.messages):
            if isinstance(message, HumanMessage):
                return _content_text(message)
        return ""

    @property
    def last_tool_message(self) -> ToolMessage | None:
        last = self.last_message
        return last if isinstance(last, ToolMessage) else None

    @property
    def is_first_turn(self) -> bool:
        return not any(isinstance(m, AIMessage) for m in self.messages)


def _content_text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "".join(parts)


def _matches(cond: ScriptCondition, view: _ConversationView, tool_names: set[str]) -> bool:
    if cond.system_contains is not None and cond.system_contains not in view.system_text:
        return False
    if cond.last_message_contains is not None:
        last = view.last_message
        if last is None or cond.last_message_contains not in _content_text(last):
            return False
    if cond.after_tool is not None:
        tool_msg = view.last_tool_message
        if tool_msg is None or tool_msg.name != cond.after_tool:
            return False
    if cond.first_turn is not None and cond.first_turn != view.is_first_turn:
        return False
    return cond.tool_available is None or cond.tool_available in tool_names


def _fill(template: str, view: _ConversationView) -> str:
    tool_msg = view.last_tool_message
    values = {
        "last_input": view.last_human_text,
        "last_tool_result": _content_text(tool_msg) if tool_msg is not None else "",
    }
    result = template
    for key, value in values.items():
        result = result.replace("{" + key + "}", value)
    return result


def _fill_args(args: Any, view: _ConversationView) -> Any:
    if isinstance(args, str):
        return _fill(args, view)
    if isinstance(args, dict):
        return {k: _fill_args(v, view) for k, v in args.items()}
    if isinstance(args, list):
        return [_fill_args(v, view) for v in args]
    return args


def resolve_script_path(path: str) -> Path:
    """Resolve a script path: absolute, relative to ``$CRUCIBLE_SCRIPT_DIR``, or relative to the cwd."""
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    script_dir = os.environ.get("CRUCIBLE_SCRIPT_DIR")
    if script_dir and (Path(script_dir) / candidate).is_file():
        return Path(script_dir) / candidate
    return candidate


class ScriptedChatModel(BaseChatModel):
    """A LangChain chat model that replies from a deterministic script (see module docstring)."""

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    model_name: str = Field(default="scripted", alias="model")
    script_path: str | None = None
    script: Script | None = None

    @model_validator(mode="after")
    def _load_script(self) -> ScriptedChatModel:
        if self.script is None:
            self.script = Script.load(resolve_script_path(self.script_path)) if self.script_path else Script()
        return self

    @property
    def _llm_type(self) -> str:
        return "crucible-scripted"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model_name": self.model_name, "script_path": self.script_path}

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        """Record the tool schemas so rules can check ``tool_available``; no provider formatting needed."""
        formatted = [convert_to_openai_tool(tool) for tool in tools]
        return super().bind(tools=formatted, **kwargs)

    def respond(self, messages: Sequence[BaseMessage], tool_names: set[str] | None = None) -> AIMessage:
        """Pick the first matching rule and build the AI message it describes."""
        assert self.script is not None  # set by the validator
        view = _ConversationView(messages)
        names = tool_names or set()
        response = next(
            (rule.respond for rule in self.script.rules if _matches(rule.when, view, names)),
            self.script.default,
        )
        text = _fill(response.text, view)
        tool_calls = [
            {
                "name": call.name,
                "args": _fill_args(call.args, view),
                "id": f"call_{next(_call_ids)}",
                "type": "tool_call",
            }
            for call in response.tool_calls
        ]
        prompt_chars = sum(len(_content_text(m)) for m in messages)
        usage = {
            "input_tokens": max(1, prompt_chars // 4),
            "output_tokens": max(1, len(text) // 4),
            "total_tokens": max(1, prompt_chars // 4) + max(1, len(text) // 4),
        }
        return AIMessage(content=text, tool_calls=tool_calls, usage_metadata=usage)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        tools = kwargs.get("tools") or []
        tool_names = {t.get("function", {}).get("name", "") for t in tools if isinstance(t, dict)}
        message = self.respond(messages, tool_names)
        return ChatResult(generations=[ChatGeneration(message=message)])
