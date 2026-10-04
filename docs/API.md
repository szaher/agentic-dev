# Machine-readable contracts

`agentic-dev` exposes stable JSON documents so AgentFlow, native agent integrations, CI, IDE extensions, and other tooling do not need to parse human-facing terminal output.

Current schema version: **1**.

## Compatibility handshake

```bash
agentic contracts --json              # agentic.contracts v1
agentic contracts schema NAME [--version V]
```

Consumers decide compatibility from this document, never from `agentic --version`
(`agentic_version` is informational only). It lists:

- `contracts`: contract name → document versions this installation emits, each with a JSON Schema shipped inside the package (`agentic contracts schema NAME` prints it, so an installed artifact can validate its own output);
- `document_types`: `<contract>@<version>` → the `document_type` values it covers;
- `features`: capability flags such as `commands.canonical-discovery`, `verification.full-kind-filter`, `verification.no-checks-status`, `worktree.lifecycle`, `instructions.managed-block`;
- `exit_codes`: stable process exit codes per command (`verify run`, `ready diff|apply|verify|make`, `instructions block`).

Adding a contract version or a feature is additive; removing one or changing a listed exit code is breaking.
Schemas live in `src/agentic_dev/schemas/`.

## Session planning (S1)

```bash
agentic contracts schema repository-profile
agentic contracts schema session-request
agentic contracts schema session-plan
agentic session plan --request request.json --path . --json
```

The committed `.agentic/profile.toml` is an optional `agentic.repository-profile@1` document. The caller supplies `agentic.session-request@1` as JSON. The planner emits `agentic.session-plan@1`; it reads repository and local environment facts and creates no workspace or session state. It does not launch a harness.

The request contains a task and named implementer/reviewer invocations. Each invocation has independent filesystem (`read-only`, `workspace-write`) and network (`off`, `on`) bounds. The profile may set role ceilings. The plan records requested and effective bounds, per-harness enforceability, concrete candidate mechanisms, and blockers. Missing enforcement evidence blocks the plan. See [SESSION-PERMISSIONS.md](SESSION-PERMISSIONS.md) for composition and scope.

`request_digest` hashes the canonical request. `inputs_digest` covers the current commit, profile, readiness, providers and skill content, capability and trust state, Serena/CodeGraph availability, detected versions and repository configuration, harness availability/version/facts, and contract/features. `plan_digest` hashes the semantic plan while excluding the absolute `repository` locator. Equivalent checkouts therefore retain the same approval identity. The `tools` array reports Serena and CodeGraph availability, version (or `null` when undetermined), and configuration (`.serena/project.yml` and `.codegraph/`); harness versions appear under `invocations`. Exit codes: `0` ready plan, `1` blocked plan, `2` invalid request or profile. A blocked plan is still valid JSON and must not be executed.

Minimal request:

```json
{
  "schema_version": "1",
  "document_type": "agentic.session-request",
  "task": "Fix a failing test",
  "invocations": [
    {"id": "implement", "role": "implementer", "harness": "codex"},
    {"id": "review", "role": "reviewer", "harness": "claude"}
  ]
}
```

The absence of a profile uses defaults. Permission boundaries are still checked and may produce blockers until the installed harness/version has verified enforcement facts.
When a local probe matches the exact harness version and platform, `enforcement.probe_id` points to the partial observation in [SESSION-PERMISSION-PROBE.md](SESSION-PERMISSION-PROBE.md). A probe ID does not mean the complete invocation is enforceable.

## Session preparation (S2)

```bash
agentic contracts schema session-record
agentic session prepare --plan approved-plan.json --path /path/to/linked-worktree --json
```

The caller supplies the exact approved `agentic.session-plan@1` document and an existing, separate linked worktree of its planning repository. The target worktree must be clean: tracked modifications and ordinary untracked files are refused. Previously prepared, Git-excluded skill directories permit idempotent reruns. The plan carries its canonical request. Preparation resolves that request again in the target worktree and compares `request_digest`, `inputs_digest`, and `plan_digest` before writing anything. A changed commit, profile, provider, skill, capability, trust setting, tool version or availability, harness fact, readiness result, or contract makes the plan stale. The caller must replan and approve the new digest.

A ready plan places only its selected skills under that worktree's harness skill directories. Each placed skill directory has a local `.gitignore` and is checked with Git before the command returns. Existing content is never overwritten. The emitted `agentic.session-record@1` identifies the plan, request, inputs, worktree commit, selected skills, capability and trust resolution, tools, invocations, and inspected visibility. Visibility lists detected workspace and user-level paths and explicitly marks what could not be determined; it does not assert that a harness loaded every path. The command never launches a harness or changes capability/trust configuration.

Exit codes: `0` prepared record, `1` blocked plan, `2` invalid plan or worktree, `3` `SESSION_PLAN_STALE` with no mutation, `4` skill placement conflict or I/O error, `5` `SESSION_WORKSPACE_DIRTY` with no Agentic Dev placement. A real harness whose enforcement remains `unknown` produces a blocked plan and cannot be prepared.

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
- zero or more install/test/lint/format/typecheck/build commands (`commands`, a map by kind) and the same list with provenance (`discovered_commands`: `{kind, command, source}` in deterministic order);
- installed and recommended skills;
- current optional-capability state;
- native agent integration status.

Polyglot repositories intentionally return **arrays** of commands. There is no single global `TEST_CMD` winner in the API contract.

Commands come from Agentic Dev's single canonical discovery service (`agentic_dev.commands`). `repo inspect`, readiness evidence (`command.*`), and verification all consume it, so they always agree.

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

The intended integration boundary is process/API-level, not Python-internal imports (decisions: [AGENTFLOW-AUDIT.md](AGENTFLOW-AUDIT.md)):

```text
AgentFlow
   |
   +-- agentic contracts --json               (handshake: required contracts/features)
   +-- agentic repo inspect . --json
   +-- agentic ready verify . --scope local --json
   +-- agentic verify run . --kind test --json
   +-- agentic worktree create|status|clean --json
   +-- agentic capabilities status --json
   +-- agentic instructions block put|remove --json
   +-- agentic doctor --json
   |
   +-- consumes facts / commands / capabilities
   +-- decides mandatory workflow gates and evidence policy
```

### Worktrees and capabilities

`agentic worktree create|list|status|clean --json` emit `agentic.worktree`, `agentic.worktrees`, `agentic.worktree-status`, and `agentic.worktree-clean` (contracts `worktree`, `worktree-list`, `worktree-status`, `worktree-clean`). Agentic Dev owns the Git mechanics; cleaning is always explicit and refuses dirty worktrees without `--force`. Exit codes: `worktree create` 0 created, 2 nothing created (path or branch exists, bad base); `worktree clean` 0 removed, 2 nothing removed (uncommitted changes without `--force`, the primary worktree, or an error).

`agentic capabilities status --json` is a bare map from capability name to state (contract `capability-status`). It predates document envelopes, so it has no `document_type`.

### Providers and skill activation

```bash
agentic providers inspect SOURCE --json        # agentic.provider-source: name, version, skills, content_digest (no install)
agentic providers list --json                  # agentic.providers: installed, verified, content_digest
agentic providers add SOURCE --sha256 D --json # agentic.provider-install (replaces a provider of the same name)
agentic skills add NAME... --target all --shared --json   # agentic.skills-activation
agentic skills add NAME... --target all --shared --dry-run --json   # same document, nothing written
```

`skills add --json` reports one outcome per (skill, harness): `written`, `unchanged`, or `skipped-unmanaged` (a `SKILL.md` not managed by Agentic Dev is never overwritten without `--force`). Any skipped outcome makes `status` `conflict` and exits 1; an unknown skill exits 2. `--dry-run` (`dry_run: true`, feature `skills.activation-dry-run`) writes nothing at all (no skill files, git excludes, `.agentic/skills.json` or metrics) and reports what a real run would do, conflicts included, so a caller can check every harness before changing anything else.

### Managed instruction blocks

```bash
agentic instructions block put --file AGENTS.md --owner agentflow --id workflow --content-file - --json
agentic instructions block remove --file AGENTS.md --owner agentflow --id workflow --json
agentic instructions block list --json
```

A tool owns the *content* of one `<owner>.<id>` block in a shared instruction file (`AGENTS.md`, `CLAUDE.md`, `.claude/CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`); Agentic Dev owns the *mutation*, using the same marker, hash, and conflict protocol as readiness remediation. Hand-edited blocks are never overwritten or removed; content outside the block is preserved byte for byte; writes are atomic with rollback; repeating a request is a no-op. The `readiness` owner and every `agentic*` owner (for example `agentic`, `agentic-dev`, `agentic-tools`) are reserved for Agentic Dev; tools such as `agentflow` use their own name. Document types `agentic.instruction-block` and `agentic.instruction-blocks`. Exit codes: `0` ok (`created`, `appended`, `replaced`, `unchanged`, `removed`, `absent`), `1` `conflict`/`refused` (nothing written), `2` usage, `3` rolled back.

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

## Verification run

```bash
agentic verify run [PATH] --json                          # change-aware plan
agentic verify run [PATH] --kind test --kind lint --json  # full-project, every discovered command per kind
agentic verify run [PATH] --command "make e2e" --json     # explicit commands (kind "custom")
agentic verify run [PATH] --kind test --include-changed   # full + change-aware additions
```

Document type `agentic.verification-run` v1 (`src/agentic_dev/schemas/verification-run-v1.schema.json`). `status` is authoritative:

| status | meaning | success | exit |
|---|---|---|---|
| `passed` | checks executed and all passed | `true` | 0 |
| `failed` | a check failed | `false` | 1 |
| `no-checks` | a requested kind had no runnable command (`missing_kinds`, nothing executed), or the run executed nothing | `false` | 1 |

Zero checks is never success. `--include-changed` may only add checks to the full baseline, never remove one. Full verification covers `build`, `test`, `lint`, and `typecheck` (`format` rewrites files and `install` prepares an environment, so neither is a check).


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
agentic metrics record <event-type> --field key=value [--session-id ID] [--path REPO] [--json]
```

With `--json` it emits `agentic.metric-record` (contract `metric-record`, feature `metrics.record-report`): `recorded: false` and `event: null` when metrics are disabled, otherwise the stored event. It exits 0 either way; a malformed `--field` exits 2. Callers never need to ask whether metrics are on: Agentic Dev decides, and only stores events when the user enabled metrics.

Event schema:

```text
src/agentic_dev/schemas/metric-event-v1.schema.json
```

The built-in exporter only writes JSON/JSONL files. There is no network export.
