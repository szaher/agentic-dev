#!/usr/bin/env bash
# Prove the contracts AgentFlow consumes work from an installed agentic-dev
# artifact (wheel or sdist). Every document is validated against the schema the
# *installed* package ships (`agentic contracts schema NAME`), never the source tree.
#
#   scripts/ci-contracts-smoke.sh /path/to/installed/bin/agentic
#
# PYTHON must be an interpreter with jsonschema (default: python3).
set -Eeuo pipefail

agentic="$1"
python="${PYTHON:-python3}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
export AGENTIC_DEV_CONFIG_DIR="$work/config" AGENTIC_WORKTREE_ROOT="$work/worktrees"

fail() { echo "contracts smoke: $*" >&2; exit 1; }
expect_exit() { # expect_exit CODE OUTFILE -- command...
  local want="$1" out="$2"; shift 3
  set +e; "$@" > "$out"; local got=$?; set -e
  [[ "$got" == "$want" ]] || fail "exit $got, expected $want: $*"
}

# A repository whose only test entry point is `make check` (audit R4).
repo="$work/repo"
git init -q "$repo"
printf '# Demo\n' > "$repo/README.md"
printf 'print(1)\n' > "$repo/app.py"
printf 'check:\n\ttouch ran-make-check\n' > "$repo/Makefile"
git -C "$repo" add -A
git -C "$repo" -c user.name=t -c user.email=t@example.invalid commit -qm init

cd "$work"  # nothing may resolve from a source checkout
mkdir schemas out
"$agentic" contracts --json > out/contracts.json
for name in $("$python" -c 'import json,sys; print(" ".join(json.load(open(sys.argv[1]))["contracts"]))' out/contracts.json); do
  "$agentic" contracts schema "$name" > "schemas/$name.json"
done

cd "$repo"
"$agentic" repo inspect --json > "$work/out/repo-inspection.json"
"$agentic" ready assess . --json > "$work/out/readiness-assessment.json"
expect_exit 0 "$work/out/verification-run.json" -- "$agentic" verify run . --kind test --json
[[ -f ran-make-check ]] || fail "verify run --kind test did not run make check"
expect_exit 1 "$work/out/verification-run-missing.json" -- "$agentic" verify run . --kind typecheck --json
"$agentic" capabilities status --json > "$work/out/capability-status.json"
"$agentic" worktree create run-1 --agent agentflow --json > "$work/out/worktree.json"
"$agentic" worktree list --json > "$work/out/worktree-list.json"
"$agentic" worktree status run-1 --json > "$work/out/worktree-status.json"
"$agentic" worktree clean run-1 --json > "$work/out/worktree-clean.json"
block=(--file AGENTS.md --owner agentflow --id workflow)
printf '## AgentFlow\n\nRun `agentflow status`.\n' \
  | "$agentic" instructions block put "${block[@]}" --content-file - --json > "$work/out/instruction-block.json"
printf '## AgentFlow\n\nRun `agentflow status`.\n' \
  | "$agentic" instructions block put "${block[@]}" --content-file - --json > "$work/out/instruction-block-again.json"
"$agentic" instructions block list --json > "$work/out/instruction-block-list.json"
"$agentic" instructions block remove "${block[@]}" --json > "$work/out/instruction-block-removed.json"

"$python" - "$work" <<'PY'
import json, sys
from pathlib import Path
import jsonschema

work = Path(sys.argv[1])
schemas = {p.stem: json.loads(p.read_text()) for p in (work / "schemas").glob("*.json")}
documents = {p.stem: json.loads(p.read_text()) for p in (work / "out").glob("*.json")}
contract_of = lambda name: next(c for c in sorted(schemas, key=len, reverse=True) if name.startswith(c))
for name, document in sorted(documents.items()):
    jsonschema.validate(document, schemas[contract_of(name)])

contracts = documents["contracts"]
for feature in ("commands.canonical-discovery", "verification.full-kind-filter", "verification.no-checks-status",
                "worktree.lifecycle", "instructions.managed-block"):
    assert feature in contracts["features"], feature

# R4: one discoverer; all three consumers agree on `make check`.
inspection = documents["repo-inspection"]
assert inspection["commands"]["test"] == ["make check"], inspection["commands"]
assert {"kind": "test", "command": "make check", "source": "Makefile"} in inspection["discovered_commands"]
tests = next(r for r in documents["readiness-assessment"]["requirements"] if r["id"] == "feedback.tests.available")
assert [e["value"] for e in tests["evidence"]] == ["make check"], tests
run = documents["verification-run"]
assert (run["status"], [r["command"] for r in run["results"]]) == ("passed", ["make check"]), run
missing = documents["verification-run-missing"]
assert (missing["status"], missing["success"], missing["missing_kinds"]) == ("no-checks", False, ["typecheck"])

assert documents["instruction-block"]["status"] == "created"
assert documents["instruction-block-again"]["status"] == "unchanged"
assert documents["instruction-block-removed"]["status"] == "removed"
assert documents["worktree"]["branch"] == "agentic/run-1"
print(f"contracts smoke: {len(documents)} documents validated against installed schemas")
PY
