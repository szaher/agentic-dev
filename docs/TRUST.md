# Trust and permission profiles

Capabilities do not all have the same risk. `agentic-dev-env` models that explicitly with permission profiles.

## Built-in profiles

### safe

Local, low-risk defaults:

```text
repo.read
network.docs
browser.isolated
security.scan
secret.scan
```

### development

Adds normal development privileges such as repository writes, general network access, persistent/authenticated browser use, local containers, local database access, cluster read access, and observability read access.

### production-read

A read-oriented operational profile:

```text
repo.read
network.docs
network.general
browser.isolated
security.scan
secret.scan
database.read
cluster.read
cloud.read
observability.read
```

It deliberately does not grant cluster/cloud/database write permissions.

## Inspect

```bash
agentic trust list
agentic trust list --json
agentic trust show safe --json
```

## Select a user default

```bash
agentic trust set development
```

## Select for one repository

```bash
agentic trust set production-read --repo --path .
```

Repository state is written to `.agentic/trust.json` and added to the local Git exclude file so an upstream repository is not polluted.

## Custom profiles

```bash
agentic trust define review-only \
  --permission repo.read \
  --permission security.scan \
  --permission secret.scan \
  --description "Read-only code and security review"
```

## Capability enforcement

A capability declares required permissions. Mode-specific permissions are added dynamically.

For example:

```text
browser-automation --mode isolated
    requires browser.isolated

browser-automation --mode existing-browser
    requires browser.authenticated

sast
    requires repo.read + security.scan + network.general

container-image-scan
    requires security.scan + network.general + container.run
```

If the selected profile lacks a permission, `agentic capabilities enable` or `run` fails before invoking the provider.

The trust system is a local capability boundary; it is not a substitute for OS sandboxing, cloud IAM, Kubernetes RBAC, database authorization, or AgentFlow approval policy. Those remain separate enforcement layers.
