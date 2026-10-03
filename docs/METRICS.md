# Measurement and evaluation

Measurement is **local and disabled by default**.

`agentic-dev` does not send telemetry to a server. Enabling metrics writes structured JSONL events to the local agentic-dev configuration directory. Export is explicit and file-only.

## Enable

```bash
agentic metrics status
agentic metrics enable
```

Disable without deleting existing events:

```bash
agentic metrics disable
```

Delete local events:

```bash
agentic metrics clear --yes
```

## What the core measures

When metrics are enabled, agentic-dev automatically records narrow outcome events for:

- execution backend calls: backend, tool name, success/failure, return code, duration, command hash;
- verification checks and total verification duration;
- change size from Git diff numstat;
- CodeGraph availability/usefulness during verification;
- worktree session start/end;
- skill recommendation counts and activations;
- capability recommendation counts, enablement, and run outcomes.

Raw command strings, stdout, stderr, repository absolute paths, task text, passwords, tokens, cookies, authorization headers, and private-key contents are not written to metric events by the built-in instrumentation.

Repository identity is stored as:

- repository basename;
- a short SHA-256-derived local identifier.

## Summary

```bash
agentic metrics summary --json
agentic metrics summary --since 7d --json
agentic metrics summary --path . --since 24h
```

The summary reports:

- execution count and failure rate;
- average execution duration;
- tool calls per session/task;
- retries;
- verification pass rate and total/average duration;
- time to first passing focused test;
- change insertions/deletions;
- reverted-edit count;
- skill recommendation uptake;
- capability recommendation uptake;
- context-source use/usefulness;
- AgentFlow stage outcomes.

## AgentFlow and agent integration events

AgentFlow, Claude/Codex/Pi adapters, or other local integrations can add structured events:

```bash
agentic metrics record agentflow.stage \
  --session-id run-123 \
  --field stage=review \
  --field outcome=passed

agentic metrics record retry \
  --session-id run-123 \
  --field reason=test-failure

agentic metrics record tool.call \
  --session-id run-123 \
  --field tool=serena \
  --field success=true

agentic metrics record context.used \
  --session-id run-123 \
  --field source=context7 \
  --field useful=true

agentic metrics record change.reverted \
  --session-id run-123 \
  --field count=1
```

Use `--path .` when the event should be associated with a repository.

Metric field names containing secret-like terms such as `token`, `password`, `authorization`, `cookie`, `api_key`, `private_key`, or `credential` are automatically redacted. Integrations should still avoid placing sensitive values in arbitrary non-sensitive field names.

## Context-tool usefulness

CodeGraph use during the built-in verification planner is measured automatically when available.

Serena, Context7, Claude/Codex/Pi native tool calls happen outside the agentic-dev process. Those integrations can report:

```text
tool.call
context.used
```

events through the generic local event interface.

This keeps the core agent-neutral instead of inventing unsupported hooks into each agent.

## Export

Export stays local:

```bash
agentic metrics export \
  --output ./agentic-metrics.jsonl \
  --format jsonl \
  --since 7d
```

or:

```bash
agentic metrics export \
  --output ./agentic-metrics.json \
  --format json
```

There is intentionally no network-export option.

The event schema is:

```text
src/agentic_dev/schemas/metric-event-v1.schema.json
```

## Event storage

Default location:

```text
~/.config/agentic-dev/metrics/
├── settings.json
└── events.jsonl
```

The location follows `AGENTIC_DEV_CONFIG_DIR` when set.

## Evaluation use

The data is intended for local A/B comparison of coding-agent workflows, for example:

- Serena + CodeGraph versus plain text search;
- focused verification versus full-suite verification;
- one coding harness versus another;
- a skill recommendation enabled versus skipped;
- AgentFlow pattern/stage outcomes.

The metrics layer measures outcomes. It does not decide whether a workflow is acceptable; AgentFlow remains responsible for workflow/evidence policy.
