# Native agent integrations

The core of agentic-dev-env stays vendor-neutral. Claude Code, Codex, and Pi each get a thin native adapter around the same repository detector, skill registry, and `agentic` CLI.

This avoids maintaining three copies of the engineering skills.

## Architecture

```text
                   agentic-dev-env core
          detection + skill registry + CLI
                         |
              +----------+----------+
              |          |          |
              v          v          v
           Claude      Codex        Pi
           plugin      plugin     package
```

The native adapters deliberately expose only a small orchestration surface. The 16+ engineering skills remain repo/task-selected instead of being permanently loaded into every session.

## Install all available integrations

After running `./install.sh`:

```bash
agentic integrations install all
agentic integrations status
```

`setup-coding-agent-env.sh --configure-agents` also attempts this for the agent CLIs already installed on the machine.

Missing agents are skipped when using `all`.

## Claude Code

The repository is a Claude Code marketplace:

```text
.claude-plugin/marketplace.json
integrations/claude/
├── .claude-plugin/plugin.json
└── skills/repo/SKILL.md
```

Manual install:

```bash
claude plugin marketplace add szaher/agentic-dev-env
claude plugin install agentic-dev-env@agentic-dev-env
```

The plugin contributes one lightweight `repo` skill that teaches Claude to use the local `agentic` control plane. Repository-specific engineering skills are still selected separately.

Official docs: https://code.claude.com/docs/en/plugins

## Codex

The repository also exposes a Codex marketplace:

```text
.agents/plugins/marketplace.json
integrations/codex/
├── plugin.json
├── .codex-plugin/plugin.json
└── skills/repo/SKILL.md
```

Register the marketplace:

```bash
codex plugin marketplace add szaher/agentic-dev-env
```

Then start Codex, run `/plugins`, choose the `agentic-dev-env` marketplace, and install **Agentic Dev Env**. Current Codex CLI marketplace commands manage marketplace sources; plugin installation is completed through the plugin browser/Desktop Plugins Directory.

Official docs: https://developers.openai.com/plugins/build/plugins

## Pi

The repository root is also a Pi package through `package.json`.

Install:

```bash
pi install git:github.com/szaher/agentic-dev-env
```

The package provides:

- the `agentic-repo` skill;
- `/agentic-doctor`;
- `/agentic-skills <task>`;
- `/agentic-skills-activate <task>`;
- `/agentic-status`.

Pi project-specific engineering skills are installed under:

```text
.pi/skills/<skill>/SKILL.md
```

Official package docs: https://pi.dev/docs/latest/packages

Official skills docs: https://pi.dev/docs/latest/skills

## Direct skill activation still works

Plugins/packages do not replace repository-specific selection.

Examples:

```bash
agentic skills suggest . --task "debug reconcile failures"
agentic skills suggest . --task "debug reconcile failures" --yes --target claude
agentic skills suggest . --task "debug reconcile failures" --yes --target codex
agentic skills suggest . --task "debug reconcile failures" --yes --target pi
agentic skills suggest . --task "debug reconcile failures" --yes --target all
```

Target semantics:

- `both` = Claude + Codex, retained for compatibility;
- `all` = Claude + Codex + Pi;
- individual targets install only for that agent.

## Why the native adapters stay small

A permanently enabled plugin contributes discovery/context overhead. Therefore the plugin/package should expose the control plane, not every possible engineering skill.

The normal flow is:

```text
native integration
      |
      v
agentic skills suggest
      |
      v
repo/task evidence
      |
      v
selected local skills only
```

That keeps agent context focused while still making the environment discoverable and easy to operate.
