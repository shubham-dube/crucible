"""Built-in reporters: table (rich), json, sarif."""

from __future__ import annotations

import io
import json
from typing import Any

from rich.console import Console
from rich.table import Table

from crucible.domain.findings import Severity
from crucible.reporting.base import FindingsReport, register_reporter

_SARIF_LEVEL = {Severity.ERROR: "error", Severity.WARNING: "warning", Severity.INFO: "note"}
_STYLE = {Severity.ERROR: "bold red", Severity.WARNING: "yellow", Severity.INFO: "cyan"}


class TableReporter:
    """Human-readable terminal table."""

    name = "table"

    def render(self, report: FindingsReport) -> str:
        buffer = io.StringIO()
        console = Console(file=buffer, width=140, force_terminal=False, color_system=None)
        for target in report.targets:
            console.print(f"[bold]{target.network}[/bold]  {target.file or ''}")
            if not target.findings:
                console.print("  no findings")
                continue
            table = Table(show_lines=False, expand=True)
            table.add_column("severity", no_wrap=True)
            table.add_column("rule", no_wrap=True)
            table.add_column("agent", no_wrap=True)
            table.add_column("message")
            for f in target.findings:
                table.add_row(f.severity.value, f.rule_id, f.agent or "-", f.message, style=_STYLE[f.severity])
            console.print(table)
            counts = {s: sum(1 for f in target.findings if f.severity is s) for s in Severity}
            console.print(
                f"  {counts[Severity.ERROR]} error(s), {counts[Severity.WARNING]} warning(s), "
                f"{counts[Severity.INFO]} info"
            )
        return buffer.getvalue()


class JsonReporter:
    """Machine-readable JSON (the FindingsReport model)."""

    name = "json"

    def render(self, report: FindingsReport) -> str:
        return report.model_dump_json(indent=2)


class SarifReporter:
    """SARIF 2.1.0, consumable by GitHub code scanning."""

    name = "sarif"

    def render(self, report: FindingsReport) -> str:
        rule_ids = sorted({f.rule_id for f in report.all_findings})
        results: list[dict[str, Any]] = []
        for f in report.all_findings:
            location: dict[str, Any] = {}
            if f.location.file:
                location["physicalLocation"] = {"artifactLocation": {"uri": f.location.file}}
            if f.agent or f.location.json_path:
                location["logicalLocations"] = [
                    {"name": f.agent or "", "fullyQualifiedName": f.location.json_path or f.agent or ""}
                ]
            result: dict[str, Any] = {
                "ruleId": f.rule_id,
                "ruleIndex": rule_ids.index(f.rule_id),
                "level": _SARIF_LEVEL[f.severity],
                "message": {"text": f.message + (f" Fix: {f.remediation}" if f.remediation else "")},
                "partialFingerprints": {"crucible/v1": f.fingerprint},
            }
            if location:
                result["locations"] = [location]
            results.append(result)
        sarif = {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "crucible",
                            "version": report.version,
                            "informationUri": "https://github.com/shubham-dube/crucible",
                            "rules": [{"id": r, "name": r.replace("/", "_")} for r in rule_ids],
                        }
                    },
                    "results": results,
                }
            ],
        }
        return json.dumps(sarif, indent=2)


for _reporter in (TableReporter(), JsonReporter(), SarifReporter()):
    register_reporter(_reporter)
