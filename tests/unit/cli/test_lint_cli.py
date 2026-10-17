"""CLI behaviour: exit codes and formats."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from crucible.interfaces.cli.app import app

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "networks"
runner = CliRunner()


@pytest.fixture(autouse=True)
def _fixtures_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRUCIBLE_FIXTURES", str(FIXTURES.parent))


def test_bad_network_fails_on_error() -> None:
    result = runner.invoke(app, ["lint", str(FIXTURES / "lint_bad.hocon"), "-f", "json"])
    assert result.exit_code == 1
    rules = {f["rule_id"] for f in json.loads(result.stdout)["targets"][0]["findings"]}
    assert {"topology/dangling-tool", "topology/cycle-risk", "topology/routing-overlap"} <= rules


def test_fail_on_never() -> None:
    assert runner.invoke(app, ["lint", str(FIXTURES / "lint_bad.hocon"), "--fail-on", "never"]).exit_code == 0


def test_clean_network_passes_on_warning() -> None:
    assert runner.invoke(app, ["lint", str(FIXTURES / "smoke_desk.hocon"), "--fail-on", "warning"]).exit_code == 0


def test_output_file(tmp_path: Path) -> None:
    out = tmp_path / "r.sarif"
    runner.invoke(app, ["lint", str(FIXTURES / "lint_bad.hocon"), "-f", "sarif", "-o", str(out)])
    assert json.loads(out.read_text())["version"] == "2.1.0"


def test_unparseable_network_exit_2(tmp_path: Path) -> None:
    bad = tmp_path / "broken.hocon"
    bad.write_text("{ tools: [ ", encoding="utf-8")
    assert runner.invoke(app, ["lint", str(bad)]).exit_code == 2


def test_version() -> None:
    assert runner.invoke(app, ["version"]).exit_code == 0
