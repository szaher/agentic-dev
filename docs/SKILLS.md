# Context-aware Agent Skills

Agentic development needs more than installed tools. Tools answer **what the agent can call**; skills encode **how to perform a class of engineering work well**.

`agentic-dev-env` therefore detects repository and task context, recommends a small skill set, explains why each skill was suggested, and lets the user decide what to activate.

## Native locations

Activated skills use the native project skill directories:

```text
Claude Code: .claude/skills/<skill>/SKILL.md
Codex:       .codex/skills/<skill>/SKILL.md
Pi:          .pi/skills/<skill>/SKILL.md
```

The built-in skills use the portable `SKILL.md` format rather than a custom instruction format.

## Default behavior

Run:

```bash
agentic skills suggest .
```

The CLI scans repository signals and shows recommendations with evidence:

```text
Repository: example

Detected context:
  - language:python — Python project/source detected
  - framework:fastapi — fastapi declared in Python project metadata
  - testing:pytest — pytest declared in Python project metadata

Skill recommendations:
   1. [✓] python-engineering
      why: Python project/source detected
   2. [✓] api-design
      why: HTTP API framework detected
   3. [✓] test-development
      why: pytest declared in Python project metadata
```

In an interactive terminal:

```text
Select skills [Enter=recommended, comma-separated numbers, a=all, n=none]:
```

Nothing is activated merely because it was detected.

## Task-aware recommendations

Repository shape is only part of the context. The current task can change the useful skill set:

```bash
agentic skills suggest . \
  --task "debug API latency and optimize PostgreSQL queries"
```

This can surface workflow skills such as `debugging`, `performance-analysis`, `api-design`, and `database-migrations` in addition to technology/language skills.

Task matching is deterministic keyword/rule matching, not an opaque generated probability.

## Local by default

The default activation mode is local:

```bash
agentic skills suggest .
```

Selected skills are copied into the selected Claude/Codex/Pi project skill directories and those specific generated directories are added to `.git/info/exclude`.

This is appropriate when:
- you are initializing an upstream repository;
- the team has not agreed to track agent skills;
- the recommendations are personal/workstation-specific.

## Shared/team mode

When the team intentionally wants to version the skills:

```bash
agentic skills suggest . --shared
```

or:

```bash
agentic skills add api-design test-development --shared
```

Shared mode does not add those skill directories to the local exclude file, so they can be committed normally.

## Human control

Useful commands:

```bash
agentic skills list
agentic skills explain kubernetes-operator-development
agentic skills explain debugging --full

agentic skills suggest .
agentic skills suggest . --task "review this PR for API compatibility"

agentic skills add api-design test-development
agentic skills remove api-design
agentic skills status .
```

For automation/noninteractive usage:

```bash
agentic skills suggest . --yes
```

To emit machine-readable recommendations without activating anything:

```bash
agentic skills suggest . --json
```

## Repo initialization integration

The existing initializer invokes skill recommendations after tool/language setup:

```bash
agentic-repo-init .
```

Task-aware form:

```bash
agentic-repo-init . \
  --task "review the controller reconciliation logic"
```

Controls:

```text
--no-skills
--skills-yes
--skills-shared
--skills-target both|claude|codex
```

`--check` shows recommendations but never activates them.

## Built-in catalog

The first catalog intentionally stays compact:

### Language
- python-engineering
- go-engineering
- rust-engineering
- typescript-engineering

### Technology / repository type
- kubernetes-development
- kubernetes-operator-development
- github-actions
- container-development
- terraform-development

### Engineering workflow
- api-design
- database-migrations
- test-development
- debugging
- code-review
- refactoring
- performance-analysis

The goal is not to attach every plausible skill. The recommender caps the default active recommendation set and keeps additional matching skills optional.

## Conflict safety

The toolkit marks only skills it manages. If a destination already contains an unmanaged `SKILL.md`, the CLI refuses to overwrite or remove it unless the user explicitly uses `--force` for activation.

This prevents a local environment tool from destroying repository-owned skill content.

## Registry-driven detection

The registry lives with the built-in skills and maps each skill to:
- repo signals;
- task keywords;
- category;
- description;
- ordering priority.

Repository detection produces facts such as:

```text
language:python
framework:fastapi
repo-type:kubernetes-operator
database:migrations
ci:github-actions
technology:containers
```

The recommender then maps those facts plus task text to skills. That separation keeps detection reusable and avoids a large collection of skill-specific shell conditionals.
