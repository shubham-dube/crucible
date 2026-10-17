# Security

## Reporting
Please report vulnerabilities privately to the maintainer (Shubham Dubey) via GitHub security advisories on
`shubham-dube/crucible`. Do not open public issues for security problems.

## Threat model and controls
| Area | Risk | Control |
|---|---|---|
| Secrets in traces | Target sly_data values / canaries leaking into reports, PR comments, API responses, the dashboard | Every finding is redacted against all tracked sensitive values in the judge engine; API run/answer payloads pass through `mask_run`; leak evidence masks the value it reports. Crucible's own agents only ever see masked evidence and ids. |
| Provider keys | Leakage via logs or the browser | Keys only from env/secret store (`SecretStr`), never logged; the dashboard proxies API calls server-side so `X-API-Key` never reaches the browser. |
| API access | Unauthenticated use | `X-API-Key` required when `CRUCIBLE_API_KEYS` is set (constant-time comparison); a warning is logged when auth is disabled (development only). CORS restricted to configured origins. |
| Path traversal | Ids from URLs used as file names | All audit / batch / target ids are validated (`storage/ids.py`); projects are addressed by registered name, never by path. |
| Resource abuse | Huge or endless jobs | Request bounds (repetitions ≤ 20, ≤ 50 targets, ≤ 20 chaos faults, timeouts ≤ 3600 s), per-run hard timeouts, bounded drain of runaway requests, bounded in-memory event buffers, SSE ends with the job. |
| Untrusted target code | Target coded tools execute in the Crucible process | Only operator-registered projects run in service mode. Run untrusted projects in an isolated container per project (see `deploy/`); the API image runs as a non-root user. |
| Supply chain | Dependency drift | `uv.lock` / `pnpm-lock.yaml` frozen installs in CI and images; Neuro-SAN pinned exactly. |
| Indirect prompt injection in Crucible itself | Target outputs steering Crucible's agents | Crucible's agents receive tool JSON summaries, never raw target output beyond masked excerpts; instructions require citing tool ids; fixes are accepted only by the deterministic verifier. |
