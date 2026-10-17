# Crucible

**Chaos, fuzz and regression QA for multi-agent networks — an agent network that tests agent networks.**

Multi-agent systems fail in ways final-answer evals never see: wrong routing between specialists, agents ping-ponging a task until the step budget dies, tools that time out while the network confidently hallucinates, tool output that hijacks the network, and private data meant for Neuro-SAN's `sly_data` channel quietly leaking into LLM prompts.

Crucible points at a [Neuro-SAN](https://github.com/cognizant-ai-lab/neuro-san) network and:

1. **Lints the topology** — cycles, unreachable agents, overlapping routing descriptions, unbounded budgets, risky sly_data allow-lists.
2. **Plans scenarios** that cover every delegation and tool edge, including adversarial personas.
3. **Injects chaos** into coded tools — latency, exceptions, malformed or instruction-carrying output — without editing your HOCON.
4. **Runs and traces** every delegation, tool call, token and the exact prompt sent to each LLM call.
5. **Judges** traces for loops, mis-routing, unhandled tool failures, budget breaches and **canary-proven sly_data leaks**.
6. **Diffs** against a baseline so regressions fail CI.
7. **Proposes fixes** and **verifies** them by re-running before suggesting anything.

Delivered as a CLI, GitHub Action, REST/SSE API, web dashboard and MCP tool.

> Status: under active development. See [`docs/PROGRESS.md`](docs/PROGRESS.md).

## Quick start (development)

```bash
uv sync
make check          # ruff + mypy + pytest (keyless)
```

Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` for live-LLM runs. All tests run without keys using Crucible's deterministic `ScriptedChatModel`.

## Documentation
- [Product requirements](docs/PRD.md)
- [Architecture](docs/architecture/overview.md) · [Neuro-SAN integration notes](docs/architecture/neurosan-integration.md)
- [Roadmap](docs/plan/ROADMAP.md) · [Progress](docs/PROGRESS.md) · [Handover](docs/HANDOVER.md)
- [Workflow](docs/process/WORKFLOW.md) · [Conventions](docs/process/CONVENTIONS.md) · [ADRs](docs/adr/)

## License
Apache-2.0
