# Roadmap

This roadmap turns `agentic-dev-env` from a workstation bootstrap into a stable developer capability control plane for coding agents.

The design boundary is:

```text
agentic-dev-env
  owns environment, repository discovery, capabilities, skills, trust,
  execution options, and verification discovery

AgentFlow
  owns workflow state, stages, retries, evidence semantics, approvals,
  and orchestration across coding harnesses
```

## Principles

1. **Machine-readable first.** Every important human-facing command should have a stable JSON form that another tool can consume.
2. **Detect, recommend, then enable.** Security-sensitive capabilities are never enabled just because they were detected.
3. **Least privilege.** Read-only and isolated modes are the default for browser, database, cluster, cloud, and observability access.
4. **One canonical source.** Repository facts, skills, capabilities, and verification commands should not be rediscovered independently by every integration.
5. **Agent-neutral core.** Claude Code, Codex, Pi, AgentFlow, CI, and future IDE adapters consume the same contracts.
6. **Verification is deterministic.** Agents may reason about what to run; compilers, linters, tests, scanners, and build tools decide whether checks pass.
7. **Upstream-friendly defaults.** Local setup should not pollute repositories or execute project-controlled installation scripts without explicit opt-in.

---

## Milestone 1 — Stable inspection contract (v0.5)

**Goal:** make `agentic-dev-env` consumable by AgentFlow and native integrations without parsing human-readable output.

### Deliverables

- `agentic repo inspect [PATH] --json`
- `agentic doctor --json`
- schema version on every machine-readable document
- repository facts and evidence
- detected package managers/frameworks/repository types
- deterministic install/test/lint/format/typecheck/build command discovery
- active/recommended skills
- enabled optional capabilities
- detected coding-agent integrations
- stable JSON Schema documents under `schemas/`

### Acceptance criteria

- read-only: inspection never modifies the repository;
- deterministic output for the same filesystem/tool state;
- schema validated in CI;
- additive evolution within schema version 1;
- AgentFlow can consume the output without importing agentic-dev-env internals.

---

## Milestone 2 — Security capability pack (v0.6) ✅

**Goal:** make security verification a first-class optional capability.

Initial capabilities:

- `secret-scan`
- `dependency-vulnerability`
- `sast`
- `iac-misconfiguration`
- `container-image-scan`
- `sbom`

Candidate providers:

- Trivy for vulnerabilities, secrets, IaC/configuration, images, and SBOM workflows
- Semgrep for source-level static analysis
- optional Gitleaks/OSV adapters where they materially improve coverage

### Acceptance criteria

- recommendation only by default;
- no remote upload of source code unless the selected provider explicitly requires it and the user opts in;
- machine-readable results;
- verification planner can consume security checks later.

---

## Milestone 3 — Trust and permission profiles (v0.7) ✅

**Goal:** make capability access explicit and composable.

Initial profiles:

- `safe`
- `development`
- `production-read`
- custom repo/user profiles

Permission vocabulary:

- repo read/write
- network/docs
- browser isolated/authenticated
- database read/write
- cluster read/write
- cloud read/write
- observability read
- secret access

### Acceptance criteria

- capability enablement declares required permissions;
- higher-risk modes require explicit selection;
- profiles are inspectable as JSON;
- no credentials are written into repository instructions.

---

## Milestone 4 — Worktree and session manager (v0.8) ✅

**Goal:** make parallel agent work safe by default.

Commands:

- `agentic worktree create <name>`
- `agentic worktree list`
- `agentic worktree status`
- `agentic worktree clean <name>`

Features:

- one task/agent per worktree;
- predictable worktree root;
- branch naming policy;
- collision detection;
- stale-worktree cleanup;
- optional agent/session metadata.

---

## Milestone 5 — Verification planner (v0.9) ✅

**Goal:** choose the smallest defensible verification plan for a change.

Inputs:

- Git diff
- repository inspection contract
- changed languages/frameworks
- Serena references
- CodeGraph impact
- repository-native commands
- enabled security capabilities

Output:

```text
changed files
affected symbols/components
recommended checks
why each check is needed
checks intentionally skipped
```

Commands:

- `agentic verify plan`
- `agentic verify run`
- `agentic verify --json`

AgentFlow should consume the plan but retain authority over which gates are mandatory.

---

## Milestone 6 — Execution backends and sandboxing (v0.10) ✅

**Goal:** stop assuming every agent command should execute directly on the host.

Backends:

- `host`
- `container`
- `devcontainer`
- optional `dagger`

Features:

- repo-specific backend selection;
- mounted workspace policy;
- network policy;
- secret injection boundary;
- disposable execution;
- normalized command result/evidence.

---

## Milestone 7 — Infrastructure capability packs (v0.11+) ✅

Add only as optional capability packs.

### Database

- PostgreSQL
- MySQL
- SQLite
- schema introspection
- migration validation
- ephemeral local databases
- read-only default

### Kubernetes/OpenShift

- kubectl / oc
- Helm / Kustomize
- resources/events/logs
- explicit `cluster-read` vs `cluster-write`
- context/namespace visibility before execution

### Cloud

- AWS
- Azure
- GCP
- credential/profile detection
- read-only default
- explicit write/admin elevation

### Observability

- OpenTelemetry-aware workflows
- logs
- metrics
- traces
- profiling
- provider adapters rather than a provider-specific core

---

## Milestone 8 — Provider ecosystem and lifecycle

**Goal:** make capabilities and skills extensible without hard-coding everything into the main repository.

Potential features:

- external skill providers
- external capability providers
- provider manifest/schema
- compatibility constraints
- signed/versioned source metadata
- `agentic update`
- compatibility checks for Claude/Codex/Pi/MCP providers
- migration hooks
- Linux/WSL support
- remote/SSH development profiles

---

## Milestone 9 — Measurement and evaluation

**Goal:** measure whether the environment actually improves coding-agent outcomes.

Possible metrics:

- tool calls per task
- failed command rate
- retries
- time to first passing focused test
- total verification duration
- context sources used
- change size
- reverted edits
- Serena/CodeGraph/Context7 usefulness
- skill/capability recommendation acceptance
- AgentFlow stage outcomes

Telemetry should be local/off by default unless the user explicitly enables export.

---

## Immediate execution order

The next implementation sequence is:

1. **v0.5 inspection contract**
2. security capability pack
3. trust profiles
4. worktree/session manager
5. verification planner
6. sandbox/execution backends
7. database / cluster / cloud / observability packs

This order is intentional. The inspection contract becomes the API every later feature and AgentFlow integration can build on.
