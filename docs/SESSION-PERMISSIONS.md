# Session permissions (S1)

A session plan describes the authority each harness invocation needs. Agentic Dev resolves these requirements and reports whether the selected harness can enforce them. AgentFlow owns approval of the plan and, in S3, launches each invocation with the recorded enforcement settings.

## Independent dimensions

| Dimension | Levels, least to most authority | Meaning |
| --- | --- | --- |
| Filesystem | `read-only`, `workspace-write` | Reads are allowed; writes, if any, are confined to the prepared workspace. The control checkout, sibling repositories, home directory, and global configuration are outside the grant. |
| Network | `off`, `on` | `off` forbids agent-controlled egress, including shell commands, built-in web tools, plugins, and MCP tools. Model transport and authentication required to run the harness are outside this agent-tool grant. |

There is no total order across dimensions. `workspace-write` with `network-off` is a normal combination. A trust profile's capability permissions, such as `repo.write` or `network.general`, are separate prerequisites and do not establish sandbox enforcement.

Each invocation supplies a **minimum** and **maximum** for each dimension. A minimum is the access the invocation needs to do its work; a maximum is its ceiling. The repository profile may lower the maximum. Resolution picks the least authority satisfying the minimum under both ceilings, independently for each dimension. A minimum above either ceiling produces a blocker. It never becomes a silent downgrade.

Defaults are:

| Role | Filesystem minimum / maximum | Network minimum / maximum |
| --- | --- | --- |
| `implementer` | `workspace-write` / `workspace-write` | `off` / `off` |
| `reviewer` | `read-only` / `read-only` | `off` / `off` |

The request may explicitly require network access. A reviewer is always read-only in v1, even if the request or profile asks for writes. A profile may constrain an implementer to read-only, in which case a write-requiring request blocks. Profile permission ceilings are optional and are keyed by role; absent ceilings do not add authority beyond the request's maximum.

Example request fragment:

```json
{
  "id": "implement",
  "role": "implementer",
  "harness": "codex",
  "permissions": {
    "filesystem": {"minimum": "workspace-write", "maximum": "workspace-write"},
    "network": {"minimum": "off", "maximum": "off"}
  }
}
```

Example profile fragment:

```toml
[permissions.implementer]
filesystem = "workspace-write"
network = "off"

[permissions.reviewer]
filesystem = "read-only"
network = "off"
```

## Enforceability and blockers

Enforceability is specific to the harness executable, version, dimension, effective level, and scope. It has three states: `enforceable`, `unenforceable`, or `unknown`. Only a demonstrated launch mechanism covering the entire boundary may be `enforceable`. The plan records the exact flags or configuration and the evidence behind the assessment. An `unenforceable` or `unknown` mandatory boundary blocks the invocation. A post-run repository fingerprint is detection, not enforcement; tool denial by prompt is advisory.

S1 inspects locally available harnesses. The installed Codex CLI exposes filesystem sandbox modes and an approval policy; the installed Claude Code CLI exposes permission modes and restricted tooling. Those options alone do not establish complete filesystem and network boundaries, especially when built-in tools, plugins, MCP servers, hooks, or user configuration can reach outside the workspace. Pi and OpenCode are not installed in the current development environment. The capability model therefore records gaps conservatively. Version-specific end-to-end probes are needed before changing a fact to `enforceable`. A caller cannot override an unknown fact by declaring its own enforcement support.

The installed-version command sandbox and restricted-tool measurements are recorded in [SESSION-PERMISSION-PROBE.md](SESSION-PERMISSION-PROBE.md). Their probe IDs accompany matching version/platform facts in the plan without turning partial observations into an `enforceable` claim.

Interactive harness approval and sandbox escalation are denied in v1. AgentFlow's human approval is bound to the `plan_digest` and does not authorize a tool to escape the sandbox during execution. S1 creates no workspace and invokes no harness.

## Contract behavior

`agentic.session-request@1` contains named invocations and their per-dimension bounds. `agentic.repository-profile@1` contains optional role ceilings. `agentic.session-plan@1` records requested bounds, effective levels, per-dimension enforceability and mechanism, and blockers. Unknown keys, dimensions, levels, and roles are input errors. Invocation order and all set-like fields are canonicalized before hashing. Permission bounds, effective permissions, harness version, and enforceability facts contribute to plan identity.

The planner may display a blocked plan, but AgentFlow must not prepare a workspace or invoke a harness from it. S1 only plans. Preparation and invocation enforcement arrive in S2 and S3.
