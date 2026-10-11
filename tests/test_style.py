from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_human_output import blocked_plan

from agentic_dev import human_output, style

ROOT = Path(__file__).resolve().parents[1]


class FakeTTY(io.StringIO):
    def isatty(self) -> bool:
        return True


def run(*args: str, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = {key: value for key, value in os.environ.items()
              if key not in {"NO_COLOR", "FORCE_COLOR", "CLICOLOR_FORCE", "AGENTIC_COLOR"}}
    merged.update(PYTHONPATH=str(ROOT / "src"), AGENTIC_DEV_CONFIG_DIR=tempfile.mkdtemp(), **(env or {}))
    return subprocess.run([sys.executable, "-m", "agentic_dev.cli", *args],
                          cwd=cwd, env=merged, capture_output=True, text=True, check=False)


class DetectionTests(unittest.TestCase):
    def tearDown(self):
        style.configure("never")

    def test_interactive_terminal_is_styled_and_pipes_are_plain(self):
        self.assertTrue(style.configure("auto", stream=FakeTTY(), env={}))
        self.assertFalse(style.configure("auto", stream=io.StringIO(), env={}))

    def test_automation_and_opt_out_environments_stay_plain_on_a_tty(self):
        for env in ({"NO_COLOR": ""}, {"TERM": "dumb"}, {"CI": "true"}, {"CLAUDECODE": "1"},
                    {"CODEX_SANDBOX": "seatbelt"}, {"AGENTIC_COLOR": "never"}):
            with self.subTest(env=env):
                self.assertFalse(style.configure("auto", stream=FakeTTY(), env=env))

    def test_explicit_choices_override_detection(self):
        self.assertTrue(style.configure("auto", stream=io.StringIO(), env={"FORCE_COLOR": "1"}))
        self.assertTrue(style.configure("auto", stream=io.StringIO(), env={"AGENTIC_COLOR": "always"}))
        self.assertFalse(style.configure("never", stream=FakeTTY(), env={"FORCE_COLOR": "1"}))
        self.assertTrue(style.configure("always", stream=io.StringIO(), env={"NO_COLOR": "1"}))


class RenderingTests(unittest.TestCase):
    def tearDown(self):
        style.configure("never")

    def test_styled_views_strip_to_the_exact_plain_text(self):
        failed_run = {
            "status": "failed",
            "missing_kinds": [],
            "results": [{"kind": "test", "command": "pytest", "success": False, "returncode": 1,
                         "stderr": "AssertionError: expected 2"}],
        }
        views = [
            lambda: human_output.session_plan(blocked_plan()),
            lambda: human_output.verification_run(failed_run),
            lambda: human_output.session_error("dirty", "worktree has unapproved changes"),
            lambda: human_output.skills_status("/repo", {"claude": ["debugging"], "codex": [], "pi": [], "opencode": []}),
        ]
        for view in views:
            style.configure("never")
            plain = view()
            style.configure("always")
            styled = view()
            self.assertNotIn("\x1b[", plain)
            self.assertIn("\x1b[", styled)
            self.assertEqual(style.strip(styled), plain)

    def test_spinner_animates_only_on_an_interactive_stream(self):
        style.configure("never")
        quiet = io.StringIO()
        with patch.dict(os.environ, {"AGENTIC_COLOR": "auto"}, clear=True), style.spinner("Working", stream=quiet):
            pass
        self.assertEqual(quiet.getvalue(), "")

        style.configure("always")
        loud = FakeTTY()
        with style.spinner("Working", stream=loud):
            pass
        self.assertIn("Working", loud.getvalue())
        self.assertTrue(loud.getvalue().endswith("\r\x1b[K"))


class CliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp(prefix="style-cli-"))
        subprocess.run(["git", "init", "-q", str(cls.root)], check=True)
        (cls.root / "README.md").write_text("# Demo\n")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_readiness_views_match_plain_output_once_stripped(self):
        for command in (["ready", "assess"], ["ready", "plan"], ["ready", "diff"]):
            with self.subTest(command=command):
                plain = run("--color", "never", *command, str(self.root), cwd=self.root)
                styled = run("--color", "always", *command, str(self.root), cwd=self.root)
                self.assertEqual(plain.returncode, styled.returncode)
                self.assertNotIn("\x1b[", plain.stdout)
                self.assertIn("\x1b[", styled.stdout)
                self.assertEqual(style.strip(styled.stdout), plain.stdout)

    def test_json_and_piped_output_never_contain_escapes(self):
        forced = run("--color", "always", "ready", "assess", str(self.root), "--json", cwd=self.root)
        self.assertNotIn("\x1b[", forced.stdout)
        piped = run("ready", "assess", str(self.root), cwd=self.root)
        self.assertNotIn("\x1b[", piped.stdout + piped.stderr)


if __name__ == "__main__":
    unittest.main()
