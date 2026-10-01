from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentic_dev_env.capabilities import (
    disable,
    enable,
    status,
    suggest_for_repo,
)
from agentic_dev_env.cli import build_parser


class BrowserCapabilityTests(unittest.TestCase):
    def make_repo(self) -> Path:
        root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        return root

    def test_web_repo_recommends_browser_automation_but_does_not_enable_it(self):
        root = self.make_repo()
        (root / "package.json").write_text(json.dumps({
            "dependencies": {"react": "^19.0.0"},
            "devDependencies": {"@playwright/test": "^1.0.0"},
        }))
        with tempfile.TemporaryDirectory() as config:
            with patch.dict(os.environ, {"AGENTIC_DEV_ENV_CONFIG_DIR": config}):
                _ctx, recs = suggest_for_repo(root)
                names = [r.name for r in recs]
                self.assertIn("browser-automation", names)
                self.assertFalse(status()["browser-automation"]["enabled"])

    def test_performance_task_recommends_devtools(self):
        root = self.make_repo()
        _ctx, recs = suggest_for_repo(root, "investigate frontend page load performance and network trace")
        names = [r.name for r in recs]
        self.assertIn("browser-debug", names)

    def test_web_research_task_recommends_browser_use(self):
        root = self.make_repo()
        _ctx, recs = suggest_for_repo(root, "do web research across a vendor portal")
        names = [r.name for r in recs]
        self.assertIn("browser-agent", names)

    @patch("agentic_dev_env.capabilities._run", return_value=0)
    @patch("agentic_dev_env.capabilities.shutil.which")
    def test_enable_playwright_registers_isolated_mcp_and_records_state(self, which, run):
        which.side_effect = lambda name: f"/bin/{name}" if name in {"claude", "codex"} else None
        with tempfile.TemporaryDirectory() as config:
            with patch.dict(os.environ, {"AGENTIC_DEV_ENV_CONFIG_DIR": config}):
                self.assertEqual(enable("browser-automation", target="both", mode="isolated"), 0)
                calls = [call.args[0] for call in run.call_args_list]
                self.assertIn(["/bin/claude", "mcp", "add", "playwright", "npx", "@playwright/mcp@latest", "--isolated"], calls)
                self.assertIn(["/bin/codex", "mcp", "add", "playwright", "npx", "@playwright/mcp@latest", "--isolated"], calls)
                item = status()["browser-automation"]
                self.assertTrue(item["enabled"])
                self.assertEqual(item["configuration"]["mode"], "isolated")

    @patch("agentic_dev_env.capabilities._run", return_value=0)
    @patch("agentic_dev_env.capabilities.shutil.which")
    def test_existing_browser_playwright_uses_extension(self, which, run):
        which.side_effect = lambda name: "/bin/claude" if name == "claude" else None
        with tempfile.TemporaryDirectory() as config:
            with patch.dict(os.environ, {"AGENTIC_DEV_ENV_CONFIG_DIR": config}):
                self.assertEqual(enable("browser-automation", target="claude", mode="existing-browser"), 0)
                self.assertIn(
                    ["/bin/claude", "mcp", "add", "playwright", "npx", "@playwright/mcp@latest", "--extension"],
                    [call.args[0] for call in run.call_args_list],
                )

    def test_cli_exposes_capability_commands(self):
        parser = build_parser()
        args = parser.parse_args(["capabilities", "suggest", ".", "--task", "test the UI"])
        self.assertEqual(args.capabilities_command, "suggest")
        args = parser.parse_args([
            "capabilities", "enable", "browser-automation",
            "--target", "claude", "--mode", "isolated",
        ])
        self.assertEqual(args.name, "browser-automation")
        self.assertEqual(args.target, "claude")


if __name__ == "__main__":
    unittest.main()
