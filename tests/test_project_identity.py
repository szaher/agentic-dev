from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Keep these split so this test does not trigger its own repository scan.
FORBIDDEN = (
    "agentic-dev-" + "env",
    "agentic_dev_" + "env",
    "AGENTIC_DEV_" + "ENV",
    "setup-coding-" + "agent-env",
    "saad-tool-" + "repo-init",
    "Agentic Dev " + "Env",
    ".saad-" + "agent",
)

TEXT_SUFFIXES = {
    ".md", ".py", ".sh", ".json", ".toml", ".yml", ".yaml", ".ts",
}


class ProjectIdentityTests(unittest.TestCase):
    def test_public_identity_is_agentic_dev(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())
        self.assertEqual(project["project"]["name"], "agentic-dev")
        self.assertEqual(
            project["project"]["scripts"]["agentic"],
            "agentic_dev.cli:main",
        )
        self.assertTrue((ROOT / "src" / "agentic_dev" / "__init__.py").exists())
        self.assertFalse((ROOT / "src" / ("agentic_dev_" + "env")).exists())

    def test_no_legacy_identity_references_remain(self):
        findings: list[str] = []
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if ".git" in path.parts:
                continue
            if path.suffix not in TEXT_SUFFIXES and path.name not in {"Makefile"}:
                continue
            text = path.read_text(errors="ignore")
            for token in FORBIDDEN:
                if token in text:
                    findings.append(f"{path.relative_to(ROOT)}: {token}")
        self.assertEqual(findings, [], "\n" + "\n".join(findings))


if __name__ == "__main__":
    unittest.main()
