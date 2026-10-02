"""Readiness fixture repositories.

Each scenario is an explicit, readable set of files that is materialized as a
fresh Git repository on demand. The fixtures are generated instead of checked
in, so their files (Go sources, AGENTS.md, workflows, ...) never leak into
Agentic Dev's own repository inspection or self-assessment.

Standard library only, so package CI can use it without the test extras:

    python3 tests/readiness_fixtures.py list
    python3 tests/readiness_fixtures.py materialize optimized-node /tmp/fixture
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# --------------------------------------------------------------- python ---

PY_README = """# Demo service

A small HTTP service.

## Development

```bash
uv sync
uv run pytest
```
"""

PY_PROJECT = """[project]
name = "demo"
version = "0.1.0"
dependencies = []

[dependency-groups]
dev = ["pytest", "ruff"]

[tool.ruff]
line-length = 100
"""

PY_SOURCES = {
    "src/demo/__init__.py": "",
    "src/demo/core.py": "def answer() -> int:\n    return 42\n",
    "tests/test_core.py": "from demo.core import answer\n\n\ndef test_answer():\n    assert answer() == 42\n",
}

FOUNDATIONAL_PYTHON = {"README.md": PY_README, "pyproject.toml": PY_PROJECT, **PY_SOURCES}

# Lints and documents setup, but declares no test runner and has no tests.
MISSING_TESTS = {
    "README.md": PY_README,
    "pyproject.toml": '[project]\nname = "demo"\nversion = "0.1.0"\n\n[tool.ruff]\nline-length = 100\n',
    "src/demo/__init__.py": "",
    "src/demo/core.py": "def answer() -> int:\n    return 42\n",
}

# Everything Structured needs except agent instructions.
NO_AGENT_INSTRUCTIONS = {
    **FOUNDATIONAL_PYTHON,
    "pyproject.toml": PY_PROJECT + "\n[tool.mypy]\nfiles = [\"src\"]\n",
    ".gitignore": ".venv/\n.env\n",
    ".pre-commit-config.yaml": (
        "repos:\n  - repo: https://github.com/astral-sh/ruff-pre-commit\n    rev: v0.6.0\n"
        "    hooks:\n      - id: ruff\n"
    ),
    "docs/architecture.md": "# Architecture\n\n`demo.core` holds pure domain logic.\n",
    "CONTRIBUTING.md": "# Contributing\n\n## Code style\n\nRuff defaults; type hints everywhere.\n",
}

# Structured, with workflows, but architecture boundaries are only team policy.
AMBIGUOUS_POLICY = {
    **NO_AGENT_INSTRUCTIONS,
    "AGENTS.md": """# Agent guide

## Commands

- Test: `uv run pytest`
- Lint: `uv run ruff check .`
- Typecheck: `uv run mypy`

## Architecture

`src/demo/core.py` is pure logic; HTTP adapters must not be imported from it.

## Conventions

- Type-annotate every public function.

## Workflow: adding an endpoint

1. Add the handler.
2. Add a test in `tests/`.
3. Run the commands above.

## Do NOT

- Do not import adapters from `demo.core`.
""",
}

# ------------------------------------------------------------------- go ---

STRUCTURED_GO = {
    "go.mod": "module example.com/svc\n\ngo 1.22\n",
    "go.sum": "",
    "main.go": 'package main\n\nimport "example.com/svc/internal/handlers"\n\nfunc main() { handlers.Serve() }\n',
    "internal/handlers/health.go": "package handlers\n\nfunc Serve() {}\n",
    "internal/handlers/health_test.go": 'package handlers\n\nimport "testing"\n\nfunc TestServe(t *testing.T) { Serve() }\n',
    "README.md": "# svc\n\n## Getting started\n\n```bash\ngo build ./...\ngo test ./...\n```\n",
    ".gitignore": ".env\n",
    ".golangci.yml": "linters:\n  enable:\n    - govet\n",
    "AGENTS.md": """# Agent guide

## Commands

- Build: `go build ./...`
- Test: `go test ./...`

## Architecture

`main.go` wires the server; handlers live in `internal/handlers`.

## Conventions

- Return errors; never panic in handlers.

## Do NOT

- Do not edit generated files.
""",
    ".github/workflows/ci.yml": """name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: go test ./...
      - run: golangci-lint run
""",
}

# ----------------------------------------------------------------- node ---

NODE_AGENTS = """# Agent guide

## Commands

- Install: `pnpm install`
- Build: `pnpm build`
- Test: `pnpm test`
- Lint and types: `pnpm lint && pnpm typecheck`

## Architecture

`src/index.ts` starts the server. Routes live in `src/api/routes.ts`.
Dependency boundaries are enforced by `.dependency-cruiser.cjs`.

## Conventions

- Named exports only; no default exports.

## Examples

Follow `src/api/routes.ts` when adding a route.

## Workflow: adding an API route

1. Add the handler to `src/api/routes.ts`.
2. Add a colocated `*.test.ts`.
3. Run `pnpm test`.

## Do NOT

- Never import from `src/api` inside `src/domain`.
- Never read `.env` files or print secrets.
"""

OPTIMIZED_NODE = {
    "package.json": """{
  "name": "web",
  "private": true,
  "scripts": {
    "build": "tsc -p .",
    "test": "vitest run",
    "lint": "eslint .",
    "typecheck": "tsc --noEmit",
    "deps": "depcruise src"
  },
  "devDependencies": {
    "dependency-cruiser": "^16.0.0",
    "eslint": "^9.0.0",
    "typescript": "^5.6.0",
    "vitest": "^2.1.0"
  }
}
""",
    "pnpm-lock.yaml": "lockfileVersion: '9.0'\n",
    "tsconfig.json": '{\n  "compilerOptions": {\n    "strict": true,\n    "outDir": "dist"\n  }\n}\n',
    "eslint.config.js": "export default [];\n",
    ".dependency-cruiser.cjs": (
        "module.exports = { forbidden: [{ name: 'domain-not-api', severity: 'error',\n"
        "  from: { path: '^src/domain' }, to: { path: '^src/api' } }] };\n"
    ),
    ".gitignore": "node_modules/\ndist/\n.env\n",
    "README.md": "# web\n\n## Setup\n\n```bash\npnpm install\npnpm test\n```\n",
    "src/index.ts": "import { routes } from './api/routes';\n\nexport const app = routes;\n",
    "src/api/routes.ts": "export const routes = ['/health'];\n",
    "src/api/routes.test.ts": "import { routes } from './routes';\n\ntest('health', () => expect(routes).toContain('/health'));\n",
    "src/domain/order.ts": "export const total = (xs: number[]) => xs.reduce((a, b) => a + b, 0);\n",
    "AGENTS.md": NODE_AGENTS,
    ".github/workflows/ci.yml": """name: ci
on: [push, pull_request]
jobs:
  checks:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pnpm install --frozen-lockfile
      - run: pnpm lint
      - run: pnpm typecheck
      - run: pnpm test
""",
}

AUTONOMOUS_NODE = {
    **OPTIMIZED_NODE,
    "AGENTS.md": NODE_AGENTS + """
## Agent metrics

We review agent task completion and intervention rates in the weekly retro.
""",
    "CONTRIBUTING.md": "# Contributing\n\n## Pull requests\n\nOpen a PR from a topic branch; CI must pass.\n",
    ".github/workflows/security.yml": """name: security
on: [pull_request]
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pnpm audit --prod
      - uses: github/codeql-action/analyze@v3
""",
}

SCENARIOS: dict[str, dict[str, str]] = {
    "empty": {},
    "foundational-python": FOUNDATIONAL_PYTHON,
    "missing-tests": MISSING_TESTS,
    "no-agent-instructions": NO_AGENT_INSTRUCTIONS,
    "ambiguous-policy": AMBIGUOUS_POLICY,
    "structured-go": STRUCTURED_GO,
    "optimized-node": OPTIMIZED_NODE,
    "autonomous-node": AUTONOMOUS_NODE,
}


def materialize(name: str, target: Path) -> Path:
    """Write scenario ``name`` into ``target`` as a committed Git repository."""

    files = SCENARIOS[name]
    target.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(target)], check=True)
    # No background maintenance/gc: tests snapshot .git to prove read-only behavior.
    for key, value in (("maintenance.auto", "false"), ("gc.auto", "0")):
        subprocess.run(["git", "-C", str(target), "config", key, value], check=True)
    for relative, text in files.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    subprocess.run(["git", "-C", str(target), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(target), "-c", "user.name=Agentic Fixture",
         "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false",
         "commit", "-q", "--allow-empty", "-m", f"fixture: {name}"],
        check=True,
    )
    return target


def main(argv: list[str]) -> int:
    if argv[:1] == ["list"]:
        print("\n".join(SCENARIOS))
        return 0
    if len(argv) == 3 and argv[0] == "materialize" and argv[1] in SCENARIOS:
        print(materialize(argv[1], Path(argv[2])))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
