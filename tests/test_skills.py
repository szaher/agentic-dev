from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from agentic_dev_env.detect import detect_repo
from agentic_dev_env.skills import activate, installed_skills, recommend, remove


class SkillTests(unittest.TestCase):
    def make_repo(self) -> Path:
        root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        return root

    def test_detects_python_fastapi_and_testing(self):
        root = self.make_repo()
        (root / "pyproject.toml").write_text(
            """[project]
name = "demo"
version = "0.1.0"
dependencies = ["fastapi", "sqlalchemy", "pytest"]
"""
        )
        (root / "tests").mkdir()
        ctx = detect_repo(root)
        self.assertIn("language:python", ctx.facts)
        self.assertIn("framework:fastapi", ctx.facts)
        self.assertIn("database:sqlalchemy", ctx.facts)
        self.assertIn("testing:pytest", ctx.facts)
        self.assertIn("repo-type:api", ctx.facts)

    def test_task_changes_recommendations(self):
        root = self.make_repo()
        (root / "pyproject.toml").write_text(
            """[project]
name = "demo"
version = "0.1.0"
"""
        )
        ctx = detect_repo(root)
        names = [r.skill.name for r in recommend(ctx, task="debug failing API regression")]
        self.assertIn("python-engineering", names)
        self.assertIn("debugging", names)
        self.assertIn("api-design", names)
        self.assertIn("test-development", names)

    def test_local_activation_writes_both_native_locations_and_excludes(self):
        root = self.make_repo()
        activate(root, ["python-engineering"], shared=False, target="both")
        self.assertTrue((root / ".claude/skills/python-engineering/SKILL.md").exists())
        self.assertTrue((root / ".agents/skills/python-engineering/SKILL.md").exists())
        status = installed_skills(root)
        self.assertEqual(status["claude"], ["python-engineering"])
        self.assertEqual(status["codex"], ["python-engineering"])
        exclude = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--git-path", "info/exclude"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        exclude_path = Path(exclude)
        if not exclude_path.is_absolute():
            exclude_path = root / exclude_path
        text = exclude_path.read_text()
        self.assertIn("/.claude/skills/python-engineering/", text)
        self.assertIn("/.agents/skills/python-engineering/", text)
        self.assertIn("/.agentic/", text)

    def test_shared_activation_is_not_added_to_local_exclude(self):
        root = self.make_repo()
        activate(root, ["go-engineering"], shared=True, target="both")
        exclude = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--git-path", "info/exclude"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        exclude_path = Path(exclude)
        if not exclude_path.is_absolute():
            exclude_path = root / exclude_path
        text = exclude_path.read_text() if exclude_path.exists() else ""
        self.assertNotIn("go-engineering", text)

    def test_unmanaged_skill_is_not_overwritten_or_removed(self):
        root = self.make_repo()
        dest = root / ".claude/skills/python-engineering"
        dest.mkdir(parents=True)
        skill = dest / "SKILL.md"
        skill.write_text("# custom\n")
        activate(root, ["python-engineering"], shared=False, target="claude")
        self.assertEqual(skill.read_text(), "# custom\n")
        removed = remove(root, ["python-engineering"], target="claude")
        self.assertEqual(removed, [])
        self.assertTrue(skill.exists())


if __name__ == "__main__":
    unittest.main()
