from __future__ import annotations

import json
import os
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jsonschema

from agentic_dev.verification import execute, full_plan, plan


ROOT = Path(__file__).resolve().parents[1]


class VerificationPlannerTests(unittest.TestCase):
    def repo(self) -> Path:
        root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        (root / "pyproject.toml").write_text(
            """[project]
name = "demo"
version = "0.1.0"
dependencies = ["pytest"]

[tool.ruff]
line-length = 100

[tool.pyright]
"""
        )
        (root / "main.py").write_text("value = 1\n")
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run([
            "git", "-C", str(root),
            "-c", "user.name=Agentic Test",
            "-c", "user.email=agentic@example.invalid",
            "commit", "-qm", "init",
        ], check=True)
        return root

    def schema(self) -> dict:
        return json.loads((ROOT / "schemas/verification-plan-v1.schema.json").read_text())

    @patch("agentic_dev.verification.shutil.which", return_value=None)
    def test_source_change_selects_repo_native_checks(self, which):
        root = self.repo()
        (root / "main.py").write_text("value = 2\n")
        with tempfile.TemporaryDirectory() as config:
            with patch.dict(os.environ, {"AGENTIC_DEV_CONFIG_DIR": config}):
                result = plan(root)

        jsonschema.validate(result, self.schema())
        commands = {item.get("command") for item in result["checks"]}
        self.assertIn("uv run pytest", commands)
        self.assertIn("uv run ruff check .", commands)
        self.assertIn("uv run pyright", commands)
        self.assertEqual(result["changed_languages"], ["python"])

    @patch("agentic_dev.verification.shutil.which", return_value=None)
    def test_docs_only_change_skips_code_checks(self, which):
        root = self.repo()
        (root / "README.md").write_text("changed docs\n")
        subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)
        # untracked/working changes are intentionally part of the plan.
        with tempfile.TemporaryDirectory() as config:
            with patch.dict(os.environ, {"AGENTIC_DEV_CONFIG_DIR": config}):
                result = plan(root)
        self.assertEqual(result["checks"], [])
        self.assertTrue(result["skipped_checks"])

    @patch("agentic_dev.verification.capability_status")
    @patch("agentic_dev.verification.shutil.which", return_value=None)
    def test_enabled_security_checks_join_plan(self, which, capability_state):
        capability_state.return_value = {
            "secret-scan": {"enabled": True},
            "sast": {"enabled": True},
            "dependency-vulnerability": {"enabled": False},
            "iac-misconfiguration": {"enabled": False},
            "sbom": {"enabled": False},
        }
        root = self.repo()
        (root / "main.py").write_text("value = 3\n")
        result = plan(root)
        caps = {item.get("capability") for item in result["checks"] if item["kind"] == "security"}
        self.assertEqual(caps, {"secret-scan", "sast"})

    @patch("agentic_dev.verification._codegraph_affected")
    @patch("agentic_dev.verification.shutil.which", return_value=None)
    def test_codegraph_affected_test_is_preserved_as_evidence(self, which, affected):
        affected.return_value = {
            "available": True,
            "tests": ["tests/test_main.py"],
            "raw": {"tests": ["tests/test_main.py"]},
        }
        root = self.repo()
        (root / "main.py").write_text("value = 4\n")
        result = plan(root)
        evidence = [x for x in result["checks"] if x["kind"] == "affected-test"]
        self.assertEqual(evidence[0]["test_file"], "tests/test_main.py")
        self.assertIsNone(evidence[0]["command"])

    def test_execute_is_fail_fast_by_default(self):
        root = self.repo()
        verification_plan = {
            "repository": str(root),
            "checks": [
                {"kind": "test", "command": "printf first", "reason": "test"},
                {"kind": "test", "command": "exit 7", "reason": "test"},
                {"kind": "test", "command": "printf never", "reason": "test"},
            ],
        }
        result = execute(verification_plan)
        self.assertFalse(result["success"])
        self.assertEqual(len(result["results"]), 2)
        self.assertTrue(result["results"][0]["success"])
        self.assertFalse(result["results"][1]["success"])

    def test_execute_continue_on_failure(self):
        root = self.repo()
        verification_plan = {
            "repository": str(root),
            "checks": [
                {"kind": "test", "command": "exit 7", "reason": "test"},
                {"kind": "test", "command": "printf later", "reason": "test"},
            ],
        }
        result = execute(verification_plan, continue_on_failure=True)
        self.assertFalse(result["success"])
        self.assertEqual(len(result["results"]), 2)
        self.assertTrue(result["results"][1]["success"])


class FullVerificationTests(unittest.TestCase):
    """verification-run-v1: full kind filtering, explicit commands, and the no-checks outcome."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "Makefile").write_text("test:\n\ttouch ran-test\nlint:\n\ttrue\n")
        (self.root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                        "commit", "-qm", "init"], check=True)
        self.schema = json.loads((ROOT / "schemas/verification-run-v1.schema.json").read_text())

    def cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "AGENTIC_DEV_CONFIG_DIR": tempfile.mkdtemp()}
        return subprocess.run([sys.executable, "-m", "agentic_dev.cli", "verify", "run", *args],
                              cwd=self.root, env=env, capture_output=True, text=True, check=False)

    def test_every_discovered_command_of_each_kind_is_planned(self):
        planned = full_plan(self.root, kinds=["test", "lint"])
        self.assertEqual([(c["kind"], c["command"]) for c in planned["checks"]],
                         [("test", "make test"), ("test", "uv run pytest"), ("lint", "make lint")])
        self.assertEqual(planned["missing_kinds"], [])

    def test_missing_required_kind_is_no_checks_and_runs_nothing(self):
        run = execute(full_plan(self.root, kinds=["test", "typecheck"]))
        jsonschema.validate(run, self.schema)
        self.assertEqual((run["status"], run["success"], run["missing_kinds"]), ("no-checks", False, ["typecheck"]))
        self.assertEqual(run["results"], [])
        self.assertFalse((self.root / "ran-test").exists())

    def test_change_aware_run_with_nothing_to_check_is_no_checks(self):
        run = execute(plan(self.root))
        jsonschema.validate(run, self.schema)
        self.assertEqual((run["mode"], run["status"], run["success"], run["checks_executed"]),
                         ("change-aware", "no-checks", False, 0))

    def test_explicit_commands_and_failures(self):
        run = execute(full_plan(self.root, commands=["exit 3"]))
        jsonschema.validate(run, self.schema)
        self.assertEqual((run["status"], run["results"][0]["kind"], run["results"][0]["origin"]),
                         ("failed", "custom", "explicit"))

    def test_change_aware_augmentation_only_adds(self):
        (self.root / "main.py").write_text("x = 1\n")
        baseline = full_plan(self.root, kinds=["test"])
        augmented = full_plan(self.root, kinds=["test"], include_changed=True)
        base_checks = [(c["kind"], c["command"]) for c in baseline["checks"]]
        self.assertEqual([(c["kind"], c["command"]) for c in augmented["checks"]][:len(base_checks)], base_checks)
        self.assertIn(("lint", "make lint"), [(c["kind"], c["command"]) for c in augmented["checks"]])
        self.assertTrue(all(c["origin"] == "change-aware" for c in augmented["checks"][len(base_checks):]))

    def test_cli_exit_codes(self):
        passed = self.cli(".", "--kind", "lint", "--json")
        self.assertEqual(passed.returncode, 0, passed.stderr)
        jsonschema.validate(json.loads(passed.stdout), self.schema)
        missing = self.cli(".", "--kind", "typecheck")
        self.assertEqual(missing.returncode, 1)
        self.assertIn("no runnable command for required kind(s): typecheck", missing.stdout)
        self.assertIn("verification: no-checks", missing.stdout)
        self.assertEqual(self.cli(".").returncode, 1)  # change-aware, nothing changed
        self.assertEqual(self.cli(".", "--command", "exit 4").returncode, 1)
        self.assertEqual(self.cli(".", "--kind", "format").returncode, 2)
        self.assertEqual(self.cli(".", "--include-changed").returncode, 2)


if __name__ == "__main__":
    unittest.main()
