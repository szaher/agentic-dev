# Agentic Dev + AgentFlow MVP

Status: **accepted plan** (2026-10-03), written after M16. It replaces the assumption that M17 → M18 → … → M22 are each built intact before anyone can use the product. Milestones are not releases (see [Milestones and releases](ROADMAP.md#milestones-and-releases)); this document decides what the first public release, the **Developer Preview**, must contain.

The boundary frozen in M16 does not move:

```text
Agent Ready   → defines readiness
Agentic Dev   → resolves and prepares the environment
AgentFlow     → governs the workflow and its lifecycle
Harness       → performs the delegated work
```

The MVP keeps that split at the **session boundary**:
- AgentFlow resolves its own workflow (pattern, stages, reviewers, attempts, approvals). It then hands Agentic Dev a generic **environment request**.
- Agentic Dev resolves and prepares that environment and reports what it prepared.
- Agentic Dev never interprets AgentFlow semantics (`standard`, `tdd`, review stages, approval or retry policy).

---

## 1. MVP definition

Today a developer can assess and fix a repository's agent readiness (agentic-dev), and separately run a governed implement → verify → review → approve loop (AgentFlow). But nothing connects the two around **a task**. Which skills, capabilities, trust level, permissions, isolation and verification a task gets is still assembled by hand across separate commands, nothing shows that whole picture before anything changes, and nothing records afterwards what the agent was actually given. The MVP makes this possible: **in an existing repository, a developer states a task, sees one plan of the environment the agent will get, approves exactly that plan, and receives a verified, reviewed change made in an isolated workspace, together with a record of what was prepared and what happened.** It is one guided flow with explicit, plan-bound approval, rather than a dozen independent switches.

---

## 2. Primary user journey

| # | Step | The developer… |
|---|---|---|
| J1 | Understand the repository | enters an existing repository; agentic-dev identifies languages, package managers, and build/test/lint/typecheck commands. |
| J2 | Assess readiness | sees the Agent Ready level and what blocks effective agent work. |
| J3 | Remediate | previews safe fixes, applies them, and commits them. Human decisions are listed, never guessed. |
| J4 | State a task | runs one AgentFlow command with a task description (for example "fix issue #123: …") and, optionally, an agent. |
| J5 | Resolve the session | AgentFlow resolves the workflow and builds an environment request. Agentic Dev resolves it, with the repository profile, into a plan: agent, skills, tools, capabilities, trust, permissions, isolation and verification. |
| J6 | Review the plan | sees the whole plan, its digest, its blockers and what will *not* be exposed, before **any** mutation or execution. |
| J7 | Approve and prepare | approves this exact plan. AgentFlow creates the run's worktree; Agentic Dev revalidates the plan and prepares the worktree. Nothing is enabled silently. |
| J8 | Hand off | AgentFlow runs its stages in the prepared workspace with the permissions the plan enforces. |
| J9 | Governed SDLC | agents plan, implement, verify and review under AgentFlow's pattern; deterministic gates and read-only reviews decide acceptance; risk decides human approval. |
| J10 | Result | receives the change (a branch), verification and review evidence, the workflow outcome, and Agentic Dev's **session record** of what was prepared. |

The journey ends with J10 on the developer's machine. Opening a pull request, remote execution, and teams of agents are beyond the MVP (see §5).

---

## 3. User-visible experience

The target transcript. Output is illustrative, but every field shown is a requirement. Lines are grouped by owner: AgentFlow prints the workflow, and Agentic Dev's plan supplies the environment.

```console
$ agentic ready assess .
Repository  python (uv) · pytest · ruff · mypy
Readiness   foundational  (next: structured)
Blockers for structured
  conventions.tooling       Linting or formatting configured     → safe fix available
Run: agentic ready make . --target structured --dry-run

$ agentic ready make . --target structured        # safe changes only; asks for decisions it cannot make
$ git commit -am "Make repository agent-ready"
$ agentflow init                                   # once per repository; commit what it lists

$ agentflow run "Fix issue #123: divide() crashes on a zero denominator" --agent codex
Workflow                                                          (AgentFlow)
  Pattern        standard   plan → implement → verify → review → approve
  Reviewer       claude · read-only
Environment                                     (agentic session plan · plan sha256:9e1f…)
  Repository     python (uv) · readiness structured ✓ (required: structured = profile ∨ workflow)
  Agent          codex 0.48 · workspace-write ✓ enforced · network-off ✓ enforced
  Skills         python-engineering, debugging, test-development     (3 of 16 built-in)
  Tools          serena, codegraph
  Capabilities   none required · secret-scan available, not enabled
  Trust          development (ceiling: development)
  Isolation      worktree from 1a2b3c4 (checkout is clean ✓)
  Verification   lint, typecheck, test (full)
  Not exposed    13 built-in skills · browser, database, cloud capabilities
  Also visible   2 user-level Codex skills outside agentic-dev's control · visibility of MCP config: undetermined
Approve plan 9e1f…? [y/N] y

Run 3f2c9a  pattern=standard  executor=codex  reviewers=claude
  ✓ prepared    worktree agentflow/3f2c9a · plan 9e1f… revalidated
  ✓ plan        codex                         12s
  ✓ implement   codex                         1m48s
  ✓ verify      ruff · mypy · pytest (3 commands, all passed)
  ✓ review      claude (read-only): AGENTFLOW_REVIEW_PASS
  ✓ approve     auto-approved (risk: low)
Status: complete

$ agentflow report
Change         branch agentflow/3f2c9a  (2 files, +18 −3)
Verification   passed · evidence .agentflow/evidence/3f2c9a/verify-gates.json
Review         passed · evidence .agentflow/evidence/3f2c9a/review-review-1-claude.json
Approval       plan 9e1f… approved interactively · stage approval auto (low risk)
Session record .agentflow/evidence/3f2c9a/session-record.json  (agentic.session-record v1)
Next           review the branch, then merge or open a pull request yourself
```

When the plan has a blocker, it says so before anything changes, and then it stops. Blockers include:
- readiness below the effective minimum;
- a required capability that is not enabled;
- a permission the harness cannot enforce;
- a trust ceiling below what is requested;
- a dirty checkout when isolation is on;
- a hand-edited managed block.

If the plan becomes stale between approval and preparation, preparation refuses and nothing changes.

---

## 4. Journey capability map

Legend: ✅ exists · ◐ partial · ✗ missing. "Source" is the current roadmap milestone the work would have come from.

| # | Desired outcome | Exists | Partial | Missing | Source | Owner |
|---|---|---|---|---|---|---|
| J1 | Repository facts and canonical commands | `agentic repo inspect --json`; canonical command discovery (M16) | — | — | M5–M13, M16 | agentic-dev |
| J2 | Readiness level and blockers | `agentic ready assess/explain --json`, spec 1.0.1 | — | — | M14 | Agent Ready (standard), agentic-dev (assessment) |
| J3 | Safe remediation and enforcement | `ready plan/diff/apply/make/verify`, CI check | — | — | M15 | agentic-dev |
| J4 | One task entry point | `agentflow run TASK` | Task is a free-form string, and nothing derives an environment from it | — | M22 | AgentFlow |
| J5 | Session resolution | `skills suggest --task`, `capabilities suggest --task`, trust profiles, `verify plan`, AgentFlow pattern requirements (M16) | Each answers separately. Skill suggestion is imprecise (it recommends `terraform-development` for a Python bug fix) | **`session-request` → `session-plan`**; repository profile; composition rules; permission vocabulary with enforceability; plan identity (digests) | M22 (session), M17 (EnvironmentProfile), M21 (intent) | AgentFlow (request), agentic-dev (plan) |
| J6 | Whole plan before mutation | `ready plan`, `skills add --dry-run`, `agentflow run --dry-run`, instruction-block dry runs | Each previews only its own piece | Combined plan with blockers, "not exposed" and visibility; approval bound to `plan_digest` | M22 | agentic-dev (plan), AgentFlow (approval) |
| J7 | Approve and prepare | Run worktree, dirty-checkout block, durable run start, local (git-excluded) skill activation, capability status (M16) | Skills are activated repo-wide, not per session; nothing revalidates what was approved | **`session prepare --path WS`** with stale-plan refusal; per-session skill placement; selected-harness visibility inspection | M22, M18 (visibility, minimal) | AgentFlow (when, worktree), agentic-dev (mechanics) |
| J8 | Hand-off and enforcement | Process + JSON contracts, handshake, control-root bridge (M16) | The implementing agent is launched with **no** permission mode; only reviews are restricted to read-only | Enforced permission modes per invocation, failing closed when the harness cannot enforce one | new | AgentFlow (invocation), agentic-dev (vocabulary, enforceability facts) |
| J9 | Governed SDLC | Stages, attempts, fail-closed gates through `agentic verify`, read-only reviews, risk approval, worktree isolation | **No test runs a real agent end to end**; OpenCode has no `agentic integrations install` | Real-harness end-to-end coverage; OpenCode parity | M22 (parity), new | AgentFlow |
| J10 | Result and records | Branch per run, gate/review/agent evidence, `agentflow status` | No consolidated report; evidence is spread across files | **`agentflow report`** (AgentFlow's run record) wrapping **`agentic.session-record`** (what Agentic Dev prepared) | M21 (record only), new | AgentFlow (run), agentic-dev (session) |

What the map says:
- J1–J3 are done (M14–M16).
- The product gap is J4–J8. It is a *session*: a request, a plan with identity, plan-bound approval, revalidated preparation, enforced permissions, and two records split by owner.
- J9's real-harness gap matters more than any new artifact type.

---

## 5. MVP scope

### Session architecture

```text
 1. AgentFlow resolves workflow/pattern (its own config; never Agentic Dev)
 2. AgentFlow builds agentic.session-request@1
 3. agentic session plan --request R --json          # read-only
 4. AgentFlow shows the plan
 5. User approves plan_digest  (or --yes)
------------------------------------------------------------------
 no mutation before this line
------------------------------------------------------------------
 6. AgentFlow persists the approved run (plan_digest bound to the run)
 7. AgentFlow creates the run's worktree (M16 lifecycle)
 8. agentic session prepare --plan P --path WS --json
      → revalidates inputs; SESSION_PLAN_STALE = zero mutation
      → agentic.session-record@1
 9. AgentFlow revalidates its own prerequisites
10. AgentFlow executes its stages with the plan's enforced permissions
```

### Contracts

**`agentic.session-request@1`** is produced by AgentFlow. It holds only generic environment requirements:
- the task text and the requested harness (and reviewer harnesses, as additional read-only invocations);
- minimum readiness and required capabilities;
- allowed and required skills;
- the trust ceiling;
- verification kinds;
- per-invocation filesystem and network minimum access and ceilings, resolved independently (see [SESSION-PERMISSIONS.md](SESSION-PERMISSIONS.md)).

It never contains a pattern name, stages, attempts, or approval or retry policy.

**`agentic.repository-profile@1`** lives in `.agentic/profile.toml` and is committed. It is environment-only:
- preferred agent;
- readiness minimum;
- allowed and required skills;
- required capabilities;
- trust ceiling.

Pattern, reviewers, attempts, stages, approvals and workflow gates stay in AgentFlow's configuration.

**`agentic.session-plan@1`** is the resolved environment, with:
- harness and version;
- selected skills with provider/content digests, and the skills not exposed;
- tools and capabilities;
- trust;
- per-dimension permissions (`requested`, `effective`, `enforceable`, and how each is enforced);
- isolation requirements and verification kinds;
- visibility (prepared, detected external, undetermined);
- blockers;
- `request_digest`, `inputs_digest` and `plan_digest`.

**`agentic.session-record@1`** is what Agentic Dev prepared:
- the plan, repository, profile and request digests;
- Agentic Dev build identity, contracts and features;
- selected skills and provider digests, capabilities and trust;
- the readiness result;
- harness and tool versions;
- the enforced permissions;
- prepared-workspace facts.

It contains **no** AgentFlow facts.

### Composition rule (frozen)

> When sources are combined (profile, request, defaults), constraints can be strengthened but never silently weakened.

- **Readiness:** the effective minimum is the stronger of the two (profile `structured` + workflow `foundational` → `structured`).
- **Required capabilities and required skills:** union.
- **Allowed skills:** intersection. A required skill outside the allowed set is a blocker.
- **Trust:** the ceiling is the lower one. A request above the ceiling **blocks**; it never escalates (profile ceiling `safe` + workflow asking `development` → blocker).
- **Permissions:** filesystem and network resolve separately. A required minimum above the request or profile ceiling blocks; a missing or unverified harness enforcement mechanism also blocks.

### Plan identity and approval

- **`request_digest`** covers the canonical request.
- **`inputs_digest`** covers everything resolution read:
  - repository commit and profile;
  - installed provider and skill content;
  - capability state and trust configuration;
  - harness availability and version;
  - contracts and features.
- **`plan_digest`** covers the canonical plan, excluding timestamps and presentation fields.

Approval binds to `plan_digest` and is **per run**:

| Situation | Result |
|---|---|
| Same run, restart, same `plan_digest` | Approval preserved |
| New run, identical plan, same commit | Ask again |
| New run with `--yes` | Explicit non-interactive approval |
| Plan changes after approval | Approval invalid; replan and ask |

`session prepare` recomputes the inputs. If they no longer produce the approved `plan_digest`, it fails with `SESSION_PLAN_STALE` and changes nothing. This closes the plan → approve → prepare TOCTOU gap.

### Must-have

1. **The four contracts above**, with schemas in the package and offered through `agentic contracts`.
2. **`agentic session plan --request R --json`.**
   - Read-only, deterministic resolution: the same request and inputs give the same `plan_digest`.
   - Applies the composition rule and reports blockers.
   - Has human output.
3. **Permission vocabulary with enforceability.** For each first-class harness (Claude Code, Codex, Pi, OpenCode), Agentic Dev states:
   - which modes it can enforce, and how;
   - which harness version that applies to.

   An unenforceable mandatory restriction is a blocker (fail closed).
4. **`agentic session prepare --plan P --path WS --json`.**
   - Revalidates the plan (`SESSION_PLAN_STALE`, zero mutation).
   - Places only the selected skills, local and git-excluded, in `WS`.
   - Verifies capabilities and trust, but never enables them.
   - Returns `session-record`.
5. **Selected-harness visibility inspection.** For the harnesses in the plan, the record states:
   - exactly what Agentic Dev selected and prepared;
   - detected externally visible assets (for example user-level skills or MCP configuration);
   - any visibility it could not determine.

   The MVP promises exactly this, and not "everything the agent saw".
6. **AgentFlow sessions:**
   - building the request from its resolved workflow;
   - showing the plan;
   - per-run approval bound to `plan_digest`, persisted with the run (`--yes` for scripts);
   - the lifecycle above;
   - passing enforced permissions to every harness invocation;
   - `--dry-run` shows the plan and changes nothing.
7. **`agentflow report`.** It is AgentFlow's run record and wraps the session record:
   - run id and AgentFlow version;
   - pattern digest;
   - the worktree and branch lifecycle;
   - stages and attempts, gates, reviews and approvals;
   - the outcome.
8. **End-to-end acceptance test** (§7), in CI with a scripted harness and manually with real agents before release.

### Should-have

- **Pack, single-agent and local.** A named, versioned, shareable repository profile, selectable with `--pack`. It adds reuse across repositories and does not unlock the journey, so it must not delay S1–S4.
- **Broad catalog scan** (`agentic catalog scan`) across all harnesses. The MVP only needs the selected-harness inspection.
- **Better task-aware skill selection.** Precision matters more once the plan shows it.
- **Context surface measurement** in the session record: count of skills, MCP servers and instruction bytes exposed. This measures; it does not enforce.
- **OpenCode parity** in `agentic integrations install`.
- **agentflow#5:** validate a recorded worktree before resuming a run.

### Not MVP

- Federated discovery and supply-chain metadata for external ecosystems (M20).
- Content-addressed store; `env lock/diff/apply/export`; recreating an environment elsewhere (M21 beyond the session record).
- Context-budget *enforcement* (M22 beyond measurement).
- AgentTeam definitions and multi-agent packaging; portable Agent definitions across runtimes (M17/M19 beyond the repository profile and a single-agent pack).
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
| **S1. Deterministic session planning** | `repository-profile@1`, `session-request@1`, `session-plan@1`; profile loading and validation; request validation; composition rules; deterministic task-aware resolution; permission vocabulary and enforceability facts; blockers; `request_digest`, `inputs_digest`, `plan_digest`; human output and `--json` | M22, M17, M21 (intent) | agentic-dev |
| **S2. Prepare and record** | `session prepare --plan --path`; stale-plan refusal with zero mutation; per-session skill placement; capability and trust verification; selected-harness visibility inspection; `session-record@1` | M22, M21 (record only), M18 (visibility, minimal) | agentic-dev |
| **S3. AgentFlow sessions** | Request building from the resolved workflow; plan display; per-run approval bound to `plan_digest`; lifecycle steps 6–10; enforced permissions on every invocation; `--dry-run` shows the plan | M16 follow-on | AgentFlow |
| **S4. Results and real agents** | `agentflow report`; permission enforcement verified against real Claude Code and Codex CLIs; scripted-harness end-to-end test in CI | new | AgentFlow (agentic-dev for enforcement facts) |
| **S5. Developer Preview** | §7 passes; should-haves that fit; #74; docs walkthrough; release per §8 | M19 (pack, minimal) | both |

**Explicitly not S1:**
- no mutation;
- no `session prepare`;
- no worktree creation;
- no AgentFlow changes;
- no Pack, catalog, lockfile or store.

The enforceability facts in S1 depend on what each harness CLI can actually enforce, so investigating the real CLIs starts with S1, not S4.

### Decisions (settled 2026-10-03)

- **D1. Where preparation runs: accepted, with the request boundary.**
  - AgentFlow resolves its workflow and builds the request, then decides *when* to plan and prepare.
  - Agentic Dev owns planning and preparation mechanics. It never creates or manages the run's worktree; it prepares the path it is given.
- **D2. Repository profile: accepted, environment-only.** `.agentic/profile.toml` with schema `repository-profile@1`. The name avoids ambiguity with trust and execution profiles. The composition rule above is frozen with it.
- **D3. Pack: should-have.**
- **D4. Approval: per run, bound to `plan_digest`, never reused for a new run** (see the table in §5).

---

## 7. MVP acceptance test

A throwaway repository, built by a script in CI (`scripts/mvp-acceptance.sh`) from a fixed fixture, run against the **installed** wheels of both projects.

**Fixture: `mvp-calc`**
- A small Python package (`calc/ops.py` with `divide()`), `pyproject.toml` managed by uv, pytest tests, and no linter configured.
- `ISSUE.md` describes bug #123: `divide(1, 0)` raises `ZeroDivisionError`, and the expected behaviour is that it raises `ValueError("denominator must be non-zero")`.
- A committed `.agentic/profile.toml`:
  - preferred agent `codex`;
  - readiness minimum `foundational`;
  - trust ceiling `development`;
  - `skills.allowed = ["python-engineering", "debugging", "test-development"]`.
- AgentFlow's configuration selects pattern `standard` and reviewer `claude`.

**Scenario (must pass without manual intervention except where stated)**
1. `agentic ready assess .` reports a level and names the missing linter as a blocker on the way to `structured`.
2. `agentic ready make . --target structured --dry-run` proposes a safe fix. `agentic ready make . --target structured` applies it, and the script commits it.
3. `agentflow init` succeeds, and the files it lists are committed.
4. `agentflow run --dry-run "Fix issue #123 …"` prints the workflow and the session plan with its `plan_digest`; `.agentflow/` and the worktree list are byte-identical before and after.
5. `agentflow run --yes "Fix issue #123 …"`:
   - **Before any stage:**
     - the plan is printed and the run persists its approved `plan_digest`;
     - the worktree is created from the committed HEAD;
     - `session prepare` revalidates the plan;
     - only the three allowed skills exist in the worktree's harness skill directories;
     - the primary checkout is unchanged.
   - **Stages:**
     - the implementing harness runs with the plan's enforced permissions and edits `calc/ops.py` and a test;
     - the verify gate runs lint and test through `agentic verify run`, and passes;
     - the review runs read-only and leaves the worktree fingerprint unchanged;
     - low risk is auto-approved.
   - **Result:** the status is `complete`, and branch `agentflow/<run>` has the change.
6. `agentflow report` lists the branch, diffstat, passed gates, passed review, the approved `plan_digest` and the session record.
7. The session record:
   - validates against `agentic contracts schema session-record`;
   - lists exactly the three skills with their content digests, the trust, the readiness result, the enforced permissions, the harness versions and the visibility findings;
   - contains no AgentFlow-owned fields.
8. Re-running `agentic session plan` with the same request and unchanged inputs yields the same `plan_digest`.

**Negative scenarios (each stops before any stage, and the repository is unchanged)**
- Isolation with an uncommitted change in the checkout.
- Readiness below the effective minimum.
- A required capability that is not enabled.
- A skill in the profile that is not installed.
- A hand-edited `agentflow.workflow` block during `agentflow init`.
- **The approved plan becomes stale before prepare** (for example, a skill's content changes after approval): `SESSION_PLAN_STALE`, no preparation and no stage.
- **A required permission that the selected harness cannot enforce:** a blocker in the plan, and no harness invocation.

The last two are core safety tests, not optional hardening.

**Harnesses**
- In CI, the implementing and reviewing "agents" are a scripted `CommandHarness` that applies a known patch and prints `AGENTFLOW_REVIEW_PASS`. This makes the test deterministic and credential-free. The scripted harness declares its own enforceability, so the permission scenarios are testable without real CLIs.
- Before release, the same scenario is run manually on macOS and Linux with real Codex as the implementing agent and real Claude Code as the reviewer, and the transcripts are kept with the release notes.

---

## 8. Release criterion

The Developer Preview is published when all of these hold:

1. **Scenario:** §7 passes in CI on Linux and macOS against wheels and sdists installed from build artifacts, including every negative scenario. It also passes manually with real Codex and Claude Code on both platforms.
2. **Contracts:** `repository-profile`, `session-request`, `session-plan` and `session-record` v1 are in `agentic contracts`, with schemas shipped in the package, and documented in `docs/API.md`. AgentFlow negotiates them through the handshake only.
3. **Safety:**
   - Every path that changes the repository or global state has a preview and an approval bound to what was previewed.
   - Nothing enables a capability or escalates trust silently.
   - No harness is invoked without its plan's permissions enforced.
   - Any security-relevant issue is closed.
4. **Packaging:**
   - #74 is done, so development builds are distinguishable, and a development build refuses to generate a PyPI-pinned CI check.
   - agentic-dev is published first. AgentFlow then declares a released `agentic-dev` range (no git pin) and is published.
   - The RELEASING.md consumer smoke test passes from PyPI for both packages.
5. **Docs:**
   - A quickstart that follows §3 step by step.
   - The known limitations: the §5 "Not MVP" list, plus harness-specific permission gaps.
   - What the session record and run report do and do not guarantee.
6. **Version:** the version numbers of both packages are chosen at release time; no milestone dictates them.
