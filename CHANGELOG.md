# Changelog

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
