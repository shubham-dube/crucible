# Engineering conventions

## Repository layout
```
src/crucible/
  domain/          pure pydantic models + enums. Imports nothing from crucible except domain.
  config/          Settings (pydantic-settings, env prefix CRUCIBLE_)
  observability/   logging (structlog) + tracing setup
  integrations/
    neurosan/      the ONLY place that imports neuro_san (loader, sessions, preppers, callbacks, scripted LLM)
  topology/        graph building + lint rule registry
  execution/       TargetAdapter port, runner, trace normaliser
  chaos/           fault catalog + plans
  scenarios/       coverage planner + fixture I/O
  judges/          judge registry + judges
  regression/      baseline + diff
  fixes/           patch model + verify loop
  reporting/       reporters (markdown/json/sarif/junit)
  storage/         repository ports + sqlite/postgres impls, artifact store
  interfaces/      cli/ (typer), api/ (FastAPI), worker/
agents/            Crucible's own Neuro-SAN network (registries/ + coded_tools/)
examples/targets/  bug zoo: target networks with seeded defects + expected findings
tests/             unit/ (mirrors src), integration/, e2e/
web/               Next.js dashboard
docs/              PRD, architecture, ADRs, plans, process, handover
```

## Layering
`domain` ← `topology|execution|chaos|scenarios|judges|regression|fixes|reporting|storage` ← `interfaces`, `agents/coded_tools`.
Feature packages talk to each other through `domain` models and Protocol ports, never through each other's internals.
Anything importing `neuro_san` goes in `integrations/neurosan`.

## Python
- Python 3.13, `from __future__ import annotations` not needed; use modern typing (`list[str]`, `X | None`).
- ruff (line length 119) for lint + format; mypy `--strict` for `src/`.
- Public classes/functions get a one-line docstring minimum; explain *why* in comments only where non-obvious.
- Errors: raise domain exceptions from `crucible.domain.errors`; never swallow exceptions silently.
- Logging: `structlog.get_logger(__name__)`; no `print` outside CLI presentation code.
- Pure functions where possible; side effects at the edges (adapters, storage, interfaces).
- Plugins: register with `@registry.register("name")`; registries live next to their port.

## Tests
- pytest; files `test_<module>.py`; one behaviour per test; descriptive names.
- Markers: `integration` (Neuro-SAN in-process, keyless), `live` (needs real LLM keys, skipped otherwise), `e2e`.
- No network in unit tests. Use `ScriptedChatModel` for deterministic agent behaviour.

## Naming
- Finding rule ids: `<area>/<kebab-name>`, e.g. `topology/routing-overlap`, `trace/ping-pong`, `leak/sly-data-in-prompt`.
- Fault ids: `fault/<kebab-name>`.

## Commits
Conventional Commits; scope = package (`feat(judges): ...`). Author Shubham Dubey; no AI trailers.

## Frontend (web/)
Next.js (App Router) + TypeScript strict + Tailwind + shadcn/ui; pnpm; ESLint + Prettier; data via typed API client generated from the FastAPI OpenAPI schema.
