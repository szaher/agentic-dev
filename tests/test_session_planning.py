from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jsonschema

from agentic_dev.contracts import schema
from agentic_dev.session import load_profile, plan_session, validate_request


def verified_harness(name: str = "codex", version: str = "test-1.0") -> dict:
    return {
        "name": name,
        "available": True,
        "executable": f"/test/{name}",
        "version": version,
        "permissions": {
            "filesystem": {
                level: {
                    "status": "enforceable",
                    "mechanism": "scripted test sandbox",
                    "evidence": "test fixture",
                }
                for level in ("read-only", "workspace-write")
            },
            "network": {
                level: {
                    "status": "enforceable",
                    "mechanism": "scripted test sandbox",
                    "evidence": "test fixture",
                }
                for level in ("off", "on")
            },
        },
    }


class SessionPlanningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="session-plan-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        self.config = Path(self.tmp.name) / "config"
        env = patch.dict(os.environ, {"AGENTIC_DEV_CONFIG_DIR": str(self.config)})
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
            "task": "Fix a bug",
            "invocations": [
                {"id": "implement", "role": "implementer", "harness": "codex"}
            ],
        }
        self.facts = {"codex": verified_harness()}

    def plan(self, request: dict | None = None, *, facts: dict | None = None) -> dict:
        return plan_session(
            self.root, request or self.request, harness_facts=facts or self.facts
        )

    def test_schema_and_determinism_with_no_mutation(self):
        before = {
            p.relative_to(self.root): p.read_bytes()
            for p in self.root.rglob("*")
            if p.is_file()
        }
        first = self.plan()
        second = self.plan()
        after = {
            p.relative_to(self.root): p.read_bytes()
            for p in self.root.rglob("*")
            if p.is_file()
        }
        self.assertEqual(first["status"], "ready")
        self.assertEqual(first, second)
        self.assertEqual(before, after)
        self.assertFalse(self.config.exists())
        jsonschema.validate(first, schema("session-plan"))
        jsonschema.validate(validate_request(self.request), schema("session-request"))
        jsonschema.validate(load_profile(self.root), schema("repository-profile"))

    def test_profile_permission_ceiling_blocks_without_downgrade(self):
        profile = self.root / ".agentic" / "profile.toml"
        profile.parent.mkdir()
        profile.write_text(
            'schema_version = "1"\ndocument_type = "agentic.repository-profile"\n'
            '[permissions.implementer]\nfilesystem = "read-only"\n'
        )
        plan = self.plan()
        self.assertEqual(plan["status"], "blocked")
        self.assertIn(
            "permission-conflict", {item["code"] for item in plan["blockers"]}
        )
        self.assertEqual(
            plan["invocations"][0]["permissions"]["filesystem"]["effective"]["level"],
            "read-only",
        )

    def test_relevant_inputs_change_digests(self):
        first = self.plan()
        changed_request = {**self.request, "task": "Fix a different bug"}
        second = self.plan(changed_request)
        self.assertNotEqual(first["request_digest"], second["request_digest"])
        self.assertNotEqual(first["plan_digest"], second["plan_digest"])
        facts = {"codex": verified_harness(version="test-2.0")}
        third = self.plan(facts=facts)
        self.assertNotEqual(first["inputs_digest"], third["inputs_digest"])
        self.assertNotEqual(first["plan_digest"], third["plan_digest"])

    def test_blockers_for_missing_skill_capability_and_unavailable_harness(self):
        request = {
            **self.request,
            "required_skills": ["absent-skill"],
            "required_capabilities": ["browser-automation"],
        }
        facts = {"codex": {**verified_harness(), "available": False}}
        plan = self.plan(request, facts=facts)
        self.assertEqual(plan["status"], "blocked")
        self.assertTrue(
            {"skill-missing", "capability-disabled", "harness-unavailable"}
            <= {item["code"] for item in plan["blockers"]}
        )

    def test_unknown_keys_are_usage_errors(self):
        with self.assertRaisesRegex(ValueError, "unknown request keys"):
            self.plan({**self.request, "pattern": "fast"})
        with self.assertRaisesRegex(ValueError, "reviewers cannot"):
            validate_request(
                {
                    **self.request,
                    "invocations": self.request["invocations"]
                    + [
                        {
                            "id": "review",
                            "role": "reviewer",
                            "permissions": {
                                "filesystem": {"maximum": "workspace-write"}
                            },
                        }
                    ],
                }
            )

    def test_profile_preferred_harness_can_fill_omitted_harness(self):
        profile = self.root / ".agentic" / "profile.toml"
        profile.parent.mkdir()
        profile.write_text(
            'schema_version = "1"\ndocument_type = "agentic.repository-profile"\n'
            'preferred_harness = "codex"\n'
        )
        request = {
            **self.request,
            "invocations": [{"id": "implement", "role": "implementer"}],
        }
        jsonschema.validate(validate_request(request), schema("session-request"))
        self.assertEqual(self.plan(request)["invocations"][0]["harness"], "codex")
        with self.assertRaisesRegex(ValueError, "must be a non-empty string"):
            validate_request({**self.request, "trust_ceiling": None})

    def test_skill_allowlist_and_trust_ceiling_block(self):
        profile = self.root / ".agentic" / "profile.toml"
        profile.parent.mkdir()
        profile.write_text(
            'schema_version = "1"\ndocument_type = "agentic.repository-profile"\n'
            'trust_ceiling = "safe"\nallowed_skills = ["code-review"]\n'
        )
        request = {
            **self.request,
            "trust_profile": "development",
            "required_skills": ["python-engineering"],
        }
        plan = self.plan(request)
        self.assertTrue(
            {"trust-ceiling", "skill-disallowed"}
            <= {item["code"] for item in plan["blockers"]}
        )
        self.assertNotIn(
            "python-engineering", {item["name"] for item in plan["skills"]["selected"]}
        )

    def test_readiness_minimum_blocks(self):
        plan = self.plan({**self.request, "readiness_minimum": "autonomous"})
        self.assertEqual(plan["status"], "blocked")
        self.assertIn("readiness", {item["code"] for item in plan["blockers"]})


if __name__ == "__main__":
    unittest.main()
