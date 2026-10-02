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

# Legacy names are allowed only where they are required to migrate users or preserve
# historical records. New product code/docs should never reintroduce them.
LEGACY_ALLOWED_PATHS = {
    "CHANGELOG.md",
    "docs/MIGRATION.md",
    "docs/roadmaps/ROADMAP-v0.5-v0.13.md",
    "install.sh",
    "scripts/agentic-setup.sh",
    "scripts/agentic-setup-linux.sh",
    "src/agentic_dev/paths.py",
    "tests/test_paths.py",
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

    def test_no_unscoped_legacy_identity_references_remain(self):
        findings: list[str] = []
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if ".git" in path.parts:
                continue
            if path.suffix not in TEXT_SUFFIXES and path.name not in {"Makefile"}:
                continue
            rel = path.relative_to(ROOT).as_posix()
            if rel in LEGACY_ALLOWED_PATHS:
                continue
            text = path.read_text(errors="ignore")
            for token in FORBIDDEN:
                if token in text:
                    findings.append(f"{path.relative_to(ROOT)}: {token}")
        self.assertEqual(findings, [], "\n" + "\n".join(findings))


if __name__ == "__main__":
    unittest.main()
