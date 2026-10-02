# Worktrees and agent sessions

Parallel write-capable agents should not share one working tree. The worktree manager creates isolated Git worktrees and attaches local session metadata to each one.

## Create

```bash
agentic worktree create api-refactor \
  --agent codex \
  --task "Refactor the API compatibility layer"
```

By default:

- branch: `agentic/api-refactor`
- location: `~/.local/share/agentic-dev/worktrees/<repo>/api-refactor`
- base: current `HEAD`

Override when needed:

```bash
agentic worktree create fix-123 \
  --branch fix/123 \
  --base main \
  --root ~/Developer/worktrees
```

## Inspect

```bash
agentic worktree list
agentic worktree list --json

agentic worktree status api-refactor
agentic worktree status api-refactor --json
```

The status includes branch, HEAD, dirty state, and agent/task metadata.

Session metadata lives at:

```text
<worktree>/.agentic/session.json
```

and is excluded through the repository-local Git exclude mechanism.

## Clean

A dirty worktree is refused by default:

```bash
agentic worktree clean api-refactor
```

To deliberately discard uncommitted work:

```bash
agentic worktree clean api-refactor --force
```

The branch is retained unless explicitly requested:

```bash
agentic worktree clean api-refactor --delete-branch
```

The primary worktree can never be removed through this command.

## AgentFlow

AgentFlow can create one worktree per workflow attempt/executor and record the worktree path in its own run state. `agentic-dev` owns Git isolation mechanics; AgentFlow remains responsible for lifecycle policy, retries, evidence, approvals and deciding when cleanup is allowed.
