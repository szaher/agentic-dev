# Machine-readable contracts

`agentic-dev` exposes stable JSON documents so AgentFlow, native agent integrations, CI, IDE extensions, and other tooling do not need to parse human-facing terminal output.

Current schema version: **1**.

## Repository inspection

```bash
agentic repo inspect . --json
```

Optional task context changes skill recommendations but does not mutate the repository:

```bash
agentic repo inspect . \
  --task "review the API compatibility of this change" \
  --json
```

The document includes:

- repository path/name;
- normalized repository facts;
- evidence for each fact;
- facts grouped by type;
- package managers;
- zero or more install/test/lint/format/typecheck/build commands;
- installed and recommended skills;
- current optional-capability state;
- native agent integration status.

Polyglot repositories intentionally return **arrays** of commands. There is no single global `TEST_CMD` winner in the API contract.

Schema:

```text
src/agentic_dev/schemas/repo-inspection-v1.schema.json
```

## Environment/doctor document

```bash
agentic doctor --json
```

The document includes:

- core tool availability and resolved executable paths;
- Claude Code/Codex/Pi availability and integration status;
- optional capability state;
- agentic-dev version.

Schema:

```text
src/agentic_dev/schemas/doctor-v1.schema.json
```

## Stability rules

For schema version 1:

- existing fields keep their meaning;
- fields may be added without a schema-version bump when consumers can safely ignore them;
- fields are not silently repurposed;
- breaking removals/renames/type changes require a new schema version;
- repository inspection is read-only;
- facts and recommendations are deterministic rules, not generated model judgments.

Consumers should check both:

```json
{
  "schema_version": "1",
  "document_type": "agentic.repo-inspection"
}
```

before interpreting a document.

## AgentFlow

The intended integration boundary is process/API-level, not Python-internal imports:

```text
AgentFlow
   |
   +-- agentic repo inspect . --json
   +-- agentic ready assess . --json
   +-- agentic doctor --json
   |
   +-- consumes facts / commands / capabilities
   +-- decides mandatory workflow gates and evidence policy
```

This keeps AgentFlow independent of the implementation details of repository detection.


## Agent Ready assessment

```bash
agentic ready assess . --json                      # agentic.readiness-assessment
agentic ready explain . --json                     # agentic.readiness-explanation (subject: repository)
agentic ready explain <rule-id> --path . --json    # agentic.readiness-explanation (subject: rule)
agentic ready plan . --target optimized --json     # agentic.readiness-plan
```

Schemas: `src/agentic_dev/schemas/readiness-assessment-v1.schema.json`, `src/agentic_dev/schemas/readiness-explanation-v1.schema.json`, `src/agentic_dev/schemas/readiness-plan-v1.schema.json`.

Every document identifies the assessor, the exact Agent Ready spec (`name`, `version`, `sha256`, `source`), and the repository by directory name and Git `revision`. Absolute paths are never included, and evidence `source` values are repository-relative.

Each entry in `requirements` has a `status`:

| Status | Meaning |
|---|---|
| `pass` | the rule applies and its evidence is present (`evidence` lists it) |
| `fail` | the rule applies and evidence is missing (`missing_evidence`) or prohibited evidence is present (`evidence`) |
| `unknown` | the outcome cannot be established safely: the spec marks the rule as team policy, or this assessor does not support an evidence type (`unsupported_evidence`) |
| `not-applicable` | the rule's applicability condition is not met (`applicability`) |

`maturity.current` is requirement-based. A level is reached only when every required rule of that level and every lower level is `pass` or `not-applicable`, and `unknown` blocks like `fail`. `summary`, `pillars`, and `dimensions` counts are diagnostics and never determine maturity.

The same repository content and the same spec version produce the same document, with no timestamps. Assessment is read-only: commands are never executed and nothing is written. Errors (unknown rule, target level, or spec) exit with status `2` and a message on stderr.

### Remediation contract (preview)

`agentic.readiness-remediation` v1 (`src/agentic_dev/schemas/readiness-remediation-v1.schema.json`) describes what can safely be changed toward a target level, in three separate parts:

- `remediations`: one per open Agent Ready rule. Each is `safe-automatic`, `human-decision` (a stated decision plus detected candidates), or `unsupported`, and the spec's remediation classification caps it (never upgraded).
- `maintenance_actions`: operational scaffolding for the readiness lifecycle, such as a readiness CI check. They are not rules and must be evidence-neutral: they can never satisfy or change a readiness requirement.
- `changes`: declarative managed-block edits with provenance, each owned by exactly one remediation set or maintenance action.

In v0.15 slice 1 it is a library preview (`agentic_dev.readiness.remediation.propose`). `ready diff`/`ready apply` build on it. See [REMEDIATION.md](REMEDIATION.md).

### Readiness make

`agentic ready make --target LEVEL --json` emits `agentic.readiness-make` v1 (`src/agentic_dev/schemas/readiness-make-v1.schema.json`): `status` (`target-met`, `needs-decision`, `no-safe-progress`, `conflict`, `rolled-back`, `round-limit`), `exit_code` (`0`, `1`, `3`, `4`; `2` is a usage error with no document), `dry_run`, `maturity` (`before`, `after`, `target_met`, `ci_visible`), `rounds`, `written`, `uncommitted`, `diffs` (dry run), and `remaining` (`human_decision` with candidates, `unsupported`).

### Readiness verification

`agentic ready verify --target LEVEL --json` emits `agentic.readiness-verification` v1 (`src/agentic_dev/schemas/readiness-verification-v1.schema.json`). It carries `scope` (default `ci`: tracked files only), `target`, `passed`, `exit_code` (`0` met, `1` not met, `3` pinned spec mismatch; `2` is a usage error with no document), `pin` (`spec_version`, `spec_sha256`, `matched`, `problems`), `maturity`, `blockers`, and, for the `ci` scope, `local`: the working-tree maturity and per-rule `differences` with their `local_only_evidence`. Every readiness document (assessment, explanation, plan, remediation, verification) carries `"scope": "local" | "ci"`.

## Verification plan

```bash
agentic verify --json
agentic verify plan --path . --base main --json
```

Document type:

```json
{
  "schema_version": "1",
  "document_type": "agentic.verification-plan"
}
```

Schema:

```text
src/agentic_dev/schemas/verification-plan-v1.schema.json
```

The plan is advisory to orchestration layers: AgentFlow may make any subset of checks mandatory or add policy-specific gates.


## Execution result

```bash
agentic execution run "pytest -q" --json
```

Document type:

```json
{
  "schema_version": "1",
  "document_type": "agentic.execution-result"
}
```

Schema:

```text
src/agentic_dev/schemas/execution-result-v1.schema.json
```

Execution results include backend, exact argv, normalized stdout/stderr/return code, and backend metadata.


## Infrastructure status

```bash
agentic infra status --json
```

Document type:

```json
{
  "schema_version": "1",
  "document_type": "agentic.infrastructure-status"
}
```

Schema:

```text
src/agentic_dev/schemas/infrastructure-status-v1.schema.json
```

Infrastructure operation results are normalized JSON documents specific to database, cluster, cloud, and observability operations.


## Provider lifecycle

```bash
agentic providers doctor --json
```

Provider manifests use:

```text
src/agentic_dev/schemas/provider-manifest-v1.schema.json
```

Installed providers may contribute skills and command-backed capabilities only when their recorded content digest still matches. Provider Git sources retain the resolved commit SHA and signature status.

## Remote development profiles

```bash
agentic remote list --json
agentic remote test <name> --json
```

Remote state is local user configuration and contains connection metadata only. Passwords and private-key contents are not stored.


## Measurement

Metrics are disabled by default.

```bash
agentic metrics status
agentic metrics summary --json
```

External local integrations such as AgentFlow can submit schema-v1 events through:

```bash
agentic metrics record <event-type> --field key=value
```

Event schema:

```text
src/agentic_dev/schemas/metric-event-v1.schema.json
```

The built-in exporter only writes JSON/JSONL files. There is no network export.
