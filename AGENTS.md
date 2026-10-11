# Agent instructions: agentic-dev

Agentic Dev is the `agentic` CLI. It makes repositories agent-ready and prepares
safe development environments for coding agents. It is Python 3.11+ with
**no runtime dependencies** (the standard library only).

## Commands

```bash
pip install -e '.[dev]'        # ruff, mypy, jsonschema (pinned dev tools)
make check                     # everything CI runs: syntax, lint, typecheck, tests, smoke
make lint                      # python3 -m ruff check src tests scripts
make typecheck                 # python3 -m mypy
make python-test               # PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'
PYTHONPATH=src python3 -m unittest tests/test_readiness_compare.py   # one module
PYTHONPATH=src python3 -m agentic_dev.cli ready assess .            # run the CLI from source
```

## Layout

- `src/agentic_dev/cli.py`: argparse wiring; each `cmd_*` builds a document, then prints JSON or text.
- `src/agentic_dev/human_output.py` and `src/agentic_dev/readiness/render.py`: text views (render supplied facts only).
- `src/agentic_dev/readiness/`: Agent Ready assessment, plan, apply, make, verify, and compare.
- `src/agentic_dev/schemas/`: one JSON Schema per contract version, registered in `src/agentic_dev/contracts.py`.
- `tests/`: `unittest` modules; CLI tests run `python -m agentic_dev.cli` in a subprocess.
- `docs/`: design and contract docs. Start with `docs/ARCHITECTURE.md` and `docs/API.md`.

## Conventions

- Every module starts with `from __future__ import annotations` and is fully type-hinted; keep mypy clean.
- Lines are at most 120 characters. Ruff enforces correctness rules only, so match the surrounding formatting.
- Machine-readable output is a versioned document with `schema_version` and `document_type`.
  A new document needs a schema in `src/agentic_dev/schemas/`, a `Contract` in `REGISTRY`,
  and, if it has exit codes, an `EXIT_CODES` entry. `tests/test_contracts.py` enforces this.
- Text and `--json` views describe the same document. Exit codes come from the document, not the view.
- Readiness assessment is deterministic: no network, no LLM, no writes. Only `ready apply` and
  `ready make` write, and only managed blocks.
- Tests isolate user state with `AGENTIC_DEV_CONFIG_DIR` set to a temporary directory.
- Record user-visible changes under `## Unreleased` in `CHANGELOG.md`.

## Do not

- Do not add runtime dependencies to `pyproject.toml`; dev and test extras are fine.
- Do not run `ruff format` on the repository. Formatting is not adopted, and it would rewrite most files.
- Never remove or rename a contract field, document type, or listed exit code. That breaks
  consumers such as AgentFlow. Add fields, or add a new contract version.
- Never edit `src/agentic_dev/readiness/specs/` by hand. Use `scripts/sync-agent-ready-spec.py`.
- Never commit secrets or `.env` files, and never print credentials in command output.
- Do not let tests touch the real `~/.config` or a real repository; use temporary directories.
- Do not change the version in `pyproject.toml` or `src/agentic_dev/__init__.py` outside a release
  (see `docs/RELEASING.md`).

## Common tasks

- New CLI command: add a `cmd_*` and a parser entry in `src/agentic_dev/cli.py`, a text renderer, and
  a `--json` contract (see Conventions). Then document it in `README.md` and `docs/`.
- Readiness change: measure it with `agentic ready assess . --json > before.json`, make the change,
  then run `agentic ready compare before.json`. Exit 1 means a rule regressed.
- Before finishing: run `make check` and review `git diff`.
