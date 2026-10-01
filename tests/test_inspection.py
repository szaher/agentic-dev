from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jsonschema

from agentic_dev_env.inspection import doctor_document, inspect_repository


ROOT = Path(__file__).resolve().parents[1]


class InspectionContractTests(unittest.TestCase):
    def make_repo(self) -> Path:
        root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        return root

    def schema(self, name: str) -> dict:
        return json.loads((ROOT / "schemas" / name).read_text())

    @patch("agentic_dev_env.inspection.integration_status", return_value=[])
    @patch("agentic_dev_env.inspection.capability_status", return_value={})
    def test_repo_inspection_validates_and_is_read_only(self, caps, integrations):
        root = self.make_repo()
        (root / "pyproject.toml").write_text(
            """[project]
name = "demo"
version = "0.1.0"
dependencies = ["fastapi", "pytest"]

[tool.ruff]
line-length = 100
"""
        )
        (root / "tests").mkdir()
        before = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if ".git/" not in p.as_posix())

        doc = inspect_repository(root, task="review the API tests")
        jsonschema.validate(doc, self.schema("repo-inspection-v1.schema.json"))

        self.assertEqual(doc["schema_version"], "1")
        self.assertEqual(doc["document_type"], "agentic.repo-inspection")
        self.assertIn("language:python", doc["repository"]["facts"])
        self.assertIn("framework:fastapi", doc["repository"]["facts"])
        self.assertIn("uv sync", doc["commands"]["install"])
        self.assertIn("uv run pytest", doc["commands"]["test"])
        self.assertIn("uv run ruff check .", doc["commands"]["lint"])
        self.assertIn("python-engineering", [x["name"] for x in doc["skills"]["recommended"]])

        after = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if ".git/" not in p.as_posix())
        self.assertEqual(before, after)
        self.assertFalse((root / ".agentic").exists())
        self.assertFalse((root / ".serena").exists())
        self.assertFalse((root / ".codegraph").exists())

    @patch("agentic_dev_env.inspection.integration_status", return_value=[])
    @patch("agentic_dev_env.inspection.capability_status", return_value={})
    def test_polyglot_commands_are_arrays_not_single_winner(self, caps, integrations):
        root = self.make_repo()
        (root / "go.mod").write_text("module example.com/demo\ngo 1.25\n")
        (root / "Cargo.toml").write_text('[package]\nname="demo"\nversion="0.1.0"\nedition="2024"\n')

        doc = inspect_repository(root)
        self.assertIn("go test ./...", doc["commands"]["test"])
        self.assertIn("cargo test", doc["commands"]["test"])
        self.assertIn("go build ./...", doc["commands"]["build"])
        self.assertIn("cargo build", doc["commands"]["build"])

    @patch("agentic_dev_env.inspection.integration_status", return_value=[])
    @patch("agentic_dev_env.inspection.capability_status", return_value={})
    @patch("agentic_dev_env.inspection.shutil.which")
    def test_doctor_document_validates(self, which, caps, integrations):
        which.side_effect = lambda name: f"/usr/local/bin/{name}" if name in {"git", "rg"} else None
        doc = doctor_document()
        jsonschema.validate(doc, self.schema("doctor-v1.schema.json"))
        self.assertEqual(doc["schema_version"], "1")
        self.assertEqual(doc["document_type"], "agentic.doctor")
        self.assertTrue(doc["tools"]["git"]["available"])
        self.assertFalse(doc["tools"]["codex"]["available"])


if __name__ == "__main__":
    unittest.main()
