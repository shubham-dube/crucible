# Crucible as an MCP tool

Crucible's own Neuro-SAN network can be served as an MCP tool named `crucible` by Neuro-SAN's server, so any MCP
client (IDE agents, other agent networks) can ask "audit this network".

```bash
crucible mcp-server examples/targets -t fragile_weather --port 8080            # live LLMs (needs ANTHROPIC_API_KEY)
crucible mcp-server examples/targets -t fragile_weather --port 8080 --scripted # keyless demo
```

JSON-RPC over `POST http://127.0.0.1:8080/mcp` (protocol 2025-06-18; send `MCP-Protocol-Version` after initialize):
```bash
curl -s -X POST localhost:8080/mcp -H 'content-type: application/json' -H 'MCP-Protocol-Version: 2025-06-18' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"crucible",
       "arguments":{"user_message":{"text":"Audit this network and tell me if it is safe to merge."}}}}'
```
The tool's arguments are a Neuro-SAN ChatRequest (`user_message`, optional `sly_data`, `chat_context`). The project and
target come from the server's `CRUCIBLE_PROJECT_DIR` / `CRUCIBLE_TARGET` (set by `crucible mcp-server`) or from
`sly_data.project_dir` / `sly_data.target`. Verified by `tests/integration/test_mcp_server.py` (`make test-e2e`).
