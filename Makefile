SHELL := /bin/bash

.PHONY: check syntax smoke

check: syntax smoke

syntax:
	bash -n install.sh
	bash -n scripts/setup-coding-agent-env.sh
	bash -n scripts/saad-tool-repo-init.sh
	bash -n tests/smoke.sh

smoke:
	bash tests/smoke.sh
