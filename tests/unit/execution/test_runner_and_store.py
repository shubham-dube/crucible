"""Runner orchestration with a fake adapter, canary planting and the file store."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.helpers import agent, make_graph

from crucible.domain.errors import CrucibleError
from crucible.domain.scenario import Interaction, Scenario
from crucible.domain.trace import LlmCall, LlmMessage, RunResult
from crucible.execution.canaries import CANARY_KEY, plant
from crucible.execution.ports import RunRequest
from crucible.execution.runner import Runner
from crucible.integrations.neurosan.direct_adapter import attribute_calls
from crucible.storage.run_store import FileRunStore


class FakeAdapter:
    name = "fake"

    def __init__(self) -> None:
        self.requests: list[RunRequest] = []

    def run(self, request: RunRequest) -> RunResult:
        self.requests.append(request)
        return RunResult(
            run_id=request.run_id,
            target=request.target,
            scenario_id=request.scenario.id,
            repetition=request.repetition,
            answer="ok",
            sensitive=request.sensitive,
        )


SCENARIO = Scenario(
    id="s1",
    interactions=(Interaction(text="hi", sly_data={"token": "SECRET-123456", "n": 5, "nested": {"pin": "998877"}}),),
)


def test_plant_tracks_values_and_adds_canary() -> None:
    planted, sensitive = plant(SCENARIO, canary="CRUCIBLE-CANARY-X")
    values = {sv.value: sv for sv in sensitive}
    assert set(values) == {"SECRET-123456", "998877", "CRUCIBLE-CANARY-X"}
    assert values["998877"].key == "nested.pin"
    assert values["CRUCIBLE-CANARY-X"].planted
    assert planted.interactions[0].sly_data[CANARY_KEY] == "CRUCIBLE-CANARY-X"
    assert CANARY_KEY not in SCENARIO.interactions[0].sly_data


def test_runner_repetitions_and_unique_canaries() -> None:
    adapter = FakeAdapter()
    seen = []
    batch = Runner(adapter, timeout_s=5).run("t", [SCENARIO], repetitions=3, on_result=seen.append)
    assert len(batch.runs) == 3 == len(seen)
    canaries = {r.scenario.interactions[0].sly_data[CANARY_KEY] for r in adapter.requests}
    assert len(canaries) == 3
    assert len({r.run_id for r in batch.runs}) == 3


def test_store_roundtrip(tmp_path: Path) -> None:
    store = FileRunStore(tmp_path)
    batch = Runner(FakeAdapter()).run("t", [SCENARIO])
    store.save(batch)
    assert store.list_ids() == [batch.batch_id]
    assert store.load(batch.batch_id) == batch
    with pytest.raises(CrucibleError):
        store.load("nope")


def test_attribute_calls_by_system_prompt() -> None:
    graph = make_graph(
        agent("front", tools=["a"], instructions="[front] route things"), agent("a", instructions="[a] do a")
    )
    calls = [
        LlmCall(id="1", messages=(LlmMessage(role="system", content="[a] do a\nextra"),)),
        LlmCall(id="2", messages=(LlmMessage(role="human", content="x"),)),
    ]
    assert [c.agent for c in attribute_calls(calls, graph)] == ["a", None]
