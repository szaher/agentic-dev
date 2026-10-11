# Agent readiness of this repository

Agentic Dev assesses its own repository against the Agent Ready Spec. The two
snapshots in this directory record the change from making it agent-ready:

- `assessment-before.json`: `main` at `f73a3dc`, before any changes.
- `assessment-after.json`: after adding `AGENTS.md`, lint/typecheck enforcement, and `.env` ignores.

Reproduce the measurement:

```bash
agentic ready compare docs/readiness/assessment-before.json docs/readiness/assessment-after.json
agentic ready compare docs/readiness/assessment-before.json   # baseline vs the repository now
```

## Result

**Unaware → Structured (+2 levels).** 11 rules improved and none regressed.
Passing rules went from 9 to 21, and failing rules from 20 to 9.

| Change | Rules it satisfied |
|---|---|
| `AGENTS.md` (+ `CLAUDE.md` importing it) | `context.agent_instructions`, `.commands`, `.concise`, `.file_pointers`, `context.task_workflows`, `conventions.documented`, `constraints.documented`, `constraints.agent_secrets_policy` |
| Ruff configured and enforced (`make lint`, CI) | `conventions.tooling` |
| mypy configured and enforced (`make typecheck`, CI); `tsconfig.json` for the Pi extension | `feedback.typecheck` |
| `.env` files ignored | `constraints.secrets.ignored` |

`feedback.build.available` moved from not-applicable to pass. The detected
`python -m build` command made the rule apply, so the comparison treats the move as neutral.

## Still open

| Level | Rule | Status | What it needs |
|---|---|---|---|
| Optimized | `constraints.architecture_boundaries` (required) | unknown | A machine-checkable boundary policy, such as an import-linter contract |
| Autonomous | `context.contribution_workflow` (required) | fail | An end-to-end contribution workflow or a pull request template |
| Autonomous | `feedback.ci.security` (required) | fail | A security check in CI, for example secret or dependency scanning |
| Autonomous | `feedback.agent_effectiveness` (required) | unknown | Declared agent-effectiveness tracking |
| Structured | `feedback.dependencies.locked` (recommended) | fail | A committed lockfile (`uv.lock`) |

Recommended and advisory rules still failing: `constraints.secrets.scanning`, `context.decisions`,
`context.issue_templates`, `conventions.exemplars`, `context.codeowners`, and `feedback.typecheck.strict`.
