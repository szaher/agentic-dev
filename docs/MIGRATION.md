# Migrating from agentic-dev-env to Agentic Dev

The GitHub repository, Python distribution, import package, configuration namespace, and helper scripts were renamed for the Agentic Dev product identity.

## Canonical identity

```text
Product             Agentic Dev
GitHub               szaher/agentic-dev
PyPI                 agentic-dev
Python package       agentic_dev
CLI                  agentic
Config               ~/.config/agentic-dev
Data                 ~/.local/share/agentic-dev
Environment prefix   AGENTIC_DEV_
```

## User configuration

On first `agentic` startup, default legacy configuration from:

```text
~/.config/agentic-dev-env
```

is copied non-destructively into:

```text
~/.config/agentic-dev
```

Rules:

- existing files in the new location are never overwritten;
- the legacy directory is never deleted;
- the old embedded Python copy and old policy-template copy are not migrated because the current installation supplies them;
- provider state, capability state, trust profiles, remotes, execution settings, metrics, and other user state are copied when the destination is missing.

A migration record is written under the new config directory so the default migration is not repeatedly performed.

## Environment-variable compatibility

The canonical variables are:

```text
AGENTIC_DEV_CONFIG_DIR
AGENTIC_DEV_BIN_DIR
```

For the transition release, the previous config/bin variables are still accepted as fallbacks. If a legacy config variable is explicitly set, Agentic Dev continues to use that configured directory instead of copying it.

New automation should use only `AGENTIC_DEV_*`.

## Existing worktrees

Existing Git worktree directories under the previous data root are **not moved automatically**.

Moving an attached worktree directory behind Git's back can invalidate Git worktree metadata. Existing linked worktrees remain discoverable through `git worktree list` and through Agentic Dev's worktree commands. Newly created worktrees use:

```text
~/.local/share/agentic-dev/worktrees/
```

unless `AGENTIC_WORKTREE_ROOT` is set.

## Managed Claude/Codex instruction blocks

`agentic setup --configure-agents` removes both the old and current Agentic Dev managed-marker blocks before writing the current block. User-written content outside those markers is preserved.

## Helper command compatibility

The public interface is:

```bash
agentic setup
agentic repo init
```

A source installation via `./install.sh` provides the pre-rename helper aliases for one transition release. They are deprecated and should not be used in new scripts.

PyPI/uv installations expose the public `agentic` CLI; helper shell assets are bundled internally and are not intended as public entry points.

## Python imports

The import package is now:

```python
import agentic_dev
```

The former import package is not retained as a compatibility package. The Python API was not declared stable before this rename; callers should update imports before adopting the new distribution.
