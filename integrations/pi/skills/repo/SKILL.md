---
name: agentic-repo
description: Use agentic-dev-env to inspect the current repository, recommend focused engineering skills, and diagnose the local coding-agent environment.
---

# Agentic Dev Env for Pi

Use the `agentic` CLI or the package commands exposed by this integration.

Useful Pi commands:

- `/agentic-doctor` checks the local toolchain.
- `/agentic-skills <task>` previews repo/task-aware recommendations without changing the repo.
- `/agentic-skills-activate <task>` activates the recommended skills for Pi in this repository.
- `/agentic-status` shows active project skills.

Prefer a small skill set. Do not activate every matching skill. Do not install project dependencies unless the user explicitly asks.


## Optional capabilities

Do not assume browser or other sensitive capabilities are installed. When browser interaction would materially help, preview the recommendation first:

```bash
agentic capabilities suggest . --task "<task>"
```

Only enable a capability when the user explicitly wants browser/tool access. Prefer isolated browser mode for routine UI testing.
