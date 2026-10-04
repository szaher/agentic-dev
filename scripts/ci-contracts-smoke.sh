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
# AgentFlow pattern requirements (slice 4): local readiness, metrics, kinds plus custom commands.
expect_exit 1 "$work/out/readiness-verification.json" -- "$agentic" ready verify . --target foundational --scope local --json
"$agentic" metrics record agentflow.stage --field stage=verify --field outcome=passed --json > "$work/out/metric-record-disabled.json"
"$agentic" metrics enable > /dev/null
"$agentic" metrics record agentflow.stage --field stage=verify --field outcome=passed --session-id run-1 --json > "$work/out/metric-record.json"
expect_exit 0 "$work/out/verification-run-mixed.json" -- "$agentic" verify run . --kind test --command true --json
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

# Provider bootstrap (AgentFlow's agentflow-sdlc path): inspect, pinned install, list, activate.
prov="$work/provider"
mkdir -p "$prov/skills/smoke-sdlc"
printf -- '---\nname: smoke-sdlc\ndescription: Smoke skill.\n---\n\n# Smoke\n' > "$prov/skills/smoke-sdlc/SKILL.md"
printf '{"schema_version":"1","name":"smoke-flow","version":"1.0.0","description":"Smoke provider","skills":[{"name":"smoke-sdlc","description":"Smoke skill.","category":"workflow","path":"skills/smoke-sdlc"}]}\n' > "$prov/agentic-provider.json"
"$agentic" providers inspect "$prov" --json > "$work/out/provider-source.json"
digest="$("$python" -c 'import json,sys; print(json.load(open(sys.argv[1]))["content_digest"])' "$work/out/provider-source.json")"
"$agentic" providers add "$prov" --sha256 "$digest" --json > "$work/out/provider-install.json"
"$agentic" providers list --json > "$work/out/providers.json"
"$agentic" skills add smoke-sdlc --target all --shared --dry-run --json > "$work/out/skills-activation-preview.json"
test ! -e "$repo/.claude/skills/smoke-sdlc" && test ! -e "$repo/.agentic/skills.json"
"$agentic" skills add smoke-sdlc --target all --shared --json > "$work/out/skills-activation.json"

# S1: exercise the installed parser and planner, including a fail-closed real harness.
mkdir -p "$repo/.agentic"
printf 'schema_version = "1"\ndocument_type = "agentic.repository-profile"\npreferred_harness = "codex"\n[permissions.implementer]\nfilesystem = "workspace-write"\nnetwork = "off"\n' > "$repo/.agentic/profile.toml"
printf '{"schema_version":"1","document_type":"agentic.session-request","task":"Fix a failing test","invocations":[{"id":"implement","role":"implementer","harness":"codex"}],"verification_kinds":["test"]}\n' > "$work/out/session-request.json"
expect_exit 1 "$work/out/session-plan.json" -- "$agentic" session plan --request "$work/out/session-request.json" --path "$repo" --json
# Resolve the executable's installed Python environment, including uv tool links.
"$python" - "$agentic" "$repo" "$work/out/repository-profile.json" <<'PY'
import subprocess, sys
from pathlib import Path

installed_python = Path(sys.argv[1]).resolve().parent / "python"
assert installed_python.is_file(), installed_python
result = subprocess.run(
    [str(installed_python), "-I", "-c",
     "import json,sys; from agentic_dev.session import load_profile; print(json.dumps(load_profile(sys.argv[1])))",
     sys.argv[2]],
    check=True, capture_output=True, text=True,
)
Path(sys.argv[3]).write_text(result.stdout)
PY

# S2: use the installed interpreter and an isolated linked worktree to produce
# a positive record. Synthetic enforcement exists only inside this test seam;
# the public CLI remains fail closed for actual harness observations.
"$python" - "$agentic" "$work" <<'PY'
import subprocess, sys
from pathlib import Path

installed_python = Path(sys.argv[1]).resolve().parent / "python"
work = Path(sys.argv[2])
result = subprocess.run(
    [str(installed_python), "-I", "-c", r'''
import json, subprocess, sys
from pathlib import Path
from agentic_dev.session import plan_session
from agentic_dev.session_prepare import prepare_session

work = Path(sys.argv[1])
source, workspace = work / "s2-repo", work / "s2-worktree"
source.mkdir()
(source / "README.md").write_text("# Python project\n")
subprocess.run(["git", "init", "-q", str(source)], check=True)
subprocess.run(["git", "-C", str(source), "add", "README.md"], check=True)
subprocess.run(["git", "-C", str(source), "-c", "user.name=Test", "-c",
                "user.email=test@example.invalid", "commit", "-qm", "init"], check=True)
request = {"schema_version":"1", "document_type":"agentic.session-request",
           "task":"Fix a Python bug", "required_skills":["python-engineering"],
           "invocations":[{"id":"implement", "role":"implementer", "harness":"codex"}]}
facts = {"codex":{"name":"codex", "available":True, "executable":"/test/codex", "version":"test-1.0",
         "permissions":{dimension:{level:{"status":"enforceable", "mechanism":"test fixture", "evidence":"test fixture"}
                  for level in levels} for dimension,levels in
                  (("filesystem",("read-only","workspace-write")),("network",("off","on")))}}}
plan = plan_session(source, request, harness_facts=facts)
assert plan["status"] == "ready", plan["blockers"]
subprocess.run(["git", "-C", str(source), "worktree", "add", "-q", "-b", "s2-smoke",
                str(workspace)], check=True)
blocked = plan_session(source, request)
assert blocked["status"] == "blocked", blocked
blocked_file = work / "blocked-s2-plan.json"
blocked_file.write_text(json.dumps(blocked))
rejected = subprocess.run([str(Path(sys.executable).parent / "agentic"), "session", "prepare",
                           "--plan", str(blocked_file), "--path", str(workspace), "--json"],
                          capture_output=True, text=True, check=False)
assert rejected.returncode == 1, (rejected.returncode, rejected.stderr)
assert not (workspace / ".codex").exists()
record = prepare_session(plan, workspace, harness_facts=facts)
(work / "out" / "session-record.json").write_text(json.dumps(record))
assert subprocess.check_output(["git", "-C", str(workspace), "status", "--porcelain"],
                               text=True) == ""
''', str(work)],
    check=True, capture_output=True, text=True,
)
PY

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
                "worktree.lifecycle", "instructions.managed-block", "skills.activation-dry-run",
                "metrics.record-report", "readiness.scope-ci"):
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

assert documents["readiness-verification"]["scope"] == "local"
assert (documents["metric-record-disabled"]["recorded"], documents["metric-record"]["recorded"]) == (False, True)
mixed = documents["verification-run-mixed"]
assert sorted(r["command"] for r in mixed["results"]) == ["make check", "true"], mixed

assert documents["instruction-block"]["status"] == "created"
assert documents["instruction-block-again"]["status"] == "unchanged"
assert documents["instruction-block-removed"]["status"] == "removed"
assert documents["worktree"]["branch"] == "agentic/run-1"
installed = documents["providers"]["providers"][0]
assert (installed["content_digest"], installed["verified"]) == (documents["provider-source"]["content_digest"], True)
preview = documents["skills-activation-preview"]
assert (preview["dry_run"], preview["status"]) == (True, "ok"), preview
assert preview["outcomes"] == documents["skills-activation"]["outcomes"]
assert {o["status"] for o in documents["skills-activation"]["outcomes"]} == {"written"}
request = documents["session-request"]
profile = documents["repository-profile"]
session = documents["session-plan"]
assert len([item for item in request["invocations"] if item["role"] == "implementer"]) == 1
assert profile["preferred_harness"] == "codex"
assert session["status"] == "blocked" and session["blockers"]
assert any(item["code"] == "permission-unenforceable" for item in session["blockers"])
assert all(permission["enforceable"] == "unknown" for invocation in session["invocations"]
           for permission in invocation["permissions"].values())
assert {item["name"] for item in session["tools"]} == {"serena", "codegraph"}
record = documents["session-record"]
assert record["status"] == "prepared" and record["prepared"]["git_excluded"]
assert record["prepared"]["skill_paths"]
print(f"contracts smoke: {len(documents)} documents validated against installed schemas")
PY
