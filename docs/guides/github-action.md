# Crucible in GitHub Actions

Gate pull requests on **new** agent-network defects (routing loops, sly_data leaks, masked tool failures, prompt
injection, budget regressions) while tolerating known ones recorded in a baseline.

## 1. Record a baseline on `main`

```yaml
# .github/workflows/crucible-baseline.yml
on: { push: { branches: [main] } }
permissions: { contents: write }
jobs:
  baseline:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: shubham-dube/crucible/action@main
        with:
          project: agents            # directory with crucible.yaml
          fail-on: never
          write-baseline: .crucible/baseline.json
          comment: "false"
      - uses: actions/upload-artifact@v4   # or commit the file
        with: { name: crucible-baseline, path: .crucible/baseline.json }
```

## 2. Gate pull requests

```yaml
# .github/workflows/crucible.yml
on: pull_request
permissions: { contents: read, pull-requests: write, security-events: write }
jobs:
  crucible:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: shubham-dube/crucible/action@main
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}   # only if your networks call real LLMs
        with:
          project: agents
          baseline: .crucible/baseline.json
          fail-on: error
          repetitions: "3"           # agents are stochastic: judge 3 runs per scenario
```

What you get:
- **Step summary + sticky PR comment**: gate verdict, new / fixed / unchanged findings, metric regressions.
- **Code scanning alerts** (SARIF) pointing at the HOCON file and agent.
- **Exit code**: fails only on NEW findings at/above `fail-on` (or on metric regressions).

## Inputs
| input | default | meaning |
|---|---|---|
| `project` | — | directory containing `crucible.yaml` |
| `targets` | all | space-separated target names |
| `fail-on` | `error` | `error`, `warning` or `never` |
| `baseline` | — | baseline `.json` file; missing file = gate on all findings |
| `write-baseline` | — | write a fresh baseline file |
| `repetitions` | `1` | runs per scenario |
| `comment` | `true` | sticky PR comment |
| `upload-sarif` | `true` | upload to code scanning |

Locally the same gate is: `crucible audit agents --baseline .crucible/baseline.json --fail-on error`.
