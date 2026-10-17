"""Convert Neuro-SAN MAXIMAL ChatMessage dicts into Crucible spans."""

from __future__ import annotations

from typing import Any

from crucible.domain.trace import Span, SpanKind, TokenUsage, agent_of

__all__ = ["Normaliser", "agent_of", "origin_path"]

# neuro_san.message.types.chat_message_type values
SYSTEM, HUMAN, AI, AGENT, AGENT_FRAMEWORK, AGENT_TOOL_RESULT, AGENT_PROGRESS = 1, 2, 4, 100, 101, 103, 104


def origin_path(origin: Any) -> tuple[str, ...]:
    """[{tool, instantiation_index}, ...] -> ('tool#idx', ...)."""
    if not isinstance(origin, list):
        return ()
    return tuple(f"{o.get('tool')}#{o.get('instantiation_index', 1)}" for o in origin if isinstance(o, dict))


def _clean_args(args: Any) -> dict[str, Any]:
    if not isinstance(args, dict):
        return {}
    hidden = {"origin", "origin_str", "progress_reporter", "reservationist"}
    return {k: v for k, v in args.items() if k not in hidden}


class Normaliser:
    """Stateful converter; feed messages in order, then read ``spans``, ``answer`` and ``tokens``."""

    def __init__(self) -> None:
        self.spans: list[Span] = []
        self.answer: str = ""
        self.returned_sly_data: dict[str, Any] = {}
        self.chat_context: dict[str, Any] | None = None
        self._front_tokens: TokenUsage = TokenUsage()

    @property
    def tokens(self) -> TokenUsage:
        """Token usage reported for the front man (whole request)."""
        return self._front_tokens

    def _add(self, kind: SpanKind, path: tuple[str, ...], text: str, turn: int, t: float, **kw: Any) -> None:
        self.spans.append(
            Span(
                id=f"s{len(self.spans) + 1}",
                seq=len(self.spans) + 1,
                kind=kind,
                agent=kw.pop("agent", agent_of(path)),
                origin=path,
                text=text,
                turn=turn,
                t=round(t, 4),
                **kw,
            )
        )

    def feed(self, message: dict[str, Any], turn: int = 0, t: float = 0.0) -> None:
        """Consume one ChatMessage dict."""
        if not message:
            return
        mtype = message.get("type")
        path = origin_path(message.get("origin"))
        text = str(message.get("text") or "")
        raw_structure = message.get("structure")
        structure: dict[str, Any] = raw_structure if isinstance(raw_structure, dict) else {}
        if mtype == SYSTEM:
            self._add(SpanKind.SYSTEM_PROMPT, path, text, turn, t)
        elif mtype == HUMAN:
            self._add(SpanKind.USER_INPUT, path, text, turn, t)
        elif mtype == AI:
            self._add(SpanKind.LLM_OUTPUT, path, text, turn, t)
        elif mtype == AGENT_TOOL_RESULT:
            source = agent_of(origin_path(message.get("tool_result_origin")))
            self._add(SpanKind.TOOL_RETURN, path, text, turn, t, target=source)
        elif mtype == AGENT_FRAMEWORK:
            self.answer = text
            if isinstance(message.get("sly_data"), dict):
                self.returned_sly_data = dict(message["sly_data"])
            if isinstance(message.get("chat_context"), dict):
                self.chat_context = message["chat_context"]
            self._add(SpanKind.FINAL_ANSWER, path, text, turn, t)
        elif mtype == AGENT:
            self._feed_agent(path, text, structure, turn, t)

    def _feed_agent(self, path: tuple[str, ...], text: str, st: dict[str, Any], turn: int, t: float) -> None:
        if st.get("invoking_start"):
            self._add(
                SpanKind.DELEGATION,
                path,
                text,
                turn,
                t,
                target=st.get("invoked_agent_name"),
                data={"params": _clean_args(st.get("params"))},
            )
        elif st.get("tool_start"):
            self._add(SpanKind.TOOL_ARGS, path, text, turn, t, data={"args": _clean_args(st.get("tool_args"))})
        elif st.get("tool_end"):
            kind = SpanKind.TOOL_ERROR if st.get("tool_error") else SpanKind.TOOL_RESULT
            self._add(kind, path, str(st.get("tool_output", "")), turn, t)
        elif "total_tokens" in st:
            usage = TokenUsage(
                total=int(st.get("total_tokens") or 0),
                prompt=int(st.get("prompt_tokens") or 0),
                completion=int(st.get("completion_tokens") or 0),
                cost_usd=float(st.get("total_cost") or 0.0),
            )
            if len(path) <= 1 and usage.total >= self._front_tokens.total:
                self._front_tokens = usage
            self._add(SpanKind.TOKENS, path, "", turn, t, data=usage.model_dump())
        elif text.strip():
            self._add(SpanKind.FRAMEWORK, path, text.strip()[:2000], turn, t)
