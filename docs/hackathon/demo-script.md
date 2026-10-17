# Demo script (≈5 minutes)

Setup (once): `uv sync`, `cd web && pnpm install && pnpm build`.
Terminal A: `CRUCIBLE_PROJECTS="zoo=examples/targets" CRUCIBLE_API_KEYS=demo uv run crucible serve --port 8765`
Terminal B: `cd web && CRUCIBLE_API_KEY=demo pnpm start` → http://localhost:3000
(Live mode: export ANTHROPIC_API_KEY and drop `--scripted`; everything else is identical.)

1. **The problem (30 s)** — show `examples/targets/registries/support_loop.hocon`: two specialists that "ask each
   other when unsure". `crucible run examples/targets -t support_loop` → 150+ hand-offs, timeout.
2. **Static lint (30 s)** — `crucible lint examples/targets/registries/*.hocon`: cycle, routing overlap, wildcard
   sly_data, unbounded budget, before running anything.
3. **Dashboard audit (60 s)** — open support_loop: graph shows the cycle in red. Click *Run audit* → live SSE progress
   → findings: ping-pong (154 hand-offs, evidence spans), timeout, budget.
4. **Verified fix (45 s)** — *Find verified fixes* → ACCEPTED: remove back-edge, "4 findings resolved, no new
   findings", coloured config diff. A cosmetic fix would be REJECTED by the verifier.
5. **Leak proof (45 s)** — account_leak audit: `leak/sly-data-exposure` first emitted by `profile_lookup`, seen in
   the LLM prompt and the answer; open the run trace → *Exact LLM inputs* show `[REDACTED]` where the secret was.
6. **Chaos + injection (45 s)** — `crucible chaos examples/targets -t clean_concierge` (resilience matrix);
   `crucible audit examples/targets -t injectable_research` → agent emailed notes to `exfil@attacker.test`.
7. **Crucible is a Neuro-SAN network (45 s)** — `crucible audit examples/targets -t fragile_weather --agentic
   --scripted`: 17 hand-offs conductor → specialists → tools → verified fix → report. Then
   `crucible mcp-server examples/targets -t fragile_weather --scripted` and call it over MCP.
8. **Merge gate + evaluation (30 s)** — `crucible bench` → recall 100% / precision 100%; show the GitHub Action
   summary (`docs/guides/github-action.md`).
