# Readiness remediation contract

Status: **contract v1, preview only** (v0.15 slice 1, #53). This document defines
*what* may be changed and *how* changes must behave before any command performs
them. `ready diff` / `ready apply` (#54) and `ready make` (#56) implement this
contract and must not extend it ad hoc.

```text
assessment (v0.14)  ->  remediation document (this contract)  ->  apply (#54)
"what is missing?"      "what can safely be fixed, and how?"      managed-block writes
```

## Remediation classes

Every open rule (`fail` or `unknown`) at or below the target level gets exactly
one class:

| Class | Meaning | What tooling may do |
|---|---|---|
| `safe-automatic` | The change can be produced deterministically from observed repository evidence, or from content the spec itself defines | Apply the referenced declarative actions |
| `human-decision` | The fix needs a person: project policy, substantive content, or a choice | State the decision and show detected **candidates**. Never pick one |
| `unsupported` | No safe action exists in this version, even though the spec calls the rule automatable (for example it would execute project code) | Explain why. Do nothing |

### The spec classification is an upper bound

The Agent Ready spec classifies each rule's remediation as `automatable`,
`assisted`, or `human-required`. Agentic Dev may **downgrade** that class, but it
never **upgrades** it:

| Spec classification | Allowed remediation classes |
|---|---|
| `automatable` | `safe-automatic`, `human-decision`, `unsupported` |
| `assisted` | `human-decision`, `unsupported` |
| `human-required` | `human-decision` |

This is the structural guarantee that no remediation invents architecture,
security, business, dependency, protected-path, exemplar, or performance policy.
To make an `assisted` rule automatic, the spec must change first, in
agent-ready.

## Document

`agentic.readiness-remediation` v1. Schema:
[`schemas/readiness-remediation-v1.schema.json`](../schemas/readiness-remediation-v1.schema.json).
Library entry point: `agentic_dev.readiness.remediation.propose(path, target=...)`.

```json
{
  "schema_version": "1",
  "document_type": "agentic.readiness-remediation",
  "mode": "preview",
  "spec": {"name": "agent-ready", "version": "1.0.0", "sha256": "…", "source": "builtin"},
  "maturity": {"current": "foundational", "target": "structured", "target_met": false},
  "actions": [
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
      "rules": ["context.agent_instructions", "context.agent_instructions.commands"]
    }
  ],
  "items": [
    {
      "rule_id": "context.agent_instructions",
      "spec_classification": "automatable",
      "remediation_class": "safe-automatic",
      "action_ids": ["readiness.commands@AGENTS.md"],
      "decision": null
    },
    {
      "rule_id": "constraints.architecture_boundaries",
      "status": "unknown",
      "spec_classification": "human-required",
      "remediation_class": "human-decision",
      "action_ids": [],
      "decision": {
        "question": "Which modules or layers may depend on which, and which dependencies are forbidden.",
        "candidates": [{"value": "src/api", "source": "src/api", "basis": "top-level source directory"}]
      }
    }
  ],
  "summary": {"safe_automatic": 3, "human_decision": 5, "unsupported": 1, "actions": 2}
}
```

The excerpt omits some required fields. The schema is authoritative.

- **Actions are first-class and deduplicated.** Several rules can be fixed by
  one action (one commands block satisfies both `context.agent_instructions`
  and `context.agent_instructions.commands`). Items reference actions by id, and
  `action.rules` lists the reverse mapping.
- **Items** cover every open rule up to the target, of any severity. They are
  ordered by severity (required, recommended, advisory), then level, then rule id.
- **Determinism.** Same repository content, spec, and target give the same
  document. There are no timestamps.

### Invariants (validated by `check_document` before a document is returned)

1. The `remediation_class` respects the upper-bound table above.
2. `safe-automatic` items reference at least one action. Other items reference
   none.
3. `human-decision` items carry a `decision` with a question. Candidates are
   options to show a person, never a selection.
4. Every action is referenced by an item, and records **provenance**:
   `evidence` (observed in the repository, with its source) or `spec`
   (content the spec itself defines, such as the `.env` ignore patterns). An
   action with no provenance is invalid.
5. Every action passes `check_action` (see below).

## Actions

v1 has exactly one action kind, `managed-block`. New kinds require a contract
change, never an ad-hoc edit.

| Field | Meaning |
|---|---|
| `path` | Normalized repository-relative path. Never absolute, never containing `..`, never inside `.git/` |
| `format` | Marker syntax, chosen from the file type (closed table below). Unknown file types cannot hold managed blocks |
| `block_id` | `readiness.<name>`, which is stable across runs |
| `content` | Block body without markers, normalized to no leading or trailing blank lines and one final newline. It must not contain marker text |
| `content_sha256` | sha256 of `content` |
| `prelude` | Written before the block **only** when the action creates the file (for example `# Agent instructions`) |
| `target` | Precondition captured at preview: `exists`, file `sha256`, and whether Git tracks it |

### Managed-block markers

| Format | Files | Markers |
|---|---|---|
| `markdown` | `*.md`, `*.mdc`, `*.markdown` | `<!-- agentic-dev:begin <block-id> sha256=<content-sha256> -->` … `<!-- agentic-dev:end <block-id> -->` |
| `hash` | `.gitignore`, `.gitattributes`, `.dockerignore`, `CODEOWNERS`, `*.yml`, `*.yaml`, `*.toml`, `*.cfg`, `*.ini`, `*.sh`, `*.py` | `# agentic-dev:begin <block-id> sha256=<content-sha256>` … `# agentic-dev:end <block-id>` |

The `sha256` in the begin marker records what Agentic Dev last wrote. A block
whose current body no longer matches its marker digest was **edited by hand**.

### Apply semantics (normative for #54)

For one action, compare the file on disk with the preview:

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

**Transactions and rollback.** A run snapshots every file it will touch (bytes
or absence) before writing. Each file is written to a temporary file in the same
directory and atomically renamed, preserving its mode. If any action in the run
fails or conflicts, every file touched so far is restored from its snapshot, and
created files are deleted. A run never leaves partial writes. A second run with
the same inputs is a no-op.

**Removal.** Removing a block deletes the lines from its begin marker through
its end marker, plus the single separator line inserted before it. If the file
is then empty or equal to the action's `prelude`, the file is deleted.

**Committed vs local.** `target.tracked` reports whether Git tracks the file.
Agentic Dev's `repo init` creates locally excluded `AGENTS.md`/`CLAUDE.md`. Blocks
written there satisfy a local assessment but are invisible to CI, and
`ready verify` (#55) must surface that difference.

## Current catalog (spec 1.0.0)

The spec marks five rules `automatable`. All others are `assisted` or
`human-required` and therefore `human-decision`.

| Rule | Class | Action / reason |
|---|---|---|
| `context.agent_instructions` | `safe-automatic`* | `readiness.commands` block in the first existing root instruction file (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.github/copilot-instructions.md`), otherwise a new `AGENTS.md` |
| `context.agent_instructions.commands` | `safe-automatic`* | the same `readiness.commands` action |
| `constraints.secrets.ignored` | `safe-automatic` | `readiness.secrets-ignored` block in `.gitignore`: `.env`, `.env.*`, keeping `.env.example`/`.sample`/`.template` trackable |
| `feedback.dependencies.locked` | `unsupported` | producing a lockfile runs the package manager (project code, network) |
| `context.issue_templates` | `unsupported` | templates would be generic content not derived from evidence |

\* When no commands are discovered there are no facts to document, so the item
becomes `human-decision` instead of creating an empty instruction file just to
satisfy the rule.

Candidate providers (detected, never chosen): top-level source directories for
`constraints.architecture_boundaries` and `context.architecture`, existing lint,
format, and type-checker configuration for `conventions.documented`, and
discovered commands for `context.readme.setup`.

## Open questions for later slices

- **Secret scanning and CI readiness checks.** The roadmap lists both as safe
  automatic, but `constraints.secrets.scanning` is `assisted` in spec 1.0.0, and a
  CI readiness check is not a spec rule. Making either automatic needs a spec
  change in agent-ready (reclassification is a minor spec change) or a separate,
  explicitly contracted "maintenance action" category. Decide in #55.
- **Applying a saved preview** (`ready apply --from preview.json`) relies on the
  `target` preconditions above. Whether to support it is decided in #54.
