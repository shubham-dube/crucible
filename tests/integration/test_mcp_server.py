"""Crucible's network served as an MCP tool by Neuro-SAN's own server (scripted, keyless)."""

from __future__ import annotations

import socket
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from crucible.services.mcp_server import prepare, server_command

ZOO = Path(__file__).resolve().parents[2] / "examples" / "targets"
HEADERS = {"content-type": "application/json", "MCP-Protocol-Version": "2025-06-18"}


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.e2e
def test_crucible_is_an_mcp_tool(tmp_path: Path) -> None:
    port = _free_port()
    env = prepare(tmp_path / "home", ZOO, "fragile_weather", scripted=True)
    server = subprocess.Popen(server_command(port), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}/mcp"
    try:
        for _ in range(120):
            try:
                init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}
                if httpx.post(url, json=init, timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
        tools = httpx.post(url, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers=HEADERS, timeout=10)
        assert [t["name"] for t in tools.json()["result"]["tools"]] == ["crucible"]
        call = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "crucible", "arguments": {"user_message": {"text": "Audit this network."}}},
        }
        result = httpx.post(url, json=call, headers=HEADERS, timeout=180).json()["result"]
        assert result["isError"] is False
        assert "Audit complete" in result["content"][0]["text"]
        assert list((tmp_path / "home" / "audits").glob("audit-*.json"))
    finally:
        server.terminate()
        server.wait(timeout=30)
