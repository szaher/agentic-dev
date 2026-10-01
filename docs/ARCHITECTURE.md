# Architecture

## What we are solving

Coding agents are capable reasoners, but a repository is not just text. Useful software work depends on several different kinds of knowledge:

- exact file and text location;
- syntax and AST structure;
- symbols, definitions, references, and implementations;
- call relationships and change impact;
- external API documentation that matches the version in use;
- the repository's actual runtime, package manager, wrappers, and tests;
- an isolated place to make changes;
- deterministic verification after the edit.

Without those layers, an agent spends context and tool calls rebuilding information that local developer tooling already knows how to answer.

## The model

```text
                    Claude Code / Codex / other agent
                                |
                    global tool-routing policy
                                |
                    context-aware Agent Skills
                                |
        +-----------------------+-----------------------+
        |                       |                       |
   exact / structural      semantic / graph       external knowledge
   rg, fd, ast-grep        Serena, CodeGraph       Context7, Repomix
        |                       |                       |
        +-----------------------+-----------------------+
                                |
                       repository conventions
                   mise / uv / package managers
                                |
                       edit -> verify -> diff
                                |
                  compiler / lint / typecheck / tests
                                |
                         Git branch/worktree
```

No one tool is the universal code browser. The value comes from routing each question to the cheapest precise source of truth.

## Why two scripts

Machine state and repository state have different lifecycles.

### Machine bootstrap

`setup-coding-agent-env.sh` manages things that should normally be shared across projects:

- CLI foundation;
- runtime managers;
- agent-facing MCP tools;
- optional language/toolchain support;
- shell integration;
- global Claude/Codex tool policy.

It should be run once and rerun when the workstation needs updating.

### Repository bootstrap

`saad-tool-repo-init.sh` manages project-specific discovery:

- languages and frameworks;
- package managers and lockfiles;
- declared runtime versions;
- test/lint/format/typecheck/build commands;
- Serena project configuration;
- CodeGraph project index;
- local machine-readable repository facts.

This script is deliberately conservative because it may be run on upstream repositories that the user does not own.

## Retrieval routing

The default routing policy is:

| Question | Tool |
|---|---|
| Where does this exact string occur? | `rg` |
| Which files match this name/pattern? | `fd` |
| Which code matches this syntax shape? | `ast-grep` |
| Where is this symbol defined/referenced/implemented? | Serena |
| Who calls this and what could this change affect? | CodeGraph |
| What does the current library API say? | Context7 |
| I need a compressed whole-repo snapshot | Repomix |
| Is the change correct? | Compiler, linter, type checker, tests |

This reduces two common forms of waste: reading too much source when a symbol lookup would do, and invoking expensive semantic tooling for a trivial literal search.

## Verification boundary

Code intelligence helps an agent understand a change. It does not prove the change is correct.

The preferred end of a task is:

```text
format -> lint -> typecheck/compiler -> focused tests -> broader tests -> git diff
```

A repository can replace any step with its own wrapper command. The initializer tries to discover and reuse existing `make`, package scripts, `mvnw`, `gradlew`, and similar conventions.

## Local state

The initializer may create:

```text
.codegraph/
.serena/
.saad-agent/repo.env
AGENTS.md
CLAUDE.md
```

Generated state is added to `.git/info/exclude` so an upstream repository is not modified merely because the local agent environment was initialized. Existing tracked instruction files are preserved.

## Dependency installation boundary

Language-server/toolchain prerequisites may be installed automatically because they enable the local development environment.

Project dependencies are different. Commands such as `npm install`, `uv sync`, `bundle install`, or lifecycle scripts can execute repository-controlled code. For that reason, dependency installation is explicit through `--install-project-deps`.

## Concurrency boundary

Multiple write-capable agents should not share one checkout. Git worktrees provide cheap isolation with one branch and working directory per task while sharing repository objects.


## Skills layer

Tools answer what the agent can call. Skills encode how to carry out a recognizable engineering workflow.

The skill system intentionally stays on-demand:

```text
repository signals + optional task text
                 |
                 v
       deterministic recommendation
                 |
                 v
         explain evidence to user
                 |
                 v
      user selects / accepts / skips
                 |
          +------+------+
          |             |
          v             v
 .claude/skills     .codex/skills
```

Skills are local/untracked by default so initializing an upstream repository does not pollute a pull request. Shared mode is explicit for teams that want to version the workflow.

The recommender is registry-driven rather than embedding skill-specific conditionals in the Bash bootstrap.


## Optional capability layer

Not every useful agent tool belongs in the default workstation.

Capabilities that are security-sensitive, expensive, overlapping, or task-specific are opt-in:

```text
repo + task context
       |
       v
capability suggestion
       |
       v
explicit user enable
       |
       +-- browser-automation -> Playwright MCP
       +-- browser-debug      -> Chrome DevTools MCP
       +-- browser-agent      -> Browser Use
```

This differs from core tools such as `rg` or `git`: repo detection may recommend an optional capability, but it never enables one.

Browser is the first pack because it has a meaningful security boundary. Existing-browser mode may expose authenticated sessions, cookies, internal pages, and actions available to the browser session.

Future packs can use the same abstraction for databases, Kubernetes clusters, cloud accounts, observability systems, or desktop automation.
