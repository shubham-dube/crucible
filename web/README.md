# Crucible dashboard

Next.js 16 (App Router, Cache Components) + TypeScript + Tailwind v4, shadcn/ui-style primitives.

```bash
# 1. API (from the repo root)
CRUCIBLE_PROJECTS="zoo=examples/targets" CRUCIBLE_API_KEYS=devkey crucible serve --port 8765
# 2. Dashboard
cd web && pnpm install
CRUCIBLE_API_URL=http://127.0.0.1:8765 CRUCIBLE_API_KEY=devkey pnpm dev    # or: pnpm build && pnpm start
```

- The browser only talks to `/api/crucible/*`; that route handler adds the API key server-side and streams SSE through.
- Pages: overview (`/`), target (`/projects/[project]/[target]`: delegation graph, lint, run audit with chaos /
  agentic, live progress), audit (`/audits/[id]`: findings + evidence, verified fixes with diffs, runs, regression vs
  `main`), run trace (`/audits/[id]/runs/[run]`: spans timeline, exact LLM inputs with secrets redacted).
- API types live in `src/lib/api.ts` and mirror `openapi.json` (regenerate with `crucible serve --openapi web/openapi.json`).
