from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class IntegrationPackagingTests(unittest.TestCase):
    def load_json(self, path: str):
        with (ROOT / path).open() as f:
            return json.load(f)

    def test_claude_marketplace_points_to_plugin(self):
        marketplace = self.load_json(".claude-plugin/marketplace.json")
        self.assertEqual(marketplace["name"], "agentic-dev-env")
        self.assertEqual(marketplace["plugins"][0]["source"], "./integrations/claude")
        plugin = self.load_json("integrations/claude/.claude-plugin/plugin.json")
        self.assertEqual(plugin["name"], "agentic-dev-env")
        self.assertTrue((ROOT / "integrations/claude/skills/repo/SKILL.md").exists())

    def test_codex_marketplace_points_to_plugin(self):
        marketplace = self.load_json(".agents/plugins/marketplace.json")
        entry = marketplace["plugins"][0]
        self.assertEqual(entry["name"], "agentic-dev-env")
        self.assertEqual(entry["source"]["source"], "local")
        self.assertEqual(entry["source"]["path"], "./integrations/codex")
        portable = self.load_json("integrations/codex/plugin.json")
        compat = self.load_json("integrations/codex/.codex-plugin/plugin.json")
        self.assertEqual(portable["name"], "agentic-dev-env")
        self.assertEqual(compat["skills"], "./skills/")
        self.assertTrue((ROOT / "integrations/codex/skills/repo/SKILL.md").exists())

    def test_pi_package_exposes_extension_and_skill(self):
        package = self.load_json("package.json")
        self.assertIn("pi-package", package["keywords"])
        self.assertEqual(package["pi"]["extensions"], ["./integrations/pi/extensions/agentic.ts"])
        self.assertEqual(package["pi"]["skills"], ["./integrations/pi/skills"])
        self.assertTrue((ROOT / "integrations/pi/extensions/agentic.ts").exists())
        self.assertTrue((ROOT / "integrations/pi/skills/repo/SKILL.md").exists())

    def test_adapter_skills_have_matching_names(self):
        claude = (ROOT / "integrations/claude/skills/repo/SKILL.md").read_text()
        codex = (ROOT / "integrations/codex/skills/repo/SKILL.md").read_text()
        pi = (ROOT / "integrations/pi/skills/repo/SKILL.md").read_text()
        self.assertIn("name: repo", claude)
        self.assertIn("name: repo", codex)
        self.assertIn("name: agentic-repo", pi)


if __name__ == "__main__":
    unittest.main()
