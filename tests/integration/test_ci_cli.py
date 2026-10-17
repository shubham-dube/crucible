"""CI-facing CLI behaviour: portable baseline files, summary file, report formats."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from crucible.interfaces.cli.app import app
from crucible.services.gate import SUMMARY_MARKER

ZOO = Path(__file__).resolve().parents[2] / "examples" / "targets"


@pytest.mark.integration
@pytest.mark.usefixtures("crucible_home")
def test_baseline_file_gate_and_summary(tmp_path: Path) -> None:
    runner = CliRunner()
    baseline = tmp_path / "baseline.json"
    base_args = ["audit", str(ZOO), "-t", "fragile_weather", "--no-save"]
    first = runner.invoke(app, [*base_args, "--fail-on", "never", "--write-baseline", str(baseline), "-f", "junit"])
    assert first.exit_code == 0, first.output
    data = json.loads(baseline.read_text())
    runs = data["audits"]["fragile_weather"]["batch"]["runs"]
    assert all(span["kind"] == "delegation" for run in runs for span in run["spans"])
    assert all(run["llm_calls"] == [] for run in runs)
    summary = tmp_path / "summary.md"
    gated = runner.invoke(
        app, [*base_args, "--baseline", str(baseline), "--summary-file", str(summary), "-f", "sarif"]
    )
    assert gated.exit_code == 0, gated.output
    text = summary.read_text()
    assert text.startswith(SUMMARY_MARKER)
    assert "gate passed" in text
    assert "0 new" in text
