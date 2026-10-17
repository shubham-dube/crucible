"""HTTP API end to end with the real worker and the bug zoo (keyless)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from crucible.interfaces.api.app import create_app
from crucible.interfaces.api.settings import ApiSettings

ZOO = Path(__file__).resolve().parents[2] / "examples" / "targets"
KEY = {"X-API-Key": "test-key"}
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    home = tmp_path_factory.mktemp("api-home")
    settings = ApiSettings(home=home, api_keys="test-key", project_map_override={"zoo": ZOO})
    return TestClient(create_app(settings))


def _wait(client: TestClient, job_id: str) -> dict[str, Any]:
    for _ in range(600):
        job = client.get(f"/v1/jobs/{job_id}", headers=KEY).json()
        if job["status"] in ("succeeded", "failed"):
            return job  # type: ignore[no-any-return]
        time.sleep(0.1)
    raise AssertionError("job timed out")


def test_health_and_auth(client: TestClient) -> None:
    assert client.get("/v1/health").json()["status"] == "ok"
    assert client.get("/v1/projects").status_code == 401
    assert client.get("/v1/projects", headers={"X-API-Key": "wrong"}).status_code == 401
    projects = client.get("/v1/projects", headers=KEY).json()
    assert projects[0]["name"] == "zoo"
    assert client.get("/v1/projects/nope/targets/x/graph", headers=KEY).status_code == 404


def test_graph_and_lint(client: TestClient) -> None:
    graph = client.get("/v1/projects/zoo/targets/support_loop/graph", headers=KEY).json()
    assert graph["front_man"] == "helpdesk"
    assert {"source": "billing_expert", "target": "payments_expert", "kind": "internal"} in graph["edges"]
    lint = client.get("/v1/projects/zoo/targets/support_loop/lint", headers=KEY).json()
    assert "topology/cycle-risk" in {f["rule_id"] for f in lint["findings"]}


def test_audit_job_masked_run_baseline_diff_and_sse(client: TestClient) -> None:
    started = client.post("/v1/audits", headers=KEY, json={"project": "zoo", "targets": ["account_leak"]})
    assert started.status_code == 202
    job = _wait(client, started.json()["id"])
    assert job["status"] == "succeeded", job
    assert job["result"]["gate_failed"] is True
    audit_id = job["result"]["audit_ids"]["account_leak"]

    audit = client.get(f"/v1/audits/{audit_id}", headers=KEY).json()
    assert [f["rule_id"] for f in audit["findings"]] == ["leak/sly-data-exposure"]
    assert "SYNTH-ID-4417-2290" not in json.dumps(audit)
    run = client.get(f"/v1/audits/{audit_id}/runs/{audit['runs'][0]['run_id']}", headers=KEY).json()
    assert "SYNTH-ID-4417-2290" not in json.dumps(run)
    assert run["spans"]

    assert client.put(f"/v1/baselines/account_leak/main?audit_id={audit_id}", headers=KEY).status_code == 200
    diff = client.get(f"/v1/audits/{audit_id}/diff?against=main", headers=KEY).json()
    assert diff["new"] == []
    assert len(diff["persisting"]) == 1

    with client.stream("GET", f"/v1/jobs/{job['id']}/events?poll_s=0.05", headers=KEY) as stream:
        body = "".join(stream.iter_text())
    assert '"type": "run"' in body
    assert "event: end" in body
    assert client.get("/v1/audits", headers=KEY).json()[0]["id"] == audit_id


def test_fix_job(client: TestClient) -> None:
    job = _wait(
        client,
        client.post("/v1/audits", headers=KEY, json={"project": "zoo", "targets": ["fragile_weather"]}).json()["id"],
    )
    audit_id = job["result"]["audit_ids"]["fragile_weather"]
    fix = _wait(client, client.post(f"/v1/audits/{audit_id}/fix", headers=KEY, json={"project": "zoo"}).json()["id"])
    verdicts = fix["result"]["verdicts"]
    assert [v["accepted"] for v in verdicts] == [True]
    assert "If a tool returns an error" in verdicts[0]["diff"]


def test_validation_errors(client: TestClient) -> None:
    bad = client.post("/v1/audits", headers=KEY, json={"project": "zoo", "repetitions": 0})
    assert bad.status_code == 422
    agentic = client.post("/v1/audits", headers=KEY, json={"project": "zoo", "agentic": True})
    assert agentic.status_code == 422
    assert client.get("/v1/jobs/job-nope", headers=KEY).status_code == 404
    assert client.get("/v1/audits/audit-nope", headers=KEY).status_code == 404


def test_path_traversal_rejected(client: TestClient) -> None:
    for path in ("/v1/audits/..%2F..%2Fcrucible", "/v1/audits/....json", "/v1/audits/a%5Cb"):
        assert client.get(path, headers=KEY).status_code in (400, 404)
