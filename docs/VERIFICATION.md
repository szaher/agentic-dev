# Change-aware verification

The verification planner chooses a small defensible set of checks from the actual change rather than blindly running every repository command.

## Plan

```bash
agentic verify
agentic verify --json

agentic verify plan --path .
agentic verify plan --path . --base main --json
```

The plan uses:

- Git changed files, including working-tree and untracked files;
- the stable repository inspection contract;
- detected lint/typecheck/test/build commands;
- changed language/file categories;
- CodeGraph `affected` when a local graph exists;
- optional CodeGraph symbol impact via repeated `--symbol`;
- enabled security capabilities.

Example:

```bash
agentic verify plan \
  --base main \
  --symbol TrainingReconciler \
  --json
```

## CodeGraph

If `.codegraph/` exists and the CLI is installed, the planner invokes:

```text
codegraph affected <changed-files...> --json
```

Affected test paths are preserved as selection evidence. The planner does not invent test-runner arguments for those paths because repositories differ in how focused test execution is expressed.

For explicit symbols:

```text
codegraph impact <symbol> --json
```

is included in the plan's impact section.

## Serena

Serena availability is recorded in the plan. Serena's semantic reference operations are agent/MCP-facing; the CLI planner does not pretend there is a batch reference CLI that does not exist. Agents can use Serena interactively to refine the plan, while AgentFlow can consume the deterministic plan document.

## Security checks

If security capabilities are enabled, relevant checks join the plan:

- `secret-scan` for changed files;
- `sast` for source changes;
- `iac-misconfiguration` for IaC/config changes;
- `sbom` for package/build metadata changes.

They retain their trust-profile enforcement when executed.

## Run

```bash
agentic verify run .                     # change-aware
agentic verify run . --json
agentic verify run . --kind test --kind lint   # full-project: every discovered command of each kind
agentic verify run . --command "make e2e"      # explicit command, executed by Agentic Dev
agentic verify run . --kind test --include-changed   # full baseline + change-aware additions
```

`status` is `passed`, `failed`, or `no-checks`. A requested kind with no discovered
command, or a run that executes nothing, is `no-checks` with `success: false` and
exit 1: zero checks is never success. Change-aware checks can only add to a full
baseline, never remove from it. See [API.md](API.md#verification-run).

Execution is fail-fast by default.

To gather all results:

```bash
agentic verify run --continue-on-failure --json
```

Every deterministic command produces normalized stdout/stderr/return-code evidence. Security checks preserve their own normalized capability result.

## AgentFlow boundary

`agentic-dev` determines what checks are relevant and can execute them. AgentFlow decides which checks are mandatory workflow gates, whether evidence is fresh enough, whether a retry is allowed, and whether human/reviewer approval is required.
