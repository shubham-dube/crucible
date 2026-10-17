"""PR-gate semantics end to end: baseline the known defects, then only NEW ones fail."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from crucible.interfaces.cli.app import app

ZOO = Path(__file__).resolve().parents[2] / "examples" / "targets"


@pytest.mark.integration
@pytest.mark.usefixtures("crucible_home")
def test_baseline_gate() -> None:
    runner = CliRunner()
    args = ["audit", str(ZOO), "-t", "fragile_weather", "-f", "json"]
    first = runner.invoke(app, [*args, "--update-baseline", "main"])
    assert first.exit_code == 1  # known masked error fails an un-baselined audit
    second = runner.invoke(app, [*args, "--baseline", "main"])
    assert second.exit_code == 0, second.output
    assert "0 new" in second.output
