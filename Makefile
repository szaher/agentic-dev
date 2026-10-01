SHELL := /bin/bash

.PHONY: check syntax smoke python-test

check: syntax python-test smoke

syntax:
	bash -n install.sh
	bash -n scripts/setup-coding-agent-env.sh
	bash -n scripts/saad-tool-repo-init.sh
	bash -n tests/smoke.sh
	PYTHONPATH=src python3 -m py_compile src/agentic_dev_env/*.py

python-test:
	PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py' -v

smoke:
	bash tests/smoke.sh
