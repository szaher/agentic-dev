# Changelog

## Unreleased

v0.15 (Agent Ready remediation + CI), slice 1: remediation contract.

- Added the remediation contract (`docs/REMEDIATION.md`) and `schemas/readiness-remediation-v1.schema.json`: `safe-automatic` / `human-decision` / `unsupported` classes, managed-block markers, and normative apply, conflict, idempotency, and rollback semantics.
- Added `agentic_dev.readiness.remediation.propose`, which builds a read-only remediation preview. The spec classification is an upper bound and is never upgraded. Actions record provenance, and policy rules become decisions with detected candidates instead of invented content.

## 0.14.0 - 2026-10-02

Stable Agent Ready Specification v1 assessment release.

- Promoted the completed v0.14 milestone from prerelease to stable.
- Includes `agentic ready assess`, `agentic ready explain`, and `agentic ready plan`, with deterministic offline assessment and requirement-based maturity.
- Includes the vendored Agent Ready Specification v1 bundle pinned by source commit and SHA-256.
- Includes wheel/sdist installation smoke tests and PyPI Trusted Publishing through `.github/workflows/publish.yml`.
- Preserves the v0.14 guarantees: read-only assessment, repository-relative evidence, redaction of suspected secrets, and `unknown` distinct from `fail`.

## 0.14.0a2 - 2026-10-02

Agent Ready Specification v1 assessment (Roadmap v2 milestone v0.14, in progress).

- Added `agentic ready assess`, `agentic ready explain` (repository or rule), and `agentic ready plan`, each with `--json`, `--target`, and `--spec`.
- Added the `agentic_dev.readiness` engine: three-valued evaluation (`pass`/`fail`/`unknown`/`not-applicable`), requirement-based cumulative maturity in which `unknown` blocks like `fail`, and concrete repository-relative evidence with file and line.
- Vendored Agent Ready Spec `1.0.0` (owned by szaher/agent-ready), pinned by sha256 and source commit and verified on load. Assessment needs no network and no YAML parser.
- Added `scripts/sync-agent-ready-spec.py` to update and verify the pinned spec.
- Added JSON contracts: `readiness-assessment-v1`, `readiness-explanation-v1`, `readiness-plan-v1`.
- Assessment is read-only, deterministic, and private: no command execution, no writes, no timestamps, no absolute paths, and redacted secret-bearing matches.
- Added realistic generated fixtures (empty, foundational-python, missing-tests, no-agent-instructions, ambiguous-policy, structured-go, optimized-node, autonomous-node) and a read-only regression test.
- Package CI now proves that installed wheels and sdists assess a repository with the packaged spec.
- Added `docs/READINESS.md` and readiness sections in `docs/API.md` and `README.md`.

## 0.14.0a1 - 2026-10-02

Agentic Dev product/package rename and packaging hardening.

- Renamed the product/repository identity from `agentic-dev-env` to **Agentic Dev** / `agentic-dev`.
- Renamed the Python distribution to `agentic-dev` and the import package to `agentic_dev`.
- Kept the public command surface as `agentic`.
- Renamed configuration/data namespaces to `~/.config/agentic-dev`, `~/.local/share/agentic-dev`, and `AGENTIC_DEV_*`.
- Added non-destructive one-time migration for legacy user configuration and fallback support for legacy config/bin environment variables.
- Preserved existing linked Git worktrees in place instead of moving them unsafely.
- Bundled setup/repository bootstrap scripts and the global policy template into wheel/sdist installations so `uv tool install agentic-dev` provides a complete CLI.
- Added transitional helper aliases for source installs and legacy managed-instruction marker cleanup.
- Added wheel/sdist build-and-install smoke validation and PyPI Trusted Publishing workflow.
- Added migration/release documentation and a scoped identity-regression check.

## 0.13.0 - 2026-10-02

Local measurement and evaluation.

- Added local metrics/event store, disabled by default.
- Added `agentic metrics status/enable/disable/summary/export/clear/record`.
- Added schema-v1 metric events and automatic sensitive-key redaction.
- Added hashed repository identities instead of storing absolute repository paths in events.
- Added execution duration/failure/tool-call measurement without storing raw command strings.
- Added verification check and total-duration measurement plus time to first passing focused test.
- Added change-size measurement and CodeGraph context usefulness signals.
- Added worktree session start/end events.
- Added skill/capability recommendation uptake measurement by matching recommended item names to later activation/enablement.
- Added generic events for AgentFlow stages, retries, external tool calls, context usefulness, and reverted edits.
- Added per-session/task tool-call summaries.
- Added explicit local file export only; no network telemetry/export.
- Added privacy and lifecycle regression tests.
- Completed the original agentic-dev-env roadmap.

## 0.12.0 - 2026-10-02

Provider ecosystem, lifecycle, Linux/WSL, and remote development profiles.

- Added versioned external provider manifest protocol and JSON Schema.
- Added external Agent Skill contributions without allowing built-in skill overrides.
- Added trust-gated command-backed external capabilities.
- Added local and Git provider installation with recorded content/manifest digests.
- Added optional expected SHA-256 pinning and Git signed-commit verification.
- Added provider verify/doctor/update/remove commands and explicit migration hooks.
- Added `agentic update --yes` for installed external providers.
- Added compatibility checks for agentic-dev-env version, host platform, executables, and coding-agent CLIs.
- Added dedicated Linux/WSL workstation bootstrap while preserving the macOS path.
- Added SSH development profiles with non-interactive connectivity testing and no secret storage.
- Added provider/remote state to machine-readable inspection and doctor documents.
- Added provider, remote, manifest, and Linux shell regression coverage.

## 0.11.0 - 2026-10-02

Infrastructure capability packs.

- Added database-read/write/local capability packs.
- Added SQLite/PostgreSQL/MySQL schema inspection and guarded SQL execution.
- Added detected migration/schema validation for Alembic, Django, and Prisma.
- Added ephemeral local PostgreSQL/MySQL containers with generated mode-0600 credential state.
- Added cluster-read/write packs for kubectl/oc with read-verb classification.
- Added cloud-read identity operations and explicit cloud-write command path.
- Added provider-neutral OpenTelemetry/observability status with secret-like environment values redacted.
- No built-in trust profile grants cluster.write or cloud.write.
- Added infrastructure status to machine-readable inspection/doctor contracts.
- Added infrastructure status JSON schema and safety regression tests.

## 0.10.0 - 2026-10-02

Execution backends and sandboxing.

- Added host, Docker/Podman container, Dev Container, and Dagger execution backends.
- Added `agentic execution status/configure/run`.
- Generic containers default to no network and require explicit images.
- Dev Container execution uses the repo's own configuration.
- Dagger execution uses Workspace `exec --no-apply`.
- Added trust enforcement for container/network execution.
- Routed normal verification commands through the execution backend abstraction.
- Added normalized execution-result JSON schema and backend regression tests.
- Inspection/doctor documents now expose execution backend state.

## 0.9.0 - 2026-10-02

Change-aware verification planner.

- Added `agentic verify`, `agentic verify plan`, and `agentic verify run`.
- Plans from Git changed/untracked files plus the v1 repository inspection contract.
- Selects repository-native lint, typecheck, test, and build commands based on changed source/configuration.
- Skips code checks for documentation-only changes.
- Integrates CodeGraph affected tests and optional symbol impact when indexed.
- Records Serena availability without inventing unsupported batch-reference CLI behavior.
- Adds enabled security capabilities as relevant verification checks.
- Executes deterministically with fail-fast or continue-on-failure modes.
- Added verification-plan JSON schema and regression tests.

## 0.8.0 - 2026-10-02

Worktree and agent session manager.

- Added `agentic worktree create/list/status/clean`.
- Added predictable per-repository worktree roots with an environment override.
- Added per-worktree agent/task session metadata.
- Added dirty-worktree protection and explicit force removal.
- Added optional branch deletion and collision detection.
- Prevented primary-worktree removal.
- Kept session metadata local through Git exclude.
- Added machine-readable JSON output and real-Git regression tests.

## 0.7.0 - 2026-10-02

Security capability pack and trust profiles (roadmap v0.6 + v0.7).

- Added secret, dependency vulnerability, SAST, IaC misconfiguration, container-image, and SBOM capabilities.
- Added Trivy and Semgrep Community Edition provider adapters.
- Added normalized machine-readable security scan result envelopes.
- Added built-in safe, development, and production-read trust profiles.
- Added custom user trust profiles and repo-scoped profile selection.
- Capability enable/run now enforces declared permissions before provider invocation.
- Authenticated/persistent browser modes and network/container-sensitive scans require stronger permissions.
- Repo-scoped trust state remains local via .git/info/exclude.
- Inspection/doctor documents now expose trust state.
- Added security/trust regression tests and documentation.

## 0.5.0 - 2026-10-02

Stable machine-readable inspection contract.

- Added `agentic repo inspect [PATH] --json`.
- Added `agentic doctor --json`.
- Added schema version 1 for repository and doctor documents.
- Added repository facts/evidence, package managers, polyglot command discovery, skills, capabilities, and native integration state to inspection output.
- Replaced the single-command assumption at the API layer with arrays for polyglot install/test/lint/format/typecheck/build workflows.
- Added JSON Schema documents and schema validation in CI.
- Added `docs/API.md` and a versioned product roadmap.
- Kept repository inspection strictly read-only.

## 0.4.0 - 2026-10-01

Optional capability packs.

- Added `agentic capabilities list/suggest/enable/disable/status`.
- Added browser as the first optional capability pack.
- Added Playwright MCP as the default browser-automation provider.
- Added Chrome DevTools MCP for browser-debug and frontend performance workflows.
- Added Browser Use for advanced autonomous browser workflows.
- Added isolated/persistent/existing-browser Playwright modes and isolated/headless Chrome DevTools modes.
- Browser recommendations are repo/task-aware but never auto-enable access.
- Added web-app and Playwright repository detection.
- Added capability state reporting to `agentic doctor`.
- Added browser security guidance and regression tests.

## 0.3.0 - 2026-10-01

Native agent integrations.

- Added a Claude Code marketplace/plugin with a lightweight repo orchestration skill.
- Added a Codex repo marketplace plus portable and compatibility plugin manifests.
- Added a Pi package with an orchestration skill and interactive commands.
- Added `agentic integrations install/status`.
- Added Pi as a project skill target under `.pi/skills`.
- Added `all` skill targeting across Claude, Codex, and Pi while keeping `both` as Claude+Codex compatibility behavior.
- Integrated native setup into `--configure-agents`.
- Added manifest/package regression tests and integration documentation.

## 0.2.0 - 2026-10-01

Context-aware Agent Skills.

- Added the unified `agentic` CLI.
- Added deterministic repository/task context detection.
- Added an interactive skill recommender that explains why each skill matched.
- Added local-only activation by default, with explicit shared/team mode.
- Added native project skill installation for Claude Code (`.claude/skills`) and Codex (`.codex/skills`).
- Added 16 focused built-in engineering skills.
- Integrated skill suggestions into repository initialization with `--task`, `--skills-yes`, `--skills-shared`, `--skills-target`, and `--no-skills`.
- Added unit tests for detection, recommendation, activation, local excludes, and conflict protection.

## 0.1.0 - 2026-10-01

Initial repository release.

- macOS workstation bootstrap with a universal CLI foundation.
- Language-aware repository initialization for polyglot projects.
- Serena, CodeGraph, Context7, Repomix, ast-grep, and deterministic CLI routing.
- Runtime/package-manager detection for Python, Go, Rust, Node, JVM, C/C++, Ruby, PHP, Swift, Terraform, Shell, Lua, Zig, and common infrastructure tooling.
- Conservative project-dependency installation: opt-in only.
- Global Claude Code and Codex tool policy support.
- Read-only repo readiness checks and smoke-test CI.
