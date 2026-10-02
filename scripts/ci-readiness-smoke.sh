#!/usr/bin/env bash
# Prove an installed agentic-dev artifact (wheel or sdist) can assess a
# repository with its packaged Agent Ready spec, without any source-tree paths.
#
#   scripts/ci-readiness-smoke.sh /path/to/installed/bin/agentic
set -Eeuo pipefail

agentic="$1"
source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

python3 "$source_root/tests/readiness_fixtures.py" materialize optimized-node "$work/fixture" >/dev/null
python3 "$source_root/tests/readiness_fixtures.py" materialize ambiguous-policy "$work/policy" >/dev/null

# Run from an unrelated directory so nothing can resolve from the checkout.
cd "$work"
"$agentic" ready assess "$work/fixture" --json > assess.json
"$agentic" ready assess "$work/fixture" > assess.txt
"$agentic" ready explain "$work/fixture" > explain.txt
"$agentic" ready explain feedback.tests.available --path "$work/fixture" > rule.txt
"$agentic" ready plan "$work/fixture" > plan.txt
"$agentic" ready plan "$work/policy" --target optimized --json > plan.json
pin_sha="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sha256"])' "$source_root/src/agentic_dev/readiness/specs/PIN.json")"
"$agentic" ready verify "$work/fixture" --target optimized --spec-sha256 "$pin_sha" --json > verify.json
set +e
"$agentic" ready verify "$work/fixture" --target autonomous > /dev/null; not_met=$?
"$agentic" ready verify "$work/fixture" --target optimized --spec-version 0.0.0 > /dev/null; mismatch=$?
set -e
[[ "$not_met" == 1 && "$mismatch" == 3 ]] || { echo "unexpected verify exit codes: $not_met $mismatch" >&2; exit 1; }

python3 - "$source_root" "$work" <<'PY'
import json, sys
from pathlib import Path
import jsonschema

root = Path(sys.argv[1])
schema = lambda name: json.loads((root / "schemas" / f"{name}-v1.schema.json").read_text())

assessment = json.loads(Path("assess.json").read_text())
jsonschema.validate(assessment, schema("readiness-assessment"))
pin = json.loads((root / "src/agentic_dev/readiness/specs/PIN.json").read_text())
assert assessment["spec"] == {"name": "agent-ready", "version": pin["spec_version"],
                              "sha256": pin["sha256"], "source": "builtin"}, assessment["spec"]
assert assessment["maturity"]["current"] == "optimized", assessment["maturity"]
for name in ("assess.json", "plan.json", "verify.json", "assess.txt", "explain.txt", "rule.txt", "plan.txt"):
    assert sys.argv[2] not in Path(name).read_text(), f"absolute path leaked into {name}"

plan = json.loads(Path("plan.json").read_text())
jsonschema.validate(plan, schema("readiness-plan"))
assert [(s["id"], s["status"]) for s in plan["steps"]] == [("constraints.architecture_boundaries", "unknown")]

verification = json.loads(Path("verify.json").read_text())
jsonschema.validate(verification, schema("readiness-verification"))
assert (verification["scope"], verification["exit_code"], verification["pin"]["matched"]) == ("ci", 0, True)

assert "Maturity: Optimized" in Path("assess.txt").read_text()
assert "Why fixture is Optimized" in Path("explain.txt").read_text()
assert "Runnable test suite" in Path("rule.txt").read_text()
assert "read-only; nothing was modified" in Path("plan.txt").read_text()
print(f"readiness smoke ok: spec {pin['spec_version']} sha256 {pin['sha256'][:12]}")
PY
