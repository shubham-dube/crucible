"""Exported scenarios run unchanged under Neuro-SAN's own data-driven test driver."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import pytest

from crucible.config.project import Project
from crucible.scenarios.io import to_neurosan_test

ZOO = Path(__file__).resolve().parents[2] / "examples" / "targets"


@pytest.mark.integration
def test_exported_cases_pass_in_neurosan_driver(tmp_path: Path) -> None:
    from neuro_san.test.driver.data_driven_agent_test_driver import DataDrivenAgentTestDriver
    from neuro_san.test.unittest.unit_test_assert_forwarder import UnitTestAssertForwarder

    project = Project.load(ZOO)
    project.activate()
    spec = project.target("clean_concierge")
    for scenario in project.scenarios(spec).scenarios:
        path = tmp_path / f"{scenario.id}.hocon"
        path.write_text(json.dumps(to_neurosan_test(scenario, str(project.network_path(spec)))), encoding="utf-8")
        DataDrivenAgentTestDriver(UnitTestAssertForwarder(unittest.TestCase())).one_test(str(path))
