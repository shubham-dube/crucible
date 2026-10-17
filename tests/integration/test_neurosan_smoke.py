"""Proves a real Neuro-SAN delegation chain runs in-process, deterministically, with no API keys."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture
def neurosan_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRUCIBLE_FIXTURES", str(FIXTURES))
    from crucible.integrations.neurosan.toolpath import configure_tool_path

    monkeypatch.setenv("PYTHONPATH", "")
    configure_tool_path(FIXTURES / "coded_tools")


def _chat(hocon: Path, text: str, sly_data: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    from neuro_san.client.agent_session_factory import AgentSessionFactory
    from neuro_san.client.streaming_input_processor import StreamingInputProcessor

    session = AgentSessionFactory().create_session("direct", str(hocon), use_direct=True, metadata={"user_id": "t"})
    session.reset()
    sip = StreamingInputProcessor(session=session)
    proc = sip.get_message_processor()
    request = sip.formulate_chat_request(text, sly_data, None, {"chat_filter_type": "MAXIMAL"})
    messages: list[dict[str, Any]] = []
    for resp in session.streaming_chat(request):
        msg = resp.get("response", {})
        messages.append(msg)
        proc.process_message(msg, resp.get("type"))
    return str(proc.get_answer()), messages


@pytest.mark.integration
@pytest.mark.usefixtures("neurosan_env")
def test_front_man_delegates_to_coded_tool() -> None:
    answer, messages = _chat(FIXTURES / "networks" / "smoke_desk.hocon", "where is my order?", {"secret": "x"})

    assert "order A-42 shipped" in answer
    texts = " ".join(str(m.get("text", "")) for m in messages)
    assert "order_lookup" in texts  # delegation edge visible in the MAXIMAL stream
    assert os.environ["AGENT_TOOL_PATH"].endswith("coded_tools")
