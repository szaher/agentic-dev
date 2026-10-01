# Agent configuration

Installing a binary does not guarantee that a coding agent can call it or knows when to use it. The environment therefore separates **tool registration** from **tool-routing instructions**.

## Claude Code

User-level instructions:

```text
~/.claude/CLAUDE.md
```

Project-level instructions can live in the repository's `CLAUDE.md`.

When `setup-coding-agent-env.sh --configure-agents` sees the `claude` command, it asks Serena to configure Claude Code and lets CodeGraph's installer configure its supported integration. It also installs a marker-delimited managed policy block in the user-level `CLAUDE.md`.

Serena upstream provides:

```bash
serena setup claude-code
```

CodeGraph provides:

```bash
codegraph install --target=claude --location=global --yes
```

Context7 remains explicit because its setup may require authentication:

```bash
npx ctx7 setup --claude
```

After changing MCP configuration, restart Claude Code and verify its connected tools.

## Codex

User-level instructions:

```text
~/.codex/AGENTS.md
```

Project-level `AGENTS.md` files add repository-specific instructions.

When `--configure-agents` sees the `codex` command, the setup script runs Serena's Codex setup, lets CodeGraph configure its integration, and installs the managed routing policy into the user-level `AGENTS.md`.

Serena upstream provides:

```bash
serena setup codex
```

CodeGraph provides:

```bash
codegraph install --target=codex --location=global --yes
```

Context7:

```bash
npx ctx7 setup --codex
```

Restart Codex after MCP configuration changes.

## Managed instruction block

The toolkit does not replace either global instruction file. It removes only its previous marker-delimited block and appends the current version:

```text
<!-- agentic-dev-env:start -->
...
<!-- agentic-dev-env:end -->
```

Everything outside those markers is preserved.

The source is [`../templates/global-agent-policy.md`](../templates/global-agent-policy.md).

## CLI tools do not need MCP registration

Tools such as these are available through normal shell execution:

```text
rg
fd
ast-grep
git
gh
jq
yq
just
repomix
```

The global policy still tells the agent when to prefer them.

## Project instructions

`saad-tool-repo-init.sh` creates local `AGENTS.md` and `CLAUDE.md` only when those files do not already exist. The generated content is repository-specific: detected languages, package managers, tools, and commands.

Those locally generated files are excluded through `.git/info/exclude`. If a repository already maintains tracked agent instructions, the initializer leaves them alone.
