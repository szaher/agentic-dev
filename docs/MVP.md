# Agentic Dev + AgentFlow MVP

Status: **proposal**, written after M16 (2026-10-03). It replaces the assumption that M17 → M18 → … → M22 are each built intact before anyone can use the product. Milestones are not releases (see [Milestones and releases](ROADMAP.md#milestones-and-releases)); this document decides what the first public release, the **Developer Preview**, must contain.

Owners in this document: **Agent Ready** (the standard), **agentic-dev** (repository and environment mechanics), **AgentFlow** (workflow policy and lifecycle). The boundary frozen in M16 does not move.

---

## 1. MVP definition

Today a developer can assess and fix a repository's agent readiness (agentic-dev), and separately run a governed implement → verify → review → approve loop (AgentFlow). But nothing connects the two around **a task**. Which skills, capabilities, trust level, isolation and verification a task gets is still assembled by hand across separate commands, nothing shows that whole picture before anything changes, and nothing records afterwards what the agent was actually given. The MVP makes this possible: **in an existing repository, a developer states a task, sees one plan of the environment the agent will get, approves it, and receives a verified, reviewed change made in an isolated workspace, together with a record of exactly what was used.** It is one guided flow with explicit approval, rather than a dozen independent switches.

---

## 2. Primary user journey

| # | Step | The developer… |
|---|---|---|
| J1 | Understand the repository | enters an existing repository; agentic-dev identifies languages, package managers, and build/test/lint/typecheck commands. |
| J2 | Assess readiness | sees the Agent Ready level and what blocks effective agent work. |
| J3 | Remediate | previews safe fixes, applies them, and commits them. Human decisions are listed, never guessed. |
| J4 | State a task | runs one command with a task description (for example "fix issue #123: …") and, optionally, an agent. |
| J5 | Resolve the session | gets the agent, pattern, skills, tools, capabilities, trust, isolation and verification resolved from the repository, its committed profile, and the task. |
| J6 | Review the plan | sees the whole plan before **any** mutation or execution, including what will *not* be exposed and anything that blocks the run. |
| J7 | Prepare | approves; the isolated workspace is created and only the selected skills are placed in it. Missing capabilities are reported, never enabled silently. |
| J8 | Hand off | AgentFlow takes over with the prepared workspace and the plan as its run's inputs. |
| J9 | Governed SDLC | agents plan, implement, verify and review under AgentFlow's pattern; deterministic gates and read-only reviews decide acceptance; risk decides human approval. |
| J10 | Result | receives the change (a branch), verification evidence, review evidence, the workflow outcome, and a **session record** of exactly what was used. |

The journey ends with J10 on the developer's machine. Opening a pull request, remote execution, and teams of agents are beyond the MVP (see §5).

---

## 3. User-visible experience

The target transcript. Output is illustrative, but every field shown is a requirement.

```console
$ agentic ready assess .
Repository  python (uv) · pytest · ruff · mypy
Readiness   foundational  (next: structured)
Blockers for structured
  conventions.tooling       Linting or formatting configured     → safe fix available
  feedback.tests.available  Runnable test suite                   → present (make test)
Run: agentic ready make . --target structured --dry-run

$ agentic ready make . --target structured        # safe changes only; asks for decisions it cannot make
$ git commit -am "Make repository agent-ready"
$ agentflow init                                   # once per repository; commit what it lists

$ agentflow run "Fix issue #123: divide() crashes on a zero denominator" --agent codex
Session plan                                                     (agentic session plan)
  Repository     python (uv) · readiness structured ✓ (required: foundational)
  Task           Fix issue #123: divide() crashes on a zero denominator
  Agent          codex · may write inside the worktree only · network: off
  Reviewer       claude · read-only
  Pattern        standard   plan → implement → verify → review → approve
  Skills         python-engineering, debugging, test-development     (3 of 16 built-in)
  Tools          serena, codegraph
  Capabilities   none required · secret-scan available, not enabled
  Trust          development
  Isolation      worktree agentflow/3f2c9a from 1a2b3c4 (checkout is clean ✓)
  Verification   lint, typecheck, test (full) · change-aware: off
  Not exposed    13 built-in skills · browser, database, cloud capabilities
  Also visible   2 user-level Claude skills outside agentic-dev's control (listed in the record)
Proceed? [y/N] y

Run 3f2c9a  pattern=standard  executor=codex  reviewers=claude
  ✓ plan        codex                         12s
  ✓ implement   codex                         1m48s
  ✓ verify      ruff · mypy · pytest (3 commands, all passed)
  ✓ review      claude (read-only): AGENTFLOW_REVIEW_PASS
  ✓ approve     auto-approved (risk: low)
Status: complete

$ agentflow report
Change         branch agentflow/3f2c9a  (2 files, +18 −3)   worktree ~/.local/share/agentic-dev/worktrees/…/agentflow-3f2c9a
Verification   passed · evidence .agentflow/evidence/3f2c9a/verify-gates.json
Review         passed · evidence .agentflow/evidence/3f2c9a/review-review-1-claude.json
Approval       auto (low risk)
Session record .agentflow/evidence/3f2c9a/session-record.json  (agentic.session-record v1)
Next           review the branch, then merge or open a pull request yourself
```

When the plan cannot proceed (readiness below the pattern's requirement, a required capability that is not enabled, a dirty checkout with isolation, a hand-edited managed block), it says so in the plan, before anything changes. Then it stops.

---

## 4. Journey capability map

Legend: ✅ exists · ◐ partial · ✗ missing. "Source" is the current roadmap milestone the work would have come from.

| # | Desired outcome | Exists | Partial | Missing | Source | Owner |
|---|---|---|---|---|---|---|
| J1 | Repository facts and canonical commands | `agentic repo inspect --json`; canonical command discovery (M16) | — | — | M5–M13, M16 | agentic-dev |
| J2 | Readiness level and blockers | `agentic ready assess/explain --json`, spec 1.0.1 | — | — | M14 | Agent Ready (standard), agentic-dev (assessment) |
| J3 | Safe remediation and enforcement | `ready plan/diff/apply/make/verify`, CI check | — | — | M15 | agentic-dev |
| J4 | One task entry point | `agentflow run TASK` | Task is a free-form string; agentic-dev has no task entry point | Nothing ties the task to environment resolution | M22 | AgentFlow (entry), agentic-dev (resolution) |
| J5 | Session resolution | `skills suggest --task`, `capabilities suggest --task`, trust profiles, `verify plan`, pattern requirements (M16) | Each answers separately. Skill suggestion is imprecise (it recommends `terraform-development` for a Python bug fix) | **One resolver and one plan document.** A committed repository profile as resolver input. A harness permission mode as part of the plan | M22 (session), M17 (EnvironmentProfile), M21 (intent file) | agentic-dev |
| J6 | Whole plan before mutation | `ready plan`, `skills add --dry-run`, `agentflow run --dry-run`, instruction-block dry runs | Each previews only its own piece | Combined plan with "not exposed" and blockers, plus an explicit approval step | M22 | agentic-dev (plan), AgentFlow (approval gate) |
| J7 | Prepare the workspace | Run worktree, dirty-checkout block, local (git-excluded) skill activation, capability status, readiness/capability preconditions (M16) | Skills are activated repo-wide, not per session; capabilities are checked but nothing is prepared per task | **`session prepare` in a given workspace** that places only the selected skills and verifies the rest. Report of harness assets outside agentic-dev's control | M22, M18 (scan) | agentic-dev (mechanics), AgentFlow (when: at run start) |
| J8 | Hand-off | Process + JSON contracts, handshake, control-root bridge (M16) | AgentFlow takes a pattern and a task, not a session | AgentFlow consumes `session-plan`/`session-record` | M16 follow-on | AgentFlow |
| J9 | Governed SDLC | Stages, attempts, fail-closed gates through `agentic verify`, read-only reviews, risk approval, worktree isolation, durable start | Harness invocation flags are fixed. The implementing agent gets **no** permission mode, so non-interactive edits may be refused or unbounded depending on the CLI. **No test runs a real agent end to end** (tests use a fake harness). OpenCode has no `agentic integrations install` | Permission mode per agent from the plan; real-harness end-to-end coverage; OpenCode parity | M22 (parity), new | AgentFlow (invocation, policy), agentic-dev (permission vocabulary) |
| J10 | Result and record | Branch per run, gate/review/agent evidence, `agentflow status` | No consolidated report; evidence is spread across files | **`agentflow report`** and a **session record**: contracts/features, versions, skill and provider digests, capabilities, trust, readiness document, pattern, run-start commit, harness CLI versions | M21 (lock), new | AgentFlow (report), agentic-dev (record content) |

What the map says:
- J1–J3 are done (M14–M16).
- The product gap is J4–J8. It is a *session*: one resolver, one plan, one preparation step, one record.
- J9 has two correctness gaps (harness permissions and real-harness coverage) that matter more than any new artifact type.

---

## 5. MVP scope

### Must-have

1. **Session plan** (`agentic session plan --task T [--agent A] [--pattern P] --json` → `agentic.session-plan` v1).
   - It is pure resolution: it never mutates. It composes repository facts, readiness, skill and capability recommendations, trust, isolation, the pattern's requirements, verification kinds and the harness permission mode.
   - The plan names what is *not* exposed, and every blocker.
2. **Repository profile.** A committed, versioned file (minimal EnvironmentProfile) that the resolver honours: preferred agent and reviewer, pattern, required/allowed skills and capabilities, trust ceiling, readiness target.
   - The same commit, profile and task produce the same plan.
   - This is the minimal subset of M17's EnvironmentProfile and M21's intent file, and nothing more.
3. **Session prepare in a workspace** (`agentic session prepare --plan F --path WS --json`). It places only the selected skills, locally and git-excluded, in the given workspace. It verifies, never enables, capabilities and trust. It reports harness assets it cannot control (for example user-level skills). It returns a `session-record` document.
4. **AgentFlow runs sessions.**
   - `agentflow run TASK` asks for the plan, prints it, and requires approval (`--yes` for scripts).
   - At run start it executes, in this order: worktree, then `session prepare` in that worktree, then preconditions, then stages.
   - It stores the plan and record as evidence, and passes the plan's permission mode to each harness invocation.
   - `--dry-run` shows the plan and changes nothing.
5. **Harness permission modes.** Each first-class harness (Claude Code, Codex, Pi, OpenCode) gets an explicit, recorded mode for implementing (write inside the workspace only) and for reviewing (read-only). These come from the plan rather than fixed flags. Where a CLI cannot express a mode, the plan says so.
6. **`agentflow report`.** One summary of the change (branch, diffstat), verification, reviews, approval and the session record path.
7. **Session record**, written into the run's evidence and schema-validated:
   - every contract and feature used;
   - agentic-dev and AgentFlow versions;
   - harness CLI versions;
   - skill and provider content digests;
   - capability state, trust and the readiness document;
   - the pattern and its digest;
   - the run-start commit and the worktree branch.

   This is the MVP's reproducibility promise: *what was used* is exact and verifiable. *Recreating it* is beyond the MVP.
8. **End-to-end acceptance test** (§7), in CI with a scripted harness and manually with at least one real agent before release.

### Should-have

- **Pack, single-agent and local.** A named, versioned, shareable repository profile (built-in or provider-supplied), selectable with `--pack`. It is the minimal M19: no AgentTeam, no remote installation.
- **Read-only harness asset scan** (`agentic catalog scan`). It lists what Claude, Codex, Pi and OpenCode already expose globally, so the plan's "Also visible" line is complete. It is the minimal M18: no import, export, vendor or fork.
- **Better task-aware skill selection.** Precision matters more once the plan shows it; a session with irrelevant skills undermines the "minimal surface" claim.
- **Context surface measurement.** Count the skills, MCP servers and instruction bytes exposed per session in the record. Measuring, not enforcing, is the minimal M22 budget.
- **OpenCode parity** in `agentic integrations install`.
- **agentflow#5:** validate a recorded worktree before resuming a run.

### Not MVP

- Federated discovery and supply-chain metadata for external ecosystems (M20).
- Content-addressed store; `env lock/diff/apply/export`; recreating an environment elsewhere (M21 beyond the session record).
- Context-budget *enforcement* (M22 beyond measurement).
- AgentTeam definitions and multi-agent packaging; portable Agent definitions across runtimes (M17/M19 beyond the profile and a single-agent pack).
- Catalog import/export, vendor/fork, URI model, remote scope (M18).
- MCP server and plugin management as artifacts (Serena and CodeGraph stay as today's tools).
- Running the agent itself inside a container or devcontainer (gates can already use execution backends).
- Organization policy (M23), credential broker (M24), unified remote execution (M25), evaluation and OpenTelemetry (M26), distribution polish beyond PyPI (M27).
- Opening pull requests, fetching issue text from GitHub, Windows.

---

## 6. Collapsed implementation sequence

The MVP replaces M17–M22 with five steps. Each step ends with something usable from the CLI. The remaining parts of M17–M22 return to the roadmap after the Developer Preview, re-planned from user feedback.

| Step | Delivers | Pulled from | Owner |
|---|---|---|---|
| **S1. Session plan** | `session-plan` v1 schema and contract; repository profile v1 (minimal EnvironmentProfile); `agentic session plan`; deterministic resolution tests; permission-mode vocabulary per harness | M22, M17, M21 (intent) | agentic-dev |
| **S2. Session prepare and record** | `session prepare --path WS`; per-session skill placement; capability and trust verification; asset-visibility report; `session-record` v1 | M22, M21 (record only), M18 (scan, minimal) | agentic-dev |
| **S3. AgentFlow sessions** | `agentflow run` plans, shows and approves; run start becomes worktree → prepare → preconditions; plan and record as evidence; permission modes passed to harnesses; `--dry-run` shows the plan | M16 follow-on | AgentFlow |
| **S4. Results and real agents** | `agentflow report`; harness permission modes verified against real Claude Code and Codex CLIs; scripted-harness end-to-end test in CI | new | AgentFlow (agentic-dev for record content) |
| **S5. Developer Preview** | §7 passes; should-haves that fit (pack, catalog scan, skill precision, OpenCode parity); #74 dev version; docs walkthrough; release per §8 | M19 (pack, minimal) | both |

S1 and the S4 harness investigation can start in parallel: the permission-mode vocabulary in S1 depends on what each CLI can actually express.

### Decisions to confirm before S1

- **D1. Where preparation runs.**
  - Recommendation: agentic-dev owns the plan and the preparation mechanics; AgentFlow decides *when* (at run start, inside the run's worktree). This keeps M16 decision 6 (AgentFlow owns the worktree lifecycle) and decision 3 (preconditions in the effective workspace).
  - The north-star `agentic session prepare` without AgentFlow (an ungoverned direct agent session) is then a should-have that reuses the same plan and record.
- **D2. Profile format and location.** Recommendation: a single file, `.agentic/profile.toml` (committed), with schema `profile` v1. It is a subset of M21's `config.toml` intent, so M21 can grow from it instead of replacing it.
- **D3. Pack in MVP.** Recommendation: should-have. A repository profile already makes sessions repeatable. A pack only adds sharing across repositories, which is valuable but not on the critical path of the journey.
- **D4. Approval default.**
  - Recommendation: `agentflow run` with a task always shows the plan and asks; `--yes` is required for non-interactive use.
  - Does an identical plan, already approved for this commit, skip the question?

---

## 7. MVP acceptance test

A throwaway repository, built by a script in CI (`scripts/mvp-acceptance.sh`) from a fixed fixture, run against the **installed** wheels of both projects.

**Fixture: `mvp-calc`**
- A small Python package (`calc/ops.py` with `divide()`), `pyproject.toml` managed by uv, pytest tests, and no linter configured.
- `ISSUE.md` describes bug #123: `divide(1, 0)` raises `ZeroDivisionError`, and the expected behaviour is that it raises `ValueError("denominator must be non-zero")`.
- A committed `.agentic/profile.toml`:
  - pattern `standard`, agent `codex`, reviewer `claude`;
  - readiness target `foundational`, trust ceiling `development`;
  - `skills.allowed = ["python-engineering", "debugging", "test-development"]`.

**Scenario (must pass without manual intervention except where stated)**
1. `agentic ready assess .` reports a level and names the missing linter as a blocker on the way to `structured`.
2. `agentic ready make . --target structured --dry-run` proposes a safe fix. `agentic ready make . --target structured` applies it, and the script commits it.
3. `agentflow init` succeeds, and the files it lists are committed.
4. `agentflow run --dry-run "Fix issue #123 …"` prints the session plan; `.agentflow/` and the worktree list are byte-identical before and after.
5. `agentflow run --yes "Fix issue #123 …"`:
   - **Before any stage:** the plan is printed. The worktree is created from the committed HEAD. Only the three allowed skills exist in the worktree's harness skill directories. The primary checkout is unchanged.
   - **Stages:** the implementing harness edits `calc/ops.py` and a test. The verify gate runs lint and test through `agentic verify run`, and passes. The review runs read-only and leaves the worktree fingerprint unchanged. Low risk is auto-approved.
   - **Result:** the status is `complete`, and branch `agentflow/<run>` has the change.
6. `agentflow report` lists the branch, diffstat, passed gates, passed review and the session record.
7. The session record:
   - validates against `agentic contracts schema session-record`;
   - lists exactly the three skills with their content digests, the trust profile, the readiness document, the pattern and its digest, the run-start commit and the harness versions.
8. Re-running `agentic session plan` with the same commit, profile and task yields an identical plan document, apart from timestamps.

**Negative scenarios (each stops before any stage, and the repository is unchanged)**
- Isolation with an uncommitted change in the checkout.
- Readiness below the profile's target.
- A required capability that is not enabled.
- A skill in the profile that is not installed.
- A hand-edited `agentflow.workflow` block during `agentflow init`.

**Harnesses**
- In CI, the implementing and reviewing "agents" are a scripted `CommandHarness` that applies a known patch and prints `AGENTFLOW_REVIEW_PASS`. This makes the test deterministic and credential-free.
- Before release, the same scenario is run manually on macOS and Linux with real Codex as the implementing agent and real Claude Code as the reviewer, and the transcripts are kept with the release notes.

---

## 8. Release criterion

The Developer Preview is published when all of these hold:

1. **Scenario:** §7 passes in CI on Linux and macOS against wheels and sdists installed from build artifacts. It also passes manually with real Codex and Claude Code on both platforms.
2. **Contracts:** `session-plan`, `session-record` and `profile` v1 are in `agentic contracts`, with schemas shipped in the package, and documented in `docs/API.md`. AgentFlow negotiates them through the handshake only.
3. **Safety:**
   - Every path that changes the repository or global state has a preview and an explicit approval.
   - Nothing enables a capability or escalates trust silently.
   - No harness is invoked with broader permissions than its plan states.
   - Any security-relevant issue is closed.
4. **Packaging:**
   - #74 is done, so development builds are distinguishable.
   - agentic-dev is published first. AgentFlow then declares a released `agentic-dev` range (no git pin) and is published.
   - The RELEASING.md consumer smoke test passes from PyPI for both packages.
5. **Docs:**
   - A quickstart that follows §3 step by step.
   - The known limitations: the §5 "Not MVP" list, plus harness-specific permission gaps.
   - A short explanation of what the session record does and does not guarantee.
6. **Version:** the version numbers of both packages are chosen at release time; no milestone dictates them.
