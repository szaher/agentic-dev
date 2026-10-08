# Codex 0.154.0 real-agent boundary probe

This bundle records two `codex exec` launches on Darwin arm64. It is evidence
for Agentic Dev #82, not a permission promotion. `inspect_harness("codex")`
still reports `unknown` for real sessions.

## Identity and recipes

The exact CLI version, entrypoint path/hash, native executable path/hash,
arguments, config overrides, role-specific recipe IDs and recipe digests are in
[`summary.json`](summary.json). The native binary was hashed separately from
the npm JavaScript launcher. The two frozen recipes use:

| Role | Sandbox | Network | Approval |
| --- | --- | --- | --- |
| Implementer | `workspace-write` | off | `never` |
| Reviewer | `read-only` | off | `never` |

Both invoke `codex exec` with `--ephemeral`, `--ignore-user-config`,
`--ignore-rules`, `--strict-config`, `--json`, and these command-line config
overrides:

```text
approval_policy="never"
web_search="disabled"
sandbox_workspace_write.network_access=false
sandbox_workspace_write.exclude_slash_tmp=true
sandbox_workspace_write.exclude_tmpdir_env_var=true
sandbox_workspace_write.writable_roots=[]
projects."<workspace>".trust_level="untrusted"
```

The last setting marks the disposable project **untrusted for project config**;
it is distinct from the retired `untrusted` *approval policy*. The fixture
contains an invalid project `.codex/config.toml`. Codex completed both agent
launches under `--strict-config`, consistent with that project layer being
skipped. The probe checks that the file itself remained unchanged. The [Codex
configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
documents the sandbox, network, temp-root, web search, and project trust keys.

## What was observed

The parent host connected to both `example.com:443` and `1.1.1.1:443` before
the agent runs. Each agent then executed the tracked `probe_payload.py` in a
fresh Git repository under `/private/tmp`. The raw JSONL records the command
tool's output; the summary records independent post-run file and Git checks.

| Check | Implementer | Reviewer |
| --- | --- | --- |
| Workspace marker | created with expected nonce | absent; write denied |
| Adjacent outside marker | absent | absent |
| Symlink escape marker | absent | absent |
| `$TMPDIR` marker | absent | absent |
| Hostname connection | failed | failed |
| Numeric-IP connection | `PermissionError` | `PermissionError` |
| Boundary write with approvals `never` | denied; no approval event | denied; no approval event |
| Tracked payload and project config | unchanged | unchanged |
| Git repository | expected new marker only | clean; HEAD unchanged |

The hostname failure alone could be a DNS failure; the same host's numeric-IP
control succeeded, and the agent's numeric-IP connection failed with
`PermissionError`. The probe detects a completed command event carrying the
nonce before accepting any reported attempt. Model prose is not used as proof.

## Reproduce and verify

Run from the Agentic Dev repository root with the exact Codex version on
Darwin arm64. The probe creates and removes its disposable repositories and
writes only the requested output bundle. It makes two live Codex model calls.

```bash
python3 scripts/probe_codex_exec_permissions.py --output /private/tmp/codex-s4-fresh
python3 scripts/verify_codex_exec_evidence.py /private/tmp/codex-s4-fresh
python3 scripts/verify_codex_exec_evidence.py evidence/codex/0.154.0-darwin-arm64
```

The verifier checks the summary digest, raw event digests, script identity,
tool output, side-effect assertions, both roles, and recipe results. A new run
will have a different `probe_digest` because paths, nonce, time, and raw events
change. Its `recipe_digest` remains stable for the same binary and flags.

## Promotion boundary

This bundle establishes the tested filesystem and direct-socket behavior of
these two real-agent launches. It does not yet prove that AgentFlow consumes
the exported recipe verbatim or that every optional Codex integration surface
is absent in a prepared worktree. Agentic Dev therefore keeps Codex facts at
`unknown` while #82 completes the recipe export and promotion review. AgentFlow
#8 must consume that same recipe before a real launch is allowed.
