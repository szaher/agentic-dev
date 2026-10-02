# AgentFlow / Agentic Dev boundary audit (v0.16, step 0)

Status: **audit complete; decisions accepted** (maintainer review on #63, 2026-10-02).
The audit made no code changes in either project. Tracking: #33.
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

## 4. Accepted decisions (cross-project boundary)

These are frozen for v0.16. The end state:

```text
Agent Ready   owns the standard
Agentic Dev   owns repository/environment facts, verification mechanics,
              shared-file mutation, capabilities, worktrees
AgentFlow     owns workflow meaning, required gates, approvals, retries,
              evidence, lifecycle
```

1. **Agentic Dev is a hard runtime prerequisite of AgentFlow.**
   - AgentFlow keeps no fallback for discovering repositories, tools, or verification commands, and no fallback for executing them.
   - AgentFlow talks to Agentic Dev only through process + JSON contracts.
   - Compatibility is negotiated through a machine-readable contract/feature handshake, never by parsing `agentic --version`.
   - When the integration is released, AgentFlow's package declares an `agentic-dev` dependency.
   - Explicit user gate commands remain supported, but they **execute through Agentic Dev**. There is no AgentFlow shell fallback.
2. **Gates are full-project verification for every required kind.**
   - The gate runs every discovered command of each kind the pattern requires.
   - A required kind with zero runnable commands is a failure.
   - Change-aware checks may only **augment** that baseline, never remove a required full check:

     ```text
     required full checks  +  optional changed/affected checks
     ```

   - The default is full-only, which preserves current behaviour. Augmentation is enabled per pattern.
   - The run-start commit is recorded and passed as the change-aware `--base`.
3. **`requires.readiness` is a blocking, non-remediating precondition.**
   - It is checked with `local` scope in the **effective execution workspace**.
   - A failed requirement blocks the run and reports the blockers.
   - AgentFlow never calls `ready make` implicitly.

   ```text
   create/select worktree (if the pattern enables isolation)
       ↓
   readiness + capability preconditions (in that workspace)
       ↓
   first workflow stage
   ```

4. **AgentFlow owns instruction content; Agentic Dev owns shared-file mutation.**
   - Agentic Dev adds a generic managed-block process/JSON API, and AgentFlow places an `agentflow.workflow` block through it.
   - AgentFlow does not reimplement the marker/hash/conflict protocol.
   - Shared instruction files (`AGENTS.md`, `CLAUDE.md`, and other harness instruction files) are never rewritten wholesale.
   - Files owned wholly by AgentFlow may still be replaced atomically.
5. **AgentFlow owns the `agentflow-sdlc` skill content; Agentic Dev owns placement and activation.**
   - The skill ships through the existing provider/skill mechanism.
   - Provider-manifest v1 is not extended toward portable Agent artifacts; that is v0.17.
   - The dedicated OpenCode reviewer file stays AgentFlow-owned for v0.16.
6. **Worktrees are opt-in per pattern and default off.**
   - There is **one worktree per run**, not one per attempt.
   - Agentic Dev owns create/status/clean mechanics. AgentFlow owns lifecycle policy and stores the returned path, branch, and base in run state.
   - Isolation is created before preconditions run.
   - Worktrees are never force-cleaned automatically. Failed or blocked runs keep theirs; cleanup-on-success is optional pattern policy.

Contract notes from the review:

- **R2/G1:** `verify run` with no runnable checks, or a required kind with none, emits `status: "no-checks"` and `success: false`, and exits **1**. No new exit code is added. AgentFlow keys off the structured status, not only the exit code.
- **R4/G4:** there is **one canonical command-discovery service** in Agentic Dev. `repo inspect`, readiness, and verification all consume it, and readiness keeps no hidden stronger discoverer.

## 5. v0.16 plan

Contracts first, then consumption. Prerequisites A and B come before the slices.

**Prerequisite A: AgentFlow risk bug (R3).**
- `risk.classify` includes untracked files.
- A regression test pins the untracked `auth/tokens.py` case.
- Ships now as a standalone AgentFlow fix. v0.16 may later replace this change discovery with Agentic Dev's.

**Prerequisite B: Agent Ready Spec 1.0.1 command-evidence fix (R6).**
- `agent.instructions.commands` means the instruction file documents at least one recognized **project command**, not merely a heading containing "commands".
- This is a spec semantics bugfix, and the evidence becomes derived.
- Agentic Dev re-vendors the bundle and updates the derived evidence.
- It lands before AgentFlow relies on `requires.readiness`.

**Slice 1: Agentic Dev contracts.**
- Canonical command discovery (R4).
- `verify run` schema with `no-checks` status (R2/G1).
- Full kind-filtered verification (G7).
- Worktree and capability-status schemas (G2/G3).
- Compatibility handshake (G5).
- Generic managed instruction-block API (decision 4).
- OpenCode doctor coverage (G6).

**Slice 2: AgentFlow discovery + gate consumption.**
- Remove `detected_commands`.
- Remove direct gate shell execution.
- Record the run-start base.
- Full required-kind verification.
- Optional change-aware augmentation.

**Slice 3: AgentFlow bootstrap integration.**
- Managed `agentflow.workflow` block.
- `agentflow-sdlc` skill provider.
- `doctor` delegation.

**Slice 4: pattern requirements.**
- `requires.readiness`.
- `requires.capabilities`.
- `verification.minimum`.
- Optional worktree isolation.
- Metrics events.

Each AgentFlow slice ships with a contract test. It runs the **installed**
`agentic` binary and validates the JSON against Agentic Dev's published
schemas. No Python imports cross projects.
