"""Crucible: chaos, fuzz and regression QA for multi-agent networks."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("crucible-agents")
except PackageNotFoundError:  # pragma: no cover - running from a source tree without install
    __version__ = "0.0.0"
