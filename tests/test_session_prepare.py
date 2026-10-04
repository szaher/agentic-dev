from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jsonschema

from agentic_dev.cli import main
from agentic_dev.contracts import schema
from agentic_dev.paths import LEGACY_CONFIG_ENV, NEW_CONFIG_ENV
from agentic_dev.session import plan_session
from agentic_dev.session_prepare import (
    BlockedPlanError,
    DirtyWorkspaceError,
    InvalidPlanError,
    PlacementError,
    StalePlanError,
    prepare_session,
)


def verified_harness(version: str = "test-1.0") -> dict:
    return {
        "name": "codex",
        "available": True,
        "executable": "/test/codex",
        "version": version,
        "permissions": {
            dimension: {
                level: {
                    "status": "enforceable",
                    "mechanism": "test fixture",
                    "evidence": "test fixture",
                }
                for level in levels
            }
            for dimension, levels in (
                ("filesystem", ("read-only", "workspace-write")),
                ("network", ("off", "on")),
            )
        },
    }


class SessionPrepareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="session-prepare-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        self.workspace = Path(self.tmp.name) / "worktree"
        env = patch.dict(
            os.environ, {"AGENTIC_DEV_CONFIG_DIR": str(Path(self.tmp.name) / "config")}
        )
        env.start()
        self.addCleanup(env.stop)
        (self.root / "README.md").write_text("# Test repository\n")
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "README.md"], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-qm",
                "init",
            ],
            check=True,
        )
        self.request = {
            "schema_version": "1",
            "document_type": "agentic.session-request",
            "task": "Fix a Python bug",
            "required_skills": ["python-engineering"],
            "invocations": [
                {"id": "implement", "role": "implementer", "harness": "codex"}
            ],
        }
        self.facts = {"codex": verified_harness()}

    def plan(self) -> dict:
        return plan_session(self.root, self.request, harness_facts=self.facts)

    def worktree(self) -> None:
        subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "worktree",
                "add",
                "-q",
                "-b",
                "test-session",
                str(self.workspace),
            ],
            check=True,
        )

    def test_prepares_selected_skills_only_in_worktree_and_validates_record(self):
        plan = self.plan()
        self.assertEqual(plan["status"], "ready", plan["blockers"])
        self.worktree()
        record = prepare_session(plan, self.workspace, harness_facts=self.facts)
        jsonschema.validate(record, schema("session-record"))
        invalid = copy.deepcopy(record)
        invalid["invocations"][0]["permissions"]["filesystem"]["effective"]["level"] = (
            "root-write-everywhere"
        )
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(invalid, schema("session-record"))
        self.assertEqual(record["plan_digest"], plan["plan_digest"])
        self.assertEqual(record["request_digest"], plan["request_digest"])
        self.assertEqual(record["inputs_digest"], plan["inputs_digest"])
        self.assertEqual(record["tools"], plan["tools"])
        self.assertEqual(record["status"], "prepared")
        self.assertEqual(
            {item["name"] for item in record["skills"]},
            {item["name"] for item in plan["skills"]["selected"]},
        )
        for relative in record["prepared"]["skill_paths"]:
            self.assertTrue((self.workspace / relative).is_file())
            self.assertFalse((self.root / relative).exists())
            self.assertEqual(
                subprocess.run(
                    ["git", "-C", str(self.workspace), "check-ignore", "-q", relative],
                    check=False,
                ).returncode,
                0,
            )
        self.assertEqual(
            subprocess.check_output(
                ["git", "-C", str(self.workspace), "status", "--porcelain"], text=True
            ),
            "",
        )
        self.assertEqual(
            record, prepare_session(plan, self.workspace, harness_facts=self.facts)
        )

    def test_stale_inputs_refuse_before_workspace_mutation(self):
        plan = self.plan()
        self.worktree()
        changed = {"codex": verified_harness(version="test-2.0")}
        with self.assertRaisesRegex(StalePlanError, "SESSION_PLAN_STALE"):
            prepare_session(plan, self.workspace, harness_facts=changed)
        self.assertFalse((self.workspace / ".codex").exists())
        self.assertEqual(
            subprocess.check_output(
                ["git", "-C", str(self.workspace), "status", "--porcelain"], text=True
            ),
            "",
        )

    def test_changed_tool_version_refuses_before_workspace_mutation(self):
        with patch(
            "agentic_dev.session._tool_version", side_effect=["Serena A", "CodeGraph B"]
        ):
            plan = self.plan()
        self.worktree()
        with (
            patch(
                "agentic_dev.session._tool_version",
                side_effect=["Serena C", "CodeGraph B"],
            ),
            self.assertRaisesRegex(StalePlanError, "SESSION_PLAN_STALE"),
        ):
            prepare_session(plan, self.workspace, harness_facts=self.facts)
        self.assertFalse((self.workspace / ".codex").exists())

    def test_untracked_workspace_profile_is_dirty_before_skill_placement(self):
        plan = self.plan()
        self.worktree()
        profile = self.workspace / ".agentic" / "profile.toml"
        profile.parent.mkdir()
        profile.write_text(
            'schema_version = "1"\ndocument_type = "agentic.repository-profile"\n'
            'preferred_harness = "codex"\n'
        )
        before = profile.read_bytes()
        with self.assertRaisesRegex(DirtyWorkspaceError, "SESSION_WORKSPACE_DIRTY"):
            prepare_session(plan, self.workspace, harness_facts=self.facts)
        self.assertEqual(profile.read_bytes(), before)
        self.assertFalse((self.workspace / ".codex").exists())

    def test_visibility_reports_unselected_workspace_assets(self):
        extra = self.root / ".codex" / "skills" / "external"
        extra.mkdir(parents=True)
        (extra / "SKILL.md").write_text("# External\n")
        config = self.root / ".codex" / "config.toml"
        config.write_text("# Existing config\n")
        subprocess.run(["git", "-C", str(self.root), "add", ".codex"], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-qm",
                "external assets",
            ],
            check=True,
        )
        plan = self.plan()
        self.worktree()
        record = prepare_session(plan, self.workspace, harness_facts=self.facts)
        detected = record["visibility"][0]["detected_external"]
        self.assertIn(
            {"kind": "workspace-skill", "path": ".codex/skills/external/SKILL.md"},
            detected,
        )
        self.assertIn(
            {"kind": "workspace-config", "path": ".codex/config.toml"}, detected
        )
        self.assertTrue(record["visibility"][0]["undetermined"])

    def test_blocked_and_tampered_plan_refuse_without_mutation(self):
        blocked = plan_session(self.root, self.request)
        self.assertEqual(blocked["status"], "blocked")
        self.worktree()
        with self.assertRaises(BlockedPlanError):
            prepare_session(blocked, self.workspace)
        tampered = copy.deepcopy(self.plan())
        tampered["task"] = "different"
        with self.assertRaises(InvalidPlanError):
            prepare_session(tampered, self.workspace, harness_facts=self.facts)
        self.assertFalse((self.workspace / ".codex").exists())

    def test_unmanaged_conflict_refuses_without_partial_placement(self):
        plan = self.plan()
        self.worktree()
        (self.root / ".git" / "info" / "exclude").write_text(".codex/\n")
        first = plan["skills"]["selected"][0]["name"]
        conflict = self.workspace / ".codex" / "skills" / first
        conflict.mkdir(parents=True)
        (conflict / "existing.txt").write_text("unmanaged\n")
        with self.assertRaises(PlacementError):
            prepare_session(plan, self.workspace, harness_facts=self.facts)
        self.assertEqual((conflict / "existing.txt").read_text(), "unmanaged\n")
        self.assertEqual(list(self.workspace.rglob("SKILL.md")), [])

    def test_tracked_modification_refused_before_agentic_writes(self):
        plan = self.plan()
        self.worktree()
        changed = self.workspace / "README.md"
        changed.write_text("# Unapproved source\n")
        before = changed.read_bytes()
        with self.assertRaisesRegex(DirtyWorkspaceError, "SESSION_WORKSPACE_DIRTY"):
            prepare_session(plan, self.workspace, harness_facts=self.facts)
        self.assertEqual(changed.read_bytes(), before)
        self.assertFalse((self.workspace / ".codex").exists())

    def test_untracked_source_refused_before_agentic_writes(self):
        plan = self.plan()
        self.worktree()
        source = self.workspace / "calc.py"
        source.write_text("print('unapproved')\n")
        before = source.read_bytes()
        with self.assertRaisesRegex(DirtyWorkspaceError, "SESSION_WORKSPACE_DIRTY"):
            prepare_session(plan, self.workspace, harness_facts=self.facts)
        self.assertEqual(source.read_bytes(), before)
        self.assertFalse((self.workspace / ".codex").exists())

    def test_unrelated_repository_refuses(self):
        plan = self.plan()
        other = Path(self.tmp.name) / "other"
        subprocess.run(["git", "init", "-q", str(other)], check=True)
        with self.assertRaises(InvalidPlanError):
            prepare_session(plan, other, harness_facts=self.facts)

    def test_cli_rejects_real_blocked_plan(self):
        plan = plan_session(self.root, self.request)
        self.worktree()
        plan_file = Path(self.tmp.name) / "plan.json"
        plan_file.write_text(json.dumps(plan))
        with patch.object(
            sys,
            "argv",
            [
                "agentic",
                "session",
                "prepare",
                "--plan",
                str(plan_file),
                "--path",
                str(self.workspace),
                "--json",
            ],
        ):
            with self.assertRaises(SystemExit) as result:
                main()
            self.assertEqual(result.exception.code, 1)
        self.assertFalse((self.workspace / ".codex").exists())

    def test_cli_invalid_and_stale_plan_do_not_migrate_legacy_config(self):
        self.worktree()
        legacy = Path(self.tmp.name) / "legacy-config"
        legacy.mkdir()
        (legacy / "trust.json").write_text('{"source":"legacy"}\n')
        current = Path(self.tmp.name) / "new-config"
        plan_file = Path(self.tmp.name) / "plan.json"
        clean_env = {
            key: value
            for key, value in os.environ.items()
            if key not in {NEW_CONFIG_ENV, LEGACY_CONFIG_ENV}
        }
        with (
            patch.dict(os.environ, clean_env, clear=True),
            patch("agentic_dev.paths.legacy_default_config_dir", return_value=legacy),
            patch("agentic_dev.paths.default_config_dir", return_value=current),
        ):
            for document, expected in (({}, 2), (self.plan(), 3)):
                with self.subTest(expected_exit=expected):
                    plan_file.write_text(json.dumps(document))
                    with (
                        patch.object(
                            sys,
                            "argv",
                            [
                                "agentic",
                                "session",
                                "prepare",
                                "--plan",
                                str(plan_file),
                                "--path",
                                str(self.workspace),
                                "--json",
                            ],
                        ),
                        self.assertRaises(SystemExit) as result,
                    ):
                        main()
                    self.assertEqual(result.exception.code, expected)
                    self.assertFalse(current.exists())
                    self.assertFalse((self.workspace / ".codex").exists())
