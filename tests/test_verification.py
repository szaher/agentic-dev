from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jsonschema

from agentic_dev.verification import execute, plan


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


if __name__ == "__main__":
    unittest.main()
