# Readiness remediation contract

Status: **contract v1**. Defined in v0.15 slice 1 (#53), executed by `ready diff` /
`ready apply` (#54). The CI check maintenance action and the assessment scope ship
with `ready verify` (#55). `ready make` (#56) builds on all of these. Every
command implements this contract and must not extend it ad hoc.

> **The readiness spec controls what may be remediated. Agentic Dev controls how
> safely it performs permitted remediation. Maintenance actions only maintain
> Agentic Dev/readiness infrastructure.**

```text
assessment (v0.14)  ->  remediation document (this contract)  ->  apply (#54)
"what is missing?"      "what can safely be changed, and how?"    managed-block writes
```

## Commands

```bash
agentic ready diff .                       # unified diff of every permitted change; writes nothing
agentic ready apply . --dry-run            # same plan, plus the full remediation report
agentic ready apply . --target structured  # write the permitted changes, all-or-nothing
agentic ready apply . --json               # agentic.readiness-remediation, mode "applied"
```

| Exit code | `ready diff` / `ready apply` |
|---|---|
| `0` | planned, applied, or nothing to change |
| `1` | conflict or refusal: **nothing was written** |
| `2` | usage or spec error (unknown target, invalid spec, missing path) |
| `3` | a write failed and the whole run was rolled back |

Only changes owned by `safe-automatic` remediations or maintenance actions are
written. `human-decision` items are listed with their candidates, and
`unsupported` items with their reason. Neither is ever applied. Files are left
uncommitted for review. Changes to files Git does not track are flagged as
improving local readiness only.

The `--json` document is the remediation document with `mode` (`dry-run` or
`applied`), per-change `outcomes` (`create`, `append`, `replace`, `unchanged`,
`conflict`, `refused`, plus the file diff and `ci_visible`), and a `result`
(`planned`, `applied`, `no-op`, `conflict`, files `written`, `maturity_after`).

### Refreshing managed blocks

Once a rule passes it is no longer open. Its managed block would then never be
updated, even after new facts appear (for example a new `typecheck` target). A
passing rule whose own generated block is **stale** therefore gets a
`safe-automatic` remediation with `status: "pass"`, which only refreshes that
block. The rule already passes, so a refresh cannot satisfy anything new. A
hand-edited block that is not stale is left alone. A hand-edited block that is
stale is a conflict.

## Two kinds of change, kept structurally separate

| | Rule remediation | Maintenance action |
|---|---|---|
| Purpose | Fix an Agent Ready rule | Operational scaffolding for the Agentic Dev readiness lifecycle, such as a readiness CI check |
| Tied to a rule | Yes, exactly one rule per remediation | **Never** |
| Governed by | The rule's spec remediation classification (the **ceiling**) | This contract's maintenance rules |
| Can satisfy a readiness requirement | Yes. That is its purpose | **No.** It must be evidence-neutral (see below) |
| JSON location | `remediations[]` | `maintenance_actions[]` |

Both use the same change mechanism (`changes[]`, managed blocks), with the same
safety properties. Each change has exactly one owner.

## Rule remediation classes

Every open rule (`fail` or `unknown`) at or below the target level gets exactly
one class:

| Class | Meaning | What tooling may do |
|---|---|---|
| `safe-automatic` | The change can be produced deterministically from observed repository evidence, or from content the spec itself defines | Apply the referenced changes |
| `human-decision` | The fix needs a person: project policy, substantive content, or a choice | State the decision and show detected **candidates**. Never pick one |
| `unsupported` | No safe change exists in this version, even though the spec calls the rule automatable (for example it would execute project code) | Explain why. Do nothing |

### The ceiling rule

The Agent Ready spec classifies each rule's remediation as `automatable`,
`assisted`, or `human-required`. That classification is authoritative. Agentic
Dev may **downgrade** it, but it never **upgrades** it:

| Spec classification | Allowed remediation classes |
|---|---|
| `automatable` | `safe-automatic`, `human-decision`, `unsupported` |
| `assisted` | `human-decision`, `unsupported` |
| `human-required` | `human-decision` |

The ceiling is what guarantees that no remediation invents architecture,
security, business, dependency, protected-path, exemplar, or performance policy.
The dependency runs one way: agent-ready decides what is safe and appropriate,
and Agentic Dev obeys. A classification is never changed in agent-ready just so
Agentic Dev can automate something. If finer-grained automation is wanted, the
right fix is a better rule model in the spec.

## Maintenance actions

A maintenance action maintains Agentic Dev's own readiness infrastructure. The
first one, a readiness CI check, ships with `ready verify` (#55). Slice 1 defines
the category and its guards. Legitimate examples:

- add or update the Agentic Dev readiness CI check;
- add or update a managed readiness workflow block;
- add or update Agentic Dev-generated support configuration.

Every maintenance action has:

```json
{
  "id": "readiness.ci-check",
  "class": "safe-automatic",
  "kind": "maintenance-action",
  "title": "Readiness CI check",
  "reason": "…",
  "source": {"type": "agentic-dev", "contract": "readiness-remediation-v1"},
  "change_ids": ["readiness.ci-check@.github/workflows/agentic-readiness.yml"]
}
```

### What a maintenance action can never do

`check_maintenance` enforces each of these, and tests cover every one:

| Forbidden | Enforcement |
|---|---|
| Reference, claim, or stand in for a readiness rule | No rule fields (the schema forbids `rule_id`, `rules`, `spec_classification`). Its changes are owned by the maintenance action, which shares no change and no file with rule remediations |
| **Satisfy an Agent Ready requirement merely by existing**, or bypass an `assisted` / `human-required` / `unsupported` classification | **Evidence neutrality**: every line the change can introduce is checked against the spec's `path`/`heading`/`content` detections. Creating any evidence that a rule's `evidence` or `applies_when` depends on is rejected |
| Write anywhere it likes | Closed target allowlist (`.github/workflows/agentic-readiness.yml`). It contains no root-level files, so no `derived` evidence (which reads root manifests) can observe it. Adding a target is a contract change |
| Add credentials | Rejects `secrets.` references and `${{ secrets.* }}` |
| Grant permissions | Rejects `<scope>: write` and `write-all` |
| Enable cloud or cluster write access | Rejects cloud credential actions and kubeconfig use |
| Install arbitrary tools | Rejects installers (`curl`, `wget`, `sudo`, OS package managers, `npm i`, `pip install`, `cargo install`, …). The one exception is a `pip install agentic-dev==<exact version>` line, so the check runs the assessor it was generated for |
| Invent architecture policy, or enable security policy on the user's behalf | Follows from neutrality: such content would create gated evidence (for example a secret scanner in CI creates `ci.runs_security`) |

A maintenance action is always `safe-automatic`. If it cannot be produced safely
it is not proposed at all.

### Secret scanning stays `assisted`

`constraints.secrets.scanning` remains `assisted` in spec 1.0.0, so it is always a
`human-decision`. "Enable secret scanning" can mean materially different things:
using an installed scanner, installing one, modifying CI, adding a third-party
action, sending data to an external service, or changing repository security
policy. A maintenance action cannot add a scanner either: a readiness workflow
that ran `gitleaks` would create `ci.runs_security` and be rejected. A future
spec could split the rule (config present, local tool available, CI enforced)
with different classes. That change belongs in agent-ready.

## Document

`agentic.readiness-remediation` v1. Schema:
[`schemas/readiness-remediation-v1.schema.json`](../schemas/readiness-remediation-v1.schema.json).
Library entry point: `agentic_dev.readiness.remediation.propose(path, target=...)`.
Every document passes `check_document` before it is returned.

```json
{
  "schema_version": "1",
  "document_type": "agentic.readiness-remediation",
  "mode": "preview",
  "spec": {"name": "agent-ready", "version": "1.0.0", "sha256": "…", "source": "builtin"},
  "maturity": {"current": "foundational", "target": "structured", "target_met": false},
  "remediations": [
    {
      "rule_id": "context.agent_instructions",
      "spec_classification": "automatable",
      "remediation_class": "safe-automatic",
      "change_ids": ["readiness.commands@AGENTS.md"],
      "decision": null
    },
    {
      "rule_id": "constraints.architecture_boundaries",
      "status": "unknown",
      "spec_classification": "human-required",
      "remediation_class": "human-decision",
      "change_ids": [],
      "decision": {
        "question": "Which modules or layers may depend on which, and which dependencies are forbidden.",
        "candidates": [{"value": "src/api", "source": "src/api", "basis": "top-level source directory"}]
      }
    }
  ],
  "maintenance_actions": [],
  "changes": [
    {
      "id": "readiness.commands@AGENTS.md",
      "kind": "managed-block",
      "path": "AGENTS.md",
      "format": "markdown",
      "block_id": "readiness.commands",
      "content": "## Commands\n\n…\n- Test: `uv run pytest` (from `pyproject.toml`)\n",
      "content_sha256": "…",
      "prelude": "# Agent instructions\n",
      "target": {"exists": false, "sha256": null, "tracked": false},
      "provenance": [{"kind": "evidence", "type": "command.test", "value": "uv run pytest", "source": "pyproject.toml"}],
      "owner": {"type": "remediation", "rules": ["context.agent_instructions", "context.agent_instructions.commands"]}
    }
  ],
  "summary": {"safe_automatic": 3, "human_decision": 5, "unsupported": 1, "maintenance_actions": 0, "changes": 2}
}
```

The excerpt omits some required fields. The schema is authoritative.

### Invariants (`check_document`)

1. Each remediation's `spec_classification` equals the rule's classification in
   the loaded spec, and its `remediation_class` respects the ceiling.
2. `safe-automatic` remediations reference at least one change. Other
   remediations reference none. `human-decision` remediations carry a decision.
3. Each change has exactly one owner (`{"type": "remediation", "rules": [...]}`
   or `{"type": "maintenance-action", "id": ...}`), and every owner references
   its changes. One change can fix several rules (one commands block satisfies
   both `context.agent_instructions` and `.commands`).
4. No change belongs to both a remediation and a maintenance action, and the two
   never share a file.
5. Every maintenance action passes `check_maintenance`.
6. Every change passes `check_change` and records **provenance**: `evidence`
   (observed in the repository, with its source) or `spec` (content the spec
   itself defines). A change with no provenance is invalid.

**Determinism.** Same repository content, spec, and target give the same
document. There are no timestamps. Remediations are ordered by severity, then
level, then rule id. Changes and maintenance actions are ordered by id.

## Changes

v1 has exactly one change kind, `managed-block`. New kinds (for example a
managed whole file) require a contract change, never an ad-hoc edit.

| Field | Meaning |
|---|---|
| `id` | `<block_id>@<path>` |
| `path` | Normalized repository-relative path. Never absolute, never containing `..`, never inside `.git/` |
| `format` | Marker syntax, chosen from the file type (closed table below). Unknown file types cannot hold managed blocks |
| `block_id` | `readiness.<name>`, which is stable across runs |
| `content` | Block body without markers, normalized to no leading or trailing blank lines and one final newline. It must not contain marker text |
| `content_sha256` | sha256 of `content` |
| `prelude` | Written before the block **only** when the change creates the file |
| `target` | Precondition captured at preview: `exists`, file `sha256`, and whether Git tracks it |
| `owner` | The single owner (rule remediation or maintenance action) |

### Managed-block markers

| Format | Files | Markers |
|---|---|---|
| `markdown` | `*.md`, `*.mdc`, `*.markdown` | `<!-- agentic-dev:begin <block-id> sha256=<content-sha256> -->` … `<!-- agentic-dev:end <block-id> -->` |
| `hash` | `.gitignore`, `.gitattributes`, `.dockerignore`, `CODEOWNERS`, `*.yml`, `*.yaml`, `*.toml`, `*.cfg`, `*.ini`, `*.sh`, `*.py` | `# agentic-dev:begin <block-id> sha256=<content-sha256>` … `# agentic-dev:end <block-id>` |

The `sha256` in the begin marker records what Agentic Dev last wrote. A block
whose current body no longer matches its marker digest was **edited by hand**.

### Apply semantics (normative for #54)

These rules apply equally to rule-remediation changes and maintenance changes.
For one change, compare the file on disk with the preview:

| State on disk | Behavior |
|---|---|
| File changed since preview (`sha256` or existence differs from `target`) | **Conflict**: refuse, and ask the user to preview again |
| Target is a symlink, a directory, or resolves outside the repository | **Refuse** |
| File uses CRLF line endings | **Refuse** in v1 (no mixed line endings) |
| File absent | Create it as `prelude` (if any), one blank line, then the block |
| File present, no block with this id | Append: guarantee a trailing newline, insert one blank separator line if the file is non-empty, then the block |
| Block present, body digest ≠ marker digest | **Conflict**: hand-edited block, never overwritten |
| Block present, marker digest = new `content_sha256` | **No-op** (idempotent) |
| Block present and unmodified, content differs | Replace the block in place |
| Duplicate or unbalanced markers for this id | **Conflict** |

Bytes outside the managed block are always preserved exactly.

**Transactions and rollback.** A run plans every change in memory first. Any
conflict or refusal means nothing is written. Otherwise it snapshots every file
it will touch (bytes or absence) and re-verifies each file's bytes immediately
before writing it. Each file is written to a temporary file in the same
directory and atomically renamed, preserving its mode. If any change in the run
fails or conflicts, every file touched so far is restored from its snapshot, and
created files are deleted. A run never leaves partial writes. A second run with
the same inputs is a no-op. Constructing a change never runs package managers or
installers and never needs the network.

**Removal.** Removing a block deletes the lines from its begin marker through
its end marker, plus the single separator line inserted before it. If the file
is then empty or equal to the change's `prelude`, the file is deleted.

## Assessment scope: local vs CI (normative, implemented in #55)

Local assessment and CI assessment can legitimately differ. Agentic Dev's
`repo init` writes `AGENTS.md`/`CLAUDE.md` and excludes them from Git locally, so
they count as evidence in the working tree but do not exist in a CI checkout.

- **CI readiness verification must evaluate evidence available from the
  tracked repository.** It must never rely on untracked or Git-excluded local
  Agentic Dev state. Local-only evidence is never silently treated as CI
  evidence.
- Every readiness document carries `"scope": "local"` or `"scope": "ci"`. `ci`
  sees only files `git ls-files` reports. Content is read from the working tree, so
  run `ready verify` in CI for the authoritative result. Locally it is the
  closest approximation: untracked, ignored, and Git-excluded files never count,
  and command discovery ignores untracked sources (for example an untracked
  `Makefile`). The `ci` scope requires a Git repository.
- A local run may report both views and their difference. That difference is
  useful information and must not be hidden:

  ```text
  Local readiness:      Structured
  CI-visible readiness: Foundational

  Difference:
    context.agent_instructions
      local evidence: AGENTS.md
      CI evidence:    unavailable because the file is not tracked
  ```

- `apply`/`make` report when a change targets an untracked or Git-excluded file
  (`target.tracked: false`), because it improves local readiness but not
  CI-visible readiness.

## Current catalog (spec 1.0.0)

The spec marks five rules `automatable`. All others are `assisted` or
`human-required` and therefore `human-decision`. A test fails if a future spec
adds an `automatable` rule that is not explicitly handled here.

| Rule | Class | Change / reason |
|---|---|---|
| `context.agent_instructions` | `safe-automatic`* | `readiness.commands` block in the first existing root instruction file (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`), otherwise a new `AGENTS.md` |
| `context.agent_instructions.commands` | `safe-automatic`* | the same `readiness.commands` change |
| `constraints.secrets.ignored` | `safe-automatic` | `readiness.secrets-ignored` block in `.gitignore`: `.env`, `.env.*`, keeping `.env.example`/`.sample`/`.template` trackable |
| `feedback.dependencies.locked` | `unsupported` | producing a lockfile runs the package manager (project code, network) |
| `context.issue_templates` | `unsupported` | templates would be generic content not derived from evidence |

\* When no commands are discovered there are no facts to document, so the
remediation becomes `human-decision` instead of creating an empty instruction
file just to satisfy the rule.

Candidate providers (detected, never chosen): top-level source directories for
`constraints.architecture_boundaries` and `context.architecture`, existing lint,
format, and type-checker configuration for `conventions.documented`, and
discovered commands for `context.readme.setup`.

### Maintenance catalog

| Action | Opt-in flag | Change |
|---|---|---|
| `readiness.ci-check` | `ready apply --ci-check` / `ready diff --ci-check` | `.github/workflows/agentic-readiness.yml` runs `agentic ready verify . --target <floor> --spec-version <v> --spec-sha256 <digest>` on pull requests and pushes |

Maintenance is **opt-in**: `propose`/`apply` only run the actions the caller
requests. Requested actions that cannot be produced are reported in
`maintenance_skipped` with a reason, never silently dropped.

The CI check:

- uses **today's CI-visible level as its floor**, so adding it never breaks CI on
  day one. It is skipped when there is nothing to protect (CI-visible `unaware`,
  or no Git repository). When the level later rises, the block becomes stale and
  `apply --ci-check` raises the floor;
- pins the **exact Agentic Dev version** that generated it
  (`pip install agentic-dev==<version>`, the one installation maintenance may
  perform), plus the spec version and sha256. Use a released version so CI can
  install it;
- runs with `permissions: contents: read` and only GitHub's own `checkout` and
  `setup-python` actions, with no credentials;
- passes `check_maintenance`. It creates only `ci.config` evidence, which no rule
  depends on directly, so adding the check never changes any rule's status.

## Decisions

- **No `ready apply --from preview.json` in v0.15.** Every run re-proposes from
  the current repository, then checks the `target` preconditions when planning
  and again immediately before each write. A saved preview could be added later
  on top of the same preconditions.
