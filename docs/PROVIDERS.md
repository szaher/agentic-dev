# External providers and lifecycle

External providers let `agentic-dev` gain skills and command-backed capabilities without hard-coding them into core.

A provider is a directory or Git repository containing:

```text
agentic-provider.json
skills/
scripts/
...
```

## Manifest

Minimal example:

```json
{
  "schema_version": "1",
  "name": "example-provider",
  "version": "1.0.0",
  "description": "Example provider",
  "compatibility": {
    "agentic": ">=0.12.0,<1.0.0",
    "platforms": ["macos", "linux", "wsl"]
  },
  "requires": {
    "executables": ["python3"],
    "agents": ["codex"]
  },
  "skills": [
    {
      "name": "example-review",
      "description": "Example review workflow",
      "category": "review",
      "path": "skills/example-review",
      "signals": ["language:python"],
      "task_keywords": ["review"],
      "priority": 1
    }
  ],
  "capabilities": [
    {
      "name": "example-capability",
      "category": "provider",
      "provider": "example-provider",
      "description": "Run an example local command",
      "risk": "Executes provider-owned code.",
      "targets": ["local"],
      "required_permissions": ["repo.read"],
      "command": ["python3", "scripts/run.py", "{repo}"]
    }
  ]
}
```

Schema:

```text
src/agentic_dev/schemas/provider-manifest-v1.schema.json
```

Provider skill names and capability names cannot override built-in names. Built-ins win.

## Install

Local directory:

```bash
agentic providers add ./my-provider
```

Git source:

```bash
agentic providers add https://github.com/example/provider.git --ref v1.2.0
```

Pin a local/remote provider tree digest:

```bash
agentic providers add ./my-provider --sha256 <expected-tree-sha256>
```

For Git sources, require a Git-verified good signature:

```bash
agentic providers add https://github.com/example/provider.git \
  --ref v1.2.0 \
  --require-signed-commit
```

Installed metadata records:

- provider version;
- source;
- resolved Git commit SHA when applicable;
- Git signature status;
- manifest SHA-256;
- complete provider content SHA-256;
- compatibility metadata.

## Verify

```bash
agentic providers verify example-provider
agentic providers doctor --json
```

A provider whose installed content no longer matches its recorded digest is not loaded into the skill/capability registries.

## Update

Provider updates are never automatic:

```bash
agentic providers update example-provider --yes
agentic update --yes
```

`agentic update` currently updates installed external providers. Core application updates remain explicit through the installation source used for agentic-dev (for example Git pull + `./install.sh`).

## Migration hooks

Providers may declare migrations:

```json
{
  "migrations": [
    {
      "version": "1",
      "command": ["python3", "scripts/migrate_v1.py"]
    }
  ]
}
```

Hooks are arbitrary provider-owned code, so they never run during install/update.

Explicit execution:

```bash
agentic providers migrate example-provider --yes
```

## Capability execution

A command-backed provider capability must first be enabled under a trust profile:

```bash
agentic capabilities enable example-capability --profile safe
agentic capabilities run example-capability . --profile safe --json
```

`{repo}` in provider command argv is replaced with the resolved repository path.

Provider commands run from the installed provider source directory.

## Compatibility

Provider compatibility can constrain:

- agentic-dev version;
- host platform: macOS, Linux, WSL, Windows;
- required executables;
- required coding-agent CLIs.

`agentic providers doctor` reports missing requirements without installing them automatically.
