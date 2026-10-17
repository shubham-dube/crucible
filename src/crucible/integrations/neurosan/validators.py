"""Bridge Neuro-SAN's own network validators into Crucible findings."""

from __future__ import annotations

import contextlib
import io
import logging
import re
from typing import Any

from crucible.domain.findings import Finding, Location, Severity

RULE_ID = "neurosan/validator"

# Neuro-SAN messages that Crucible's own rules already report with richer detail.
_COVERED = {
    re.compile(r"references non-existent agent", re.I): "topology/dangling-tool",
    re.compile(r"unreachable agents? found", re.I): "topology/unreachable-agent",
}


def covered_by(message: str) -> str | None:
    """Return the Crucible rule id that already covers this Neuro-SAN message, if any."""
    return next((rule for pattern, rule in _COVERED.items() if pattern.search(message)), None)


def run_neurosan_validators(
    config: dict[str, Any], network_name: str, file: str | None = None, skip_rules: frozenset[str] = frozenset()
) -> list[Finding]:
    """Run ``ManifestNetworkValidator``; convert messages to findings, skipping ones covered by ``skip_rules``."""
    from neuro_san.internals.validation.network.manifest_network_validator import ManifestNetworkValidator

    try:
        # The validators also log each message as a warning; we report them as findings instead.
        previous = logging.root.manager.disable
        logging.disable(logging.WARNING)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                messages = ManifestNetworkValidator(network_name=network_name).validate(config) or []
        finally:
            logging.disable(previous)
    except Exception as exc:  # validator crashes on badly shaped input; surface instead of failing
        messages = [f"Neuro-SAN validator crashed: {exc}"]
    return [
        Finding(
            rule_id=RULE_ID,
            severity=Severity.ERROR,
            message=str(message),
            location=Location(file=file),
            remediation="Fix the network so Neuro-SAN's own validator accepts it.",
        )
        for message in messages
        if covered_by(str(message)) not in skip_rules
    ]
