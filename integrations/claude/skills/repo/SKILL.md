---
name: repo
description: Use agentic-dev-env to inspect the current repository, select focused engineering skills, or diagnose the coding-agent environment.
---

# Agentic Dev Env

Use the local `agentic` CLI as the control plane for repository-aware development setup.

When the user asks what skills are useful for the current repository or task:

1. Preview recommendations without mutating the repository:
   `agentic skills suggest . --task "<task>" --no-prompt`
2. Explain the evidence behind the recommendation rather than activating every possible skill.
3. If the user explicitly wants the recommended skills activated, use:
   `agentic skills suggest . --task "<task>" --yes --target claude`
4. Use `agentic skills status .` to verify active skills.
5. Use `agentic doctor` when the local toolchain or agent integration may be broken.

Do not install project dependencies unless the user explicitly requests it. Do not overwrite unmanaged repository skills or instruction files.
