"""ready make --target (v0.15 slice 4): rounds, stopping on decisions, dry run."""

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
from unittest.mock import patch

import jsonschema

sys.path.insert(0, str(Path(__file__).resolve().parent))
from readiness_fixtures import materialize  # noqa: E402

from agentic_dev.readiness import apply as apply_module  # noqa: E402
from agentic_dev.readiness import assess  # noqa: E402
from agentic_dev.readiness import make as make_module  # noqa: E402
from agentic_dev.readiness.make import make  # noqa: E402
from agentic_dev.readiness.spec import SpecError  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas" / "readiness-make-v1.schema.json").read_text())


def snapshot(root: Path) -> dict[str, tuple]:
    state: dict[str, tuple] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            path = Path(dirpath) / name
            info = path.lstat()
            data = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() and not path.is_symlink() else None
            state[str(path.relative_to(root))] = (info.st_mode, info.st_size, info.st_mtime_ns, data)
    return state


def sandboxes() -> set[str]:
    return {name for name in os.listdir(tempfile.gettempdir()) if name.startswith("agentic-ready-make-")}


class MakeCase(unittest.TestCase):
    def setUp(self):
        self.dirs: list[Path] = []

    def tearDown(self):
        for path in self.dirs:
            shutil.rmtree(path, ignore_errors=True)

    def repo(self, scenario: str) -> Path:
        root = Path(tempfile.mkdtemp(prefix="ready-make-"))
        self.dirs.append(root)
        return materialize(scenario, root)

    def reachable(self) -> Path:
        """Structured except for two safely fixable rules: commands and .env ignore."""

        root = self.repo("structured-go")
        agents = (root / "AGENTS.md").read_text()
        start = agents.index("## Commands")
        (root / "AGENTS.md").write_text(agents[:start] + agents[agents.index("## Architecture"):])
        (root / ".gitignore").unlink()
        subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                        "commit", "-qam", "drop commands and gitignore"], check=True)
        return root


class MakeTests(MakeCase):
    def test_reaches_the_target_with_safe_changes_only(self):
        root = self.reachable()
        self.assertEqual(assess(root)["maturity"]["current"], "foundational")
        document = make(root, target="structured")
        jsonschema.validate(document, SCHEMA)
        self.assertEqual((document["status"], document["exit_code"]), ("target-met", 0))
        self.assertEqual(document["maturity"]["before"], "foundational")
        self.assertEqual(document["maturity"]["after"], "structured")
        self.assertEqual(document["written"], [".gitignore", "AGENTS.md"])
        self.assertEqual(document["uncommitted"], [".gitignore"])
        self.assertEqual(document["maturity"]["ci_visible"], "foundational")  # not committed yet
        self.assertEqual(len(document["rounds"]), 1)
        self.assertIn("## Do NOT", (root / "AGENTS.md").read_text())  # existing content preserved

    def test_stops_on_human_decisions_instead_of_guessing(self):
        root = self.repo("foundational-python")
        before = {r["id"]: r["status"] for r in assess(root)["requirements"]}
        document = make(root, target="structured")
        jsonschema.validate(document, SCHEMA)
        self.assertEqual((document["status"], document["exit_code"]), ("needs-decision", 4))
        self.assertEqual([r["status"] for r in document["rounds"]], ["applied", "no-op"])
        decisions = {item["rule_id"]: item for item in document["remaining"]["human_decision"]}
        self.assertTrue({"conventions.documented", "constraints.documented", "feedback.typecheck"} <= set(decisions))
        self.assertIn("[tool.ruff]", [c["value"] for c in decisions["conventions.documented"]["candidates"]])
        after = {r["id"]: r["status"] for r in assess(root)["requirements"]}
        for rule_id in decisions:
            self.assertEqual(after[rule_id], before[rule_id], rule_id)
        for rel in document["written"]:
            self.assertIn("agentic-dev:begin", (root / rel).read_text())

    def test_target_already_met_changes_nothing(self):
        root = self.repo("optimized-node")
        before = snapshot(root)
        document = make(root, target="structured")
        self.assertEqual((document["status"], document["exit_code"], document["rounds"]), ("target-met", 0, []))
        self.assertEqual(snapshot(root), before)

    def test_dry_run_previews_the_whole_run_without_touching_anything(self):
        root = self.reachable()
        before, leftover = snapshot(root), sandboxes()
        document = make(root, target="structured", dry_run=True)
        jsonschema.validate(document, SCHEMA)
        self.assertEqual(snapshot(root), before)
        self.assertEqual(sandboxes(), leftover)
        self.assertTrue(document["dry_run"])
        self.assertEqual((document["status"], document["maturity"]["after"]), ("target-met", "structured"))
        self.assertTrue(any("+++ b/AGENTS.md" in diff for diff in document["diffs"]))
        self.assertTrue(any(diff.startswith("--- /dev/null\n+++ b/.gitignore") for diff in document["diffs"]))
        text = json.dumps(document)
        self.assertNotIn("agentic-ready-make-", text)
        self.assertNotIn(str(root), text)
        self.assertEqual(document["repository"]["name"], root.name)

    def test_conflict_stops_without_writing(self):
        root = self.repo("foundational-python")
        make(root, target="structured")
        agents = root / "AGENTS.md"
        agents.write_text(agents.read_text().replace("- Test:", "- Tests:"))
        (root / "Makefile").write_text("typecheck:\n\tmypy src\n")
        (root / ".gitignore").unlink()
        before = snapshot(root)
        document = make(root, target="structured")
        self.assertEqual((document["status"], document["exit_code"]), ("conflict", 1))
        self.assertEqual(snapshot(root), before)

    def test_failed_write_rolls_back(self):
        root = self.repo("foundational-python")
        before = snapshot(root)

        def broken(path, text, mode):
            raise OSError("read-only filesystem")

        with patch.object(apply_module, "_write_atomic", broken):
            document = make(root, target="structured")
        self.assertEqual((document["status"], document["exit_code"]), ("rolled-back", 3))
        self.assertIn("rolled back", document["error"])
        self.assertEqual({k: v[3] for k, v in snapshot(root).items()}, {k: v[3] for k, v in before.items()})

    def test_rounds_are_bounded(self):
        root = self.repo("foundational-python")
        real = make_module.apply_run

        def always_progress(*args, **kwargs):
            document = real(*args, **{**kwargs, "dry_run": True})
            document["result"]["status"] = "applied"
            return document

        with patch.object(make_module, "apply_run", always_progress):
            document = make(root, target="structured", max_rounds=2)
        self.assertEqual((document["status"], document["exit_code"], len(document["rounds"])), ("round-limit", 4, 2))
        with self.assertRaises(SpecError):
            make(root, target="structured", max_rounds=0)


class MakeCliTests(MakeCase):
    def cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "AGENTIC_DEV_CONFIG_DIR": tempfile.mkdtemp()}
        return subprocess.run([sys.executable, "-m", "agentic_dev.cli", *args],
                              env=env, capture_output=True, text=True, check=False)

    def test_exit_codes(self):
        root = self.reachable()
        dry = self.cli("ready", "make", str(root), "--target", "structured", "--dry-run")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn("target met — dry run, nothing was written", dry.stdout)
        met = self.cli("ready", "make", str(root), "--target", "structured", "--json")
        self.assertEqual(met.returncode, 0, met.stderr)
        jsonschema.validate(json.loads(met.stdout), SCHEMA)
        stopped = self.cli("ready", "make", str(root), "--target", "optimized")
        self.assertEqual(stopped.returncode, 4)
        self.assertIn("Needs a human decision (make never guesses these)", stopped.stdout)
        self.assertEqual(self.cli("ready", "make", str(root)).returncode, 2)
        self.assertEqual(self.cli("ready", "make", str(root), "--target", "legendary").returncode, 2)


if __name__ == "__main__":
    unittest.main()
