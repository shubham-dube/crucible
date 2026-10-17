"""Crucible's own evaluation loop: the bug zoo must be fully detected with no false positives."""

from __future__ import annotations

from pathlib import Path

import pytest

from crucible.config.project import Project
from crucible.evaluation.benchmark import run_benchmark
from crucible.services.audit import AuditOptions, AuditService

ZOO = Path(__file__).resolve().parents[2] / "examples" / "targets"


@pytest.mark.integration
def test_bug_zoo_benchmark_perfect_scores() -> None:
    report = run_benchmark(AuditService(Project.load(ZOO)), AuditOptions(timeout_s=60))
    assert report.recall == 1.0, report.to_markdown()
    assert report.precision == 1.0, report.to_markdown()
    assert all(not t.must_not_violations for t in report.targets)
