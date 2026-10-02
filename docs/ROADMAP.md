# agentic-dev-env — Roadmap v2

## Executive summary

`agentic-dev-env` has completed its first roadmap. By v0.13 it is no longer just a workstation bootstrap: it is a developer capability control plane with repository inspection, skills, capabilities, trust profiles, security scanning, worktree isolation, verification planning, execution backends, infrastructure access, provider extensibility, native agent integrations, remote profiles, and local measurement.

Roadmap v2 moves the project from a capability control plane toward a **portable agentic development platform**.

The architecture across the three related projects is:

```text
                    agent-ready
             specification + education
                        |
                        | defines
                        v
                "What does good
                agent readiness
                   look like?"
                        |
                        v
                agentic-dev-env
       assess / configure / resolve / prepare
      catalog / trust / reproduce / measure
                        |
                        | prepares
                        v
                    AgentFlow
       workflow / stages / evidence / retries
           reviews / approvals / policy
                        |
                        v
        Claude / Codex / Pi / OpenCode / ...
```

The product boundary is:

- **Agent Ready** defines what an agent-ready repository is.
- **agentic-dev-env** assesses, prepares, reproduces, secures, and configures the environment agents work in.
- **AgentFlow** governs the software-development process performed by agents.

The north-star outcome is that a developer can enter a repository, assess its readiness, prepare a minimal and reproducible agent session, and then hand the prepared environment to AgentFlow or a coding agent.

---

## Current baseline

The completed v0.5–v0.13 roadmap established:

```text
Repository intelligence
├── repo detection
├── languages/frameworks
├── package managers
├── build/test/lint/typecheck discovery
├── Serena
├── CodeGraph
└── machine-readable inspection

Skills
├── built-in skill registry
├── task-aware recommendation
├── Claude activation
├── Codex activation
├── Pi activation
└── external providers

Capabilities
├── browser automation
├── browser debugging
├── Browser Use
├── security scanning
├── database
├── Kubernetes/OpenShift
├── cloud
└── observability

Trust
├── safe
├── development
├── production-read
└── custom profiles

Execution
├── host
├── container
├── devcontainer
├── Dagger
└── SSH profiles

Software-development safety
├── Git worktrees
├── agent session metadata
├── change-aware verification
├── security verification
└── local metrics

Extension
├── provider manifest
├── provider compatibility
├── source digests
├── signed Git commit checks
├── migration hooks
└── update lifecycle

Agent integrations
├── Claude Code
├── Codex
└── Pi

Platforms
├── macOS
├── Linux
└── WSL
```

The archived v0.5–v0.13 roadmap is in [`docs/roadmaps/ROADMAP-v0.5-v0.13.md`](roadmaps/ROADMAP-v0.5-v0.13.md).

---

# Product north star

A developer should eventually be able to run:

```bash
agentic ready assess .

agentic session prepare \
  --agent codex \
  --task "fix issue #123"
```

and receive something like:

```text
Repository
  Go + Kubernetes Operator

Agent readiness
  Level 3 — Optimized

Agent
  Codex

Skills
  go-engineering
  kubernetes-operator-development
  debugging
  test-development

Capabilities
  cluster-read
  secret-scan

Tools
  Serena
  CodeGraph

Trust
  development

Isolation
  worktree agentic/issue-123

Execution
  devcontainer

Verification
  targeted Go tests
  lint
  API tests
  security scan

Environment
  locked and reproducible

Metrics
  local only

Ready.
```

AgentFlow can then execute the governed workflow on top of that environment.

---

# Product boundaries

## Agent Ready owns

[Agent Ready](https://github.com/szaher/agent-ready) remains the source of truth for:

- agent-ready principles;
- Context / Conventions / Constraints / Feedback Loops;
- maturity levels;
- educational material;
- recommended practices;
- the future machine-readable Agent Ready specification.

It answers:

> What properties should an agent-ready repository have?

It should not become an environment manager or orchestration engine.

## agentic-dev-env owns

This repository owns:

- repository assessment;
- readiness evidence collection;
- safe remediation;
- environment configuration;
- tool/runtime discovery;
- skills;
- portable agent definitions;
- MCP definitions;
- capabilities;
- trust;
- reusable packs;
- artifact catalog;
- environment reproduction;
- provider lifecycle;
- execution environment preparation;
- worktrees;
- verification discovery;
- credential references;
- session context minimization;
- local measurement.

It answers:

> What does this repository need, and how do I safely prepare it for an agent?

## AgentFlow owns

[AgentFlow](https://github.com/szaher/agentflow) remains the Agentic SDLC meta-harness.

It owns:

- workflow stages;
- state transitions;
- attempt budgets;
- retries;
- evidence semantics;
- deterministic workflow gates;
- independent reviews;
- human approvals;
- delegation;
- parallel execution policy;
- durable workflow history;
- orchestration between agents.

It answers:

> What happens next, who does it, and what evidence makes the result acceptable?

---

# Design principles

Every release in this roadmap follows these principles.

1. **Machine-readable first.** Important CLI functionality must expose stable JSON contracts.
2. **Detect → recommend → explain → explicitly enable.** Detection must never silently grant risky access.
3. **Local-first.** Local definitions and installed content work without a central service.
4. **Portable, not vendor-bound.** Definitions should survive changes between Claude, Codex, Pi, OpenCode, and future coding agents.
5. **Reference before copy.** Existing configuration is referenced where possible; vendor/fork are explicit operations.
6. **Least privilege.** Agent definitions express required capabilities rather than receiving all installed tools.
7. **Reproducibility.** Artifacts and environments resolve to versions/digests and can be locked.
8. **No competing orchestrator.** Agent teams may be defined here, but workflow semantics belong to AgentFlow.
9. **Deterministic verification.** Agents reason; tests, compilers, linters, scanners, policy engines, and gates determine verification.
10. **Do not grow the default surface indiscriminately.** Prefer task-specific activation and measurable value.

---

# Roadmap overview

| Release | Theme | Primary outcome |
|---|---|---|
| **v0.14** | Agent Ready specification + assessment | Measure whether a repository is agent-ready |
| **v0.15** | Agent Ready remediation + CI | Safely make repositories more agent-ready |
| **v0.16** | Deep AgentFlow integration | Remove duplicated environment/bootstrap logic from AgentFlow |
| **v0.17** | Unified agent artifact model | Define portable Skill, Agent, AgentTeam, MCP, Plugin, Pack, WorkflowRef, and EnvironmentProfile objects |
| **v0.18** | Local catalog + import/export | Discover and manage existing Claude/Codex/Pi/OpenCode/agentic assets |
| **v0.19** | Packs + multi-agent definitions | Package reusable environments and agent teams |
| **v0.20** | Federated discovery + supply-chain trust | Search external ecosystems without building another marketplace |
| **v0.21** | Reproducible environment manifest + lockfile | Recreate an agent development environment exactly |
| **v0.22** | Task sessions + context budgeting | Give each task the smallest useful agent/tool/skill surface |
| **v0.23** | Team / organization policy | Organization-wide constraints and approved catalogs |
| **v0.24** | Credential broker | Provide credentials to tools without exposing secrets to model context |
| **v0.25** | Unified remote / ephemeral execution | Put host/container/devcontainer/Dagger/SSH behind one execution contract |
| **v0.26** | Evaluation + optional OpenTelemetry | Evaluate agents, skills, tools, packs, and configurations scientifically |
| **v0.27** | Distribution + developer experience | Homebrew/PyPI/CI/IDE-quality product experience |
| **v0.90** | 1.0 hardening | Freeze interfaces and aggressively test compatibility/security |
| **v1.0** | Stable agentic development platform | Stable contracts, extension model, and production-ready UX |

---

# v0.14 — Agent Ready specification + assessment

## Goal

Turn the principles defined by Agent Ready into machine-evaluable repository requirements.

Agent Ready remains authoritative. `agentic-dev-env` becomes the assessment engine.

## Agent Ready specification

Add a versioned machine-readable specification to `agent-ready`:

```text
spec/
└── v1/
    ├── maturity.yaml
    ├── context.yaml
    ├── conventions.yaml
    ├── constraints.yaml
    ├── feedback.yaml
    ├── security.yaml
    ├── performance.yaml
    └── schema.json
```

Example rule:

```yaml
id: feedback.tests.available
pillar: feedback
title: Runnable test suite
required_from: foundational

evidence:
  any:
    - command.test
    - project.pytest
    - project.go_test
    - project.cargo_test
    - project.package_test

severity: required
```

Example agent-instruction rule:

```yaml
id: context.agent_instructions
pillar: context
title: Agent instructions available
required_from: structured

evidence:
  any:
    - file.AGENTS.md
    - file.CLAUDE.md
    - file.copilot_instructions
```

## CLI

```bash
agentic ready assess .
agentic ready assess . --json

agentic ready explain .
agentic ready explain context.agent_instructions

agentic ready plan .
agentic ready plan . --target optimized
```

## Maturity levels

Use the existing Agent Ready levels:

```text
0 — Unaware
1 — Foundational
2 — Structured
3 — Optimized
4 — Autonomous
```

Maturity must be **requirement-based**, not an arbitrary score. Dimension percentages may be diagnostic, but the maturity level depends on satisfying the defined requirements.

## Acceptance criteria

- assessment is read-only;
- specification is versioned;
- evidence is explainable;
- every failed requirement identifies the supporting evidence;
- same repo + same spec produces the same assessment;
- mandatory checks do not require LLM judgment;
- unsupported rules are reported as unknown rather than guessed.

---

# v0.15 — Agent Ready remediation + CI

## Goal

Move from “what is missing?” to “what can safely be fixed?”

## CLI

```bash
agentic ready apply .
agentic ready apply . --target structured

agentic ready verify .
agentic ready diff .

agentic ready make . --target optimized
```

## Safe automatic remediation

Examples:

- generate/update managed AGENTS.md sections;
- document detected build/test/lint/typecheck commands;
- configure local agentic settings;
- configure local trust profile;
- configure secret scanning;
- configure focused verification;
- add CI readiness check;
- add generated local state to appropriate excludes.

## Human-required decisions

Do **not** invent:

- business rules;
- architecture boundaries;
- protected paths;
- dependency policies;
- canonical exemplar code;
- security requirements;
- performance SLOs.

Instead present detected candidates and require a human decision.

## CI

Support:

```bash
agentic ready verify --target structured
```

Readiness should become a maintained repository property that can regress and be checked in CI.

## Acceptance criteria

- safe fixes are distinct from policy decisions;
- generated content uses managed blocks;
- existing files are not blindly overwritten;
- readiness regression is CI-detectable;
- readiness spec/version can be pinned.

---

# v0.16 — Deep AgentFlow integration

## Goal

Make AgentFlow consume `agentic-dev-env` contracts instead of rediscovering environment/repository state.

## AgentFlow consumes

```bash
agentic repo inspect . --json
agentic ready assess . --json
agentic doctor --json
agentic capabilities status --json
agentic verify plan --json
agentic worktree create ...
agentic metrics record ...
```

## Remove duplicated logic

Move generic responsibility out of AgentFlow where `agentic-dev-env` already owns it:

- language/framework detection;
- package-manager detection;
- generic skill installation;
- build/test/lint command discovery;
- worktree mechanics;
- environment capability detection.

## Pattern requirements

AgentFlow patterns should be able to declare environment/readiness requirements, for example:

```json
{
  "requires": {
    "readiness": "structured",
    "capabilities": ["secret-scan"]
  },
  "verification": {
    "minimum": ["lint", "test"]
  }
}
```

## Acceptance criteria

- one repository/environment source of truth;
- JSON/process contracts only, not imports of agentic-dev-env internals;
- AgentFlow retains authority over mandatory gates and state transitions;
- agentic-dev-env never owns AgentFlow workflow semantics.

---

# v0.17 — Unified agent artifact model

## Goal

Create portable representations for the assets developers currently configure separately.

## First-class artifact kinds

```text
Skill
Agent
AgentTeam
MCPServer
Plugin
Capability
Pack
WorkflowRef
EnvironmentProfile
```

## URI model

```text
skill://python-engineering
agent://security-reviewer
team://feature-team
mcp://github
pack://kubernetes-development
workflow://standard
profile://backend-development
```

## Portable Agent definition

```yaml
schema_version: "1"
kind: Agent

metadata:
  name: backend-reviewer
  description: Reviews backend changes

spec:
  role: reviewer

  skills:
    - skill://code-review
    - skill://api-design

  capabilities:
    - secret-scan

  tools:
    preferred:
      - serena
      - codegraph

  trust:
    maximum: safe

  execution:
    write: false

  runtime:
    compatible:
      - claude
      - codex
      - pi
      - opencode

  model:
    requirements:
      reasoning: high
```

Prefer model capabilities to hard-coded model names.

## Acceptance criteria

- schemas are versioned;
- definitions are portable;
- artifacts cannot silently escalate trust;
- built-in identifiers cannot be overridden by remote content;
- source/provenance metadata is included.

---

# v0.18 — Local catalog + import/export

## Goal

Understand and manage the assets developers already have.

## Discovery

```bash
agentic import scan
```

Potential output:

```text
Claude
  7 agents
  12 skills
  5 MCP servers

Codex
  9 skills
  4 plugins
  3 MCP servers

Pi
  8 packages
  14 skills

Local
  3 AGENTS.md files
```

## Management semantics

Three explicit modes:

```text
reference
  original remains authoritative

vendor
  copy becomes agentic-managed

fork
  copy becomes agentic-managed
  provenance is retained
```

## CLI

```bash
agentic catalog list
agentic catalog search debugging
agentic catalog inspect agent://reviewer

agentic agents add-ref ~/.claude/agents/reviewer.md
agentic agents vendor reviewer
agentic agents fork reviewer

agentic import claude
agentic import codex
agentic import pi
agentic import opencode

agentic export --target claude
agentic export --target codex
agentic export --target pi
agentic export --target opencode
```

## Scopes

```text
repo
organization
user
builtin
remote
```

Resolution precedence:

```text
repo
  ↓
organization
  ↓
user
  ↓
builtin
  ↓
remote discovery
```

Remote content must never silently override local definitions.

---

# v0.19 — Packs + AgentTeam definitions

## Goal

Package coherent development environments instead of exposing many individual switches.

## AgentPack

```yaml
kind: AgentPack

metadata:
  name: kubernetes-operator-development

spec:
  agents:
    - agent://operator-developer
    - agent://operator-reviewer

  skills:
    - skill://go-engineering
    - skill://kubernetes-development
    - skill://operator-development
    - skill://debugging

  capabilities:
    - cluster-read
    - secret-scan

  mcp:
    - serena
    - codegraph

  workflow:
    engine: agentflow
    pattern: standard

  trust:
    maximum: development
```

## AgentTeam

```yaml
kind: AgentTeam

metadata:
  name: feature-team

spec:
  agents:
    architect:
      ref: agent://software-architect
    implementer:
      ref: agent://backend-engineer
    reviewer:
      ref: agent://code-reviewer
    tester:
      ref: agent://test-engineer

  orchestration:
    engine: agentflow
    pattern: spec-driven
```

## Boundary

`agentic-dev-env` owns team membership, environment, requirements, skills, tools, and capabilities.

AgentFlow owns ordering, parallelism, delegation, retries, gates, approvals, handoffs, and termination.

## CLI

```bash
agentic packs search kubernetes
agentic packs install kubernetes-operator-development
agentic teams inspect feature-team
```

Repository initialization may recommend a pack, but must never install it silently.

---

# v0.20 — Federated discovery + supply-chain trust

## Goal

Search existing ecosystems rather than creating another isolated marketplace.

## Sources

Potential adapters:

- local catalog;
- Git repositories;
- organization catalogs;
- agentic providers;
- official MCP Registry;
- OpenAI plugin ecosystem;
- Pi packages;
- future agent ecosystems.

## Unified search

```bash
agentic search "postgres read-only"
```

## Trust metadata

Every external artifact should expose:

- source;
- publisher;
- version;
- commit;
- digest;
- signature;
- artifact type;
- executable-code presence;
- network requirements;
- credential requirements;
- permissions;
- dependencies;
- last verification time.

## Installation preview

Before installation, show exactly what will be installed and which permissions/network/credential requirements it introduces.

No remote artifact receives silent execution rights.

---

# v0.21 — Reproducible environment manifest + lockfile

## Goal

Allow an agentic environment to be recreated exactly.

## Intent

`.agentic/config.toml`:

```toml
[agent_ready]
spec = "v1"
target = "optimized"

[agents]
enabled = ["codex"]

[skills]
auto = true

[capabilities]
secret-scan = "required"
browser-automation = "optional"

[trust]
profile = "development"

[execution]
backend = "devcontainer"
```

## Resolution

`.agentic/lock.json` records:

- tool versions;
- skill versions;
- agent definitions;
- MCP versions;
- provider versions;
- commit SHAs;
- content digests;
- Agent Ready spec version;
- execution backend.

## CLI

```bash
agentic env lock
agentic env diff
agentic env apply
agentic env verify
agentic env export
```

## Content-addressed store

Use an immutable store under:

```text
~/.local/share/agentic-dev-env/store/sha256/
```

Benefits include integrity, deduplication, rollback, offline reuse, and reproducibility.

---

# v0.22 — Task sessions + context budgeting

## Goal

Prepare the smallest effective environment for one task instead of exposing every installed tool.

## CLI

```bash
agentic session prepare \
  --agent codex \
  --task "debug reconciliation race"
```

## Session resolution

Example:

```text
Repository:
  Go Kubernetes operator

Selected skills:
  go-engineering
  operator-development
  debugging
  test-development

Tools:
  Serena
  CodeGraph

Capabilities:
  cluster-read

Not activated:
  browser-automation
  Browser Use
  database-write
  cloud-write
```

## Context budget

Measure and optionally constrain:

- skills exposed;
- MCP servers exposed;
- tool definitions exposed;
- instruction size;
- repository context size.

Example policy:

```toml
[session.context]
max_skills = 6
max_mcp_servers = 4
prefer_task_specific = true
```

Bring OpenCode integration to parity with Claude, Codex, and Pi here.

---

# v0.23 — Team / organization policy

## Goal

Allow organizations to control what developers and agents may configure.

## Policy

`.agentic/policy.toml`:

```toml
[providers]
allow = ["builtin/*", "company/*"]

[security]
required = ["secret-scan", "dependency-vulnerability"]

[browser]
authenticated = false

[cloud]
write = false

[cluster]
write = false

[execution]
allowed = ["container", "devcontainer"]

[readiness]
minimum = "structured"
```

## CLI

```bash
agentic policy check
agentic policy explain browser.authenticated
agentic policy explain provider://random-source
```

## Boundary

Agentic policy controls environment/tool/provider/capability constraints and maximum trust.

AgentFlow policy controls workflow/evidence/review/approval/transition constraints.

---

# v0.24 — Credential broker

## Goal

Allow tools to use credentials without exposing secret values to model context or repository files.

## Initial sources

- environment references;
- macOS Keychain;
- 1Password CLI;
- AWS profiles;
- Azure CLI profiles;
- GCP credentials;
- SSH agent;
- provider adapters.

## Reference model

```text
credential://github-work
credential://aws-development
credential://k8s-production-read
```

## Flow

```text
Agent
  |
  | requests capability
  v
agentic credential broker
  |
  ├── resolve reference
  ├── check trust
  ├── check policy
  └── inject into tool process
```

Secret values must never be written into prompts, skills, AGENTS.md, CLAUDE.md, metrics, AgentFlow state, repo config, or logs.

---

# v0.25 — Unified remote / ephemeral execution

## Goal

Unify all execution environments under one backend contract.

## UX

```bash
agentic exec --backend host
agentic exec --backend container
agentic exec --backend devcontainer
agentic exec --backend dagger
agentic exec --backend ssh:gpu-lab
```

Potential provider-backed execution targets:

- Kubernetes Job;
- OpenShift Pod;
- Codespaces;
- cloud development machines;
- CI runners.

## Result contract

```json
{
  "backend": "ssh",
  "success": true,
  "duration_ms": 4321,
  "exit_code": 0,
  "evidence_digest": "sha256:..."
}
```

AgentFlow should consume the same result contract regardless of execution location.

---

# v0.26 — Evaluation + optional OpenTelemetry

## Goal

Move from intuition to evidence.

## Benchmark model

```bash
agentic eval run benchmark.yaml
```

Example:

```yaml
tasks:
  - python-bugfix
  - go-controller-refactor
  - typescript-ui-change

configurations:
  - baseline
  - serena
  - serena-codegraph
  - serena-codegraph-skills
```

## Metrics

Compare:

- completion success;
- first-attempt success;
- time to first passing test;
- tool calls;
- failed commands;
- retry count;
- verification duration;
- change size;
- reverted edits;
- context sources;
- skills used;
- capabilities used;
- human intervention;
- token usage when available.

This should let the project answer whether specific tools, skills, packs, or AgentFlow patterns materially improve outcomes.

Local metrics remain the default. Any OpenTelemetry export is optional and explicit. Prompt/tool bodies must not be exported by default.

---

# v0.27 — Distribution + developer experience

## Goal

Make installation and lifecycle feel like a finished developer product.

## Target installation

```bash
brew install agentic-dev-env
```

and:

```bash
uv tool install agentic-dev-env
```

Then:

```bash
agentic setup
```

instead of requiring knowledge of underlying scripts.

## Distribution

Deliver:

- PyPI;
- Homebrew;
- signed GitHub releases;
- release notes;
- SBOM;
- provenance;
- compatibility matrix;
- upgrade;
- rollback;
- uninstall.

Supported platforms for 1.0:

- macOS ARM64;
- macOS x86_64;
- Linux x86_64;
- Linux ARM64;
- WSL.

Native Windows can remain post-1.0 unless demand justifies it.

## GitHub Action

Support workflows such as:

```yaml
- uses: szaher/agentic-dev-env@v1
  with:
    command: ready verify --target structured
```

and:

```yaml
- uses: szaher/agentic-dev-env@v1
  with:
    command: verify
```

## IDE

A lightweight editor integration may expose readiness, active session, skills, capabilities, trust, verification, and AgentFlow run status.

The CLI/API remains canonical.

---

# v0.90 — 1.0 hardening

Freeze features.

## Compatibility

Freeze and test:

- CLI command names;
- JSON schemas;
- artifact schemas;
- provider schema;
- Agent Ready spec interface;
- lockfile schema;
- AgentFlow contracts.

## Fixture matrix

```text
fixtures/
├── python-fastapi/
├── django/
├── go-service/
├── go-operator/
├── rust-cli/
├── node-react/
├── nextjs/
├── java-maven/
├── polyglot/
├── monorepo/
├── terraform/
├── kubernetes/
└── legacy-repo/
```

## Hardening targets

- large repositories;
- monorepos;
- provider isolation;
- upgrades/migrations;
- corrupt lockfiles;
- network loss;
- partial installation;
- credential failure;
- worktree recovery;
- remote execution failure;
- concurrent sessions;
- schema migration;
- malicious providers;
- malicious MCP definitions;
- symlink/path escape;
- instruction/prompt injection.

## Security review

Produce a formal threat model covering provider code, MCP servers, credentials, browser sessions, cloud/cluster access, remote execution, catalog supply chain, artifact import, and organization policy.

---

# v1.0 definition of done

Do not call the project 1.0 because the feature list is large.

Ship 1.0 when the following workflow is reliable:

```bash
git clone <supported-project>
cd project

agentic setup
agentic ready assess .

agentic session prepare \
  --agent codex \
  --task "implement issue #123"
```

The system should reliably answer:

- Is this repo agent-ready?
- What is missing?
- What can safely be fixed?
- Which agent should be configured?
- Which skills are useful?
- Which MCPs/tools are useful?
- Which capabilities are needed?
- Which permissions are required?
- What trust level applies?
- What environment should execute the work?
- What verification is required?
- How is the environment reproduced?
- How is the session isolated?
- How will the outcome be measured?

Then AgentFlow should be able to run the governed development process on the prepared environment.

A credible 1.0 means:

```text
stable schemas                    ✓
stable CLI                        ✓
portable artifacts                ✓
Agent Ready assessment            ✓
safe remediation                  ✓
AgentFlow integration             ✓
reproducible environments         ✓
portable agent definitions        ✓
packs / teams                     ✓
federated discovery               ✓
supply-chain integrity            ✓
organization policy               ✓
credential isolation              ✓
sandbox/remote execution          ✓
local measurement                 ✓
evaluation                        ✓
cross-platform install            ✓
upgrade/migration                 ✓
security review                   ✓
```

---

# Cross-repository architecture

```text
┌───────────────────────────────────────┐
│              agent-ready              │
│                                       │
│ education                             │
│ maturity model                        │
│ machine-readable readiness spec       │
└──────────────────┬────────────────────┘
                   │
                   │ specification
                   v
┌───────────────────────────────────────┐
│           agentic-dev-env             │
│                                       │
│ readiness assessment                  │
│ remediation                           │
│ artifact catalog                      │
│ agent/team/skill definitions          │
│ MCP/capabilities                      │
│ environment resolution                │
│ trust / credentials                   │
│ worktrees / execution                 │
│ verification discovery                │
│ measurement                           │
└──────────────────┬────────────────────┘
                   │
                   │ prepared session +
                   │ machine-readable contracts
                   v
┌───────────────────────────────────────┐
│               AgentFlow               │
│                                       │
│ patterns                              │
│ workflow stages                       │
│ attempts / retries                    │
│ evidence                              │
│ independent review                    │
│ human approvals                       │
│ orchestration                         │
└──────────────────┬────────────────────┘
                   │
                   v
┌───────────────────────────────────────┐
│     Claude / Codex / Pi / OpenCode    │
│                                       │
│ reasoning                             │
│ coding                                │
│ debugging                             │
│ native tools/subagents                │
└───────────────────────────────────────┘
```

---

# Critical dependency order

Implementation should follow the dependency graph, not just version numbers:

```text
Agent Ready specification
        ↓
Readiness assessment
        ↓
Readiness remediation
        ↓
AgentFlow integration

Artifact schema
        ↓
Local catalog
        ↓
Import/export
        ↓
Packs / teams
        ↓
Federated discovery
        ↓
Supply-chain policy

Catalog + providers
        ↓
Environment manifest
        ↓
Lockfile
        ↓
Task/session resolution
        ↓
Context budgeting

Trust
  +
Org policy
  +
Artifact metadata
        ↓
Credential broker
        ↓
Remote execution

Sessions
  +
AgentFlow events
  +
Metrics
        ↓
Evaluation framework
```

---

# Explicit non-goals

To keep the project coherent, `agentic-dev-env` should **not** become:

- another multi-agent orchestrator — that is AgentFlow;
- another public MCP marketplace — federate existing registries/catalogs;
- another secret vault — integrate existing credential stores;
- another CI engine — expose commands/actions for existing CI systems;
- another container platform — use containers, Dev Containers, Dagger, Kubernetes, etc.;
- another model gateway — agent runtimes/model providers own model execution;
- an AI-generated architecture-policy engine — unknown business/architecture decisions require humans;
- a giant always-enabled MCP bundle — task/session preparation should expose only what is needed.

---

# Success metrics

Roadmap success should be measured by outcomes, not feature count.

## Repository readiness

- time from clone to useful agent session;
- readiness-level improvements;
- readiness regressions detected;
- automated vs human-required remediation.

## Context efficiency

- tools exposed per task;
- skills exposed per task;
- MCP servers exposed per task;
- files read per task;
- tool calls per task.

## Development effectiveness

- first-attempt success;
- time to first passing test;
- retries;
- failed commands;
- reverted edits;
- verification duration.

## Reproducibility

- lockfile reproducibility;
- environment drift incidents;
- provider integrity failures;
- successful environment restores.

## AgentFlow

- workflow completion;
- stage retries;
- review rejection rate;
- human intervention;
- approval frequency;
- evidence failures.

## Security

- trust-policy violations blocked;
- credential exposure incidents;
- unverified-provider attempts;
- excessive-permission requests;
- MCP supply-chain failures.

---

# Immediate execution order

The implementation sequence is:

```text
1. v0.14
   Agent Ready machine-readable specification
   + readiness assessment engine

2. v0.15
   safe remediation
   + readiness CI/regression checks

3. v0.16
   deep AgentFlow integration
   + remove duplicated environment discovery

4. v0.17
   unified artifact schemas

5. v0.18
   local catalog
   + import/reference/vendor/fork/export

6. v0.19
   packs + AgentTeam definitions

7. v0.20
   federated discovery
   + supply-chain metadata

8. v0.21
   environment manifest
   + lockfile
   + content-addressed store

9. v0.22
   task/session preparation
   + context budgeting
   + OpenCode parity

10. v0.23
    organization policy

11. v0.24
    credential broker

12. v0.25
    unified remote execution

13. v0.26
    evaluation / benchmarking / optional OpenTelemetry

14. v0.27
    distribution / GitHub Action / DX

15. v0.90
    feature freeze + hardening

16. v1.0
```

---

# Product identity at 1.0

At 1.0, `agentic-dev-env` should be describable as:

> **A vendor-neutral developer platform for assessing, preparing, reproducing, and governing agentic software-development environments. It makes repositories agent-ready, manages portable agent/skill/tool configurations, prepares minimal task-specific sessions, and provides the environment contract consumed by AgentFlow and coding agents such as Claude Code, Codex, Pi, and OpenCode.**

The three-project story is:

> **Agent Ready teaches and defines the standard.**

> **agentic-dev-env implements and operationalizes the standard.**

> **AgentFlow runs governed software development on top of that prepared environment.**
