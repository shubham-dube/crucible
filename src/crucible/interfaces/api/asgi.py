"""ASGI entrypoint for hosted deployments (e.g. Vercel): ``app`` built from the environment."""

from __future__ import annotations

import os

from crucible.interfaces.api.app import create_app

# Serverless functions only have a writable /tmp; keep an explicit CRUCIBLE_HOME if one is set.
if os.environ.get("VERCEL") and not os.environ.get("CRUCIBLE_HOME"):
    os.environ["CRUCIBLE_HOME"] = "/tmp/crucible"

app = create_app()
