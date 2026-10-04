# Session permission probe — macOS, 2026-10-04

This report records narrower mechanisms observed on the installed CLIs. It does **not** promote a whole invocation to `enforceable`. `agentic session plan` continues to block every real harness permission as `unknown` while launch integration, all tool surfaces, and escalation denial remain unverified.

## Installed tools and evidence IDs

| Harness | `--version` | Local probe ID | Availability |
| --- | --- | --- | --- |
| Codex | `codex-cli 0.154.0` | `macos-codex-0.154.0-2026-10-04` | Installed |
| Claude Code | `2.1.289 (Claude Code)` | `macos-claude-2.1.289-2026-10-04` | Installed |
| Pi | unavailable | — | Not installed |
| OpenCode | unavailable | — | Not installed |

The CLI `--help` output was checked for sandbox, profile, approval, tool, and restricted-mode options. Each final probe recorded the same version before and after its side-effect checks. Codex 0.154.0 requires `codex sandbox --permission-profile NAME`; passing only legacy `sandbox_mode` config to that subcommand failed before the payload ran. This matters when translating the probe into an eventual `codex exec` launch recipe. [Codex permissions](https://learn.chatgpt.com/docs/permissions), [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).

Claude Code updated from 2.1.288 to 2.1.289 during the spike. The final Claude runs recorded `2.1.289 (Claude Code)` both before and after each probe. The older observations are not attached to the current plan.

Run the reproducible, throwaway probes from this repository:

```bash
python3 scripts/probe_codex_session_permissions.py
python3 scripts/probe_claude_session_permissions.py read-only
python3 scripts/probe_claude_session_permissions.py workspace-write
```

The scripts create `workspace` and `outside` below `/private/tmp`, verify actual file contents and file existence after each attempt, and write results under `/private/tmp`. The Claude probe uses a live model invocation; its text is supporting context, while the file checks are the side-effect evidence. Neither script writes to this repository or the sibling repositories.

## Codex command sandbox

The control payload, run without Codex sandboxing, changed both files, created a file through a symlink from `workspace` to `outside`, and connected to a local loopback listener. The sandboxed payload used a temporary `CODEX_HOME`, `approval_policy = "never"`, and these profiles:

```toml
[permissions.probe-workspace]
extends = ":workspace"

[permissions.probe-workspace.filesystem]
":tmpdir" = "deny"
":slash_tmp" = "deny"

[permissions.probe-workspace.network]
enabled = false
```

The explicit temp denials matter: Codex's built-in `:workspace` profile allows writes to system temp directories as well as workspace roots. The custom profile kept the probe's `outside` directory off limits while retaining the current workspace root. [Codex permissions](https://learn.chatgpt.com/docs/permissions).

| `codex sandbox` profile | Inside write | Outside write | Symlink escape | Loopback connect |
| --- | --- | --- | --- | --- |
| No sandbox, control | Succeeded | Succeeded | Succeeded | Succeeded |
| `:read-only` | Denied | Denied | Denied | Denied |
| `probe-workspace` | Succeeded | Denied | Denied | Denied |

These are command-sandbox results on this macOS installation. They do not establish that an actual `codex exec` invocation loads this exact profile, that built-in web, MCP, connectors, and plugins have no other egress path, or that a model-requested escalation is denied. The no-escalation setting was passed to the command sandbox, but no model-driven approval request occurred. The planner therefore keeps filesystem and network status `unknown`.

## Claude Code restricted tool surface

The read-only recipe used `--restricted --strict-mcp-config --disable-slash-commands --permission-mode dontAsk --permission-prompts none --tools Read,Glob,Grep`, with Bash, PowerShell, WebFetch, WebSearch, and NotebookEdit denied. The model used Read, had no Write tool, and left both files unchanged. An outside read was denied by the restricted working-directory boundary.

The write recipe additionally exposed and allowed Edit and Write. The first run without `--allowedTools` denied even the inside write under `dontAsk`; exposing a tool with `--tools` does not grant it. With both flags, Write changed `workspace/inside.txt`. Write attempts at `../outside/new.txt` and `workspace/link-outside/via-link.txt` did not create either outside file. The tool transcript reported the direct and symlink paths as blocked; the independent file checks agreed. [Claude Code permission modes](https://code.claude.com/docs/zh-CN/agent-sdk/permissions).

| Claude recipe | Inside write | Outside new file | Symlink escape | Network tool |
| --- | --- | --- | --- | --- |
| Restricted read-only tools | Unavailable; file unchanged | Unavailable; file unchanged | Unavailable | Absent |
| Restricted Edit/Write tools with explicit allow rules | Succeeded | Denied; file absent | Denied; file absent | Absent |

No active network-capable tool was invoked, and managed, plugin, connector, and subagent surfaces were not exhaustively tested. The no-prompt flags were set, but an attempted permission escalation was not observed. The whole-invocation filesystem and network facts stay `unknown` until the exact launch recipe and remaining surfaces are tested.

## Pi and OpenCode

Neither CLI is installed, so no version-specific side-effect claim is possible here. Pi documents that its working folder is not a security boundary and its tools run with the process user's authority; `--tools read,grep,find,ls` replaces the built-in selection and is a candidate reviewer recipe only. [Pi security](https://pi.dev/docs/latest/security), [Pi CLI](https://pi.dev/docs/latest/cli).

OpenCode documents restrictive permission rules, but its shell runs with host filesystem and network authority and path inference is best effort. A future recipe must deny arbitrary shell and other egress paths before a workspace or network claim can be considered. [OpenCode permissions](https://opencode.ai/v2/docs/permissions).

## Promotion gate

Before changing any `unknown` to `enforceable`, run the actual agent launch with the exact settings AgentFlow will use. Verify inside writes, direct and symlink outside writes, network egress through every enabled tool surface, and an operation that requests more authority. Check side effects and the recorded tool/approval events. Repeat on each supported OS and installed version. Record the probe ID and launch mechanism in the plan; an unmatched version or platform remains `unknown`.
