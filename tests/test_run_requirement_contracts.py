"""Contracts behind AgentFlow pattern requirements (v0.16 slice 4): metrics, worktrees, capabilities."""

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

from agentic_dev.contracts import EXIT_CODES, schema

ROOT = Path(__file__).resolve().parents[1]


class RunRequirementContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="run-requirements-"))
        self.env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "AGENTIC_DEV_CONFIG_DIR": str(self.tmp / "config"),
                    "AGENTIC_WORKTREE_ROOT": str(self.tmp / "worktrees")}
        self.repo = self.tmp / "repo"
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        (self.repo / "README.md").write_text("# Demo\n")
        git = ["git", "-C", str(self.repo), "-c", "user.email=a@example.com", "-c", "user.name=A"]
        subprocess.run([*git, "add", "."], check=True)
        subprocess.run([*git, "commit", "-qm", "init"], check=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cli(self, *args: str, expect: int = 0) -> dict | None:
        done = subprocess.run([sys.executable, "-m", "agentic_dev.cli", *args], cwd=self.repo, env=self.env,
                              capture_output=True, text=True, check=False)
        self.assertEqual(done.returncode, expect, done.stderr)
        return json.loads(done.stdout) if done.stdout.strip().startswith("{") else None

    def test_metric_record_reports_disabled_then_the_stored_event(self):
        stage = ("agentflow.stage", "--field", "stage=implement", "--field", "outcome=passed",
                 "--field", "api_token=secret", "--session-id", "run-1", "--path", str(self.repo), "--json")
        disabled = self.cli("metrics", "record", *stage)
        jsonschema.validate(disabled, schema("metric-record"))
        self.assertEqual((disabled["recorded"], disabled["event"]), (False, None))
        self.cli("metrics", "enable")
        recorded = self.cli("metrics", "record", *stage)
        jsonschema.validate(recorded, schema("metric-record"))
        event = recorded["event"]
        self.assertEqual((recorded["recorded"], event["event_type"], event["session_id"]),
                         (True, "agentflow.stage", "run-1"))
        self.assertEqual(event["data"], {"stage": "implement", "outcome": "passed", "api_token": "<redacted>"})
        summary = self.cli("metrics", "summary", "--json")
        self.assertIn("implement", json.dumps(summary))
        self.cli("metrics", "record", "agentflow.stage", "--field", "no-equals", "--json", expect=2)

    def test_metric_record_schema_ties_recorded_to_event(self):
        bad = {"schema_version": "1", "document_type": "agentic.metric-record", "recorded": True, "event": None}
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema("metric-record"))

    def test_worktree_clean_refuses_a_dirty_worktree_and_keeps_it(self):
        created = self.cli("worktree", "create", "run-1", "--branch", "flow/run-1", "--json")
        jsonschema.validate(created, schema("worktree"))
        work = Path(created["worktree"])
        (work / "README.md").write_text("# Changed\n")
        self.cli("worktree", "clean", "run-1", "--json", expect=2)
        self.assertEqual((work / "README.md").read_text(), "# Changed\n")
        self.cli("worktree", "create", "run-1", "--branch", "flow/run-1", "--json", expect=2)
        (work / "README.md").write_text("# Demo\n")
        cleaned = self.cli("worktree", "clean", "run-1", "--json")
        jsonschema.validate(cleaned, schema("worktree-clean"))
        self.assertFalse(work.exists())

    def test_capability_status_matches_its_schema(self):
        status = self.cli("capabilities", "status", "--json")
        jsonschema.validate(status, schema("capability-status"))
        self.assertTrue(all("enabled" in item for item in status.values()))

    def test_exit_codes_are_part_of_the_contract(self):
        for command in ("metrics record", "worktree create", "worktree clean", "capabilities status"):
            self.assertIn("0", EXIT_CODES[command], command)


if __name__ == "__main__":
    unittest.main()
