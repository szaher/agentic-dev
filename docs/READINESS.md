# Agent Ready assessment

`agentic ready` measures how ready a repository is for coding agents against the
**Agent Ready Specification**, which is owned by
[szaher/agent-ready](https://github.com/szaher/agent-ready/tree/main/spec).

```text
agent-ready   defines the readiness standard (spec v1: rules, evidence, maturity)
agentic-dev   assesses repositories against it          <- this document
AgentFlow     consumes the JSON contract to govern workflows
```

Assessment is deterministic and read-only, and it uses no LLM. The same
repository content and the same spec version always produce the same result.

## Commands

```bash
agentic ready assess .                          # maturity, levels, every requirement
agentic ready assess . --json                   # agentic.readiness-assessment v1
agentic ready assess . --target structured      # report progress toward a level
agentic ready assess . --verbose                # also list not-applicable rules

agentic ready explain .                         # why the repository has its level
agentic ready explain feedback.tests.available  # one rule: definition, evidence, status
agentic ready explain context.architecture --path ../service

agentic ready plan .                            # read-only plan to the next level
agentic ready plan . --target optimized --json  # agentic.readiness-plan v1
```

Every command accepts `--json` and `--spec PATH` (see [Spec source](#spec-source)).
The text views render the same documents as `--json`. Unknown rules, levels, or
specs exit with status `2`.

## Maturity

The five Agent Ready levels are:

| Rank | Level | In short |
|---|---|---|
| 0 | Unaware | the floor; no requirements |
| 1 | Foundational | agents can build and test: README with setup, test command, lint/format, build where needed |
| 2 | Structured | agents are told structure, conventions, and constraints: instruction file, architecture, conventions, prohibitions, type checking, tests, secrets hygiene |
| 3 | Optimized | complex work is supported: scoped instructions in workspaces, task workflows, machine-checkable architecture boundaries |
| 4 | Autonomous | automated gates: contribution workflow, CI tests, lint, and security, tracked agent effectiveness |

Maturity is **requirement-based**:

> A repository is at level N only when every *required* rule of level N and of
> every lower level is `pass` or `not-applicable`.

A single failing required rule blocks its level and every level above it, no
matter how many other rules pass. `unknown` blocks exactly like `fail`, so a
level is only claimed on positive evidence. Pass/fail counts are shown as
diagnostics but never decide the level. Recommended and advisory rules
never block.

The full list of rules per level is in the
[spec README](https://github.com/szaher/agent-ready/blob/main/spec/README.md#maturity-semantics).

## Statuses

| Status | When |
|---|---|
| `pass` | the rule applies and its evidence is present; `evidence` lists what was found, with file and line |
| `fail` | the rule applies and evidence is missing (`missing_evidence`) or prohibited evidence was found (for example a tracked `.env`) |
| `unknown` | the outcome cannot be established safely: the spec marks the rule as team policy (architecture boundaries, agent permissions, effectiveness tracking), or this assessor does not support an evidence type (`unsupported_evidence`) |
| `not-applicable` | the rule's applicability condition does not hold, for example no build step for a pure-Python project, or no MCP config to check for inline secrets |

Uncertainty is never reported as failure. `unknown` results carry the spec's
reason, and `agentic ready plan` marks them `human-required` with the decision
a person has to make. The tool will not invent architecture policy.

## Evidence

Evidence comes from the spec's evidence vocabulary and is gathered only from
repository content and Git metadata:

- **files and directories** (`AGENTS.md`, `CLAUDE.md`, CI workflows, lockfiles, …),
  matched with the spec's glob semantics (hidden and vendored directories are
  not traversed implicitly);
- **Markdown headings** in instruction files, the README, or the contributing
  guide (headings inside code fences are ignored);
- **file content** lines (for example `.env` in `.gitignore`, or a scanner in CI);
- **derived facts**, such as the test, build, lint, format, and typecheck commands.
  These reuse the same command discovery as `agentic repo inspect` and add the
  spec's extra sources (justfile, `check` targets, tox/nox, CMake, Swift, …);
- **tracked files** via `git ls-files`, so a local, ignored `.env` is not
  reported as a committed secret.

Workstation state (installed tools, local metrics, credentials, network) is
never evidence. Commands are discovered, never executed.

Heading and content checks show that a section *exists*, not that it is good.
Each result lists the matching heading and line so a person can judge quality.

## Guarantees

- **Read-only.** `assess`, `explain`, and `plan` never write to the repository:
  no files, no Git index, no `.agentic/`. A regression test snapshots every file
  (including `.git`) around all commands.
- **Deterministic.** Rules and evidence are id-sorted. There are no timestamps.
  Identical content gives identical output across checkouts.
- **Private.** No absolute paths. The repository is identified by directory
  name and HEAD `revision`. Evidence sources are repository-relative, and
  matches in MCP or security-sensitive content are reported as `<redacted>`.
- **Offline.** The spec is packaged with Agentic Dev.

The path you pass is resolved to its Git top-level directory, like
`agentic repo inspect`. A non-Git directory is assessed as-is (tracked-file
checks then fall back to the files present).

## Spec source

By default Agentic Dev uses the spec bundle pinned into the distribution:

```text
src/agentic_dev/readiness/specs/
├── agent-ready-spec-1.0.0.json   copy of agent-ready spec/dist (canonical JSON)
└── PIN.json                      spec_version, sha256, agent-ready source commit
```

The digest is verified on every load, and a mismatch is reported as a corrupt
installation. Every result reports the exact spec `name`, `version`,
`sha256`, and `source`.

To assess against a local spec under development, build it in agent-ready and
point at the bundle or its directory:

```bash
(cd ../agent-ready && pnpm spec:build)
agentic ready assess . --spec ../agent-ready/spec/dist
```

YAML sources are never read directly. The loader is a `SpecSource` abstraction,
so a signed or remote resolver can be added later without changing the engine.

### Updating the pinned spec

```bash
# agent-ready checkout at the merged commit to pin
python3 scripts/sync-agent-ready-spec.py --from ../agent-ready
python3 scripts/sync-agent-ready-spec.py --check   # also runs in `make syntax`
```

The sync refuses a dirty `spec/` tree. It replaces the vendored bundle and
records the new version, digest, and source commit. Spec major versions with a
`schema_version` the assessor does not support are rejected.

## Remediation (planning only)

Each rule declares a remediation classification:

| Classification | Meaning |
|---|---|
| `automatable` | can be produced from repository facts without inventing policy |
| `assisted` | tooling can scaffold, a person supplies or confirms the content |
| `human-required` | needs a team decision, which the plan states as *Required decision* |

`agentic ready plan` lists the required rules blocking the target in level and
dependency order, then recommended and optional items. It only *describes*
remediation. Applying it (`ready apply`) and CI regression gates are planned for
v0.15.

## Machine-readable contracts

| Command | `document_type` | Schema |
|---|---|---|
| `ready assess --json` | `agentic.readiness-assessment` | `schemas/readiness-assessment-v1.schema.json` |
| `ready explain --json` | `agentic.readiness-explanation` | `schemas/readiness-explanation-v1.schema.json` |
| `ready plan --json` | `agentic.readiness-plan` | `schemas/readiness-plan-v1.schema.json` |

See [API.md](API.md#agent-ready-assessment) for the stability rules shared by all
contracts. External consumers such as AgentFlow should call the CLI and read
these documents, not import Python internals.
