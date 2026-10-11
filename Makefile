SHELL := /bin/bash

.PHONY: check syntax lint typecheck smoke python-test

check: syntax lint typecheck python-test smoke

syntax:
	bash -n install.sh
	bash -n scripts/agentic-setup.sh
	bash -n scripts/agentic-setup-linux.sh
	bash -n scripts/agentic-repo-init.sh
	bash -n tests/smoke.sh
	bash -n scripts/ci-readiness-smoke.sh
	PYTHONPATH=src python3 -m py_compile src/agentic_dev/*.py src/agentic_dev/readiness/*.py scripts/sync-agent-ready-spec.py
	python3 scripts/sync-agent-ready-spec.py --check

lint:
	python3 -m ruff check src tests scripts

typecheck:
	python3 -m mypy

python-test:
	PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py' -v

smoke:
	bash tests/smoke.sh
