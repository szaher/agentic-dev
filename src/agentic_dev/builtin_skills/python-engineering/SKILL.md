---
name: python-engineering
description: Apply repository-native Python engineering practices for implementation, refactoring, testing, typing, and packaging.
---

# Python Engineering

Use this skill when changing Python code.

## Workflow

1. Read `pyproject.toml`, existing package layout, and nearby tests before editing.
2. Reuse the repository's package/environment manager. Prefer `uv` only when the repo already uses it or no stronger convention exists.
3. Preserve public API behavior unless the task explicitly changes it.
4. Match the repo's typing level; do not introduce broad `Any` or suppressions to make checks pass.
5. Prefer small modules/functions with explicit boundaries over hidden global state.

## Verification

Run the repo's own format, lint, type-check, and focused test commands. If none are documented, infer cautiously from `pyproject.toml`.