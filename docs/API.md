# Machine-readable contracts

`agentic-dev-env` exposes stable JSON documents so AgentFlow, native agent integrations, CI, IDE extensions, and other tooling do not need to parse human-facing terminal output.

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
- agentic-dev-env version.

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
   +-- agentic doctor --json
   |
   +-- consumes facts / commands / capabilities
   +-- decides mandatory workflow gates and evidence policy
```

This keeps AgentFlow independent of the implementation details of repository detection.


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
