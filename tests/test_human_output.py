from __future__ import annotations

import contextlib
import io
import json
import unittest
from argparse import Namespace
from types import SimpleNamespace
from unittest.mock import patch

from agentic_dev import human_output
from agentic_dev.cli import build_parser, cmd_session_plan, cmd_session_prepare
from agentic_dev.session_prepare import DirtyWorkspaceError


def blocked_plan() -> dict:
    return {
        "status": "blocked",
        "task": "Fix the parser",
        "repository": "/repo",
        "plan_digest": "a" * 64,
        "readiness": {"current": "unaware", "minimum": "foundational"},
        "skills": {"selected": [{"name": "python-engineering"}]},
        "capabilities": [],
        "trust": {"profile": "safe"},
        "verification_kinds": ["test"],
        "tools": [
            {"name": "serena", "available": True, "configured": False, "version": "1.7"}
        ],
        "invocations": [
            {
                "id": "implement",
                "role": "implementer",
                "harness": "codex",
                "version": "0.1",
                "permissions": {
                    "filesystem": {
                        "effective": {"level": "workspace-write"},
                        "enforceable": "unknown",
                    },
                    "network": {
                        "effective": {"level": "off"},
                        "enforceable": "unknown",
                    },
                },
            }
        ],
        "blockers": [
            {"code": "readiness", "detail": "readiness unaware is below foundational"},
            {
                "code": "permission-unenforceable",
                "invocation": "implement",
                "detail": "filesystem=workspace-write on codex is unknown",
            },
        ],
    }


class HumanOutputTests(unittest.TestCase):
    def test_blocked_session_leads_with_actions_and_full_digest(self):
        output = human_output.session_plan(blocked_plan())
        self.assertTrue(output.startswith("SESSION PLAN  BLOCKED\n"))
        self.assertLess(output.index("Needs attention"), output.index("Environment"))
        self.assertLess(output.index("Next"), output.index("Harness permissions"))
        self.assertIn("agentic ready plan /repo", output)
        self.assertIn("Permission enforcement unverified", output)
        self.assertIn("Preparation stays blocked", output)
        self.assertIn("a" * 64, output)
        self.assertIn("filesystem: workspace-write — unknown", output)

    def test_ready_plan_has_approval_step(self):
        plan = blocked_plan()
        plan["status"] = "ready"
        plan["blockers"] = []
        output = human_output.session_plan(plan)
        self.assertIn("SESSION PLAN  READY", output)
        self.assertIn("Review and approve this plan digest", output)
        self.assertNotIn("Needs attention", output)

    def test_prepared_record_reports_skills_and_visibility(self):
        record = {
            "workspace": "/repo-worktree",
            "commit": "b" * 40,
            "plan_digest": "a" * 64,
            "prepared": {"skill_paths": [".codex/skills/python-engineering/SKILL.md"]},
            "visibility": [
                {
                    "harness": "codex",
                    "undetermined": ["MCP visibility unknown"],
                    "detected_external": [
                        {"kind": "user-path-present", "path": "~/.codex/config.toml"}
                    ],
                }
            ],
        }
        output = human_output.session_record(record)
        self.assertIn("SESSION PREPARED", output)
        self.assertIn("Skills placed (1)", output)
        self.assertIn("codex: undetermined", output)
        self.assertIn("~/.codex/config.toml", output)
        self.assertIn("Review the session record", output)

    def test_other_primary_views_have_clear_result_and_next_step(self):
        repository = {
            "repository": {"name": "repo", "root": "/repo", "facts": ["python"]},
            "commands": {"test": ["pytest"], "lint": []},
            "skills": {
                "recommended": [{"name": "python-engineering", "recommended": True}]
            },
            "capabilities": {"sast": {"enabled": False}},
        }
        self.assertIn("Next\n", human_output.repository_inspection(repository))
        verification = {
            "repository": "/repo",
            "changed_files": ["app.py"],
            "checks": [
                {"kind": "test", "command": "pytest", "reason": "Python project"}
            ],
            "skipped_checks": [],
        }
        self.assertIn(
            "VERIFICATION PLAN  1 check(s)",
            human_output.verification_plan(verification),
        )
        self.assertIn("Next\n", human_output.verification_plan(verification))
        run = {"status": "no-checks", "results": [], "missing_kinds": ["test"]}
        self.assertIn("Add runnable checks", human_output.verification_run(run))
        failed = {
            "status": "failed",
            "missing_kinds": [],
            "results": [
                {
                    "kind": "test",
                    "command": "pytest",
                    "success": False,
                    "returncode": 1,
                    "stderr": "setup detail\nAssertionError: expected 2",
                }
            ],
        }
        self.assertIn(
            "AssertionError: expected 2", human_output.verification_run(failed)
        )
        self.assertIn("Exit code: 1", human_output.verification_run(failed))

    def test_inventory_views_separate_status_from_action(self):
        tools = {
            "git": "/bin/git",
            "rg": None,
            "codex": "/bin/codex",
            "claude": None,
            "pi": None,
            "opencode": None,
        }
        integration = [
            SimpleNamespace(
                name="codex",
                available=True,
                configured=False,
                detail="marketplace not registered",
            )
        ]
        output = human_output.doctor(tools, integration, {})
        self.assertIn("ENVIRONMENT  1/2 workspace tools found", output)
        self.assertIn("Harnesses  1/4 installed", output)
        self.assertIn("Missing: rg", output)
        self.assertIn("Next\n", output)
        capability = {
            "sast": {"enabled": False, "provider": "semgrep", "configuration": None}
        }
        self.assertIn(
            "0 enabled / 1 available", human_output.capabilities_status(capability)
        )
        self.assertIn("Next\n", human_output.capabilities_status(capability))

    def test_worktree_and_trust_views_replace_raw_json(self):
        tree = {
            "repository": "/repo",
            "worktrees": [
                {
                    "worktree": "/repo",
                    "branch": "main",
                    "head": "a" * 40,
                    "dirty": False,
                    "session": None,
                },
                {
                    "worktree": "/tree",
                    "branch": "feature",
                    "head": "b" * 40,
                    "dirty": True,
                    "session": {"agent": "codex", "task": "Fix parser"},
                },
            ],
        }
        listing = human_output.worktree_list(tree)
        self.assertIn("PRIMARY  clean", listing)
        self.assertIn("LINKED  dirty", listing)
        detail = human_output.worktree_status(tree["worktrees"][1])
        self.assertIn("WORKTREE  DIRTY", detail)
        self.assertIn("Inspect uncommitted changes", detail)
        trust = {
            "current_profile": "safe",
            "profiles": {
                "safe": {
                    "selected": True,
                    "description": "Local read access",
                    "permissions": ["fs.read"],
                },
                "development": {
                    "selected": False,
                    "description": "Workspace edits",
                    "permissions": ["fs.read", "fs.write"],
                },
            },
        }
        self.assertIn("selected: safe", human_output.trust_list(trust))
        self.assertIn("Other profiles: development", human_output.trust_show(trust))

    def test_infrastructure_status_summarizes_environment(self):
        document = {
            "repository": "/repo",
            "tools": {"kubectl": {"available": True}, "aws": {"available": False}},
            "cluster": {"context": "development", "namespace": "apps"},
            "cloud": {
                "aws_profile": None,
                "azure_configured": False,
                "gcp_configured": False,
            },
            "observability": {"collector_available": False, "config_files": []},
        }
        output = human_output.infrastructure_status(document)
        self.assertIn("INFRASTRUCTURE", output)
        self.assertIn("Context: development", output)
        self.assertIn("Not installed: aws", output)
        self.assertIn("Next\n", output)

    def test_capability_catalog_is_short_by_default_with_details_on_request(self):
        item = SimpleNamespace(
            name="sast",
            category="security",
            description="Scan source code.",
            provider="semgrep",
            targets=("local",),
            required_permissions=("repo.read",),
            risk="Reads source files.",
        )
        compact = human_output.capabilities_list((item,))
        self.assertIn("Security (1)", compact)
        self.assertIn("sast — Scan source code.", compact)
        self.assertNotIn("Risk: Reads source files.", compact)
        detail = human_output.capabilities_list((item,), verbose=True)
        self.assertIn("Risk: Reads source files.", detail)
        self.assertTrue(
            build_parser().parse_args(["capabilities", "list", "--verbose"]).verbose
        )

    def test_session_cli_text_and_json_keep_same_document_and_exit(self):
        plan = blocked_plan()
        with (
            patch("agentic_dev.cli.load_session_request", return_value={}),
            patch("agentic_dev.cli.plan_session", return_value=plan),
        ):
            text_out = io.StringIO()
            with contextlib.redirect_stdout(text_out):
                self.assertEqual(
                    cmd_session_plan(
                        Namespace(path="/repo", request="request.json", json=False)
                    ),
                    1,
                )
            self.assertIn("Next\n", text_out.getvalue())
            json_out = io.StringIO()
            with contextlib.redirect_stdout(json_out):
                self.assertEqual(
                    cmd_session_plan(
                        Namespace(path="/repo", request="request.json", json=True)
                    ),
                    1,
                )
            self.assertEqual(json.loads(json_out.getvalue()), plan)

    def test_prepare_error_preserves_json_mode_message_and_exit(self):
        error = DirtyWorkspaceError("SESSION_WORKSPACE_DIRTY: changed file")
        with (
            patch("agentic_dev.cli.load_session_plan", return_value={}),
            patch("agentic_dev.cli.prepare_session", side_effect=error),
        ):
            human = io.StringIO()
            with contextlib.redirect_stderr(human):
                self.assertEqual(
                    cmd_session_prepare(
                        Namespace(path="/tree", plan="plan.json", json=False)
                    ),
                    5,
                )
            self.assertIn("Commit or remove changes", human.getvalue())
            machine = io.StringIO()
            with contextlib.redirect_stderr(machine):
                self.assertEqual(
                    cmd_session_prepare(
                        Namespace(path="/tree", plan="plan.json", json=True)
                    ),
                    5,
                )
            self.assertEqual(
                machine.getvalue(),
                "session prepare: SESSION_WORKSPACE_DIRTY: changed file\n",
            )
