# Execution backends and sandboxing

`agentic-dev-env` separates **what should be verified** from **where the command runs**.

Supported backends:

| Backend | Behavior |
|---|---|
| `host` | runs directly in the repository checkout; default |
| `container` | Docker or Podman with the repository mounted at `/workspace` |
| `devcontainer` | uses the repository's Dev Container configuration |
| `dagger` | runs through Dagger Workspace in a container with `--no-apply` |

## Inspect

```bash
agentic execution status
agentic execution status --json
```

## Configure

The default remains host:

```bash
agentic execution configure host
```

A generic container backend requires an explicit image:

```bash
agentic execution configure container \
  --image python:3.13 \
  --network none \
  --repo
```

Repo-scoped configuration is stored under `.agentic/execution.json` and excluded locally.

A Dagger backend also requires an explicit image:

```bash
agentic execution configure dagger \
  --image golang:1.26 \
  --repo
```

## Run one command

```bash
agentic execution run "pytest -q"
```

Override the selected backend:

```bash
agentic execution run "pytest -q" \
  --backend container \
  --image python:3.13 \
  --profile development \
  --json
```

## Container isolation

Container execution mounts the repository read/write at `/workspace` so tests/builds can create normal repository artifacts. Network is disabled by default:

```text
docker|podman run --rm
  -v <repo>:/workspace
  -w /workspace
  --network none
  <image>
  sh -lc <command>
```

Container execution requires the `container.run` trust permission. Networked execution additionally requires `network.general`.

## Dev Containers

For repositories containing `.devcontainer/` or `.devcontainer.json`, the backend uses the official Dev Container CLI:

```text
devcontainer up --workspace-folder <repo>
devcontainer exec --workspace-folder <repo> sh -lc <command>
```

Dev Containers can define their own network/runtime behavior, so this backend requires both `container.run` and `network.general`.

Upstream: https://github.com/devcontainers/cli

## Dagger

The Dagger backend uses the current Workspace execution interface:

```text
dagger --workspace <repo> workspace exec \
  --no-apply \
  --from=<image> \
  -- sh -lc <command>
```

`--no-apply` prevents Dagger workspace overlay changes from being written back by agentic-dev-env verification.

Dagger manages its own engine/network behavior, therefore this backend requires `container.run` and `network.general`.

Upstream CLI reference: https://docs.dagger.io/reference/cli/

## Verification integration

```bash
agentic verify run \
  --backend container \
  --image python:3.13 \
  --profile development \
  --json
```

Normal lint/typecheck/test/build checks route through the selected execution backend. Security capability providers keep their own execution/trust rules.

The normalized result schema is:

```text
schemas/execution-result-v1.schema.json
```

## Security boundary

This abstraction does not claim containers are a complete security sandbox. Docker/Podman daemon permissions, mounted repository writes, Dev Container features, Dagger engines, kernel isolation, and host configuration remain real trust boundaries.

The design provides:
- explicit backend selection;
- least-network default for generic containers;
- explicit container/network permissions;
- normalized evidence.

It does not bypass or replace OS/container-runtime security controls.
