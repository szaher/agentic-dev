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
schemas/repo-inspection-v1.schema.json
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
schemas/doctor-v1.schema.json
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

Schemas: `schemas/readiness-assessment-v1.schema.json`, `schemas/readiness-explanation-v1.schema.json`, `schemas/readiness-plan-v1.schema.json`.

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

`agentic.readiness-remediation` v1 (`schemas/readiness-remediation-v1.schema.json`) describes what can safely be fixed toward a target level. Each open rule is `safe-automatic` (declarative managed-block actions with provenance), `human-decision` (a stated decision plus detected candidates), or `unsupported`. The spec's remediation classification is an upper bound and is never upgraded. In v0.15 slice 1 it is available as a library preview (`agentic_dev.readiness.remediation.propose`). `ready diff`/`ready apply` build on it. See [REMEDIATION.md](REMEDIATION.md).

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
schemas/verification-plan-v1.schema.json
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
schemas/execution-result-v1.schema.json
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
schemas/infrastructure-status-v1.schema.json
```

Infrastructure operation results are normalized JSON documents specific to database, cluster, cloud, and observability operations.


## Provider lifecycle

```bash
agentic providers doctor --json
```

Provider manifests use:

```text
schemas/provider-manifest-v1.schema.json
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
schemas/metric-event-v1.schema.json
```

The built-in exporter only writes JSON/JSONL files. There is no network export.
