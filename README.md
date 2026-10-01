# agentic-dev-env

A macOS bootstrap and repository initializer for coding agents.

The goal is simple: make Claude Code, Codex, and similar agents spend less time rediscovering a repository and more time making correct changes with the right local tools.

A strong model is not enough by itself. Good agentic development also needs fast deterministic search, semantic code navigation, dependency awareness, current documentation, reproducible runtimes, isolated Git workflows, and a verification loop. This repo wires those pieces together without forcing one language, framework, or package manager on every project.

## The problem

Out of the box, coding agents often fall back to a costly loop:

```text
grep -> read large file -> grep again -> infer relationships -> edit -> hope
```

That works on small tasks, but it scales poorly. The agent can waste context reconstructing symbol relationships, miss call paths, use stale external APIs, install the wrong runtime, or let multiple agents collide in the same checkout.

`agentic-dev-env` creates a local toolchain where each job has a better tool:

```text
exact search          -> rg / fd
structural code       -> ast-grep
symbols/references    -> Serena
call graph / impact   -> CodeGraph
current external docs -> Context7
whole-repo snapshot   -> Repomix
runtime versions      -> mise
Python environments   -> uv
verification          -> compiler / linter / tests
isolation             -> Git worktrees
```

The model still reasons. Deterministic tools retrieve and verify.

## What this repo provides

Two scripts form the core workflow:

- `setup-coding-agent-env.sh` — run once per Mac. Installs the common workstation foundation, optional language/toolchain support, and can wire supported tools into Claude Code and Codex.
- `saad-tool-repo-init.sh` — run per repository. Detects the languages, frameworks, package managers, runtime declarations, build/test commands, and code-intelligence prerequisites actually used by that repo.

The repository initializer follows this rule:

> Detect -> augment -> never blindly overwrite.

It preserves existing `AGENTS.md`, `CLAUDE.md`, project version files, package-manager conventions, and build wrappers.

## Quick start

### 1. Clone and install the toolkit

```bash
git clone https://github.com/szaher/agentic-dev-env.git
cd agentic-dev-env
./install.sh
exec zsh
```

This installs the two commands into `~/.local/bin` and the shared policy template into `~/.config/agentic-dev-env`.

You also get short aliases:

```bash
agentic-dev-setup
agentic-repo-init
```

The original script names remain available for compatibility.

### 2. Bootstrap the Mac once

Recommended for a workstation that already contains multiple repositories:

```bash
agentic-dev-setup \
  --scan-root ~/saad/projects \
  --configure-agents
```

A minimal setup is simply:

```bash
agentic-dev-setup
```

To preinstall support for selected ecosystems:

```bash
agentic-dev-setup --languages python,go,rust,node
```

Or a broader workstation:

```bash
agentic-dev-setup --all-languages --configure-agents
```

### 3. Initialize each repository

```bash
cd ~/saad/projects/my-project
agentic-repo-init .
```

Read-only inspection first:

```bash
agentic-repo-init . --check
```

Project dependency installation is deliberately opt-in:

```bash
agentic-repo-init . --install-project-deps
```

## Agent configuration

`--configure-agents` configures the tools that can be configured non-interactively and writes a managed tool-routing block into the user-level instruction files when the corresponding agent is installed:

```text
Claude Code: ~/.claude/CLAUDE.md
Codex:       ~/.codex/AGENTS.md
```

Existing content outside the managed block is preserved.

The managed policy tells agents when to use `rg`, `ast-grep`, Serena, CodeGraph, Context7, Repomix, and the verification toolchain. The source template is [`templates/global-agent-policy.md`](templates/global-agent-policy.md).

Context7 setup may require authentication, so it remains explicit:

```bash
npx ctx7 setup --claude
npx ctx7 setup --codex
```

## Smart repository detection

The repo initializer recognizes common project signals for:

- Python
- Go
- Rust
- Node.js / TypeScript / JavaScript
- Deno
- Java and Kotlin
- C / C++
- Ruby
- PHP
- Swift
- Terraform
- Bash / Shell
- Lua
- Zig
- Angular, Svelte, and Vue
- Docker/Podman usage
- Helm and Kustomize
- Protobuf/Buf
- Bazel
- GitHub Actions
- Ansible

It also detects package-manager and runtime conventions such as:

```text
uv.lock              pyproject.toml       poetry.lock
pnpm-lock.yaml       yarn.lock            package-lock.json
Cargo.toml           go.mod               Gemfile
composer.json        pom.xml              gradlew / mvnw
.mise.toml           .tool-versions       .python-version
.node-version        .nvmrc
```

For polyglot repositories, Serena is configured with the detected language set rather than treating the project as a single-language codebase.

## Safety defaults

The scripts are intentionally conservative.

- They are designed to be rerunnable.
- Existing `AGENTS.md` and `CLAUDE.md` files are not overwritten.
- Local generated intelligence state is added to `.git/info/exclude`, not the tracked `.gitignore`.
- Project dependencies are not installed unless `--install-project-deps` is passed.
- Container runtimes are detected but Docker Desktop/Podman Desktop are not auto-installed.
- Repository-declared versions are respected where possible instead of replacing them with global defaults.
- `--check` performs repository discovery without modifying the repo or installing support.

Useful switches:

```bash
agentic-repo-init . --no-codegraph
agentic-repo-init . --no-serena
agentic-repo-init . --no-instructions
agentic-repo-init . --no-install-language-deps
agentic-repo-init . --no-runtime-install
```

## Why these tools

The core tools are intentionally complementary rather than redundant.

| Tool | Role in agentic development |
|---|---|
| [ripgrep](https://github.com/BurntSushi/ripgrep) | Fast exact-text search. Better than spending semantic-tool calls on a literal lookup. |
| [fd](https://github.com/sharkdp/fd) | Fast file discovery with sane defaults. |
| [ast-grep](https://ast-grep.github.io/) | AST-aware structural search and repeatable source transformations. |
| [Serena](https://github.com/oraios/serena) | Symbol-level semantic navigation, references, implementations, diagnostics, and refactoring through MCP. |
| [CodeGraph](https://github.com/colbymchenry/codegraph) | Local pre-indexed graph for call paths, dependency relationships, architecture exploration, and impact analysis. |
| [Context7](https://github.com/upstash/context7) | Current, version-aware external library/API documentation for agents. |
| [Repomix](https://github.com/yamadashy/repomix) | Compact repository snapshots when whole-repo or cross-repo context is useful. |
| [mise](https://mise.jdx.dev/) | Reproducible runtime/tool version management across projects. |
| [uv](https://docs.astral.sh/uv/) | Fast Python environments, packages, and tool execution. |
| [direnv](https://direnv.net/) | Per-directory environment activation. |
| [just](https://github.com/casey/just) | Small, explicit task runner that gives humans and agents stable commands. |
| [GitHub CLI](https://cli.github.com/) | Repository, PR, issue, release, and CI workflows from the terminal. |
| [delta](https://github.com/dandavison/delta) | More readable diffs for humans and agent-assisted review. |

The full catalog, including language servers and auxiliary tools installed on demand, is in [`docs/TOOLS.md`](docs/TOOLS.md).

## Worktrees for concurrent agents

Do not run several write-capable agents in the same working tree. Give each task an isolated worktree:

```bash
mkdir -p "$HOME/Developer/worktrees/my-project"

git worktree add \
  "$HOME/Developer/worktrees/my-project/feature-a" \
  -b feature/feature-a
```

One worktree per agent keeps branches, uncommitted changes, and experiments isolated while sharing the same Git object store.

## Repository layout

```text
agentic-dev-env/
├── install.sh
├── scripts/
│   ├── setup-coding-agent-env.sh
│   └── saad-tool-repo-init.sh
├── templates/
│   └── global-agent-policy.md
├── docs/
│   ├── ARCHITECTURE.md
│   ├── AGENT_CONFIGURATION.md
│   └── TOOLS.md
├── tests/
│   └── smoke.sh
└── .github/workflows/
    └── ci.yml
```

## Design notes

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the problem model, architecture, and why machine setup and repository setup are separate concerns.

See [`docs/AGENT_CONFIGURATION.md`](docs/AGENT_CONFIGURATION.md) for Claude Code/Codex instruction hierarchy and MCP/tool setup.

## Development

Run the local checks:

```bash
make check
```

The CI workflow performs syntax checks and a read-only repository smoke test on macOS.

## License

MIT. See [`LICENSE`](LICENSE).
