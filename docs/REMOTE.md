# SSH development profiles

SSH profiles let tooling refer to remote development machines without storing passwords or private-key contents in agentic-dev.

## Add

```bash
agentic remote add gpu-lab gpu.example.com \
  --user saad \
  --port 22 \
  --identity-file ~/.ssh/id_ed25519 \
  --workdir /srv/project
```

Stored fields:

- profile name;
- host;
- user;
- port;
- identity-file path;
- optional remote working directory.

Passwords and private-key contents are not accepted.

## Inspect

```bash
agentic remote list
agentic remote list --json
agentic remote show gpu-lab
```

## Connectivity test

```bash
agentic remote test gpu-lab --json
```

The test uses non-interactive SSH with `BatchMode=yes` and a short connection timeout, so it will not prompt for passwords.

## Remove

```bash
agentic remote remove gpu-lab
```

Remote profiles are user-local state under the agentic-dev configuration directory.

They are intended as a connection-description layer for future remote execution/AgentFlow adapters, not as a replacement for SSH config, bastion policy, VPN controls, or host authorization.
