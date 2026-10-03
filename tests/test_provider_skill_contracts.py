"""Provider and skill-activation contracts consumed by AgentFlow's bootstrap (v0.16 slice 3)."""

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
SKILL = "---\nname: example-sdlc\ndescription: Example workflow skill.\n---\n\n# Example\n\nFollow the workflow.\n"


def provider(directory: Path, body: str = SKILL, version: str = "1.0.0") -> Path:
    (directory / "skills" / "example-sdlc").mkdir(parents=True, exist_ok=True)
    (directory / "skills" / "example-sdlc" / "SKILL.md").write_text(body)
    (directory / "agentic-provider.json").write_text(json.dumps({
        "schema_version": "1", "name": "example-flow", "version": version, "description": "Example provider",
        "skills": [{"name": "example-sdlc", "description": "Example workflow skill.", "category": "workflow",
                    "path": "skills/example-sdlc"}],
    }))
    return directory


class ProviderSkillContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="provider-contracts-"))
        self.env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "AGENTIC_DEV_CONFIG_DIR": str(self.tmp / "config")}
        self.repo = self.tmp / "repo"
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cli(self, *args: str, expect: int = 0) -> dict | None:
        done = subprocess.run([sys.executable, "-m", "agentic_dev.cli", *args], cwd=self.repo, env=self.env,
                              capture_output=True, text=True, check=False)
        self.assertEqual(done.returncode, expect, done.stderr)
        return json.loads(done.stdout) if done.stdout.strip().startswith("{") else None

    def test_inspect_install_and_list_agree_on_the_digest(self):
        source = provider(self.tmp / "provider")
        self.assertEqual(self.cli("providers", "list", "--json")["providers"], [])
        inspected = self.cli("providers", "inspect", str(source), "--json")
        jsonschema.validate(inspected, schema("provider-source"))
        self.assertEqual((inspected["name"], inspected["skills"]), ("example-flow", ["example-sdlc"]))
        self.assertEqual(self.cli("providers", "list", "--json")["providers"], [])  # inspect never installs

        installed = self.cli("providers", "add", str(source), "--sha256", inspected["content_digest"], "--json")
        jsonschema.validate(installed, schema("provider-install"))
        listed = self.cli("providers", "list", "--json")
        jsonschema.validate(listed, schema("providers"))
        entry = listed["providers"][0]
        self.assertEqual((entry["content_digest"], entry["verified"]), (inspected["content_digest"], True))

    def test_pinned_install_refuses_a_different_source(self):
        source = provider(self.tmp / "provider")
        self.cli("providers", "add", str(source), "--sha256", "0" * 64, expect=2)
        self.assertEqual(self.cli("providers", "list", "--json")["providers"], [])

    def test_skill_activation_reports_every_harness(self):
        self.cli("providers", "add", str(provider(self.tmp / "provider")), "--json")
        first = self.cli("skills", "add", "example-sdlc", "--target", "all", "--shared", "--json")
        jsonschema.validate(first, schema("skills-activation"))
        self.assertEqual({(o["harness"], o["status"]) for o in first["outcomes"]},
                         {(h, "written") for h in ("claude", "codex", "pi", "opencode")})
        again = self.cli("skills", "add", "example-sdlc", "--target", "all", "--shared", "--json")
        self.assertEqual({o["status"] for o in again["outcomes"]}, {"unchanged"})

    def test_unmanaged_skill_is_a_conflict_and_left_alone(self):
        self.cli("providers", "add", str(provider(self.tmp / "provider")), "--json")
        mine = self.repo / ".claude" / "skills" / "example-sdlc" / "SKILL.md"
        mine.parent.mkdir(parents=True)
        mine.write_text("my own skill\n")
        result = self.cli("skills", "add", "example-sdlc", "--target", "both", "--json", expect=1)
        jsonschema.validate(result, schema("skills-activation"))
        self.assertEqual((result["status"], result["exit_code"]), ("conflict", 1))
        self.assertEqual({o["harness"]: o["status"] for o in result["outcomes"]},
                         {"claude": "skipped-unmanaged", "codex": "written"})
        self.assertEqual(mine.read_text(), "my own skill\n")
        forced = self.cli("skills", "add", "example-sdlc", "--target", "both", "--force", "--json")
        self.assertEqual(forced["status"], "ok")

    def test_unknown_skill_is_a_usage_error(self):
        self.cli("skills", "add", "no-such-skill", "--json", expect=2)


if __name__ == "__main__":
    unittest.main()
