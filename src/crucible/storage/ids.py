"""Identifier validation for anything that becomes part of a filesystem path."""

from __future__ import annotations

import re

from crucible.domain.errors import CrucibleError

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def safe_id(value: str, kind: str = "id") -> str:
    """Reject ids that could escape their directory (path traversal) or are malformed."""
    if not _SAFE_ID.fullmatch(value or "") or ".." in value:
        raise CrucibleError(f"unknown {kind} '{value[:64]}'")
    return value
