"""Unit tests for the deterministic scripted chat model."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from crucible.integrations.neurosan.scripted_llm import Script, ScriptedChatModel


def _model(script: dict[str, object]) -> ScriptedChatModel:
    return ScriptedChatModel(script=Script.model_validate(script))


def test_first_matching_rule_emits_tool_call() -> None:
    model = _model(
        {
            "rules": [
                {"when": {"system_contains": "billing"}, "respond": {"tool_calls": [{"name": "lookup", "args": {}}]}},
                {"when": {}, "respond": {"text": "never"}},
            ]
        }
    )
    reply = model.invoke([SystemMessage("You are billing."), HumanMessage("hi")])

    assert isinstance(reply, AIMessage)
    assert [c["name"] for c in reply.tool_calls] == ["lookup"]


def test_after_tool_rule_fills_placeholders() -> None:
    model = _model(
        {"rules": [{"when": {"after_tool": "lookup"}, "respond": {"text": "got {last_tool_result} for {last_input}"}}]}
    )
    messages = [
        SystemMessage("sys"),
        HumanMessage("order 7"),
        AIMessage("", tool_calls=[{"name": "lookup", "args": {}, "id": "c1"}]),
        ToolMessage("paid", tool_call_id="c1", name="lookup"),
    ]

    assert model.invoke(messages).content == "got paid for order 7"


def test_first_turn_condition() -> None:
    model = _model(
        {"rules": [{"when": {"first_turn": True}, "respond": {"text": "first"}}], "default": {"text": "later"}}
    )

    assert model.invoke([HumanMessage("a")]).content == "first"
    assert model.invoke([HumanMessage("a"), AIMessage("x"), HumanMessage("b")]).content == "later"


def test_args_templating_is_recursive() -> None:
    model = _model(
        {
            "rules": [
                {"respond": {"tool_calls": [{"name": "t", "args": {"q": "{last_input}", "n": [1, "{last_input}"]}}]}}
            ]
        }
    )
    reply = model.invoke([HumanMessage("abc")])

    assert isinstance(reply, AIMessage)
    assert reply.tool_calls[0]["args"] == {"q": "abc", "n": [1, "abc"]}


def test_tool_available_uses_bound_tools() -> None:
    model = _model({"rules": [{"when": {"tool_available": "search"}, "respond": {"text": "can search"}}]})

    def search(query: str) -> str:
        """Search things."""
        return query

    assert model.bind_tools([search]).invoke([HumanMessage("x")]).content == "can search"
    assert model.invoke([HumanMessage("x")]).content == "OK"


def test_load_yaml_script(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "s.yaml"
    path.write_text("rules:\n  - respond: {text: hi}\n", encoding="utf-8")

    assert ScriptedChatModel(script_path=str(path)).invoke([HumanMessage("x")]).content == "hi"
