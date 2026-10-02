from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jsonschema

from agentic_dev_env.execution import run as run_execution
from agentic_dev_env.metrics import (
    clear, export, read_events, record, set_enabled, status, summary,
)
from agentic_dev_env.worktrees import create_worktree, clean_worktree


ROOT = Path(__file__).resolve().parents[1]


class MetricsTests(unittest.TestCase):
    def make_repo(self) -> Path:
        root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        (root / "README.md").write_text("demo\n")
        subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)
        subprocess.run([
            "git", "-C", str(root),
            "-c", "user.name=Agentic Test",
            "-c", "user.email=agentic@example.invalid",
            "commit", "-qm", "init",
        ], check=True)
        return root

    def test_disabled_by_default_creates_no_events(self):
        with tempfile.TemporaryDirectory() as config:
            with patch.dict(os.environ, {"AGENTIC_DEV_ENV_CONFIG_DIR": config}):
                self.assertFalse(status()["enabled"])
                self.assertFalse(record("test.event", {"value": 1}))
                self.assertEqual(read_events(), [])
                self.assertFalse((Path(config) / "metrics" / "events.jsonl").exists())

    def test_redaction_and_repository_identity(self):
        with tempfile.TemporaryDirectory() as config:
            repo = self.make_repo()
            with patch.dict(os.environ, {"AGENTIC_DEV_ENV_CONFIG_DIR": config}):
                set_enabled(True)
                self.assertTrue(record(
                    "manual.event",
                    {
                        "token": "do-not-store",
                        "nested": {"password": "also-do-not-store"},
                        "safe": "visible",
                    },
                    repository=repo,
                    session_id="task-1",
                ))
                event = read_events()[0]
                self.assertEqual(event["data"]["token"], "<redacted>")
                self.assertEqual(event["data"]["nested"]["password"], "<redacted>")
                self.assertEqual(event["data"]["safe"], "visible")
                self.assertEqual(event["repository"]["name"], repo.name)
                self.assertNotIn(str(repo), json.dumps(event))
                self.assertEqual(event["session_id"], "task-1")

                schema = json.loads((ROOT / "schemas" / "metric-event-v1.schema.json").read_text())
                jsonschema.validate(event, schema)

    def test_execution_event_contains_hash_not_raw_command(self):
        with tempfile.TemporaryDirectory() as config:
            repo = self.make_repo()
            with patch.dict(os.environ, {"AGENTIC_DEV_ENV_CONFIG_DIR": config}):
                set_enabled(True)
                result = run_execution("printf agentic-sensitive-example", repo)
                self.assertTrue(result["success"])
                self.assertGreaterEqual(result["duration_ms"], 0)
                events = [e for e in read_events() if e["event_type"] == "execution.completed"]
                self.assertEqual(len(events), 1)
                payload = events[0]["data"]
                self.assertIn("command_hash", payload)
                self.assertNotIn("command", payload)
                self.assertNotIn("agentic-sensitive-example", json.dumps(events[0]))

    def test_summary_covers_roadmap_metrics(self):
        with tempfile.TemporaryDirectory() as config:
            repo = self.make_repo()
            with patch.dict(os.environ, {"AGENTIC_DEV_ENV_CONFIG_DIR": config}):
                set_enabled(True)
                kwargs = {"repository": repo, "session_id": "session-a"}
                record("session.started", {"agent": "codex"}, **kwargs)
                record("execution.completed", {
                    "success": True, "duration_ms": 10, "tool": "pytest",
                }, **kwargs)
                record("execution.completed", {
                    "success": False, "duration_ms": 30, "tool": "ruff",
                }, **kwargs)
                record("verification.check", {
                    "kind": "test", "success": True,
                    "elapsed_from_verification_start_ms": 25,
                }, **kwargs)
                record("verification.completed", {
                    "success": True, "duration_ms": 40,
                }, **kwargs)
                record("retry", {"reason": "test-failure"}, **kwargs)
                record("skills.suggested", {
                    "count": 4,
                    "recommended_names": ["python-engineering", "test-development", "debugging", "code-review"],
                }, **kwargs)
                record("skills.activated", {
                    "count": 2,
                    "names": ["python-engineering", "debugging"],
                }, **kwargs)
                record("capabilities.suggested", {
                    "count": 2,
                    "names": ["secret-scan", "sast"],
                }, **kwargs)
                record("capability.enabled", {"name": "secret-scan"}, **kwargs)
                record("tool.call", {"tool": "serena", "success": True}, **kwargs)
                record("context.used", {"source": "codegraph", "useful": True}, **kwargs)
                record("context.used", {"source": "serena", "useful": False}, **kwargs)
                record("agentflow.stage", {"stage": "review", "outcome": "passed"}, **kwargs)
                record("change.measured", {"insertions": 12, "deletions": 3}, **kwargs)
                record("change.reverted", {"count": 1}, **kwargs)
                record("session.ended", {}, **kwargs)

                data = summary(repository=repo)
                self.assertEqual(data["execution"]["count"], 2)
                self.assertEqual(data["execution"]["failures"], 1)
                self.assertEqual(data["execution"]["failure_rate"], 0.5)
                self.assertEqual(data["workflow"]["per_session"]["session-a"]["tool_calls"], 3)
                self.assertEqual(data["workflow"]["per_session"]["session-a"]["external_tool_calls"], 1)
                self.assertEqual(data["workflow"]["retries"], 1)
                self.assertEqual(data["verification"]["time_to_first_passing_focused_test_ms"], 25)
                self.assertEqual(data["recommendations"]["skill_activation_ratio"], 0.5)
                self.assertEqual(data["recommendations"]["capability_enable_ratio"], 0.5)
                self.assertEqual(data["context"]["useful"]["codegraph"], 1)
                self.assertEqual(data["workflow"]["agentflow_stage_outcomes"]["review"]["passed"], 1)
                self.assertEqual(data["changes"]["insertions"], 12)
                self.assertEqual(data["changes"]["reverted_edits"], 1)


    def test_worktree_lifecycle_emits_session_events(self):
        with tempfile.TemporaryDirectory() as config, tempfile.TemporaryDirectory() as wtroot:
            repo = self.make_repo()
            with patch.dict(os.environ, {"AGENTIC_DEV_ENV_CONFIG_DIR": config}):
                set_enabled(True)
                created = create_worktree(
                    "metrics-session", repo,
                    agent="codex", task="do something",
                    worktree_root=wtroot,
                )
                clean_worktree("metrics-session", repo, force=True, delete_branch=True)
                events = read_events(repository=repo)
                types = [event["event_type"] for event in events]
                self.assertIn("session.started", types)
                self.assertIn("session.ended", types)
                started = next(event for event in events if event["event_type"] == "session.started")
                self.assertEqual(started["session_id"], "metrics-session")
                self.assertTrue(started["data"]["has_task"])
                self.assertNotIn("do something", json.dumps(started))

    def test_export_is_local_file_only_and_clear_requires_yes(self):
        with tempfile.TemporaryDirectory() as config, tempfile.TemporaryDirectory() as out:
            with patch.dict(os.environ, {"AGENTIC_DEV_ENV_CONFIG_DIR": config}):
                set_enabled(True)
                record("test.event", {"ok": True})
                target = Path(out) / "metrics.jsonl"
                data = export(target)
                self.assertTrue(target.exists())
                self.assertEqual(data["event_count"], 1)
                self.assertFalse(data["network_export"])
                with self.assertRaises(PermissionError):
                    clear(yes=False)
                clear(yes=True)
                self.assertEqual(read_events(), [])


if __name__ == "__main__":
    unittest.main()
