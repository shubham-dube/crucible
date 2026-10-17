"""Job queue resilience, API settings parsing and secret masking."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from crucible.domain.errors import ConfigError
from crucible.domain.trace import LlmCall, LlmMessage, RunResult, SensitiveValue, Span, SpanKind
from crucible.interfaces.api.settings import ApiSettings
from crucible.services.jobs import InProcessJobQueue, JobKind, JobStatus, JobStore
from crucible.services.masking import MASK, mask_run


def _wait(store: JobStore, job_id: str) -> JobStatus:
    for _ in range(100):
        job = store.get(job_id)
        if job is not None and job.status in (JobStatus.SUCCEEDED, JobStatus.FAILED):
            return job.status
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_failing_job_does_not_kill_worker(tmp_path: Path) -> None:
    def boom(job, emit):  # type: ignore[no-untyped-def]
        raise RuntimeError("kaboom")

    def ok(job, emit):  # type: ignore[no-untyped-def]
        emit({"type": "progress", "n": 1})
        return {"value": job.params["x"]}

    store = JobStore(tmp_path)
    queue = InProcessJobQueue(store, {JobKind.AUDIT: boom, JobKind.BENCH: ok})
    bad = queue.submit(JobKind.AUDIT, {})
    good = queue.submit(JobKind.BENCH, {"x": 7})
    assert _wait(store, bad.id) is JobStatus.FAILED
    assert _wait(store, good.id) is JobStatus.SUCCEEDED
    failed = store.get(bad.id)
    assert failed is not None
    assert failed.error is not None
    assert "kaboom" in failed.error
    finished = store.get(good.id)
    assert finished is not None
    assert finished.result == {"value": 7}
    assert [e["type"] for e in queue.events(good.id)] == ["queued", "started", "progress", "finished"]
    assert queue.events(good.id, after=3) == [{"type": "finished", "job": good.id, "status": "succeeded"}]
    assert [j.id for j in store.list()][:2] == [good.id, bad.id] or len(store.list()) == 2


def test_api_settings_parsing(tmp_path: Path) -> None:
    cfg = ApiSettings(
        projects=f"zoo={tmp_path} ; other={tmp_path}/x", api_keys="a, b,", cors_origins="http://a,http://b"
    )
    assert set(cfg.project_map()) == {"zoo", "other"}
    assert cfg.keys() == ["a", "b"]
    assert cfg.origins() == ["http://a", "http://b"]
    with pytest.raises(ConfigError):
        ApiSettings(projects="broken").project_map()


def test_mask_run_redacts_everywhere() -> None:
    secret = "SYNTH-ID-99887766"
    run = RunResult(
        run_id="r",
        target="t",
        scenario_id="s",
        answer=f"your id is {secret}",
        spans=(Span(id="s1", seq=1, kind=SpanKind.TOOL_RESULT, text=secret, data={"args": {"id": secret}}),),
        llm_calls=(LlmCall(id="l1", messages=(LlmMessage(role="tool", content=f"x {secret}"),)),),
        returned_sly_data={"k": secret},
        sensitive=(SensitiveValue(key="national_id", value=secret),),
    )
    dumped = mask_run(run).model_dump_json()
    assert secret not in dumped
    assert dumped.count(MASK) >= 5
