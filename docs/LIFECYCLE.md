# Lifecycle, compatibility, Linux/WSL and remotes

## Compatibility

```bash
agentic compatibility
agentic compatibility --json
```

The compatibility document reports:

- agentic-dev-env version;
- OS, architecture, Python, and WSL detection;
- Claude Code, Codex, Pi, Serena, CodeGraph, container and infrastructure CLI versions/availability;
- native integration status;
- installed provider metadata and compatibility constraints.

This is diagnostic. It does not automatically upgrade external tools.

## Self-update

`./install.sh` records the source checkout in:

```text
~/.config/agentic-dev-env/install.json
```

Check without network access:

```bash
agentic update check --json
```

Refresh the Git remote first:

```bash
agentic update check --fetch --json
```

Apply:

```bash
agentic update apply
```

Apply is deliberately conservative:

1. source must still be a Git checkout;
2. source checkout must be clean;
3. the configured upstream must be reachable;
4. only a fast-forward update is accepted;
5. `install.sh` is rerun from the updated checkout.

Diverged/local-modified source checkouts are refused instead of reset.

## State migrations

```bash
agentic migrate
agentic migrate --json
```

State migrations are versioned and idempotent. `install.sh` invokes migration after installing a new CLI version.

The v1 migration registry is intentionally small; future state-layout changes add numbered hooks rather than ad-hoc file rewrites.

## Linux and WSL

The main setup command is now platform-dispatching:

```bash
./install.sh
agentic-dev-setup --configure-agents
```

On macOS it uses the existing Homebrew-oriented bootstrap.

On Linux/WSL it uses:

```text
scripts/setup-linux-agent-env.sh
```

Supported Linux package-manager families:

- apt
- dnf
- pacman

The Linux bootstrap installs a conservative common CLI base, uv, Serena, CodeGraph, and selected language support where a stable distro/native installer is practical. Kubernetes/cloud/Terraform tooling that is often organization/version-policy specific is reported rather than silently installed from an arbitrary third-party repository.

`install.sh` writes PATH configuration to the active shell's:

- `~/.zshrc`
- `~/.bashrc`
- or `~/.profile`

instead of assuming zsh.

## Named SSH remotes

Remote profiles store connection metadata only. Passwords/private keys are not stored.

```bash
agentic remote add devbox \
  --host dev.example.com \
  --user saad \
  --port 22 \
  --path /srv/project

agentic remote list --json
```

Inspection uses OpenSSH BatchMode/key or SSH-agent authentication:

```bash
agentic remote inspect devbox \
  --profile production-read \
  --json
```

`development` and `production-read` include `remote.read`.

Arbitrary remote command execution uses a separate permission, `remote.exec`, which no built-in profile grants:

```bash
agentic trust define remote-runner \
  --permission remote.exec \
  --description "Explicit remote command execution"

agentic remote exec devbox "git status" \
  --profile remote-runner \
  --json
```

This separation prevents a read-oriented operational profile from silently becoming a generic remote shell.
