"""Existing documents validate against their v0.16 slice 1 schemas (worktrees, capabilities)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import jsonschema

from agentic_dev.contracts import schema

ROOT = Path(__file__).resolve().parents[1]


class DocumentContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="contract-docs-"))
        self.repo = self.tmp / "repo"
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        (self.repo / "README.md").write_text("# x\n")
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                        "commit", "-qm", "init"], check=True)
        self.env = {**os.environ, "PYTHONPATH": str(ROOT / "src"),
                    "AGENTIC_DEV_CONFIG_DIR": str(self.tmp / "config"),
                    "AGENTIC_WORKTREE_ROOT": str(self.tmp / "worktrees")}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cli(self, *args: str) -> dict:
        completed = subprocess.run([sys.executable, "-m", "agentic_dev.cli", *args], cwd=self.repo, env=self.env,
                                   capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def test_worktree_lifecycle_documents(self):
        created = self.cli("worktree", "create", "run-1", "--agent", "agentflow", "--task", "t", "--json")
        jsonschema.validate(created, schema("worktree"))
        self.assertEqual((created["branch"], created["session"]["base"]), ("agentic/run-1", "HEAD"))

        listed = self.cli("worktree", "list", "--json")
        jsonschema.validate(listed, schema("worktree-list"))
        self.assertEqual(len(listed["worktrees"]), 2)
        self.assertIsNone(listed["worktrees"][0]["session"])  # the primary worktree

        status = self.cli("worktree", "status", "run-1", "--json")
        jsonschema.validate(status, schema("worktree-status"))
        self.assertFalse(status["dirty"])

        cleaned = self.cli("worktree", "clean", "run-1", "--json")
        jsonschema.validate(cleaned, schema("worktree-clean"))
        self.assertFalse(Path(created["worktree"]).exists())

    def test_capability_status_documents(self):
        status = self.cli("capabilities", "status", "--json")
        jsonschema.validate(status, schema("capability-status"))
        self.assertTrue(status)
        doctor = self.cli("doctor", "--json")
        jsonschema.validate(doctor["capabilities"], schema("capability-status"))


if __name__ == "__main__":
    unittest.main()
