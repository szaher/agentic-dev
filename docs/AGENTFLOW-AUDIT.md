# AgentFlow / Agentic Dev boundary audit (v0.16, step 0)

Status: **audit. No code changes in either project.** Tracking: #33.
Audited: `szaher/agentflow` at `56b6e81` (agentflow-meta 0.1.0) against
`agentic-dev` 0.15.0 (`a4c25e4`). All behaviour below was confirmed against
source or by running the command.

```text
Agent Ready   defines the standard
Agentic Dev   assesses / prepares / verifies   (JSON + exit-code contracts)
AgentFlow     consumes those contracts and orchestrates (owns workflow semantics)
```

The v0.16 acceptance criteria (ROADMAP `# v0.16`) are the yardstick. They require
one repository/environment source of truth, process + JSON contracts only (no
imports of agentic-dev internals), AgentFlow keeping authority over gates and
transitions, and agentic-dev never owning workflow semantics.

## 1. Inventory of AgentFlow responsibilities

| # | AgentFlow code | What it does | Verdict |
|---|---|---|---|
| A1 | `gates.py: detected_commands` | Discovers lint/test/typecheck/build commands for Python, Node, Go, Rust, and Make, with fast/standard/strict profiles | **Duplicate → consume** `agentic repo inspect --json` (`commands`) or `agentic verify plan --json` |
| A2 | `gates.py: run_gates` | Runs gate commands on the host through `shell=True`, stopping on the first failure | **Overlap → consume** `agentic verify run --json` (adds backends/sandbox and a metrics record). AgentFlow still decides which kinds are mandatory |
| A3 | `harnesses/registry.py: detected` (`shutil.which`) | Harness availability for `detect` and `doctor` | **Duplicate → consume** `agentic doctor --json` (`tools`). That output covers claude, codex, and pi but **not opencode** (gap G6) |
| A4 | `bootstrap.py: init_project` → `AGENTS.md`, `CLAUDE.md` | Writes whole files. `--force` **overwrites** them | **Conflict** with agentic-dev managed blocks (see R1) |
| A5 | `bootstrap.py` → `agentflow-sdlc/SKILL.md` ×5 harness dirs | Generic skill placement in `.agents`, `.claude`, `.codex`, `.pi`, `.opencode` | **Duplicate mechanics → consume** agentic-dev skill/provider installation. AgentFlow keeps the **content** |
| A6 | `bootstrap.py` → `.opencode/agents/agentflow-reviewer.md` | Read-only reviewer permissions for OpenCode | **AgentFlow-owned** (review policy), with placement through the A5 mechanism |
| A7 | `cli.py: cmd_init --init-git` | `git init` | Trivial. Keep |
| A8 | `git.py: implementation_fingerprint` | Diff + untracked content hash binding evidence to code | **AgentFlow-owned** (evidence freshness is workflow semantics). Keep |
| A9 | `harnesses/common.py` before/after fingerprint | Detects reviewer mutation | **AgentFlow-owned** (review policy). Keep |
| A10 | `risk.py: classify` | Path-token risk → human approval | **Policy is AgentFlow-owned. Change discovery overlaps** `verify plan.changed_files` (see R3) |
| A11 | Engine, patterns, state, evidence, prompts, harness execution | Workflow semantics | **AgentFlow-owned. Out of scope** |
| A12 | (absent) worktree handling | Runs every stage in the repository root | **Gap → consume** `agentic worktree create/status/clean --json` |
| A13 | (absent) readiness | Never checks whether a repo is agent-ready | **Gap → consume** `agentic ready verify --json` for pattern `requires.readiness` |
| A14 | (absent) capability requirements | — | **Gap → consume** `agentic capabilities status --json` for `requires.capabilities` |
| A15 | (absent) metrics | Records nothing. agentic-dev already aggregates `agentflow.stage` events | **Gap → emit** `agentic metrics record agentflow.stage` (only when metrics are enabled; off by default) |

## 2. Risks found (must be resolved, not just noted)

**R1. `agentflow init --force` destroys agentic-dev managed content.**
It rewrites `AGENTS.md` and `CLAUDE.md` wholesale. Reproduced: `ready apply
--target structured` wrote a `readiness.commands` block, and `agentflow init
--force` then removed it, along with any human content. AgentFlow's
instructions should become **one managed block owned by AgentFlow** inside the
instruction file, never the whole file.

**R6. Readiness accepts AgentFlow's workflow commands as project commands.**
After R1, `context.agent_instructions.commands` still *passes*. The evidence is
the heading `## Useful commands` in AgentFlow's `AGENTS.md`, which lists only
`agentflow status/verify/…` and no build or test command. The evidence type
`agent.instructions.commands` matches any heading containing "commands". That
is a precision question for the **Agent Ready spec** (agent-ready owns it),
not something to patch in agentic-dev. It is recorded here so it is not lost.

**R2. A vacuous verification pass.** `agentic verify run` with zero applicable
checks returns `success: true` and exits `0`. I confirmed this on a fresh repo.
AgentFlow deliberately fails a gate when no gates are detected (`engine._gate`).
Mapping `verify run`'s exit code straight to a gate result would silently
weaken every gate. agentic-dev must report an explicit `no-checks` outcome, and
AgentFlow must treat it as not verified.

**R3. Change-aware verification needs a run base; AgentFlow risk misses new files.** `verify plan` selects
checks from changes since `--base` (default: working tree vs `HEAD`). If an
agent commits its work, the plan sees no changes and selects nothing, which
becomes R2. AgentFlow must record the run's start commit and pass `--base`.
Separately, AgentFlow's `risk.classify` uses `git diff --name-only HEAD`,
which **ignores untracked files**. A brand-new `auth/` module is therefore
classified as low risk and can be auto-approved. That is a live AgentFlow bug,
independent of v0.16. Reproduced: untracked `auth/tokens.py` → `('low', ['default classification'])`. `verify plan.changed_files` already includes untracked
files.

**R4. Two command discoverers inside agentic-dev.** `repo inspect`/`verify
plan` use `inspection.discover_commands`. `ready` extends it with
spec-defined sources (Makefile `check`, justfile, tox, nox, pytest.ini, …).
On this repo, `ready` finds `make check` as the test command, while `repo
inspect` reports **no** test command. Until there is one discoverer, "one
source of truth" is false *inside agentic-dev*, and AgentFlow would inherit
the weaker one.

**R5. Behaviour change on migration.** AgentFlow runs `python -m pytest -q` and
`npm run X`. agentic-dev proposes `uv run pytest` and pnpm/yarn/bun-aware
forms. The two are not equivalent on machines without `uv`, so migration is
visible to users and needs release notes.

## 3. Contract gaps in agentic-dev (what AgentFlow would need)

| Gap | Contract | Status today |
|---|---|---|
| G1 | `verify run` outcome | No schema (`agentic.verification-run`). No `no-checks` status. Exit code is 0/1 only |
| G2 | Worktree lifecycle | No schema for `agentic.worktree*` |
| G3 | Capability status | No schema |
| G4 | Single command discovery | R4 |
| G5 | Compatibility handshake | No machine-readable "contract versions supported". AgentFlow can only parse `agentic --version` |
| G6 | Harness coverage | `doctor.tools` and `skills --skills-target` have no `opencode` |
| G7 | Kind-filtered full verification | `verify` is change-aware only. AgentFlow's profiles mean "run these kinds over the whole project" |

`repo inspect`, `doctor`, `verify plan`, `metric-event`, `execution-result`, and
all `readiness-*` documents already have v1 schemas.

## 4. Decisions needed (cross-project boundary)

These decide who owns what, so they are the maintainer's call. Each has a
recommendation.

1. **Is agentic-dev a hard prerequisite of AgentFlow?**
   - (a) Required: AgentFlow deletes its detection code, and `agentflow doctor` fails with an install hint when `agentic` is missing or incompatible.
   - (b) Optional: AgentFlow keeps its own detection as a fallback.
   - **Recommend (a).** (b) keeps two sources of truth forever, which is exactly what v0.16 removes. Explicit `gates` in `.agentflow/config.json` stay as the escape hatch, with no detection.
2. **Gate semantics: full vs change-aware.**
   - **Recommend:** a gate stage runs **all discovered commands of the pattern's required kinds** (`verification.minimum`, e.g. `["lint","test"]`) for the whole project. That is today's AgentFlow behaviour, built on agentic-dev discovery (G7).
   - Change-aware selection (`verify plan --base <run-start>`) is an opt-in pattern field. It can add checks to a gate but never drop one.
   - Zero runnable checks for a required kind fails the gate.
3. **Readiness scope for `requires.readiness`.**
   - **Recommend `--scope local`** inside an AgentFlow run, because the agent works on the working tree.
   - CI keeps `--scope ci`.
   - The pattern requirement is a precondition checked at run start: it blocks with the `blockers` list and does not remediate. Running `ready make` is a separate, explicit human/agent action.
4. **Instruction-file ownership (R1).**
   - **Recommend:** AgentFlow's text becomes a managed block owned by AgentFlow (id `agentflow.workflow`), using agentic-dev's managed-block format and conflict rules.
   - It is written either through a new generic, opt-in agentic-dev command (`agentic instructions block put --owner agentflow …`) or by AgentFlow following the documented marker contract.
   - Never whole-file writes.
5. **Skill placement (A5).**
   - **Recommend:** AgentFlow ships its `agentflow-sdlc` skill as a provider package (provider-manifest-v1). agentic-dev installs it to each harness's directory.
   - AgentFlow stops writing five copies itself.
6. **Worktrees.**
   - **Recommend:** opt-in per pattern (`isolation: worktree`). AgentFlow calls `agentic worktree create --json` per run or attempt, records the path in run state, and decides when `clean` is allowed.
   - agentic-dev owns the Git mechanics only.

## 5. Proposed v0.16 slices (after decisions)

Same order as v0.15: contracts first, then consumption.

1. **agentic-dev contracts.** Unify command discovery (R4/G4). Give `verify run` a `no-checks` status with schema and exit code (G1/R2). Add a kind-filtered full verification mode (G7). Add schemas for worktree and capability status (G2/G3). Add a contract/compatibility document (G5). Add opencode coverage (G6).
2. **AgentFlow consumes discovery + verification.** Delete `gates.detected_commands` and route gates through agentic-dev (Decision 2). Record the run base (R3). Fix `risk.classify` to include untracked files (R3; can ship immediately as an AgentFlow bug fix).
3. **AgentFlow bootstrap via agentic-dev.** Managed instruction block (R1, Decision 4), skill provider (Decision 5), `doctor` delegation (A3).
4. **Pattern requirements.** `requires.readiness`, `requires.capabilities`, `verification.minimum`, `isolation: worktree`. Metrics events (A15).

Each AgentFlow slice ships with a contract test that runs the **installed**
`agentic` binary and validates its JSON against agentic-dev's published
schemas. There are no Python imports across projects.
