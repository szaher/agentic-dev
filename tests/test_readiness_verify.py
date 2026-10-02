"""ready verify + CI integration (v0.15 slice 3): scope, exit codes, pinning, CI check."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parent))
from readiness_fixtures import materialize  # noqa: E402

from agentic_dev import __version__  # noqa: E402
from agentic_dev.readiness import assess, explain_repository, load_spec, plan  # noqa: E402
from agentic_dev.readiness.apply import run  # noqa: E402
from agentic_dev.readiness.evidence import ScopeError  # noqa: E402
from agentic_dev.readiness.remediation import CI_CHECK, CI_WORKFLOW, check_maintenance, propose  # noqa: E402
from agentic_dev.readiness.verify import verify  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
SPEC = load_spec()


def schema(name: str) -> dict:
    return json.loads((ROOT / "schemas" / f"{name}-v1.schema.json").read_text())


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                   check=True, capture_output=True)


def commit_all(root: Path, message: str = "update") -> None:
    git(root, "add", "-A")
    git(root, "commit", "-qm", message)


def snapshot(root: Path) -> dict[str, tuple]:
    state: dict[str, tuple] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            path = Path(dirpath) / name
            info = path.lstat()
            data = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() and not path.is_symlink() else None
            state[str(path.relative_to(root))] = (info.st_mode, info.st_size, info.st_mtime_ns, data)
    return state


class VerifyCase(unittest.TestCase):
    def setUp(self):
        self.dirs: list[Path] = []

    def tearDown(self):
        for path in self.dirs:
            shutil.rmtree(path, ignore_errors=True)

    def repo(self, scenario: str) -> Path:
        root = Path(tempfile.mkdtemp(prefix="ready-verify-"))
        self.dirs.append(root)
        return materialize(scenario, root)

    def status(self, root: Path, rule_id: str, scope: str) -> str:
        return next(r["status"] for r in assess(root, scope=scope)["requirements"] if r["id"] == rule_id)


class ScopeTests(VerifyCase):
    def test_git_excluded_local_instructions_are_not_ci_evidence(self):
        # What `agentic repo init` does: a local AGENTS.md excluded via .git/info/exclude.
        root = self.repo("no-agent-instructions")
        (root / "AGENTS.md").write_text("# Local Repository Context\n\n## Commands\n\n- Test: `uv run pytest`\n")
        with (root / ".git" / "info" / "exclude").open("a") as handle:
            handle.write("/AGENTS.md\n")
        self.assertEqual(self.status(root, "context.agent_instructions", "local"), "pass")
        self.assertEqual(self.status(root, "context.agent_instructions", "ci"), "fail")

        document = verify(root, target="structured")
        jsonschema.validate(document, schema("readiness-verification"))
        self.assertEqual((document["scope"], document["exit_code"], document["passed"]), ("ci", 1, False))
        self.assertIn("context.agent_instructions", [b["id"] for b in document["blockers"]])
        local = document["local"]
        diff = next(d for d in local["differences"] if d["rule_id"] == "context.agent_instructions")
        self.assertEqual((diff["local_status"], diff["ci_status"], diff["local_only_evidence"]),
                         ("pass", "fail", ["AGENTS.md"]))

    def test_tracked_evidence_counts_in_both_scopes(self):
        root = self.repo("structured-go")
        self.assertEqual(assess(root, scope="ci")["maturity"]["current"], "structured")
        document = verify(root, target="structured")
        self.assertEqual(document["exit_code"], 0)
        self.assertEqual(document["local"]["differences"], [])

    def test_untracked_command_sources_are_ignored_in_ci(self):
        root = self.repo("missing-tests")
        (root / "Makefile").write_text("test:\n\tpytest\n")
        self.assertEqual(self.status(root, "feedback.tests.available", "local"), "pass")
        self.assertEqual(self.status(root, "feedback.tests.available", "ci"), "fail")
        commit_all(root)
        self.assertEqual(self.status(root, "feedback.tests.available", "ci"), "pass")

    def test_every_document_reports_its_scope(self):
        root = self.repo("foundational-python")
        for scope in ("local", "ci"):
            with self.subTest(scope=scope):
                documents = {
                    "readiness-assessment": assess(root, scope=scope),
                    "readiness-explanation": explain_repository(root, scope=scope),
                    "readiness-plan": plan(root, scope=scope),
                }
                for name, document in documents.items():
                    jsonschema.validate(document, schema(name))
                    self.assertEqual(document["scope"], scope)
        remediation = propose(root)
        jsonschema.validate(remediation, schema("readiness-remediation"))
        self.assertEqual(remediation["scope"], "local")

    def test_ci_scope_needs_git(self):
        root = Path(tempfile.mkdtemp())
        self.dirs.append(root)
        (root / "README.md").write_text("# x\n")
        with self.assertRaisesRegex(ScopeError, "needs a Git repository"):
            verify(root, target="foundational")
        self.assertEqual(verify(root, target="unaware", scope="local")["exit_code"], 0)


class VerifyTests(VerifyCase):
    def test_exit_codes_and_pinning(self):
        root = self.repo("optimized-node")
        self.assertEqual(verify(root, target="optimized")["exit_code"], 0)
        self.assertEqual(verify(root, target="autonomous")["exit_code"], 1)
        pinned = verify(root, target="optimized", spec_version=SPEC.version, spec_sha256=SPEC.sha256.upper())
        self.assertEqual((pinned["exit_code"], pinned["pin"]["matched"]), (0, True))
        wrong_version = verify(root, target="optimized", spec_version="2.0.0")
        self.assertEqual(wrong_version["exit_code"], 3)
        self.assertIn("pinned spec version 2.0.0", wrong_version["pin"]["problems"][0])
        wrong_digest = verify(root, target="optimized", spec_sha256="0" * 64)
        self.assertEqual((wrong_digest["exit_code"], wrong_digest["passed"]), (3, False))
        # A pin mismatch wins even when the target would not be met.
        self.assertEqual(verify(root, target="autonomous", spec_version="2.0.0")["exit_code"], 3)

    def test_blockers_name_the_rules(self):
        root = self.repo("structured-go")
        document = verify(root, target="optimized")
        self.assertEqual([b["id"] for b in document["blockers"]],
                         ["constraints.architecture_boundaries", "context.task_workflows"])
        self.assertEqual(document["blockers"][0]["status"], "unknown")

    def test_regression_is_detectable(self):
        root = self.repo("structured-go")
        self.assertEqual(verify(root, target="structured")["exit_code"], 0)
        git(root, "rm", "-q", "AGENTS.md")
        git(root, "commit", "-qm", "drop agent instructions")
        regressed = verify(root, target="structured")
        self.assertEqual(regressed["exit_code"], 1)
        self.assertEqual(regressed["maturity"]["current"], "foundational")
        self.assertIn("context.agent_instructions", [b["id"] for b in regressed["blockers"]])

    def test_verify_is_read_only_and_deterministic(self):
        root = self.repo("ambiguous-policy")
        before = snapshot(root)
        first = verify(root, target="optimized")
        second = verify(root, target="optimized")
        self.assertEqual(snapshot(root), before)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertNotIn(str(root), json.dumps(first))


class CiCheckTests(VerifyCase):
    def test_ci_check_is_opt_in(self):
        root = self.repo("structured-go")
        document = propose(root)
        self.assertEqual((document["maintenance_actions"], document["maintenance_skipped"]), ([], []))

    def test_ci_check_guards_the_current_ci_visible_level(self):
        root = self.repo("structured-go")
        before = {r["id"]: r["status"] for r in assess(root)["requirements"]}
        document = run(root, maintenance=[CI_CHECK], dry_run=False)
        jsonschema.validate(document, schema("readiness-remediation"))
        self.assertEqual([a["id"] for a in document["maintenance_actions"]], [CI_CHECK])
        self.assertIn(CI_WORKFLOW, document["result"]["written"])
        workflow = (root / CI_WORKFLOW).read_text()
        self.assertIn(f"pip install agentic-dev=={__version__}", workflow)
        self.assertIn(f"agentic ready verify . --target structured --spec-version {SPEC.version} "
                      f"--spec-sha256 {SPEC.sha256}", workflow)
        self.assertIn("contents: read", workflow)
        # Maintenance never changes readiness, even after it is written.
        self.assertEqual({r["id"]: r["status"] for r in assess(root)["requirements"]}, before)
        commit_all(root, "add readiness check")
        self.assertEqual(verify(root, target="structured", spec_version=SPEC.version,
                                spec_sha256=SPEC.sha256)["exit_code"], 0)
        again = run(root, maintenance=[CI_CHECK], dry_run=False)
        self.assertEqual(again["result"]["status"], "no-op")

    def test_ci_check_passes_the_maintenance_guards(self):
        root = self.repo("optimized-node")
        document = propose(root, maintenance=[CI_CHECK])
        changes = {c["id"]: c for c in document["changes"]}
        check_maintenance(document["maintenance_actions"][0], changes, SPEC)

    def test_ci_check_is_skipped_when_there_is_nothing_to_protect(self):
        root = self.repo("missing-tests")
        document = propose(root, maintenance=[CI_CHECK])
        self.assertEqual(document["maintenance_actions"], [])
        self.assertEqual(document["maintenance_skipped"][0]["id"], CI_CHECK)
        self.assertIn("no level to protect", document["maintenance_skipped"][0]["reason"])


class VerifyCliTests(VerifyCase):
    def cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "AGENTIC_DEV_CONFIG_DIR": tempfile.mkdtemp()}
        return subprocess.run([sys.executable, "-m", "agentic_dev.cli", *args],
                              env=env, capture_output=True, text=True, check=False)

    def test_cli_exit_codes(self):
        root = self.repo("structured-go")
        met = self.cli("ready", "verify", str(root), "--target", "structured", "--json")
        self.assertEqual(met.returncode, 0, met.stderr)
        jsonschema.validate(json.loads(met.stdout), schema("readiness-verification"))
        not_met = self.cli("ready", "verify", str(root), "--target", "optimized")
        self.assertEqual(not_met.returncode, 1)
        self.assertIn("FAILED", not_met.stdout)
        self.assertIn("CI-visible readiness: Structured", not_met.stdout)
        pin = self.cli("ready", "verify", str(root), "--target", "structured", "--spec-sha256", "0" * 64)
        self.assertEqual(pin.returncode, 3)
        self.assertIn("SPEC PIN MISMATCH", pin.stdout)
        self.assertEqual(self.cli("ready", "verify", str(root)).returncode, 2)
        self.assertEqual(self.cli("ready", "verify", str(root), "--target", "legendary").returncode, 2)

    def test_cli_ci_check_flag(self):
        root = self.repo("structured-go")
        diff = self.cli("ready", "diff", str(root), "--ci-check")
        self.assertEqual(diff.returncode, 0, diff.stderr)
        self.assertIn(f"+++ b/{CI_WORKFLOW}", diff.stdout)
        self.assertIn("maintenance readiness.ci-check", diff.stdout)
        self.assertIn("Apply with: agentic ready apply <path> --target optimized --ci-check", diff.stdout)


if __name__ == "__main__":
    unittest.main()
