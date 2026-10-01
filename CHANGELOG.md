# Changelog

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
