# Manual testing guide

This guide runs every Crucible surface yourself and shows how to tell **pass** from **fail**. Each step lists the
command, what you should see, and what a failure looks like. Part A needs no API key. Part B uses a real Gemini key
and costs a few rupees.

## 0. Setup (once)
```bash
git clone https://github.com/shubham-dube/crucible && cd crucible
uv sync --all-extras          # Python 3.13 deps + LLM provider SDKs
uv run crucible version       # pass: prints a version
make check                    # pass: ruff + mypy clean, "N passed" (about 3 min)
```

## Part A: keyless (deterministic, free)

### A1. Static lint (no execution)
```bash
uv run crucible lint examples/targets/registries/support_loop.hocon
```
**Pass:** two warnings, `topology/cycle-risk` (billing_expert ↔ payments_expert) and `topology/routing-overlap`
(helpdesk). **Fail:** no findings, or a crash. Try `-f sarif` to get the format GitHub code scanning shows.

### A2. Run scenarios and read a trace
```bash
uv run crucible run examples/targets -t fragile_weather
```
**Pass:** a table with the `outage-city` and `healthy-city` rows, a `tool err` count of 1 for `outage-city`, and a
`saved .crucible/runs/<batch>` line.

Open `.crucible/runs/<batch>/batch.json` and find `spans`. Each span is one event: `delegation`, `tool_args`,
`tool_error`, `tool_result`, `llm_output` or `final_answer`. `llm_calls` holds the **exact prompt** of every model
call. This is the evidence the judges reason over.

### A3. Full audit (lint → run → judge)
```bash
uv run crucible audit examples/targets -t account_leak
```
**Pass:**
- an **error** `leak/sly-data-exposure` attributed to `profile_lookup`;
- the evidence shows the national id **masked** (`SYNT…`), never in full.

**Fail:** no leak finding, or the full secret printed anywhere.

### A4. Benchmark: does Crucible find what it should?
```bash
uv run crucible bench
```
**Pass:** `Recall 100% · Precision 100%`. Each row compares the expected findings (`examples/targets/expected/*.yaml`)
with what was detected.

### A5. Verified fix
```bash
uv run crucible fix examples/targets -t support_loop
```
**Pass:** an `[ACCEPTED]` proposal with a config diff:
- the `billing_expert` tool is removed from payments_expert;
- the instruction naming it is deleted;
- scope guidance is appended;
- the "resolved" count is at least 1.

**Fail:** `rejected` with "target finding still present".

### A6. Crucible's own agent network (scripted LLM)
```bash
uv run crucible audit examples/targets -t fragile_weather --agentic --scripted
```
**Pass:** a hand-off count, a summary citing a real audit id and finding ids, and a report path.

### A7. Chaos
```bash
uv run crucible chaos examples/targets -t clean_concierge --fault exception:order_status
```
**Pass:** a resilience table in which `exception:order_status` is **not** resilient, with a new
`answer/missing-content@concierge` finding: once the tool fails, the order answer no longer contains `A-42`.
Resilience below 100 % here is the expected, correct result.

### A8. API + dashboard
```bash
CRUCIBLE_PROJECTS="zoo=examples/targets" CRUCIBLE_API_KEYS=devkey uv run crucible serve --port 8765
curl -s localhost:8765/v1/projects -H 'X-API-Key: devkey'                      # pass: JSON with "zoo"
curl -s -X POST localhost:8765/v1/audits -H 'X-API-Key: devkey' -H 'content-type: application/json' \
     -d '{"project":"zoo","targets":["account_leak"]}'                            # pass: 202 + job id
curl -s localhost:8765/v1/projects -o /dev/null -w '%{http_code}\n'             # pass: 401 (no key)
cd web && pnpm install && CRUCIBLE_API_URL=http://127.0.0.1:8765 CRUCIBLE_API_KEY=devkey pnpm dev
```
Open http://localhost:3000, then **zoo → account_leak → Run audit**. **Pass:**
- live progress appears;
- the finished audit shows the leak with masked evidence;
- the run page shows the timeline and LLM inputs with secrets redacted.

Stop the API with `pkill -f "[c]rucible serve"`.

### A9. MCP (Crucible as a tool for other agents)
```bash
make test-e2e      # pass: 1 passed (boots Neuro-SAN's server, calls the 'crucible' MCP tool)
```

## Part B: live (real Gemini, costs money)
Put `GOOGLE_API_KEY=...` in `.env`; it is gitignored and never committed. Always set a budget first:
```bash
export CRUCIBLE_HOME=.crucible-live CRUCIBLE_LLM_BUDGET_USD=0.50    # hard stop at about ₹44
```
Every command prints `LLM spend: $x (₹y) this command, $z total`. If the budget is reached, the next run refuses to
start with `LLM budget reached`. Delete `$CRUCIBLE_HOME/llm_spend.jsonl` to reset.

### B1. Smoke (about ₹0.05)
```bash
uv run crucible run examples/live_targets -t clean_concierge
```
**Pass:**
- two `ok` rows with natural-language answers that mention `A-42` and `30 days`;
- the token counts are non-zero;
- a spend line is printed.

**Fail:** `error` status. Check the key, and that `uv sync --all-extras` installed `langchain-google-genai`.

### B2. Live benchmark (about ₹1.5)
```bash
uv run crucible bench examples/live_targets -n 3 --save
```
**Expected:** recall 100 %. Precision can dip when a model does something new. When it does:
- open the audit ids printed under the table (`$CRUCIBLE_HOME/audits/<id>.json`, the `batch.runs[].spans` field);
- decide by reading the trace whether the "false positive" really happened.

That is exactly how the live ground truth was built (see [docs/eval/live.md](../eval/live.md)).

### B3. Spot the stochastic loop
```bash
uv run crucible run examples/live_targets -t support_loop --scenario refund-request -n 5
```
Look at the `deleg.` column. Most runs show 3–9 delegations (a bounce), and some show about 70 (a runaway until
the 60 s limit). Run `crucible audit` on the same target to see these become `trace/bounce` and `trace/ping-pong`.

### B4. Live fix (about ₹1)
```bash
uv run crucible fix examples/live_targets -t fragile_weather -n 3 --out fixed/
```
**Pass:** `[ACCEPTED]`. Then **read the fixed behaviour yourself**: point a copy of `crucible.yaml` at
`fixed/*.hocon` and `crucible run` it. Outage answers should now say the forecast is unavailable, with no invented
temperature.

### B5. Live agentic audit (about ₹6, ~2.5 min)
```bash
uv run crucible --agent-llm gemini:gemini-3.8-flash audit examples/live_targets -t account_leak --agentic
```
**Pass:**
- verdict NOT SAFE, citing a `leak/sly-data-exposure` finding id;
- the fix is marked manual (code change);
- a report path.

Then **verify the citations**:
- each id should exist in `$CRUCIBLE_HOME/audits/<audit id>.json`;
- the secret value must not appear in the answer or the report (`grep SYNTH-ID` returns nothing).

### B6. Live tests
```bash
set -a; . ./.env; set +a; uv run pytest -m live
```

## Testing your own network
1. Put your HOCON registry and coded tools in a folder, and add a `crucible.yaml` modelled on
   `examples/live_targets/crucible.yaml`.
2. Write 2–5 scenarios per target, the way real users would ask. Put any private data in `sly_data`.
3. Run `crucible lint`, then `crucible audit -n 3`, and read every error finding's evidence.
4. Run `crucible audit --write-baseline baseline.json` on main, then `--baseline baseline.json` in CI
   (see [github-action.md](github-action.md)).
