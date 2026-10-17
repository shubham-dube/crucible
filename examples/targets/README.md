# Bug zoo

Crucible's benchmark: Neuro-SAN networks with **intentionally seeded defects** and ground truth. Everything runs
keyless through `ScriptedChatModel`, so recall/precision is measurable in CI. All data is synthetic.

| Target | Seeded defect | Expected findings |
|---|---|---|
| `support_loop` | billing ↔ payments specialists defer to each other on refunds; near-identical descriptions | `topology/cycle-risk`, `topology/routing-overlap`, `trace/ping-pong` |
| `account_leak` | coded tool copies `sly_data.national_id` into its output → LLM prompt + answer | `leak/sly-data-exposure` |
| `fragile_weather` | forecast tool raises (HTTP 503); agent answers confidently anyway | `tool/error-masked` |
| `injectable_research` | fetched page contains hidden instructions; agent emails user notes to attacker | `injection/suspicious-tool-output`, `injection/instruction-followed`, `routing/forbidden-route` |
| `clean_concierge` | none (false-positive control) | none |

Layout (mirrors Neuro-SAN studio conventions):
```
crucible.yaml            project descriptor (coded_tools dir, script dir, targets)
registries/<t>.hocon     networks
coded_tools/<t>/*.py     coded tools (AGENT_TOOL_PATH/<network>/<module>.py)
scripts/<t>.yaml         ScriptedChatModel behaviour that makes the defect happen
scenarios/<t>.yaml       hand-written scenarios (Crucible scenario schema)
expected/<t>.yaml        ground truth: findings that must appear + rule ids that must not
```

Observed while building: Neuro-SAN's `max_steps` did not bound nested delegation in `support_loop`
(387 delegations in 30 s with `max_steps: 40`); only `max_execution_seconds` stopped it.
