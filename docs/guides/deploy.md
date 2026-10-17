# Deploying Crucible

## Docker Compose (API + worker + dashboard)
```bash
cp .env.example .env   # set CRUCIBLE_API_KEYS (long random), optionally ANTHROPIC_API_KEY / GOOGLE_API_KEY
docker compose -f deploy/docker-compose.yml --env-file .env up --build
# dashboard: http://localhost:3000   API: http://localhost:8765/docs
```
- `api` (deploy/Dockerfile.api): Python 3.13, frozen `uv sync`, non-root user, healthcheck on `/v1/health`, data in the
  `crucible-data` volume (`CRUCIBLE_HOME=/data`). Mount your agent projects read-only and list them in
  `CRUCIBLE_PROJECTS="name=/projects/name;..."`.
- `web` (deploy/Dockerfile.web): Next.js standalone server; talks to the API over the compose network with the key.
- Jobs run serially per API process (prompt capture is process-global, ADR 0002). Scale by running more API
  replicas behind a shared queue implementation of `JobQueue` (port in `services/jobs.py`).

> Note: the images were authored and their steps verified locally (frozen wheel install + agentic audit from the
> installed wheel; Next.js standalone build), but not built in the original sandbox, whose network blocked container
> registries. Build them once in CI or locally before relying on them.

## Without Docker
```bash
uv sync && CRUCIBLE_PROJECTS="zoo=examples/targets" CRUCIBLE_API_KEYS=devkey uv run crucible serve
cd web && pnpm install && CRUCIBLE_API_KEY=devkey pnpm build && pnpm start
```
